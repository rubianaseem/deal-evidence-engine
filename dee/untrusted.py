"""Call notes and emails are data, never instructions. Adapted from my revenue-signal-router / crm-change-control-plane.

screen() returns the ids of instruction-like patterns. A flagged document is quarantined whole: no evidence is
extracted from it, its text never reaches a model prompt, a packet or a log. The reviewer sees only the doc id and
the pattern ids. Quarantining the whole document is deliberately blunt; it can cost real evidence (see docs/EVALUATION.md).
"""
from __future__ import annotations

import re
import unicodedata

PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(previous|prior|above|earlier|your)\s+(instructions|rules|prompts?|guidelines)",
    r"disregard\s+(the\s+|all\s+|any\s+)?(previous|prior|above|rules|instructions|gate|policy|evidence)",
    r"\byou\s+are\s+now\b",
    r"^\s*(system|assistant|developer)\s*:",
    r"\b(mark|set|move|treat|classify|label|flag|update)\s+(this|it|the\s+deal|all\s+\w+)?\s*(deal\s+)?(as\s+|to\s+)?(commit|committed|closed|won|approved|verified|safe)\b",
    r"\b(auto[\s-]?approve|skip\s+(the\s+)?(approval|review|validation)s?|bypass\s+(the\s+)?(approval|review|validation|gate|rules))\b",
    r"\b(record|log|write|add)\s+(this\s+)?(as\s+)?(economic\s+buyer|paper\s+process|decision\s+process|evidence)\b",
    r"\bset\s+(the\s+)?(category|stage|amount|owner)\s*(to|=)",
    r"<\|?(im_start|system|endoftext)\|?>",
    r"\bnew\s+instructions?\s*:",
    r"\boverride\s+(the\s+)?(rules|policy|gate|safety|validation)\b",
    r"\bto\s+(the\s+)?(ai|assistant|model|llm|agent)\b",
]
_RX = [re.compile(p, re.I | re.M) for p in PATTERNS]
_INVISIBLE = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}


def normalise(text: str) -> str:
    t = "".join(ch for ch in (text or "") if ch not in _INVISIBLE)
    t = unicodedata.normalize("NFKC", t)
    return re.sub(r"(?<=\b[a-z])-(?=[a-z]\b)", "", t, flags=re.I)  # "i-g-n-o-r-e" style spacing


def screen(text: str) -> list[str]:
    if not text:
        return []
    t = normalise(text)
    return [f"P{i}" for i, rx in enumerate(_RX) if rx.search(t)]
