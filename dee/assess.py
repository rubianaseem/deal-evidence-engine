"""Evidence-gated forecast category rules. Deterministic. No model is involved in anything here.

Per deal and per MEDDPICC field the status is one of:
  satisfied, missing, rep_reported_only, stale, conflict, negated, undated, date_passed, after_close_date, not_started
Commit needs economic_buyer + decision_process + paper_process all 'satisfied' (buyer-stated, fresh, no unresolved
conflict, decision date on or before the close date, paper process under way or complete).
Best Case needs identify_pain plus one of economic_buyer / decision_process / champion.
Otherwise Pipeline. The engine proposes the evidence-supported category; it never invents a category above what the
evidence supports and never silently overrides the rep: a changed category is a held item for a manager.
Hygiene rules (stale close dates, stage skips, amount edits) are out of scope: see forecast-commit-hygiene-agent.
"""
from __future__ import annotations

from datetime import date

PAPER_RANK = {"not_started": 0, "in_progress": 1, "complete": 2}


def _canon(value: str, titles: dict) -> str:
    v = value.lower().strip()
    if v.startswith("our "):
        v = v[4:]
    for name, title in titles.items():
        if v == title.lower():
            return name.lower()
    return v


def _key(e):
    return (e["doc_date"], e["doc_id"])


def _ref(e):
    return {"doc_id": e["doc_id"], "doc_date": e["doc_date"]}


def assess_field(field: str, evid: list[dict], deal: dict, policy: dict, as_of: date, titles: dict) -> dict:
    mine = [e for e in evid if e["field"] == field]
    buyer = sorted([e for e in mine if e["strength"] == "buyer_stated"], key=_key)
    pos = [e for e in buyer if e["polarity"] == "pos"]
    neg = [e for e in buyer if e["polarity"] == "neg"]
    out = {"field": field, "status": "missing", "value": None, "evidence": [], "reasons": []}
    if not buyer:
        reps = [e for e in mine if e["strength"] == "rep_reported" and e["polarity"] == "pos"]
        if reps:
            last = sorted(reps, key=_key)[-1]
            out.update(status="rep_reported_only", value=last["value"], evidence=[_ref(last)],
                       reasons=["only the rep said it; the buyer must say it"])
        return out
    if not pos and neg:
        out.update(status="negated", evidence=[_ref(neg[-1])], reasons=["buyer evidence says the opposite"])
        return out
    if field == "economic_buyer":
        vals = {}
        for e in pos:
            vals.setdefault(_canon(e["value"], titles), []).append(e)
        if len(vals) > 1:
            latest = pos[-1]
            if latest["supersedes_cue"] and sum(1 for e in pos if e["doc_date"] == latest["doc_date"] and _canon(e["value"], titles) != _canon(latest["value"], titles)) == 0:
                pos = [e for e in pos if _canon(e["value"], titles) == _canon(latest["value"], titles)]
            else:
                out.update(status="conflict", evidence=[_ref(e) for e in pos], reasons=["different economic buyers named; a human must resolve"])
                return out
    elif field == "decision_process":
        dated = [e for e in pos if e["value"] != "undated"]
        if dated:
            vals = {e["value"] for e in dated}
            if len(vals) > 1:
                latest = dated[-1]
                if latest["supersedes_cue"]:
                    pos = [latest]
                else:
                    out.update(status="conflict", evidence=[_ref(e) for e in dated], reasons=["different decision dates with no stated reschedule"])
                    return out
            else:
                pos = dated
    elif field == "paper_process":
        ranks = [PAPER_RANK[e["value"]] for e in pos]
        if ranks and ranks[-1] < max(ranks):
            out.update(status="conflict", evidence=[_ref(e) for e in pos], reasons=["paper process went backwards between notes"])
            return out
    latest = pos[-1]
    if neg and _key(neg[-1]) >= _key(latest):
        out.update(status="conflict", evidence=[_ref(latest), _ref(neg[-1])], reasons=["a later buyer statement contradicts the earlier one"])
        return out
    out.update(value=latest["value"], evidence=[_ref(latest)])
    age = (as_of - date.fromisoformat(latest["doc_date"])).days
    max_age = policy["max_age_days"].get(field, policy["max_age_days"]["default"])
    if age > max_age:
        out.update(status="stale", reasons=[f"evidence is {age} days old; limit {max_age}"])
        return out
    if field == "decision_process":
        if latest["value"] == "undated":
            out.update(status="undated", reasons=["a decision step is named but no date"])
            return out
        d = date.fromisoformat(latest["value"])
        if d < as_of:
            out.update(status="date_passed", reasons=["the stated decision date has passed with no newer evidence"])
            return out
        cd = deal.get("close_date_d")
        if policy["decision_date_must_be_on_or_before_close_date"] and cd and d > cd:
            out.update(status="after_close_date", reasons=[f"decision date {d} is after the close date {cd}"])
            return out
    if field == "paper_process" and latest["value"] not in policy["paper_process_ok_statuses"]:
        out.update(status="not_started", reasons=["the buyer says legal or procurement has not started"])
        return out
    out["status"] = "satisfied"
    return out


def assess_deal(deal: dict, evid: list[dict], policy: dict, as_of: date, titles: dict, quarantined_docs: list[str]) -> dict:
    fields = {f: assess_field(f, evid, deal, policy, as_of, titles) for f in policy["meddpicc_fields"]}
    ok = lambda f: fields[f]["status"] == "satisfied"
    commit_missing = [f for f in policy["commit_requires"] if not ok(f)]
    miss_txt = ", ".join("%s=%s" % (f, fields[f]["status"]) for f in commit_missing)
    if not commit_missing:
        allowed, why = "Commit", ["economic buyer, dated decision process and paper process all evidenced by the buyer and fresh"]
    elif all(ok(f) for f in policy["best_case_requires_all"]) and any(ok(f) for f in policy["best_case_requires_any"]):
        allowed, why = "Best Case", ["Commit evidence missing: " + miss_txt]
    else:
        allowed, why = "Pipeline", ["Best Case evidence missing; Commit missing: " + miss_txt]
    called = deal["category_norm"]
    rank = policy["category_rank"]
    if called in rank:
        change = "none" if called == allowed else ("downgrade" if rank[called] > rank[allowed] else "upgrade_suggestion")
    else:
        change = "review_unknown_category"
    return {"deal_id": deal["deal_id"], "called_category": called, "allowed_category": allowed, "change": change,
            "why": why, "fields": fields, "quarantined_docs": quarantined_docs}
