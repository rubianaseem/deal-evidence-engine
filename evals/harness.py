"""Gold-set evaluation of the engine against the keyword baseline. Run via run_evals.py."""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from dee.ingest import load_deals, load_docs
from dee.pipeline import evaluate, load_policy

from .baseline import baseline_category, baseline_evidence, category_from_fields
from .build_gold_v1 import AS_OF, ROOT

TYPED = {"economic_buyer", "decision_process", "paper_process", "champion", "competition"}


def heldout_hash_ok() -> tuple[bool, str]:
    h = hashlib.sha256()
    for f in ("deals.csv", "notes.csv", "gold.json"):
        h.update((ROOT / "heldout" / f).read_bytes())
    want = (ROOT.parent / "gold_v1.sha256").read_text().strip()
    return h.hexdigest() == want, h.hexdigest()


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "frac": f"P {tp}/{tp+fp}, R {tp}/{tp+fn}"}


def run_split(split: str, policy: dict, client=None) -> dict:
    d = ROOT / split
    deals, docs = load_deals(d / "deals.csv"), load_docs(d / "notes.csv")
    gold = {g["deal_id"]: g for g in json.loads((d / "gold.json").read_text())}
    docs_by_id = {x["doc_id"]: x for x in docs}
    res = evaluate(deals, docs, policy, AS_OF, client=client)
    # ---- evidence extraction, field level ------------------------------------------------------------------
    gold_keys, gold_vals = set(), {}
    for g in gold.values():
        for e in g["evidence"]:
            if e["field"].startswith("__"):
                continue
            k = (e["deal_id"], e["field"], e["doc_id"], e["polarity"])
            gold_keys.add(k)
            gold_vals[k] = e["value"]
    sys_keys = {(e["deal_id"], e["field"], e["doc_id"], e["polarity"]): e for e in res["evidence"] if e["strength"] == "buyer_stated"}
    base_ev = baseline_evidence(docs)
    base_keys = {(e["deal_id"], e["field"], e["doc_id"], e["polarity"]): e for e in base_ev}
    # the engine and the baseline are both scored on buyer-stated positive and negative evidence; baseline only emits positives
    out = {}
    for name, keys in (("engine", set(sys_keys)), ("baseline", set(base_keys))):
        tp = len(keys & gold_keys)
        out[name] = prf(tp, len(keys - gold_keys), len(gold_keys - keys))
    # per-field recall for the engine
    per_field = {}
    for f in sorted({k[1] for k in gold_keys}):
        gk = {k for k in gold_keys if k[1] == f}
        out_f = {}
        for name, keys in (("engine", set(sys_keys)), ("baseline", set(base_keys))):
            kk = {k for k in keys if k[1] == f}
            out_f[name] = f"P {len(kk & gk)}/{len(kk)}, R {len(kk & gk)}/{len(gk)}"
        per_field[f] = out_f
    out["per_field"] = per_field
    # value accuracy among true positives (typed fields only; the baseline emits no values)
    tpk = [k for k in set(sys_keys) & gold_keys if k[1] in TYPED]
    ok = 0
    for k in tpk:
        want, got = str(gold_vals[k]).lower(), str(sys_keys[k]["value"]).lower()
        ok += (want == got) or (k[1] in ("economic_buyer", "champion") and (want.startswith("our ") or want in got or got in want))
    out["value_accuracy_typed_tp"] = f"{ok}/{len(tpk)}"
    # ---- unsupported claims -------------------------------------------------------------------------------
    def unsupported(evs):
        n = 0
        for e in evs:
            doc = docs_by_id.get(e["doc_id"])
            if doc is None or e["span"] not in doc["text"]:
                n += 1
        return n
    out["unsupported_claims"] = {"engine": f"{unsupported(res['evidence'])}/{len(res['evidence'])}", "baseline": f"{unsupported(base_ev)}/{len(base_ev)}",
                                 "note": "claim = span not verbatim in its source document; both emit verbatim sentences, so this isolates fabrication, not relevance"}
    gold_sent = {k: v for g in gold.values() for k, v in g["evidence_sentences"].items()}
    # claims on text that is not gold evidence = the 'false support' rate
    out["claims_not_in_gold"] = {"engine": f"{len(set(sys_keys) - gold_keys)}/{len(sys_keys)}", "baseline": f"{len(set(base_keys) - gold_keys)}/{len(base_keys)}"}
    # ---- injection ------------------------------------------------------------------------------------------
    gold_q = {x for g in gold.values() for x in g["quarantined_docs"]}
    sys_q = set(res["quarantined"])
    leak = [e for e in res["evidence"] if e["doc_id"] in sys_q]
    evading = [(g["deal_id"], x) for g in gold.values() for x in g["injected_unscreened"]]
    accepted_fake = []
    for did, doc_id in evading:
        sent = gold[did]["evidence_sentences"][f"{doc_id}|__injection_evading__|pos"]
        if any(e["doc_id"] == doc_id and e["span"] == sent and e["strength"] == "buyer_stated" for e in res["evidence"]):
            accepted_fake.append(did)
    out["injection"] = {"screened_docs_gold": len(gold_q), "quarantined_correct": len(gold_q & sys_q), "quarantined_wrong": len(sys_q - gold_q),
                        "evidence_leaked_from_quarantined_docs": len(leak), "unscreened_injections_in_gold": len(evading),
                        "unscreened_injection_accepted_as_evidence": len(accepted_fake), "accepted_fake_deals": accepted_fake}
    # ---- conflicts ------------------------------------------------------------------------------------------
    gc = {(g["deal_id"], f) for g in gold.values() for f in g["conflict_fields"]}
    sc = {(did, f) for did, a in res["assessments"].items() for f, fa in a["fields"].items() if fa["status"] in ("conflict", "negated")}
    out["conflict_detection"] = prf(len(gc & sc), len(sc - gc), len(gc - sc))
    # ---- category ---------------------------------------------------------------------------------------------
    base_fields = baseline_category(base_ev)
    rows, by_arch = [], defaultdict(lambda: Counter())
    sys_ok = base_ok = called_ok = false_commit_sys = false_commit_base = false_commit_called = 0
    sys_miss = []
    for did, a in sorted(res["assessments"].items()):
        g = gold[did]
        b = category_from_fields(base_fields.get(did, set()))
        sys_ok += a["allowed_category"] == g["gold_category"]
        base_ok += b == g["gold_category"]
        called_ok += g["called_category"] == g["gold_category"]
        false_commit_sys += a["allowed_category"] == "Commit" and g["gold_category"] != "Commit"
        false_commit_base += b == "Commit" and g["gold_category"] != "Commit"
        false_commit_called += g["called_category"] == "Commit" and g["gold_category"] != "Commit"
        by_arch[g["archetype"]]["n"] += 1
        by_arch[g["archetype"]]["engine"] += a["allowed_category"] == g["gold_category"]
        by_arch[g["archetype"]]["baseline"] += b == g["gold_category"]
        if a["allowed_category"] != g["gold_category"]:
            sys_miss.append({"deal": did, "archetype": g["archetype"], "engine": a["allowed_category"], "gold": g["gold_category"]})
    n = len(res["assessments"])
    out["category"] = {"deals": n, "engine_agreement": f"{sys_ok}/{n}", "baseline_agreement": f"{base_ok}/{n}", "rep_called_agreement": f"{called_ok}/{n}",
                       "false_commit": {"engine": false_commit_sys, "baseline": false_commit_base, "rep_called": false_commit_called},
                       "by_archetype": {k: f"engine {v['engine']}/{v['n']}, baseline {v['baseline']}/{v['n']}" for k, v in sorted(by_arch.items())},
                       "engine_misses": sys_miss}
    out["rejected_candidates"] = dict(Counter(r["reason"] for r in res["rejected"]))
    return out


def run_all(client=None) -> dict:
    policy = load_policy(str(Path(__file__).resolve().parent.parent / "config" / "policy.json"))
    ok, h = heldout_hash_ok()
    if not ok:
        raise SystemExit(f"held-out files do not match gold_v1.sha256 ({h}); refusing to evaluate. Build a new versioned set instead.")
    return {"gold_version": "gold_v1", "policy_version": policy["version"], "as_of": AS_OF.isoformat(), "heldout_sha256": h,
            "dev": run_split("dev", policy, client), "heldout": run_split("heldout", policy, client)}


def model_robustness() -> dict:
    """Run the full pipeline with the scripted fake model (all failure modes) on both splits."""
    from .scripted_model import FakeModel
    policy = load_policy(str(Path(__file__).resolve().parent.parent / "config" / "policy.json"))
    out = {}
    for split in ("dev", "heldout"):
        d = ROOT / split
        deals, docs = load_deals(d / "deals.csv"), load_docs(d / "notes.csv")
        gold = {g["deal_id"]: g for g in json.loads((d / "gold.json").read_text())}
        model = FakeModel(docs, policy, AS_OF)
        res = evaluate(deals, docs, policy, AS_OF, client=model, sleep=lambda s: None)
        docs_by_id = {x["doc_id"]: x for x in docs}
        bad_pass = sum(1 for e in res["evidence"] if e["span"] not in docs_by_id[e["doc_id"]]["text"])
        rejected = Counter(r["reason"] for r in res["rejected"] if r.get("extractor") == "claude" or r.get("extractor") == "unknown")
        n_ok = sum(res["assessments"][k]["allowed_category"] == gold[k]["gold_category"] for k in res["assessments"])
        out[split] = {"docs": len(docs), "model_calls": model.calls, "bad_candidates_produced": model.bad_added, "unparseable_outputs": model.garbage,
                      "candidates_rejected_by_reason": dict(rejected), "bad_candidates_rejected": sum(rejected.values()),
                      "unsupported_spans_in_accepted_evidence": bad_pass, "docs_using_model_output": res["sources"].get("model", 0),
                      "docs_fell_back_to_rules": res["sources"].get("rules_fallback", 0),
                      "category_agreement_with_gold": f"{n_ok}/{len(res['assessments'])}"}
    return out
