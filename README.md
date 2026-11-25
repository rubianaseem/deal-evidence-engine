# Deal Evidence Engine

**Checks MEDDPICC fields and Commit calls against what the buyer actually said in call notes and emails. Every claim carries a verbatim quote that is checked by code, a category is only proposed when the evidence supports it, and nothing reaches the (mock) CRM until a named person approves the plan's SHA-256.**

Built by Rubia Naseem, GTM Engineer (12+ yrs CRM/RevOps, HubSpot & Salesforce).

Status: implemented and tested locally on synthetic data (slice 1 of my Revenue Operations flagship). The CRM is a local mock and the Claude path is tested with a scripted fake model only.

## The problem

MEDDPICC fields and Commit calls are typed from memory. The evidence lives in call notes and emails, so forecast review turns into opinion. Both platforms let a rep set the category by hand:

- HubSpot: "Users can also manually update the forecast category for an individual deal from the deal record." ([KB: Set up the forecast tool](https://knowledge.hubspot.com/forecast/set-up-the-forecast-tool))
- Salesforce: "Users can edit the Forecast Category field on opportunities that they own, overriding the default stage-to-category mapping." ([Help: stage to forecast category mappings](https://help.salesforce.com/s/articleView?id=sales.faq_forecasts_category_mapping.htm&language=en_US&type=5), read as a search extract)

[forecast-commit-hygiene-agent](https://github.com/rubianaseem/forecast-commit-hygiene-agent) already covers stale dates, stage skips and amount edits. This repo covers the other half: is there buyer evidence behind the call?

## What it does

- **Extracts evidence offline** for the eight MEDDPICC fields: a verbatim sentence plus a value, labelled buyer-stated or rep-reported. The buyer must say it.
- **Validates every item in code**: the span exists word for word in the source, the document is not future-dated, and the value is re-derived from the span. Optional Claude output gets the same checks.
- **Detects contradictions and staleness**: two economic buyers, paper process going backwards, a later "I'm not the approver", a decision date after close, evidence past its age limit.
- **Gates the category**: Commit needs economic buyer, a dated decision process and paper process, all buyer-stated and fresh. Best Case and Pipeline follow. Changes are proposals for a manager.
- **Writes a review packet and update plan as files** (canonical, HubSpot and Salesforce renderings). It fills empty fields only.
- **Runs approved plans against a mock CRM** with idempotent keys, Retry-After, crash resume and a hash-chained audit.

## Where each step runs

1. **GitHub** stores the code, configs, synthetic samples and the gold set.
2. **Your terminal** (Mac Terminal or the Cursor terminal) runs `agent.py` on a deals CSV and a notes CSV. No API key needed.
3. **Optional Claude** runs through the same code to propose evidence, and only when you pass `--claude` with a key. Anything that fails validation is dropped.
4. **You review** `review_packet.md`, then approve the plan hash. You then update HubSpot or Salesforce yourself or through your own reviewed tooling.
5. **The agent performs no real CRM writes.** "Execute" writes to a local JSON file. No CRM API calls, no sends, no Clay.

## Guardrails and human in the loop

- Execution needs a named human in `config/approvers.json` approving the full SHA-256 of `crm_update_plan.json`. Agent identities are refused, approvals expire after 24 hours, edits to any plan file void them, and a changed export is refused as a stale snapshot. No auto-approve flag.
- Forecast category changes are held. A manager-level approver must name each one.
- Call text is untrusted: a document with instruction-like text is quarantined whole.
- Rep-typed values are never overwritten or cleared. Differences appear as suggestions.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
python run_demo.py
python agent.py run --deals sample_deals.csv --notes sample_notes.csv --out outputs/run --as-of 2026-11-25
python run_evals.py && python -m evals.failure_suite && python -m unittest discover -s tests -t .
```

## Example output (`python run_demo.py`, excerpt)

```
deal     rep called -> evidence supports   change
D-9001  Commit     -> Commit     none
D-9002  Commit     -> Best Case  downgrade
D-9003  Commit     -> Pipeline   downgrade
D-9004  Pipeline   -> Commit     upgrade_suggestion
D-9006  Commit     -> Pipeline   downgrade
D-9008  UNKNOWN    -> Pipeline   review_unknown_category
quarantined docs: ['DOC-9007-1']
execute before approval -> not approved: run `python agent.py approve` ...
agent approval -> 'claude' is an agent, model or service identity and can never approve
execute (local mock CRM): {'applied': 7, 'held_not_approved': 4, 'dead_lettered': 0, ...}
duplicate CRM effects: 0
```

## Results (synthetic gold set, `python run_evals.py`)

82 deals, 234 documents. The held-out split (24 deals) is hashed in `evals/gold_v1.sha256`. Held-out: evidence precision 63/64 vs 68/176 for the keyword baseline, but recall 63/84 vs 68/84, so it does not beat the baseline on raw recall; every miss is a paraphrase my rules do not know. Category agreement with gold 15/24 vs 8/24. Unsupported claims 0. One screen-evading injected sentence was accepted as evidence and produced a wrong Commit. Dev (tuned on) is 199/199 both ways. I wrote the data and the rules, so these are regression checks, not field accuracy. Details: [docs/EVALUATION.md](docs/EVALUATION.md).

## More

[SETUP.md](SETUP.md) | [Architecture and data contracts](docs/ARCHITECTURE.md) | [Evaluation](docs/EVALUATION.md) | [Details, costs, stack swaps](docs/DETAILS.md) | [Revenue Operations category guide](docs/CATEGORY_GUIDE.md) | [Sources](docs/SOURCES.md)

Builds on my repos: [forecast-commit-hygiene-agent](https://github.com/rubianaseem/forecast-commit-hygiene-agent) (hygiene rules, not rebuilt here), [revenue-signal-router](https://github.com/rubianaseem/revenue-signal-router) (approval, audit, screen, executor patterns adapted), [gtm-agent-eval-harness](https://github.com/rubianaseem/gtm-agent-eval-harness) (eval approach), [crm-change-control-plane](https://github.com/rubianaseem/crm-change-control-plane)
