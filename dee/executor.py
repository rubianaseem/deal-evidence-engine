"""Execute an approved plan against the mock CRM: idempotent, resumable, with dead letter and replay.

- Refuses to run unless approval.verify_approval() passes for the exact plan hash.
- Runs only non-held ops plus held items the approver listed. Everything else is logged as held_not_approved.
- Idempotency-Key per op = SHA-256 of the op's natural key (type, deal, payload, evidence refs), so a
  retry, a resume after a crash or a full re-run on the same evidence cannot apply a second write.
- Checkpoint (checkpoint.json, atomic write) after every op. A crash between commit and checkpoint is safe:
  the resend carries the same key and the CRM returns the stored result.
- 429: wait Retry-After (or exponential backoff), up to max_attempts; then dead letter.
- Permanent errors go straight to dead_letter.jsonl with the source doc ids. `replay --doc-id` re-runs them.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .approval import ApprovalError, verify_approval
from .audit import AuditLog
from .crm_mock import LostAck, PermanentError, RateLimited
from .util import read_json, sha256_file, write_json


def allowed_ops(plan: dict, approval: dict) -> tuple[list[dict], list[dict]]:
    ok_groups = set(approval.get("held_items_approved", []))
    run, held = [], []
    for op in plan["ops"]:
        (run if not op["requires_approval"] or op["group"] in ok_groups else held).append(op)
    return run, held


def execute(run_dir, crm, now, *, sleep=time.sleep, max_attempts: int = 5, base_delay: float = 1.0,
            only_ops: set[str] | None = None, audit: AuditLog | None = None, snapshot_paths: tuple | None = None) -> dict:
    run_dir = Path(run_dir)
    approval = verify_approval(run_dir, now)  # raises ApprovalError: nothing is written
    if snapshot_paths:  # (deals_path, notes_path): refuse if the inputs changed since the plan was built
        m = read_json(run_dir / "manifest.json")
        if sha256_file(snapshot_paths[0]) != m["deals_sha256"] or sha256_file(snapshot_paths[1]) != m["notes_sha256"]:
            raise ApprovalError("stale snapshot: the deal export or notes changed after the plan was built; re-run")
    plan = read_json(run_dir / "crm_update_plan.json")
    audit = audit or AuditLog(run_dir / "audit.log", clock=lambda: now)
    cp_path = run_dir / "checkpoint.json"
    cp = read_json(cp_path) if cp_path.exists() else {"plan_sha256": approval["plan_sha256"], "done": {}}
    if cp["plan_sha256"] != approval["plan_sha256"]:
        cp = {"plan_sha256": approval["plan_sha256"], "done": {}}
    run, held = allowed_ops(plan, approval)
    stats = {"applied": 0, "deduplicated": 0, "skipped_done": 0, "held_not_approved": len(held), "dead_lettered": 0, "retries": 0}
    if only_ops is None:
        for op in held:
            audit.append({"event": "op_held_not_approved", "op_id": op["op_id"], "group": op["group"]})
    for op in run:
        if only_ops is not None and op["op_id"] not in only_ops:
            continue
        if op["op_id"] in cp["done"]:
            stats["skipped_done"] += 1
            continue
        attempt, result, error = 0, None, None
        while attempt < max_attempts:
            attempt += 1
            try:
                result = crm.apply(op, op["idempotency_key"])
                break
            except RateLimited as exc:
                stats["retries"] += 1
                audit.append({"event": "op_retry", "op_id": op["op_id"], "attempt": attempt, "why": "429", "wait_s": exc.retry_after})
                if attempt < max_attempts:
                    sleep(exc.retry_after or base_delay * 2 ** (attempt - 1))
                error = "429 retry budget exhausted"
            except LostAck:
                stats["retries"] += 1
                audit.append({"event": "op_retry", "op_id": op["op_id"], "attempt": attempt, "why": "timeout_after_send"})
                sleep(base_delay * 2 ** (attempt - 1))
                error = "timeouts exhausted"
            except PermanentError as exc:
                error = str(exc)
                break
        if result is None:
            stats["dead_lettered"] += 1
            with open(run_dir / "dead_letter.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"op_id": op["op_id"], "idempotency_key": op["idempotency_key"], "error": error,
                                     "source_event_ids": op["source_event_ids"]}, sort_keys=True) + "\n")
            audit.append({"event": "op_dead_lettered", "op_id": op["op_id"], "error": error,
                          "source_event_ids": op["source_event_ids"]})
            continue
        stats["deduplicated" if result.get("deduplicated") else "applied"] += 1
        cp["done"][op["op_id"]] = result
        write_json(cp_path, cp)
        audit.append({"event": "op_result", "op_id": op["op_id"], "type": op["type"], "crm_id": result["crm_id"],
                      "deduplicated": bool(result.get("deduplicated")), "attempts": attempt,
                      "approved_by": approval["approver"]})
    return stats


def replay(run_dir, crm, now, doc_id: str, **kw) -> dict:
    """Re-run dead-lettered ops whose source documents include doc_id (same idempotency keys)."""
    dl = Path(run_dir) / "dead_letter.jsonl"
    ops = set()
    if dl.exists():
        for line in dl.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                if doc_id in rec["source_event_ids"]:
                    ops.add(rec["op_id"])
    if not ops:
        return {"replayed": 0, "note": f"no dead-lettered ops cite {doc_id}"}
    stats = execute(run_dir, crm, now, only_ops=ops, **kw)
    return {"replayed": len(ops), **stats}
