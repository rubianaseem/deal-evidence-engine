#!/usr/bin/env python3
"""deal-evidence-engine CLI. Writes files; the only 'CRM' it can touch is a local JSON mock.

  python agent.py run --deals sample_deals.csv --notes sample_notes.csv --out outputs/run --as-of 2026-11-25
  python agent.py show --out outputs/run
  python agent.py approve --out outputs/run --approver revops-lead --sha256 <64 hex> [--hold DEAL:category_change ...]
  python agent.py execute --out outputs/run --deals sample_deals.csv --notes sample_notes.csv      (local mock CRM only)
  python agent.py replay --out outputs/run --doc-id DOC-1-1 --deals ... --notes ...
  python agent.py verify --out outputs/run
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from dee import audit as audit_mod
from dee.approval import ApprovalError, approve, verify_approval
from dee.crm_mock import MockCRM
from dee.executor import execute, replay
from dee.ingest import load_deals
from dee.llm import get_client
from dee.pipeline import run
from dee.util import read_json, sha256_file


def _now(a):
    return datetime.fromisoformat(a.now.replace("Z", "+00:00")) if getattr(a, "now", None) else datetime.now(timezone.utc)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--deals", default="sample_deals.csv"); r.add_argument("--notes", default="sample_notes.csv")
    r.add_argument("--out", default="outputs/run"); r.add_argument("--as-of", default=date.today().isoformat())
    r.add_argument("--policy", default="config/policy.json"); r.add_argument("--approvers", default="config/approvers.json")
    r.add_argument("--claude", action="store_true", help="use Claude for extraction (needs ANTHROPIC_API_KEY); output still passes the validators")
    for name in ("show", "verify"):
        s = sub.add_parser(name); s.add_argument("--out", default="outputs/run")
    a_ = sub.add_parser("approve")
    a_.add_argument("--out", default="outputs/run"); a_.add_argument("--sha256", required=True); a_.add_argument("--approver", required=True)
    a_.add_argument("--hold", nargs="*", default=[], help="held item ids you have reviewed and release, e.g. D-1:category_change")
    a_.add_argument("--approvers", default="config/approvers.json"); a_.add_argument("--now")
    for name in ("execute", "replay"):
        e = sub.add_parser(name)
        e.add_argument("--out", default="outputs/run"); e.add_argument("--deals", default="sample_deals.csv"); e.add_argument("--notes", default="sample_notes.csv")
        e.add_argument("--now"); e.add_argument("--no-sleep", action="store_true")
        if name == "replay":
            e.add_argument("--doc-id", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    try:
        if args.cmd == "run":
            client = None
            if args.claude:
                client = get_client()
                if client is None:
                    print("--claude needs ANTHROPIC_API_KEY and the anthropic package (pip install -r requirements-optional.txt); using offline rules instead.", file=sys.stderr)
            res = run(args.deals, args.notes, out, date.fromisoformat(args.as_of), args.policy, args.approvers, client=client)
            m = res["manifest"]
            q = res["plans"]["queue"]
            print(f"run {m['run_id']} extractor={m['extractor']} as_of={m['as_of']}")
            print(f"deals assessed: {len(res['result']['assessments'])}, evidence kept: {len(res['result']['evidence'])}, quarantined docs: {len(res['result']['quarantined'])}")
            print(f"plan ops: {q['plain_ops']} plain field updates, {q['held_ops']} held category changes")
            print(f"plan sha256: {m['plan_sha256']}\nnothing has been written anywhere; review {out}/review_packet.md then approve")
        elif args.cmd == "show":
            m = read_json(out / "manifest.json")
            q = read_json(out / "approval_queue.json")
            print(f"plan_sha256 {m['plan_sha256']}\nplain ops {q['plain_ops']}, held ops {q['held_ops']}")
            for h in q["held"]:
                print(f"  held {h['item_id']}: {h['from']} -> {h['to']} ({h['change']})")
        elif args.cmd == "approve":
            rec = approve(out, args.sha256, args.approver, _now(args), read_json(args.approvers), args.hold)
            print(f"approved by {rec['approver_name']} until {rec['expires_at']}; held items released: {rec['held_items_approved'] or 'none'}")
        elif args.cmd in ("execute", "replay"):
            now = _now(args)
            crm = MockCRM(out / "crm_state.json", load_deals(args.deals))
            kw = {"snapshot_paths": (args.deals, args.notes)}
            if args.no_sleep:
                kw["sleep"] = lambda s: None
            if args.cmd == "execute":
                print(execute(out, crm, now, **kw))
            else:
                print(replay(out, crm, now, args.doc_id, **kw))
        elif args.cmd == "verify":
            for f in ("audit.log", "approvals.jsonl"):
                if (out / f).exists():
                    print(f, audit_mod.verify(out / f))
    except ApprovalError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
