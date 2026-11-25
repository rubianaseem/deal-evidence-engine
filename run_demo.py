"""python run_demo.py : the whole loop on the synthetic sample, offline, no API key.
run -> show -> refused execute -> refused agent approval -> named human approves -> execute against the LOCAL MOCK CRM."""
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from dee.approval import ApprovalError, approve
from dee.crm_mock import MockCRM
from dee.executor import execute
from dee.ingest import load_deals
from dee.pipeline import run
from dee.util import read_json

OUT = Path("outputs/demo")
NOW = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
if OUT.exists():
    shutil.rmtree(OUT)  # only ever touches this script's own demo output folder

res = run("sample_deals.csv", "sample_notes.csv", OUT, date(2026, 11, 25))
a = res["result"]["assessments"]
print("deal     rep called -> evidence supports   change")
for did, x in sorted(a.items()):
    print(f"{did}  {x['called_category']:<10} -> {x['allowed_category']:<9}  {x['change']}")
print("quarantined docs:", sorted(res["result"]["quarantined"]))
sha = res["manifest"]["plan_sha256"]
print("plan sha256:", sha[:16] + "...")
crm = MockCRM(OUT / "crm_state.json", load_deals("sample_deals.csv"))
approvers = read_json("config/approvers.json")
try:
    execute(OUT, crm, NOW)
except ApprovalError as e:
    print("execute before approval ->", e)
try:
    approve(OUT, sha, "claude", NOW, approvers)
except ApprovalError as e:
    print("agent approval ->", e)
held = [h["item_id"] for h in read_json(OUT / "approval_queue.json")["held"]]
rec = approve(OUT, sha, "revops-lead", NOW, approvers, held[:2])
print("approved by", rec["approver_name"], "| held items released:", rec["held_items_approved"])
print("execute (local mock CRM):", execute(OUT, crm, NOW, sleep=lambda s: None, snapshot_paths=("sample_deals.csv", "sample_notes.csv")))
print("duplicate CRM effects:", crm.duplicate_effects())
