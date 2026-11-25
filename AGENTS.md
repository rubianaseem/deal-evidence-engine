# AGENTS.md

Instructions for coding agents (Codex CLI, Cursor, Claude Code, Grok and others).

- Setup: Python 3.10+, no dependencies for the core. `python -m venv .venv && source .venv/bin/activate`.
- Layout: `dee/` engine, `config/` policy and approvers, `evals/` gold set, baseline, scripted model and failure suite, `tests/`.
- Test before you finish: `python run_demo.py && python run_evals.py && python -m evals.failure_suite && python -m unittest discover -s tests -t .`
- Safety rules are in CLAUDE.md and apply to every agent. In short: validators on every model output, quoted spans must be
  verbatim, buyer must say it, no CRM write without a hash-bound human approval, no overwriting rep-typed values, no tuning on held-out.
- Adding a detector: add it to `dee/extract.py`, add unit tests, tune only on `evals/gold_v1/dev`, bump the policy version if rules changed,
  and report held-out numbers as they come out.
- Do not put real customer notes, emails or CRM exports in this repo. Use files outside the repo and keep `outputs/` ignored.
