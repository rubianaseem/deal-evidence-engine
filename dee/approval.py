"""Enforced human approval, bound to the SHA-256 of crm_update_plan.json. Adapted from my crm-change-control-plane.

Enforced in code (each rule has a unit test or failure-suite scenario):
  - The approver is a named human in config/approvers.json. Agent, model and service identities are refused.
  - The approver gives the full 64-character SHA-256 of the plan file; it must match the file on disk and the
    hash recorded in manifest.json when the run produced it. Editing the plan voids the approval.
  - Held items (forecast category changes) run only if the approver lists them
    explicitly and is allowed to approve held items. Everything else in the plan is approved as a whole.
  - Approvals expire after approval_ttl_hours and live in a hash-chained approvals.jsonl.
There is no auto-approve flag and no code path that writes to the (mock) CRM without verify_approval() passing.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .audit import AuditLog, verify
from .util import iso, parse_dt, read_json, sha256_file


class ApprovalError(Exception):
    pass


def is_agent(approver_id: str, blocked: list[str]) -> bool:
    """True for empty ids and for any id whose hyphen/underscore-separated tokens contain a blocked identity,
    including multi-word blocked ids such as 'deal-evidence-engine'."""
    ident = "-".join(t for t in re.split(r"[^a-z0-9]+", (approver_id or "").lower()) if t)
    if not ident:
        return True
    padded = f"-{ident}-"
    for b in blocked:
        nb = "-".join(t for t in re.split(r"[^a-z0-9]+", b.lower()) if t)
        if nb and f"-{nb}-" in padded:
            return True
    return False


def approve(run_dir, sha256: str, approver_id: str, now: datetime, approvers: dict, held_items: list[str] | None = None) -> dict:
    run_dir = Path(run_dir)
    m = read_json(run_dir / "manifest.json")
    if is_agent(approver_id, approvers.get("blocked_identities", [])):
        raise ApprovalError(f"'{approver_id}' is an agent, model or service identity and can never approve")
    who = approvers.get("approvers", {}).get(approver_id)
    if not who:
        raise ApprovalError(f"unknown approver '{approver_id}'; approvers are named humans in config/approvers.json")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256 or ""):
        raise ApprovalError("approval needs the full 64-character SHA-256 printed by `python agent.py show`")
    current = sha256_file(run_dir / "crm_update_plan.json")
    if sha256 != current:
        raise ApprovalError("hash does not match crm_update_plan.json on disk; review the current plan and use its hash")
    if current != m["plan_sha256"]:
        raise ApprovalError("crm_update_plan.json differs from what this run generated; re-run instead of editing outputs")
    _check_renderings(run_dir, m)
    queue = read_json(run_dir / "approval_queue.json")
    held_ids = {h["item_id"] for h in queue["held"]}
    held_items = sorted(set(held_items or []))
    unknown = [h for h in held_items if h not in held_ids]
    if unknown:
        raise ApprovalError(f"not held items in this plan: {', '.join(unknown)}")
    if held_items and not who.get("may_approve_held"):
        raise ApprovalError(f"{who['name']} may approve the plan but not held items (forecast category changes)")
    log = AuditLog(run_dir / "approvals.jsonl", clock=lambda: now)
    return log.append({"event": "approved", "plan_sha256": sha256, "approver": approver_id, "approver_name": who["name"],
                       "run_id": m["run_id"], "held_items_approved": held_items,
                       "expires_at": iso(now + timedelta(hours=approvers.get("approval_ttl_hours", 24)))})


def _check_renderings(run_dir: Path, m: dict) -> None:
    for fname, key in (("hubspot_update_plan.json", "hubspot_plan_sha256"), ("salesforce_update_plan.json", "salesforce_plan_sha256")):
        if sha256_file(run_dir / fname) != m[key]:
            raise ApprovalError(f"{fname} differs from what this run generated; approval is void")


def verify_approval(run_dir, now: datetime) -> dict:
    run_dir = Path(run_dir)
    m = read_json(run_dir / "manifest.json")
    ap = run_dir / "approvals.jsonl"
    if not ap.exists():
        raise ApprovalError("not approved: run `python agent.py approve` with a named approver and the plan hash")
    ok, why = verify(ap)
    if not ok:
        raise ApprovalError(f"approvals log failed verification: {why}")
    recs = [json.loads(x) for x in ap.read_text().splitlines() if x.strip()]
    mine = [r for r in recs if r.get("event") == "approved"]
    if not mine:
        raise ApprovalError("not approved")
    last = mine[-1]
    current = sha256_file(run_dir / "crm_update_plan.json")
    if current != last["plan_sha256"] or current != m["plan_sha256"]:
        raise ApprovalError("plan changed after approval; approval is void")
    _check_renderings(run_dir, m)
    if now > parse_dt(last["expires_at"]):
        raise ApprovalError("approval expired; review and approve again")
    return last
