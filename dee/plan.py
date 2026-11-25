"""Build the update plan as files. Nothing here writes to any CRM.

crm_update_plan.json is canonical and is what the approver's SHA-256 binds to. hubspot_update_plan.json and
salesforce_update_plan.json are deterministic renderings of it; their hashes are recorded in manifest.json and
checked at approval and execution, so editing any of the three voids approval.

Rules for field proposals:
  - A MEDDPICC property is proposed only from a 'satisfied' field (buyer-stated, fresh, no unresolved conflict).
  - The engine fills empty properties only. If the rep already typed something that differs, the evidence is shown
    as a suggestion in the packet and nothing is written. It never overwrites or clears a typed value.
  - A changed forecast category (downgrade or upgrade suggestion) is a held item: only an approver with
    may_approve_held can release it, and only by naming it.
Custom property names (meddpicc_*, MEDDPICC_*__c) are examples; create them in your own portal or org.
"""
from __future__ import annotations

from datetime import date

from .util import canonical_json, sha256_file, sha256_text

HS_CAT = {"Commit": "COMMIT", "Best Case": "BEST_CASE", "Pipeline": "PIPELINE"}


def display_value(field: str, ev_value: str, span: str) -> str:
    if field in ("identify_pain", "decision_criteria"):
        return span[:160]
    return ev_value


def _latest_evidence(evid: list[dict], deal_id: str, field: str, ref: dict):
    for e in evid:
        if e["deal_id"] == deal_id and e["field"] == field and e["doc_id"] == ref["doc_id"] and e["strength"] == "buyer_stated" and e["polarity"] == "pos":
            return e
    return None


def build_plans(deals, assessments, evidence, policy, deals_path, notes_path, as_of: date) -> dict:
    ops, held, suggestions = [], [], []
    for deal_id in sorted(assessments):
        a, deal = assessments[deal_id], deals[deal_id]
        props, refs, expect = {}, [], {}
        for f in policy["meddpicc_fields"]:
            fa = a["fields"][f]
            if fa["status"] != "satisfied":
                continue
            ev = _latest_evidence(evidence, deal_id, f, fa["evidence"][0])
            if ev is None:
                continue
            shown = display_value(f, ev["value"], ev["span"])
            rep_val = deal.get(f, "")
            if rep_val and shown.lower() in rep_val.lower():
                continue
            if rep_val:
                suggestions.append({"deal_id": deal_id, "field": f, "rep_typed": rep_val, "evidence_value": shown, "doc_id": ev["doc_id"],
                                    "note": "rep value differs from buyer evidence; not written, rep decides"})
                continue
            props[f"meddpicc_{f}"] = f"{shown} [evidence {ev['doc_id']} {ev['doc_date']}]"
            expect[f"meddpicc_{f}"] = ""
            refs.append({"field": f, "doc_id": ev["doc_id"], "doc_date": ev["doc_date"], "span_sha256": sha256_text(ev["span"])})
        if props:
            ops.append(_op("update_meddpicc", deal_id, props, expect, refs, "meddpicc_fields", False))
        if a["change"] in ("downgrade", "upgrade_suggestion"):
            group = f"{deal_id}:category_change"
            crefs = [{"field": f, "doc_id": r["doc_id"], "doc_date": r["doc_date"], "status": a["fields"][f]["status"]}
                     for f in policy["commit_requires"] for r in (a["fields"][f]["evidence"][:1] or [{"doc_id": "", "doc_date": ""}])]
            op = _op("update_forecast_category", deal_id, {"forecast_category": a["allowed_category"]},
                     {"forecast_category": deal.get("forecast_category", "")}, crefs, group, True)
            ops.append(op)
            held.append({"item_id": group, "deal_id": deal_id, "change": a["change"], "from": a["called_category"],
                         "to": a["allowed_category"], "reason": a["why"][-1]})
    for i, op in enumerate(ops, 1):
        op["op_id"] = f"op-{i:03d}"
    canonical = {"schema": "deal-evidence-engine/crm_update_plan/v1", "as_of": as_of.isoformat(), "policy_version": policy["version"],
                 "snapshot": {"deals_sha256": sha256_file(deals_path), "notes_sha256": sha256_file(notes_path)},
                 "ops": ops, "suggestions_not_written": suggestions}
    hs = {"schema": "deal-evidence-engine/hubspot_update_plan/v1", "derived_from_sha256": sha256_text(canonical_json(canonical)),
          "note": "Rendering for HubSpot CRM v3 batch update. Internal property names are examples; confirm them in Settings > Properties.",
          "object": "deals", "updates": []}
    sf = {"schema": "deal-evidence-engine/salesforce_update_plan/v1", "derived_from_sha256": hs["derived_from_sha256"],
          "note": "Rendering for Salesforce Opportunity updates. Update StageName separately; this plan never touches stage. Custom fields are examples.",
          "sobject": "Opportunity", "updates": []}
    for op in ops:
        p = op["payload"]
        hp, sp = {}, {}
        for k, v in p.items():
            if k == "forecast_category":
                hp["hs_manual_forecast_category"], sp["ForecastCategoryName"] = HS_CAT[v], v
            else:
                hp[k] = v
                sp["MEDDPICC_" + "".join(w.capitalize() for w in k[len("meddpicc_"):].split("_")) + "__c"] = v
        hs["updates"].append({"op_id": op["op_id"], "id": op["deal_id"], "properties": hp, "requires_approval_group": op["group"] if op["requires_approval"] else None})
        sf["updates"].append({"op_id": op["op_id"], "Id": op["deal_id"], "fields": sp, "requires_approval_group": op["group"] if op["requires_approval"] else None})
    queue = {"held": held, "plain_ops": sum(1 for o in ops if not o["requires_approval"]), "held_ops": len(held)}
    return {"canonical": canonical, "hubspot": hs, "salesforce": sf, "queue": queue}


def _op(typ, deal_id, payload, expect, refs, group, requires_approval):
    key = sha256_text(canonical_json({"type": typ, "deal_id": deal_id, "payload": payload, "refs": refs}))
    return {"op_id": "", "type": typ, "deal_id": deal_id, "payload": payload, "expect": expect, "evidence_refs": refs, "group": group,
            "requires_approval": requires_approval, "op_key": key, "idempotency_key": key, "source_event_ids": [r.get("doc_id", "") for r in refs]}
