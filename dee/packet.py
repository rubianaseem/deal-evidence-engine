"""Rep and manager review packet (Markdown). The packet is the human's view: quotes, statuses, proposed changes."""
from __future__ import annotations

ORDER = {"downgrade": 0, "upgrade_suggestion": 1, "review_unknown_category": 2, "none": 3}


def build_packet(deals, assessments, res, plans, policy, as_of) -> str:
    L = [f"# Deal evidence review packet", "",
         f"As of {as_of.isoformat()}. Policy {policy['version']}. All data in this repo is synthetic. Nothing below has been written to a CRM.",
         "Quotes are copied verbatim from the source documents. Treat a real packet as sensitive: it contains buyer names and statements.", ""]
    ev_by = {}
    for e in res["evidence"]:
        ev_by.setdefault(e["deal_id"], []).append(e)
    counts = {}
    for a in assessments.values():
        counts[a["change"]] = counts.get(a["change"], 0) + 1
    L += ["## Summary", "", f"- Deals assessed: {len(assessments)}"] + [f"- {k}: {v}" for k, v in sorted(counts.items())]
    L += [f"- Documents quarantined as instruction-like: {len(res['quarantined'])}", ""]
    for did, a in sorted(assessments.items(), key=lambda kv: (ORDER.get(kv[1]["change"], 9), kv[0])):
        d = deals[did]
        L += [f"## {did} {d.get('deal_name','')} ({d.get('owner','')}, {d.get('amount','')} {d.get('currency','')}, close {d.get('close_date','')})", "",
              f"- Rep called: **{a['called_category']}**. Evidence supports: **{a['allowed_category']}**. Proposed change: **{a['change']}**.",
              f"- Why: {'; '.join(a['why'])}"]
        if a["quarantined_docs"]:
            L.append(f"- Quarantined documents (not read, possible instruction injection): {', '.join(a['quarantined_docs'])}")
        L += ["", "| Field | Status | Value | Source |", "|---|---|---|---|"]
        for f in policy["meddpicc_fields"]:
            fa = a["fields"][f]
            src = ", ".join(f"{r['doc_id']} ({r['doc_date']})" for r in fa["evidence"])
            L.append(f"| {f} | {fa['status']} | {(fa['value'] or '')[:60].replace('|','/')} | {src} |")
        bad = [(f, a["fields"][f]) for f in policy["meddpicc_fields"] if a["fields"][f]["status"] in ("conflict", "negated", "rep_reported_only")]
        if bad:
            L += ["", "Needs a human:"]
            for f, fa in bad:
                L.append(f"- {f}: {fa['status']}. {'; '.join(fa['reasons'])}")
                for e in ev_by.get(did, []):
                    if e["field"] == f and (e["doc_id"] in {r["doc_id"] for r in fa["evidence"]} or fa["status"] == "rep_reported_only"):
                        L.append(f"  - {e['doc_id']} {e['doc_date']} [{e['strength']}, {e['polarity']}]: \"{e['span']}\"")
        sat = [(f, a["fields"][f]) for f in policy["meddpicc_fields"] if a["fields"][f]["status"] == "satisfied"]
        if sat:
            L += ["", "Evidence quotes (buyer-stated, fresh):"]
            for f, fa in sat:
                for e in ev_by.get(did, []):
                    if e["field"] == f and e["doc_id"] == fa["evidence"][0]["doc_id"] and e["strength"] == "buyer_stated" and e["polarity"] == "pos":
                        L.append(f"- {f} = {e['value']}: \"{e['span']}\" ({e['doc_id']}, {e['doc_date']})")
                        break
        L.append("")
    sug = plans["canonical"]["suggestions_not_written"]
    if sug:
        L += ["## Rep-typed values that differ from buyer evidence (not written)", ""]
        L += [f"- {s['deal_id']} {s['field']}: rep typed \"{s['rep_typed'][:80]}\", evidence shows \"{s['evidence_value'][:80]}\" ({s['doc_id']})" for s in sug]
        L.append("")
    L += ["## Proposed CRM operations", "", f"- Plain field updates (approved with the plan hash): {plans['queue']['plain_ops']}",
          f"- Held forecast category changes (named by a manager-level approver): {plans['queue']['held_ops']}"]
    L += [f"  - {h['item_id']}: {h['from']} -> {h['to']}" for h in plans["queue"]["held"]]
    return "\n".join(L) + "\n"
