# SETUP

## 1. Run the sample (no API key)
```bash
python3 -m venv .venv && source .venv/bin/activate     # Python 3.10 or newer
python run_demo.py
python agent.py run --deals sample_deals.csv --notes sample_notes.csv --out outputs/run --as-of 2026-11-25
less outputs/run/review_packet.md
python agent.py show --out outputs/run                 # prints the plan SHA-256 and held items
python agent.py approve --out outputs/run --approver revops-lead --sha256 <hash from show> --hold D-9002:category_change
python agent.py execute --out outputs/run --deals sample_deals.csv --notes sample_notes.csv   # local mock CRM only
python agent.py verify --out outputs/run
```
`sample_deals.csv` has eight edge cases: clean Commit, Commit with no paper process, Commit backed only by a rep note,
a sandbagged Pipeline deal, two different economic buyers, stale evidence, an injected instruction, and a deal with no notes and
a free-text category. `sample_notes.csv` adds an orphan note and a note with an invalid date. Everything is synthetic.

Outputs in `outputs/run/`: `review_packet.md`, `deal_assessments.csv`, `evidence.jsonl`, `rejected_evidence.jsonl`,
`crm_update_plan.json` (canonical, what you approve), `hubspot_update_plan.json`, `salesforce_update_plan.json`,
`approval_queue.json`, `manifest.json`, `audit.log`, `trace.jsonl`.

## 2. Optional: Claude extraction
```bash
pip install -r requirements-optional.txt
export ANTHROPIC_API_KEY=...        # your own key; never commit it
python agent.py run --claude --as-of 2026-11-25
```
Claude only proposes evidence candidates for one screened document at a time. Each candidate still goes through the validators, and a failed
call falls back to the offline rules. This path is tested with a scripted fake model only. I have not run it against the real API in this repo.

## 3. Use your own data
Export two CSVs from your CRM and call-recording tool. Never commit them.
- `deals.csv`: `deal_id, deal_name, account_name, owner, amount, currency, stage, forecast_category, close_date` plus optional rep-typed
  `metrics, economic_buyer, decision_criteria, decision_process, paper_process, identify_pain, champion, competition`.
- `notes.csv`: `doc_id, deal_id, doc_type (call_note|email|rep_note), date (YYYY-MM-DD), author_role (buyer|rep), author_name, text`.
  Call notes need speaker lines: `BUYER Name (Title): sentence` and `REP Name: sentence`. Derive `author_role` for emails from the sender
  domain, not from a field a user can edit.

HubSpot: build a Deals view with the properties above (Settings > Properties; create `meddpicc_*` text properties) and export it; export engagements or
call transcripts from your conversation-intelligence tool. Salesforce: report on Opportunities with `ForecastCategoryName` and custom
`MEDDPICC_*__c` fields and export CSV; export Gong or similar transcripts through its own export. The plan files use example property names; confirm them in
your portal or org before anyone imports a plan. A real connector would be a separate, reviewed change.

## 4. Extend with an AI coding agent
Cursor, Claude Code, Codex CLI or Grok can all work from `AGENTS.md` and `CLAUDE.md`. Good first tasks: add a paraphrase detector (tune on dev only), add a
`policy.v2.json` with your own Commit rules, or add a read-only HubSpot importer that writes the two CSVs.

## Troubleshooting
- `REFUSED: not approved`: run `show`, then `approve` with a named approver from `config/approvers.json`.
- `REFUSED: ... differs from what this run generated`: you edited a plan file. Re-run instead.
- `REFUSED: stale snapshot`: the CSVs changed after the run. Re-run and re-approve.
- `approval expired`: 24 hour limit. Approve again.
- Everything lands in Pipeline: check `rejected_evidence.jsonl` and that notes use the `BUYER Name (Title):` line format and ISO dates.
- Held-out hash error in `run_evals.py`: someone edited `evals/gold_v1/heldout`. Restore it from git or build a new versioned set.
