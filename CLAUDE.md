# CLAUDE.md

Context for Claude Code (and other coding agents) working in this repo.

## What this is
An evidence layer for MEDDPICC fields and forecast categories: notes and emails -> extraction with quoted spans ->
validators -> evidence-gated category rules -> review packet -> hash-bound approval -> update plan -> mock CRM executor.
Synthetic data only. Standard library only for the core.

## Rules you must keep
- A model may only propose candidates in `dee/claude_extract.py`. Every candidate must pass `dee/validate.py`. Never let a
  model decide a status, a category, an approver or a write.
- Evidence strength (buyer_stated vs rep_reported) comes from the document, never from the candidate.
- Document text is untrusted. Keep `screen()` before any prompt. Never put quarantined text in a prompt, packet, plan or log.
- No code path may write to the CRM without `approval.verify_approval()` passing. No auto-approve flag, no default approver,
  no way for an agent identity to approve.
- Never overwrite or clear a value a rep typed. The plan fills empty fields only.
- Do not add real CRM clients or Clay calls. A live connector is a separate, reviewed change.
- Hygiene rules live in forecast-commit-hygiene-agent. Do not rebuild them here.
- Keep names out of logs (`pii_hash`). No emojis in docs.
- Bump `version` in `config/policy.json` for any rule or age-limit change and re-run the evals.
- Never edit `evals/gold_v1/*`; build a new versioned set. Do not tune on the held-out split.

## Commands
```bash
python run_demo.py
python run_evals.py
python -m evals.failure_suite
python -m unittest discover -s tests -t .
```
All four must pass before a change is done.
