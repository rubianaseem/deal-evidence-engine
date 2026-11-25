"""A local mock CRM (JSON file). Nothing here talks to a real CRM.

It holds deals seeded from the CRM export and behaves like the parts of a CRM API that break naive executors:
  - Idempotency-Key: a repeated key returns the stored result and writes nothing.
  - 429 with Retry-After, injected per op and attempt.
  - "lost ack": the write commits but the client sees a timeout.
  - crash after commit: the write commits, then the process dies before the executor checkpoints.
  - permanent 404/400/409: unknown deal, bad picklist value, or stale snapshot (the field changed since the plan) -> dead letter.
`effects` records every applied write with its natural op key, so tests can count duplicate effects.
"""
from __future__ import annotations

from pathlib import Path

from .util import read_json, write_json


class RateLimited(Exception):
    def __init__(self, retry_after: float):
        super().__init__(f"429 retry after {retry_after}s")
        self.retry_after = retry_after


class LostAck(Exception):
    pass


class PermanentError(Exception):
    pass


class Crash(BaseException):
    """Simulates the process dying (not caught by `except Exception`)."""


class MockCRM:
    VALID_CATEGORIES = {"Commit", "Best Case", "Pipeline"}

    def __init__(self, path, seed_deals: dict | None = None, faults: dict | None = None):
        self.path = Path(path)
        self.faults = faults or {}
        self.attempts: dict[str, int] = {}
        if not self.path.exists():
            deals = {did: {k: d.get(k, "") for k in ["forecast_category"] + [k for k in d if k.startswith("meddpicc_") or k in
                     ("metrics", "economic_buyer", "decision_criteria", "decision_process", "paper_process", "identify_pain", "champion", "competition")]}
                     for did, d in (seed_deals or {}).items()}
            # the export uses bare field names for what the CRM stores as meddpicc_<field>
            for did, d in deals.items():
                for f in ("metrics", "economic_buyer", "decision_criteria", "decision_process", "paper_process", "identify_pain", "champion", "competition"):
                    d["meddpicc_" + f] = d.pop(f, "")
            write_json(self.path, {"deals": deals, "idempotency": {}, "effects": [], "seq": 0})

    def _state(self):
        return read_json(self.path)

    def get_deal(self, deal_id):
        return self._state()["deals"].get(deal_id)

    def apply(self, op: dict, idempotency_key: str | None) -> dict:
        n = self.attempts[op["op_id"]] = self.attempts.get(op["op_id"], 0) + 1
        f = self.faults.get(op["op_id"], {})
        if n <= f.get("rate_limit_times", 0):
            raise RateLimited(f.get("retry_after", 1.0))
        if f.get("always_429"):
            raise RateLimited(f.get("retry_after", 1.0))
        st = self._state()
        if idempotency_key and idempotency_key in st["idempotency"]:
            return {**st["idempotency"][idempotency_key], "deduplicated": True}
        deal = st["deals"].get(op["deal_id"])
        if deal is None:
            raise PermanentError(f"404 unknown deal {op['deal_id']}")
        p = op["payload"]
        if "forecast_category" in p and p["forecast_category"] not in self.VALID_CATEGORIES:
            raise PermanentError(f"400 invalid forecast_category {p['forecast_category']!r}")
        for k, expected in op.get("expect", {}).items():
            if (deal.get(k, "") or "") != expected:
                raise PermanentError(f"409 stale snapshot: {k} changed since the plan was built")
        st["seq"] += 1
        rec_id = f"crm-{st['seq']:05d}"
        deal.update(p)
        result = {"status": "ok", "crm_id": rec_id}
        if idempotency_key:
            st["idempotency"][idempotency_key] = result
        st["effects"].append({"op_key": op["op_key"], "type": op["type"], "crm_id": rec_id, "deal_id": op["deal_id"]})
        write_json(self.path, st)  # committed
        if f.get("lost_ack_once") and n == 1:
            raise LostAck("timeout after commit")
        if f.get("crash_after_commit") and n == 1:
            raise Crash("process died after commit, before checkpoint")
        return {**result, "deduplicated": False}

    def duplicate_effects(self) -> int:
        seen, dup = set(), 0
        for e in self._state()["effects"]:
            if e["op_key"] in seen:
                dup += 1
            seen.add(e["op_key"])
        return dup
