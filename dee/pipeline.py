"""Run: documents -> screen -> extract -> validate -> assess -> packet -> update plan -> manifest. Writes files only."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .assess import assess_deal
from .audit import AuditLog
from .claude_extract import extract_with_model
from .extract import extract_doc
from .ingest import load_deals, load_docs, segments
from .packet import build_packet
from .plan import build_plans
from .untrusted import screen
from .util import canonical_json, iso, pii_hash, read_json, sha256_file, sha256_text, write_json


def load_policy(path="config/policy.json") -> dict:
    return read_json(path)


def evaluate(deals: dict, docs: list[dict], policy: dict, as_of: date, *, client=None, log=None, sleep=None):
    """Pure pipeline core, shared by the CLI and the evals. Returns dict with evidence, rejected, assessments, quarantine."""
    from .validate import validate_candidate
    docs_by_id = {d["doc_id"]: d for d in docs}
    quarantined, q_patterns = set(), {}
    for d in docs:
        hits = screen(d["text"])
        if hits:
            quarantined.add(d["doc_id"])
            q_patterns[d["doc_id"]] = hits
    evidence, rejected, sources = [], [], Counter()
    for d in sorted(docs, key=lambda x: x["doc_id"]):
        if d["doc_id"] in quarantined:
            rejected.append({"doc_id": d["doc_id"], "deal_id": d["deal_id"], "reason": "doc_quarantined", "patterns": q_patterns[d["doc_id"]]})
            continue
        if d["deal_id"] not in deals:
            rejected.append({"doc_id": d["doc_id"], "deal_id": d["deal_id"], "reason": "unknown_deal"})
            continue
        if client is not None:
            cands, src = extract_with_model(client, d, policy, as_of, log=log, sleep=sleep)
        else:
            cands, src = extract_doc(d, policy, as_of), "rules"
        sources[src] += 1
        seen = set()
        for c in cands:
            ev, why = validate_candidate(c, docs_by_id, quarantined, policy, as_of)
            if ev is None:
                rejected.append({"doc_id": d["doc_id"], "deal_id": d["deal_id"], "field": c.get("field"), "reason": why,
                                 "extractor": c.get("extractor"), "span_sha256": sha256_text(str(c.get("span", "")))})
                continue
            k = (ev["field"], ev["span"], ev["polarity"])
            if k not in seen:
                seen.add(k)
                evidence.append(ev)
    titles_by_deal: dict[str, dict] = {}
    for d in docs:
        if d["doc_id"] in quarantined:
            continue
        for role, name, title, _ in segments(d):
            if role == "buyer" and title and name:
                titles_by_deal.setdefault(d["deal_id"], {})[name] = title
    by_deal: dict[str, list] = {}
    for e in evidence:
        by_deal.setdefault(e["deal_id"], []).append(e)
    q_by_deal: dict[str, list] = {}
    for did in quarantined:
        q_by_deal.setdefault(docs_by_id[did]["deal_id"], []).append(did)
    docs_per_deal = Counter(d["deal_id"] for d in docs)
    assessments = {}
    for deal_id, deal in deals.items():
        if deal["category_norm"] in ("Closed", "Omit"):
            continue
        a = assess_deal(deal, by_deal.get(deal_id, []), policy, as_of, titles_by_deal.get(deal_id, {}), sorted(q_by_deal.get(deal_id, [])))
        a["docs_seen"] = docs_per_deal.get(deal_id, 0)
        if a["docs_seen"] == 0:
            a["why"] = ["no call notes or emails found for this deal"] + a["why"]
        assessments[deal_id] = a
    return {"evidence": evidence, "rejected": rejected, "assessments": assessments, "quarantined": q_patterns, "sources": dict(sources)}


def run(deals_path, notes_path, out_dir, as_of: date, policy_path="config/policy.json", approvers_path="config/approvers.json",
        client=None, log_trace=True) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    policy = load_policy(policy_path)
    deals, docs = load_deals(deals_path), load_docs(notes_path)
    now = datetime(as_of.year, as_of.month, as_of.day, 9, 0, tzinfo=timezone.utc)
    for stale in ("approvals.jsonl", "checkpoint.json", "dead_letter.jsonl", "audit.log", "crm_state.json"):
        if (out / stale).exists():
            (out / stale).unlink()  # a new run is a new plan; old approvals can never carry over (files are in the run's own out dir)
    audit = AuditLog(out / "audit.log", clock=lambda: now)
    trace = []
    audit_fn = lambda rec: audit.append({"event": rec.pop("event"), **rec})
    res = evaluate(deals, docs, policy, as_of, client=client, log=audit_fn)
    trace.append({"stage": "extract_validate", "docs": len(docs), "evidence_kept": len(res["evidence"]),
                  "candidates_rejected": len(res["rejected"]), "quarantined_docs": len(res["quarantined"]), "extractor_sources": res["sources"]})
    for did, pats in sorted(res["quarantined"].items()):
        audit.append({"event": "doc_quarantined", "doc_id": did, "patterns": pats})
    a = res["assessments"]
    trace.append({"stage": "assess", "deals": len(a), "by_allowed_category": dict(Counter(x["allowed_category"] for x in a.values())),
                  "by_change": dict(Counter(x["change"] for x in a.values()))})
    plans = build_plans(deals, a, res["evidence"], policy, deals_path, notes_path, as_of)
    write_json(out / "crm_update_plan.json", plans["canonical"])
    write_json(out / "hubspot_update_plan.json", plans["hubspot"])
    write_json(out / "salesforce_update_plan.json", plans["salesforce"])
    write_json(out / "approval_queue.json", plans["queue"])
    with open(out / "evidence.jsonl", "w", encoding="utf-8") as fh:
        for e in sorted(res["evidence"], key=lambda x: (x["deal_id"], x["doc_id"], x["field"], x["span"])):
            fh.write(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n")
    with open(out / "rejected_evidence.jsonl", "w", encoding="utf-8") as fh:
        for e in res["rejected"]:
            fh.write(json.dumps(e, sort_keys=True) + "\n")
    with open(out / "deal_assessments.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["deal_id", "owner", "amount", "called_category", "allowed_category", "change"] + [f"{f}_status" for f in policy["meddpicc_fields"]] + ["why"])
        for did, x in sorted(a.items()):
            w.writerow([did, deals[did].get("owner", ""), deals[did].get("amount", ""), x["called_category"], x["allowed_category"], x["change"]]
                       + [x["fields"][f]["status"] for f in policy["meddpicc_fields"]] + [" | ".join(x["why"])])
    (out / "review_packet.md").write_text(build_packet(deals, a, res, plans, policy, as_of), encoding="utf-8")
    plan_sha = sha256_file(out / "crm_update_plan.json")
    manifest = {"run_id": plan_sha[:12], "as_of": as_of.isoformat(), "plan_sha256": plan_sha,
                "hubspot_plan_sha256": sha256_file(out / "hubspot_update_plan.json"),
                "salesforce_plan_sha256": sha256_file(out / "salesforce_update_plan.json"),
                "deals_sha256": sha256_file(deals_path), "notes_sha256": sha256_file(notes_path),
                "policy_sha256": sha256_file(policy_path), "policy_version": policy["version"],
                "extractor": "claude+validator" if client is not None and getattr(client, "name", "") == "claude" else
                             ("scripted-model+validator" if client is not None else "rules")}
    write_json(out / "manifest.json", manifest)
    audit.append({"event": "plan_generated", "run_id": manifest["run_id"], "plan_sha256": plan_sha, "ops": len(plans["canonical"]["ops"]),
                  "held_groups": len(plans["queue"]["held"]), "extractor": manifest["extractor"]})
    for e in sorted(res["evidence"], key=lambda x: (x["deal_id"], x["doc_id"], x["field"], x["span"])):
        # PII hashed: speaker names become salted hashes; span text is never stored in the audit trail, only its SHA-256
        audit.append({"event": "evidence_accepted", "deal_id": e["deal_id"], "doc_id": e["doc_id"], "field": e["field"], "polarity": e["polarity"],
                      "strength": e["strength"], "speaker": pii_hash(e["speaker"]), "span_sha256": sha256_text(e["span"]), "extractor": e["extractor"]})
    for r in res["rejected"]:
        if r["reason"] != "doc_quarantined":
            audit.append({"event": "candidate_rejected", "deal_id": r["deal_id"], "doc_id": r["doc_id"], "field": r.get("field"), "reason": r["reason"], "span_sha256": r.get("span_sha256")})
    for did, x in sorted(a.items()):
        audit.append({"event": "deal_assessed", "deal_id": did, "called": x["called_category"], "allowed": x["allowed_category"], "change": x["change"]})
    trace.append({"stage": "plan", "ops": len(plans["canonical"]["ops"]), "held_groups": len(plans["queue"]["held"]), "plan_sha256": plan_sha})
    if log_trace:
        with open(out / "trace.jsonl", "w", encoding="utf-8") as fh:
            for t in trace:
                fh.write(json.dumps(t, sort_keys=True) + "\n")
    return {"manifest": manifest, "result": res, "plans": plans, "deals": deals}
