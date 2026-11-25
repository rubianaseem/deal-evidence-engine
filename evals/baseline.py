"""Keyword-rules baseline: what a typical 'if the notes mention X, tick the box' automation does.

No speaker check (the rep's own pitch counts), no negation, no dates, no freshness, no quarantine, no validation.
Category: Commit if economic buyer + decision process + paper process keywords all appear anywhere in the deal's
notes; Best Case if pain plus one of economic buyer / decision process / champion; else Pipeline.
"""
from __future__ import annotations

import re

from dee.extract import _QTY

KW = {
    "economic_buyer": re.compile(r"\b(cfo|ceo|economic buyer|budget|signs?|approv\w*|final say)\b", re.I),
    "decision_process": re.compile(r"\b(committee|board|decision|steering)\b", re.I),
    "paper_process": re.compile(r"\b(legal|procurement|msa|redlines?|security|contract|vendor registration)\b", re.I),
    "champion": re.compile(r"\b(champion|sponsor|forward\w*|shar\w+|introduc\w+)\b", re.I),
    "identify_pain": re.compile(r"\b(pain|problem|manual|headache|slow|backlog|struggl\w+)\b", re.I),
    "decision_criteria": re.compile(r"\b(must|require\w*|criteria|need to)\b", re.I),
}
COMPETITORS = ["AcmeLang", "TranslateCo", "Lingua Pro", "GlobalWord", "PolyglotAI", "Verbatim Labs"]
_SENT = re.compile(r"(?<=[.!?])\s+|\n")


def baseline_evidence(docs: list[dict]) -> list[dict]:
    out = []
    for d in docs:
        for sent in _SENT.split(d["text"]):
            sent = sent.strip()
            if not sent:
                continue
            hits = [f for f, rx in KW.items() if rx.search(sent)]
            if _QTY.search(sent):
                hits.append("metrics")
            if any(c.lower() in sent.lower() for c in COMPETITORS):
                hits.append("competition")
            for f in hits:
                out.append({"deal_id": d["deal_id"], "doc_id": d["doc_id"], "field": f, "polarity": "pos", "span": sent})
    return out


def baseline_category(evid: list[dict]) -> dict[str, str]:
    by = {}
    for e in evid:
        by.setdefault(e["deal_id"], set()).add(e["field"])
    return by


def category_from_fields(fields: set[str]) -> str:
    if {"economic_buyer", "decision_process", "paper_process"} <= fields:
        return "Commit"
    if "identify_pain" in fields and fields & {"economic_buyer", "decision_process", "champion"}:
        return "Best Case"
    return "Pipeline"
