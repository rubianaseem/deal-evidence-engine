"""Deterministic validators. Every evidence candidate, from the rules extractor or a model, must pass all of them.

1. doc exists, belongs to the candidate's deal, is not quarantined and is not dated after as_of
2. field is one of the eight MEDDPICC fields
3. span is a verbatim substring of the document text (no paraphrase, no ellipsis)
4. speaker role and strength are taken from the document, never from the candidate
5. value is re-derived from the span by the deterministic detectors; typed values must equal it, text values are replaced by it
6. value length is capped and contains no control characters
Rejections carry a reason code and never copy quarantined text.
"""
from __future__ import annotations

from datetime import date

from .extract import _SUPERSEDE, derive_value
from .ingest import segments

TYPED = {"economic_buyer", "decision_process", "paper_process", "metrics", "competition", "champion"}


def _locate(doc: dict, span: str):
    for role, speaker, title, sent in segments(doc):
        if span in sent or sent in span:
            return role, speaker, title
    # span may sit inside the raw text but straddle sentences: still located by raw substring, use doc author role
    return ("buyer" if doc.get("author_role") == "buyer" and doc.get("doc_type") != "rep_note" else "rep"), doc.get("author_name", ""), ""


def validate_candidate(c: dict, docs_by_id: dict, quarantined: set, policy: dict, as_of: date):
    """Return (evidence_or_None, reason_or_None)."""
    doc = docs_by_id.get(c.get("doc_id"))
    if doc is None:
        return None, "unknown_doc"
    if doc["deal_id"] != c.get("deal_id"):
        return None, "doc_belongs_to_other_deal"
    if doc["doc_id"] in quarantined:
        return None, "doc_quarantined"
    if doc["date_d"] is None:
        return None, "doc_date_invalid"
    if doc["date_d"] > as_of:
        return None, "doc_dated_in_future"
    field = c.get("field")
    if field not in policy["meddpicc_fields"]:
        return None, "unknown_field"
    span = c.get("span")
    if not isinstance(span, str) or not span.strip():
        return None, "empty_span"
    span = span.strip()
    if span not in doc["text"]:
        return None, "span_not_verbatim_in_source"
    if len(span) > 600:
        return None, "span_too_long"
    role, speaker, title = _locate(doc, span)
    dv = derive_value(field, span, speaker, title, as_of, policy["competitors"])
    if dv is None:
        return None, "span_does_not_support_field"
    value, pol = dv
    if field in TYPED:
        cv = str(c.get("value", "")).strip()
        if cv.lower() != str(value).lower():
            return None, "value_not_supported_by_span"
    if pol != c.get("polarity", pol):
        return None, "polarity_mismatch"
    value = str(value)
    if len(value) > policy["max_field_chars"] or any(ord(ch) < 32 for ch in value):
        return None, "bad_value"
    ev = {"deal_id": doc["deal_id"], "doc_id": doc["doc_id"], "doc_date": doc["date"], "field": field, "value": value,
          "span": span, "polarity": pol, "speaker": speaker, "speaker_title": title,
          "strength": "buyer_stated" if role == "buyer" else "rep_reported",
          "supersedes_cue": bool(_SUPERSEDE.search(span)), "extractor": c.get("extractor", "unknown")}
    return ev, None
