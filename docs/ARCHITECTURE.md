# Architecture and data contracts

```
deals.csv + notes.csv (CRM export, call notes, emails)
        |
   ingest.py ......... speaker-aware sentence segments; quoted replies and signatures dropped
        |
   untrusted.screen .. instruction-like text -> whole document quarantined (id + pattern ids only)
        |
   extract.py (rules, default)  or  claude_extract.py (optional, behind --claude)
        |  candidates {field, value, span, polarity}
   validate.py ....... verbatim span, deal/doc/date checks, value re-derived from span, strength from the document
        |  evidence {buyer_stated | rep_reported}
   assess.py ......... per field status; contradictions; freshness; Commit / Best Case / Pipeline gate
        |
   packet.py + plan.py  review_packet.md, crm_update_plan.json (+ HubSpot and Salesforce renderings), approval_queue.json
        |
   approval.py ....... named human + full SHA-256 + 24h TTL + held items named; renderings checked against manifest
        |
   executor.py + crm_mock.py ... idempotency keys, Retry-After, checkpoint, dead letter, replay, 409 stale check
        |
   audit.log ......... hash chain; names hashed (pii_hash); span text never stored, only its SHA-256
```

## Data contracts
**deals.csv**: one row per open deal. `forecast_category` is normalised (Commit, Best Case, Pipeline; Omit and Closed rows are skipped; anything else is
`UNKNOWN` and gets a review flag). Rep-typed MEDDPICC columns may be blank.

**notes.csv**: `doc_id, deal_id, doc_type, date, author_role, author_name, text`. `author_role` for emails and `BUYER`/`REP` line prefixes for call notes
decide evidence strength. A doc with an unknown deal, an invalid date or a future date is rejected, not guessed.

**Evidence record** (`evidence.jsonl`): `deal_id, doc_id, doc_date, field, value, span, polarity (pos|neg), strength, speaker, supersedes_cue, extractor`.

**Field statuses**: `satisfied, missing, rep_reported_only, stale, conflict, negated, undated, date_passed, after_close_date, not_started`.

**Plan** (`crm_update_plan.json`): `ops[]` of `update_meddpicc` (plain) and `update_forecast_category` (held). Each op has `payload`, `expect` (values seen at export time),
`evidence_refs` (doc id, date, span SHA-256), `group`, `op_key`, `idempotency_key`. `manifest.json` records the SHA-256 of the plan, both renderings, the deal export,
the notes file and the policy.

## Policy (`config/policy.json`, version policy.v1)
Commit needs economic_buyer, decision_process and paper_process, all `satisfied`. Best Case needs identify_pain plus one of economic_buyer, decision_process, champion.
Age limits in days: decision_process 30, paper_process 21, economic_buyer 45, champion 45, identify_pain 60, metrics 60, decision_criteria 60, competition 60.
Decision date must be today or later and on or before the close date. Paper process must be in_progress or complete.

## Trade-offs
- **Quarantine the whole document** on an injection hit: safe, but it can discard real evidence in the same note.
- **Buyer must say it**: a rep's recap of what the buyer said never satisfies the gate. This is stricter than many teams want, and it is deliberate. It depends on correct speaker labels.
- **Regex detectors**: transparent and testable, and weak on paraphrase (see EVALUATION.md). A model can widen recall, but only through the same validators.
- **Conflicts are never auto-resolved** unless the later note carries an explicit change cue (actually, moved, pushed, no longer). A human decides the rest.
- **Fill empty fields only**: avoids overwriting rep judgement, at the cost of leaving stale rep text in place. Differences are shown as suggestions.
- **Category changes are held items**: slower, but a forecast number should not move on a hash approval alone.
- **Two renderings** (HubSpot, Salesforce) are derived from one canonical plan so there is a single thing to approve.

## Permission boundaries
Read: two CSVs you supply. Write: only files under `outputs/<run>/`. The mock CRM is a JSON file inside that folder. No network calls unless you pass `--claude` with a key, and then only
screened document text goes out. Approval records are separate from the plan. Agents can propose; only named humans in `config/approvers.json` can approve.

## PII and secrets
Names and statements are personal data in a real deployment. The audit log stores salted hashes of speaker names and SHA-256 of spans, never the text. The packet and plan do contain quotes
(reviewers need them), so treat `outputs/` as sensitive and keep it out of git. The API key is read from the environment only. Set `DEE_PII_SALT` for real data.

## Structured traces
`trace.jsonl` has one line per stage with counts (documents, evidence kept, candidates rejected, quarantined documents, deals by category, ops, plan hash).
`audit.log` has one record per accepted evidence item, rejected candidate, quarantine, deal assessment, approval and CRM op result.
