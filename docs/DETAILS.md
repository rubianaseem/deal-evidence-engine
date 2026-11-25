# Details: costs, stack swaps, customising, production gaps

## API cost assumptions (no account or billing access)
I have no access to any Anthropic, CRM or cloud billing data and have not looked at any. The default path makes no API calls, so its marginal cost is zero.
With `--claude`, one call per document that passes the screen. Rough sizing you can redo yourself:

```
calls            = documents that are not quarantined (about 3 per open deal in the sample)
input tokens     ~ calls x (prompt overhead ~300 + document tokens, 300 to 1,500 for a call note or email thread)
output tokens    ~ calls x 100 to 400 (a JSON list of a few candidates)
cost per run     = input_tokens x price_in + output_tokens x price_out
```
Example: 500 open deals x 3 documents = 1,500 calls, at about 1,000 input and 250 output tokens each is about 1.5M input and 375k output tokens per full run. Look up the current per-million-token prices
for your chosen model on the provider's pricing page and multiply. Re-run only documents whose hash changed to keep repeat runs near zero. These are estimates, not measurements; I have not run the real API in this repo.

## Stack-swap table
| Piece | Here | Swap for |
|---|---|---|
| Inputs | CSV files | HubSpot CRM API, Salesforce bulk export, Snowflake or BigQuery views |
| Notes source | CSV of notes and emails | Gong, Chorus, Fireflies, Gmail or Outlook exports, HubSpot engagements |
| Extractor | regex rules | an LLM behind the same validators (`claude_extract.py` shows the shape), or a fine-tuned classifier |
| Policy | `config/policy.json` | your own Commit rules per segment or pipeline |
| Approval | CLI plus hash | Slack or Teams approval card that carries the plan hash, a ticket system |
| Executor | local mock | HubSpot batch update, Salesforce composite API, n8n workflow with the same idempotency keys |
| Audit | hash-chained JSONL | append-only table, WORM bucket, SIEM |
| Scheduling | manual | cron, GitHub Actions, n8n, Airflow before the forecast call |

## Customise for your stack
- **Fields**: rename `meddpicc_*` properties in `dee/plan.py`; HubSpot internal names and Salesforce API names differ from the examples.
- **Rules**: edit `config/policy.json` (required fields, age limits, competitors). Bump the version and re-run the evals.
- **Methodology**: MEDDIC, BANT or your own: change `meddpicc_fields`, add detectors in `dee/extract.py`, add tests.
- **Segments**: SMB may need only economic buyer plus a dated next step; enterprise may add security review. Keep one policy file per segment.
- **Categories**: if you use Most Likely or Omitted, extend `category_rank` and the HubSpot and Salesforce value maps in `dee/plan.py`.

## Production gaps (read before you rely on it)
| Capability | Status |
|---|---|
| Offline extraction, validators, gate, packet, plan files | implemented, tested locally on synthetic data |
| Hash-bound approval, idempotent mock executor, crash resume, hash-chained audit | implemented, tested locally |
| Claude extraction behind validators | implemented, tested with a scripted fake model only |
| HubSpot or Salesforce reads and writes | proposed, not built; the plan renderings are examples |
| Real transcripts, speaker diarisation, many buyers per deal | not tested |
| Paraphrase coverage on real notes | not measured; held-out recall on my own paraphrases is 63/84 |
| Production use at any company | not claimed |

Also missing for production: authentication and per-user permissions on the approval step, a secret manager, retention rules for notes, a lawful-basis and data-processing review for call content, per-segment policies, monitoring of rejection rates,
a human override path for wrongly quarantined documents, and a way to send quoted evidence back into the CRM timeline. Custom property names and picklist values must be checked against your portal or org.
