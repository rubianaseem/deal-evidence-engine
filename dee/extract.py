"""Offline deterministic MEDDPICC evidence extractor (the default; needs no API key).

For each sentence, spoken or written by a known role, detectors propose evidence:
  {deal_id, doc_id, doc_date, field, value, span, polarity, strength, speaker}
span is a verbatim sentence from the document. strength is buyer_stated or rep_reported: the buyer must say it.
Detectors are regex rules I tuned on the dev split only (see docs/EVALUATION.md). They are a baseline-beating
extractor, not a language model: paraphrases they do not know are simply missed (a recall problem, never a
fabrication problem, because every candidate also passes validate.py).
"""
from __future__ import annotations

import re
from datetime import date

from .ingest import segments

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_DM = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r"\b", re.I)
_DATE_MD = re.compile(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)

# --- patterns -------------------------------------------------------------------------------------------------
_EB_FIRST = re.compile(r"\bI\s+(?:will\s+|'ll\s+|do\s+|have to\s+|need to\s+)?(?:sign|approve|own the budget|hold the budget|make the final call|have (?:the )?final (?:say|sign[- ]?off))\b|\b(?:budget|signature|sign[- ]?off)\s+(?:sits|lies|rests)\s+with me\b|\bI(?:'m| am)\s+(?:the\s+)?(?:economic buyer|final approver|signatory|one who signs)\b", re.I)
_NAME = r"(?:(?!(?:Board|Legal|Procurement|Security|Committee|Finance|Leadership|Management|Steering|Everyone|Someone|Nobody|Anyone|Decision)\b)[A-Z][a-z]+(?:\s[A-Z][a-z]+)?|[Oo]ur\s+(?:CFO|CEO|COO|CMO|CTO|CRO|VP\s+[A-Z][A-Za-z]+|Head\s+of\s+[A-Z][A-Za-z]+))"
_EB_THIRD = re.compile(r"\b(" + _NAME + r")\s+(?:will\s+|has to\s+|needs to\s+|must\s+|is going to\s+)?(?:sign(?:s)?(?:\s+off)?\b|approve(?:s)?\b|owns the budget|holds the budget|has (?:the )?final (?:say|sign[- ]?off))")
_EB_NEG = re.compile(r"\bI(?:'m| am)\s+not\s+(?:the\s+)?(?:final\s+)?(?:decision[- ]?maker|approver|signatory|economic buyer)\b|\bsomeone else\s+(?:signs|approves|owns the budget)\b|\b(?:isn't|is not)\s+(?:the\s+)?(?:final\s+)?(?:decision[- ]?maker|approver|signatory)\b|\bI\s+(?:can't|cannot|don't|do not)\s+(?:sign|approve)\b", re.I)
_DP_KEY = re.compile(r"\b(?:committee|board|steering|exec(?:utive)?\s+(?:review|team)|approval\s+(?:meeting|call|gate)|decision\s+(?:meeting|date|call)|we(?:'ll| will)\s+decide|sign[- ]?off\s+(?:meeting|call)|leadership\s+review|invest(?:ment)?\s+committee)\b", re.I)
_DP_VERB = re.compile(r"\b(?:meet\w*|decid\w*|approv\w*|vote\w*|review\w*|sign\w*|choos\w*|select\w*|lock\w*|go\s+or\s+no[- ]go)\b", re.I)
_PAPER_KEY = re.compile(r"\b(?:procurement|legal|security\s+(?:review|questionnaire|team)|infosec|MSA|DPA|redlines?|vendor\s+(?:registration|onboarding|form)|purchase\s+order|PO\b|contract(?:\s+review)?)\b", re.I)
_PAPER_NOT = re.compile(r"\b(?:haven't|have not|hasn't|has not|hadn't|not\s+yet|yet\s+to|never\s+(?:seen|started|received)|no\s+one\s+has|nobody\s+has|won't\s+(?:start|look)|will\s+(?:only\s+)?start\s+(?:once|after|when)|not\s+started|not\s+begun|still\s+(?:need|have)\s+to\s+(?:start|send|kick))\b", re.I)
_PAPER_DONE = re.compile(r"\b(?:approved|signed\s+off|cleared|completed|finished|passed|agreed\s+(?:all|the)\s+redlines|no\s+(?:further|more)\s+(?:comments|changes|redlines)|all\s+done|is\s+done|are\s+done)\b", re.I)
_PAPER_PROG = re.compile(r"\b(?:sent|received|reviewing|under\s+review|in\s+review|redlin\w+|started|kicked\s+off|submitted|working\s+through|raised|issued|with\s+(?:our\s+)?(?:legal|procurement|security)|forwarded|reviewed|looking\s+at|in\s+progress|underway)\b", re.I)
_CHAMP = re.compile(r"\bI(?:'ll|\s+will|'ve|\s+have|'m\s+going\s+to|\s+already)\s+(?:already\s+)?(?:forward(?:ed)?|shar(?:e|ed)|circulat(?:e|ed)|introduc(?:e|ed)|brought|bring|set\s+up|booked|book|schedul(?:e|ed)|walk(?:ed)?\s+\w+\s+through|pushed|push|pitch(?:ed)?|looped\s+in|loop\s+in)\b|\bI(?:'m|\s+am)\s+(?:taking|presenting|bringing)\s+(?:this|it|the\s+\w+)\b|\bI(?:'ll|\s+will)\s+take\s+(?:this|it)\s+to\b|\bI(?:'ll|\s+will)\s+(?:sell|champion|advocate)\b", re.I)
_PAIN = re.compile(r"\b(?:problem|pain(?:ful)?|struggl\w+|breaks?|broken|manual(?:ly)?|costing\s+us|can't\s+keep\s+up|biggest\s+(?:issue|headache|challenge)|bottleneck|too\s+slow|keeps?\s+failing|error[- ]prone|falling\s+behind|backlog|headache)\b", re.I)
_QTY = re.compile(r"(?:[£$€]\s?\d[\d,\.]*\s?[kKmM]?\b|\b\d+(?:\.\d+)?\s?(?:%|percent|hours|hrs|days|weeks|FTEs?|x\b))")
_METRIC_CTX = re.compile(r"\b(?:target|goal|save|saving|reduce|cut|cutting|cost(?:s|ing)?|lose|losing|per\s+(?:month|year|quarter|week)|currently|today\s+we|at\s+the\s+moment|aim|need\s+to\s+get|down\s+to|from)\b", re.I)
_CRIT = re.compile(r"\b(?:must[- ]have|must\s+(?:integrate|support|work|meet|have)|need(?:s)?\s+to\s+(?:integrate|support|work|meet|have)|requirements?|criteria|deal[- ]?breaker|non[- ]negotiable|we(?:'ll| will)\s+(?:choose|pick|decide)\s+(?:based\s+on|on)|evaluating\s+(?:on|against)|has\s+to\s+(?:integrate|support|work|meet|have)|important\s+to\s+us)\b", re.I)
_COMP_CTX = re.compile(r"\b(?:evaluat\w+|compar\w+|also\s+(?:talking|looking|speaking)|shortlist\w*|incumbent|currently\s+(?:use|using)|alternative|quote\s+from|demo\s+from|in\s+the\s+mix|against|versus|vs\.?|trial\w*|already\s+(?:use|using|have))\b", re.I)
_CASE_STUDY = re.compile(r"\b(?:case\s+study|customers?\s+like|other\s+customers|typical(?:ly)?\s+customers?|on\s+average|our\s+customers)\b", re.I)
_SUPERSEDE = re.compile(r"\b(?:actually|instead|no\s+longer|changed|moved|pushed|rescheduled|brought\s+forward|now|correction|update)\b", re.I)


def parse_dates(sentence: str, ref: date) -> list[date]:
    out = []
    for m in _DATE_ISO.finditer(sentence):
        try:
            out.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for rx, order in ((_DATE_DM, "dm"), (_DATE_MD, "md")):
        for m in rx.finditer(sentence):
            d, mon = (m.group(1), m.group(2)) if order == "dm" else (m.group(2), m.group(1))
            try:
                dt = date(ref.year, MONTHS[mon[:3].lower()], int(d))
            except ValueError:
                continue
            if (ref - dt).days > 180:
                dt = dt.replace(year=ref.year + 1)
            out.append(dt)
    return sorted(set(out))


def paper_status(sentence: str) -> str | None:
    if not _PAPER_KEY.search(sentence):
        return None
    if _PAPER_NOT.search(sentence):
        return "not_started"
    if _PAPER_DONE.search(sentence):
        return "complete"
    if _PAPER_PROG.search(sentence):
        return "in_progress"
    return None


def decision_value(sentence: str, ref: date) -> str | None:
    if not _DP_KEY.search(sentence):
        return None
    ds = parse_dates(sentence, ref)
    if ds:
        return ds[0].isoformat()
    return "undated" if _DP_VERB.search(sentence) and not re.search(r"\b(?:not|never|hasn't|haven't)\b", sentence, re.I) else None


def competitor_in(sentence: str, competitors: list[str]) -> str | None:
    low = sentence.lower()
    for c in competitors:
        if c.lower() in low and _COMP_CTX.search(sentence):
            return c
    return None


def eb_value(sentence: str, speaker: str, title: str):
    """Return (value, polarity) or None."""
    if _EB_NEG.search(sentence):
        return (speaker or "unknown", "neg")
    if _EB_FIRST.search(sentence):
        return ((speaker or "unknown"), "pos")
    m = _EB_THIRD.search(sentence)
    if m:
        return (m.group(1), "pos")
    return None


def derive_value(field: str, span: str, speaker: str, title: str, ref: date, competitors: list[str]):
    """Deterministically recompute (value, polarity) from a span. validate.py uses this to check any candidate,
    including model output, so a value the span does not support is rejected."""
    if field == "economic_buyer":
        return eb_value(span, speaker, title)
    if field == "decision_process":
        v = decision_value(span, ref)
        return (v, "pos") if v else None
    if field == "paper_process":
        v = paper_status(span)
        return (v, "pos") if v else None
    if field == "champion":
        return (speaker or "unknown", "pos") if _CHAMP.search(span) else None
    if field == "identify_pain":
        return ("pain", "pos") if _PAIN.search(span) else None
    if field == "metrics":
        q = _QTY.search(span)
        if q and _METRIC_CTX.search(span) and not _CASE_STUDY.search(span):
            return (q.group(0).strip(), "pos")
        return None
    if field == "decision_criteria":
        return ("criteria", "pos") if _CRIT.search(span) else None
    if field == "competition":
        c = competitor_in(span, competitors)
        return (c, "pos") if c else None
    return None


def extract_doc(doc: dict, policy: dict, ref: date) -> list[dict]:
    out = []
    comps = policy["competitors"]
    for role, speaker, title, sent in segments(doc):
        for field in policy["meddpicc_fields"]:
            dv = derive_value(field, sent, speaker, title, ref, comps)
            if not dv:
                continue
            value, pol = dv
            out.append({"deal_id": doc["deal_id"], "doc_id": doc["doc_id"], "doc_date": doc["date"], "field": field,
                        "value": value, "span": sent, "polarity": pol, "speaker": speaker, "speaker_title": title,
                        "strength": "buyer_stated" if role == "buyer" else "rep_reported",
                        "supersedes_cue": bool(_SUPERSEDE.search(sent)), "extractor": "rules"})
    return out
