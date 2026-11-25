# Revenue Operations category guide

This repo is my Revenue Operations flagship (slice 1). It sits on top of pipeline hygiene and under reporting. Navigation by layer:

| RevOps layer | Question | Where I cover it |
|---|---|---|
| Data foundations | Are accounts, owners and lifecycle stages trustworthy? | [account-hierarchy-agent](https://github.com/rubianaseem/account-hierarchy-agent), [lifecycle-stage-audit-agent](https://github.com/rubianaseem/lifecycle-stage-audit-agent), [book-of-business-transfer-agent](https://github.com/rubianaseem/book-of-business-transfer-agent) |
| Change control | Can a change to the CRM be reviewed and rolled back? | [crm-change-control-plane](https://github.com/rubianaseem/crm-change-control-plane) |
| Pipeline hygiene | Are close dates, stages and amounts sane? | [forecast-commit-hygiene-agent](https://github.com/rubianaseem/forecast-commit-hygiene-agent) |
| **Deal evidence** | **Does buyer evidence support the MEDDPICC fields and the Commit call?** | **this repo** |
| Win/loss learning | Why do deals close lost? | [closed-lost-reason-agent](https://github.com/rubianaseem/closed-lost-reason-agent) |
| Handoffs | Does the AE get context from the SDR? | [sdr-ae-handoff-brief-agent](https://github.com/rubianaseem/sdr-ae-handoff-brief-agent) |
| Routing and signals | Which account gets which rep, and why? | [revenue-signal-router](https://github.com/rubianaseem/revenue-signal-router), [inbound-lead-router-n8n-to-python](https://github.com/rubianaseem/inbound-lead-router-n8n-to-python) |
| Reporting | Can the numbers be queried and tested? | [gtm-sql-revops-queries](https://github.com/rubianaseem/gtm-sql-revops-queries), [gtm-dbt-revenue-models](https://github.com/rubianaseem/gtm-dbt-revenue-models) |
| Evaluation | How do I measure an agent honestly? | [gtm-agent-eval-harness](https://github.com/rubianaseem/gtm-agent-eval-harness) |

Slice 2 of this flagship (planned, not built) adds pipeline-level inspection across deals and a calibration check of evidence-supported Commit against what actually closed.
