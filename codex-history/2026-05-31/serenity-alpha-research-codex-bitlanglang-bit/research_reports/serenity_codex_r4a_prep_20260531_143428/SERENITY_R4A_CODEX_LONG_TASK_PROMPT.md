# SERENITY R4-A CODEX LONG TASK PROMPT

You are Codex executing a long research-only task for Serenity Alpha Research.

## Project Boundaries
- This project is independent from any crypto, trading-bot, or other project context.
- Use only public research sources: SEC/EDGAR, company IR, company press releases, exchange filing links, and reputable public news.
- Do not log in, do not access brokerage accounts, do not access orders, holdings, balances, cookies, private APIs, API keys, secrets, SSH keys, or .env files.
- Do not create schedulers, cron jobs, services, monitors, alerts, or automated trading workflows.

## Hard Prohibitions
- No buy recommendations.
- No sell recommendations.
- No target prices.
- No position sizing.
- No entry timing.
- No trade plans.
- No current buy list.
- Do not treat social-media heat as positive evidence.
- Do not treat historical stock gains as T0 evidence.
- Do not treat demo, sample, evaluation, pilot, or MoU as production revenue.

## Candidate Universe
Priority candidates: TSEM, ONTO, CAMT, FORM, MTSI, FN, AEHR.
Benchmark / risk comparison: COHR, LITE, AAOI, AXTI.
Blocked/no-go caution only: POET, LWLG. Do not upgrade these.

## Per-Ticker Check Template
For each ticker, produce:
- current R3 classification
- public-source evidence table with source date and URL/reference
- latest filing / latest earnings release checked
- business segment and suspected chokepoint
- production revenue evidence
- customer concentration / customer validation evidence
- revenue quality and margin/cash conversion notes
- balance sheet, dilution, debt, and going-concern audit
- governance/accounting audit
- China/geopolitical exposure audit
- valuation crowding risk audit without target price
- shareholder capture assessment
- STOP gate results
- Scorecard v1.2 fields
- R5 underwriting readiness status

## STOP Gate Audit
Use these gates exactly:
- STOP-REV0
- STOP-DEMO-NOT-PRODUCTION
- STOP-CUSTOMER-UNCLEAR
- STOP-DILUTION
- STOP-SOCIAL-HYPE
- STOP-CUSTOMER-CONCENTRATION
- STOP-CHINA-GEO
- STOP-VALUATION-OVERHEAT
- STOP-GOING-CONCERN
- STOP-SHAREHOLDER-NOT-CAPTURED
- STOP-GOVERNANCE-ACCOUNTING
- STOP-LINKAGE-WEAK

For each gate, report: definition, evidence checked, status, citations, consequence.

## Scorecard v1.2
opportunity_score_fields:
- chokepoint_relevance
- ai_datacenter_or_semiconductor_infrastructure_linkage
- scarcity_or_substitutability
- cycle_durability
- operating_leverage_without_target_price
- right_tail_research_optionality

evidence_score_fields:
- production_revenue_evidence
- customer_validation_quality
- filing_disclosure_quality
- backlog_or_order_visibility
- technology_to_revenue_traceability
- public_source_recency

survivability_shareholder_capture_fields:
- balance_sheet_resilience
- gross_margin_and_cash_conversion
- dilution_control
- governance_and_accounting_quality
- shareholder_capture_mechanism
- geopolitical_and_supply_chain_resilience

penalty_fields:
- demo_not_production_penalty
- social_hype_penalty
- customer_concentration_penalty
- valuation_overheat_penalty
- dilution_or_going_concern_penalty
- weak_linkage_penalty

## Pairwise Comparison
Compare priority candidates pairwise on:
- chokepoint directness
- production revenue evidence
- customer validation
- survivability / shareholder capture
- hard STOP risk
- valuation crowding risk

## Final Ranking
Produce a research-only ranking, not a buy list. Explicitly label: RESEARCH_PRIORITY_RANKING_ONLY. Include uncertainty and unresolved evidence gaps.

## Final ZIP Output Rule
Write all outputs under a timestamped `research_reports/serenity_r4a_deep_dive_<timestamp>/` directory. Generate MANIFEST.md, SHA256SUMS.txt, SELF_CHECK.md, and final ZIP. The final reply must be a short summary with output directory, ZIP path, ZIP sha256, generated file count, safety confirmation, and blocked items.
