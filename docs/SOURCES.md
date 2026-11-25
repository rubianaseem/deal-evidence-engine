# Sources and inspiration

Patterns only. No code or text copied. Checked 25 Nov 2026.

Primary documentation
- HubSpot, "Set up the forecast tool" (fetched in full): forecast categories, manual per-deal override. https://knowledge.hubspot.com/forecast/set-up-the-forecast-tool
- Salesforce Help, "Manage Opportunity Stage to Forecast Category Mappings for Pipeline Forecasts" (read as a search extract; the full page fetch timed out): users can override the mapped category on opportunities they own. https://help.salesforce.com/s/articleView?id=sales.faq_forecasts_category_mapping.htm&language=en_US&type=5
- Salesforce Help, "Collaborative Forecasting Best Practice Guide" (search extract): StageName updates and ForecastCategoryName behaviour, which is why the plan never touches stage. https://help.salesforce.com/s/articleView?id=000392673&language=en_US&type=1

Inspiration (read 25 Nov 2026; see also my inspiration log)
- zime-ai/zime-gtm-skills (MIT): transcripts audited against a rubric with a quote per finding, "the buyer must say it", absence is a result. Seen via a 9 Nov 2026 write-up by Taha Ali (https://grohub.co/resources/claude-meddpicc) and the repo listing. I adopted the two rules and enforce them in code with validators and a speaker check. Nothing reused.
- Jasen Meece resharing James Veeneman, 16 Oct 2026 (a public LinkedIn post, read only as a search-result extract; I make no claim to have covered LinkedIn): score MEDDIC against the record of the deal, "identified but never present is a flag". Same thesis; my twist is span validation, gated categories, hash-bound approval and a held-out evaluation.
- Vendor case studies (Gong and Perk, Habile Labs and iSEEit) were seen as search extracts only. Their numbers are vendor claims and are not used anywhere here.

Gaps: the X connector was not available for this build, so no direct X search was done. The absence of a public repo combining all these pieces is not proof none exists.
