"""Load deals and documents (call notes, emails, rep notes) from CSV. All data in this repo is synthetic."""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

FIELDS = ["metrics", "economic_buyer", "decision_criteria", "decision_process", "paper_process", "identify_pain", "champion", "competition"]
CATS = {"commit": "Commit", "committed": "Commit", "best case": "Best Case", "bestcase": "Best Case", "best_case": "Best Case",
        "most likely": "Best Case", "pipeline": "Pipeline", "": "", "omit": "Omit", "omitted": "Omit", "closed": "Closed"}


def norm_category(v: str) -> str:
    return CATS.get((v or "").strip().lower(), "UNKNOWN")


def parse_date(v) -> date | None:
    try:
        return date.fromisoformat((v or "").strip()[:10])
    except ValueError:
        return None


def load_deals(path) -> dict[str, dict]:
    deals = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r = {k: (v or "").strip() for k, v in r.items()}
            r["category_norm"] = norm_category(r.get("forecast_category", ""))
            r["close_date_d"] = parse_date(r.get("close_date"))
            deals[r["deal_id"]] = r
    return deals


def load_docs(path) -> list[dict]:
    docs = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r["text"] = r.get("text", "")
            r["date_d"] = parse_date(r.get("date"))
            docs.append(r)
    return docs


_LINE = re.compile(r"^(BUYER|REP)\s+([^:(]+?)(?:\s*\(([^)]*)\))?:\s*(.*)$")
_SENT = re.compile(r"(?<=[.!?])\s+")


def segments(doc: dict):
    """Yield (role, speaker_name, speaker_title, sentence). Sentences are verbatim substrings of doc['text'].

    Call notes use 'BUYER Name (Title): ...' / 'REP Name: ...' lines. Emails take the author's role for every line.
    Rep notes are always rep-reported. A line with no speaker label inherits the document author's role.
    """
    default_role = "buyer" if doc.get("author_role") == "buyer" else "rep"
    if doc.get("doc_type") == "rep_note":
        default_role = "rep"
    for line in doc["text"].splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith(">"):
            continue  # quoted earlier message: not something this author just said
        if line.strip() == "--":
            break  # signature block
        m = _LINE.match(line.strip())
        if m and doc.get("doc_type") == "call_note":
            role, name, title, body = m.group(1).lower(), m.group(2).strip(), (m.group(3) or "").strip(), m.group(4)
        else:
            role, name, title, body = default_role, doc.get("author_name", ""), "", line.strip()
        for s in _SENT.split(body):
            s = s.strip()
            if s:
                yield role, name, title, s
