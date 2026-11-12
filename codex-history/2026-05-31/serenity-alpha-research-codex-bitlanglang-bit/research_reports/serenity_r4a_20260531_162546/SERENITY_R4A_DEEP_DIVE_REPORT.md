# SERENITY R4-A DEEP DIVE REPORT

Scope: research-only optical / silicon photonics / optical manufacturing / semiconductor test deep-dive. This report does not contain buy/sell recommendations, target prices, position sizing, entry timing, or trade plans.

## Executive Summary

- R5 underwriting candidates: ONTO, CAMT, FORM.
- R4 priority research: TSEM, MTSI, FN.
- R4 backlog: AEHR.
- Benchmark-only: COHR, LITE, AAOI, AXTI.
- Blocked/no-go caution references: POET, LWLG; not upgraded.
- Public source status: YES. SEC/EDGAR was used as the primary automated evidence source.

## Context Verification

- AGENTS.md: exists
- SERENITY_PROJECT_STATE.md: exists
- SERENITY_SCORECARD_V1_2.md: exists
- SERENITY_STOP_GATES.md: exists
- SERENITY_R3_CLASSIFICATION.csv: exists
- SERENITY_R4A_SCOPE.md: exists
- SERENITY_R1_R2_R3_SUMMARY.md: exists

## Ticker-by-Ticker Cards

### TSEM - Tower Semiconductor Ltd.

#### Basic Profile
- ticker: TSEM
- company: Tower Semiconductor Ltd.
- segment: specialty foundry / silicon photonics enablement
- market_cap_bucket: mid-cap / approximate
- core_business: specialty analog foundry manufacturing for RF, power, sensors, mixed-signal and related process platforms
- why_in_R4A: Potential specialty foundry exposure to silicon photonics and optical I/O manufacturing
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2026-04-30 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/928876/000117891326002318/zk2635149.htm | SEC 20-F ZK2635149 |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-21 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/928876/000117891326002871/zk2635394.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-21 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/928876/000117891326002871/zk2635394.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2026-04-30 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/928876/000117891326002318/zk2635149.htm | Revenue fact: 1.57B USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:Revenues) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2026-04-30 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/928876/000117891326002318/zk2635149.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-04-30 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0000928876.json | Revenue: 1.57B USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:Revenues); Gross profit: 363.9M USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:GrossProfit); Operating cash flow: 395.5M USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: specialty foundry manufacturing and customer qualification for silicon photonics or optical I/O process flows
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 1.57B USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:Revenues)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 395.5M USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 1.57B USD (20-F, period end 2025-12-31, filed 2026-04-30, concept us-gaap:Revenues). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | UNCLEAR | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | UNCLEAR | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Unresolved; must be cleared before R5 underwriting confidence can rise. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 72
- Evidence Score: 54
- Survivability / Shareholder Capture Score: 68
- Penalty Score: 28
- final_research_score: 63
- confidence_level: MEDIUM
- R4 classification: R4_PRIORITY_RESEARCH

#### Red Team
- if_thesis_wrong: Most likely failure is weak linkage between specialty foundry revenue and silicon-photonics thesis revenue.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Real specialty foundry revenue exists, but silicon-photonics thesis revenue is not cleanly separable in the automated public-source pass.
- next action: Continue R4 priority/backlog evidence clearing

### ONTO - Onto Innovation Inc.

#### Basic Profile
- ticker: ONTO
- company: Onto Innovation Inc.
- segment: semiconductor metrology / process control
- market_cap_bucket: mid-cap / approximate
- core_business: process control, inspection, metrology and lithography systems for semiconductor manufacturing
- why_in_R4A: Metrology and process-control exposure to advanced packaging and optical manufacturing quality
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2026-02-24 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/704532/000119312526066937/onto-20260103.htm | SEC 10-K 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-21 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/704532/000119312526234610/d17904d8k.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-21 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/704532/000119312526234610/d17904d8k.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2026-02-24 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/704532/000119312526066937/onto-20260103.htm | Revenue fact: 291.9M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2026-02-24 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/704532/000119312526066937/onto-20260103.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-05 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0000704532.json | Revenue: 291.9M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax); Gross profit: 146.4M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:GrossProfit); Operating cash flow: 26.3M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: advanced packaging, HBM and heterogeneous integration process control
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 291.9M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 26.3M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 291.9M USD (10-Q, period end 2026-03-31, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | NO | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Not triggered in this public-source pass. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | NO | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Not triggered in this public-source pass. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 84
- Evidence Score: 76
- Survivability / Shareholder Capture Score: 78
- Penalty Score: 22
- final_research_score: 79
- confidence_level: MEDIUM_HIGH
- R4 classification: R5_THESIS_UNDERWRITING_CANDIDATE

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Direct metrology/process-control exposure to advanced packaging and AI infrastructure manufacturing quality is stronger and more evidence-backed than most peers.
- next action: R5 underwriting memo with full filing/IR citations

### CAMT - Camtek Ltd.

#### Basic Profile
- ticker: CAMT
- company: Camtek Ltd.
- segment: inspection / metrology
- market_cap_bucket: mid-cap / approximate
- core_business: inspection and metrology systems for semiconductor manufacturing and advanced packaging
- why_in_R4A: Inspection and metrology exposure to advanced packaging and high-complexity manufacturing
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2026-03-19 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1109138/000117891326001561/zk2634678.htm | SEC 20-F 20-F |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-12 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1109138/000117891326002569/zk2635285.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-12 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1109138/000117891326002569/zk2635285.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2026-03-19 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1109138/000117891326001561/zk2634678.htm | Revenue fact: 496.1M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:Revenues) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2026-03-19 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1109138/000117891326001561/zk2634678.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-03-19 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001109138.json | Revenue: 496.1M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:Revenues); Gross profit: 250.3M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:GrossProfit); Operating cash flow: 141.9M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: inspection/metrology for high-density advanced packaging and complex production ramps
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 496.1M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:Revenues)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 141.9M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 496.1M USD (20-F, period end 2025-12-31, filed 2026-03-19, concept us-gaap:Revenues). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | UNCLEAR | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | NO | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Not triggered in this public-source pass. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 82
- Evidence Score: 72
- Survivability / Shareholder Capture Score: 72
- Penalty Score: 26
- final_research_score: 75
- confidence_level: MEDIUM_HIGH
- R4 classification: R5_THESIS_UNDERWRITING_CANDIDATE

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Inspection/metrology linkage to advanced packaging is direct; remaining issue is concentration/geography and durability of production demand.
- next action: R5 underwriting memo with full filing/IR citations

### FORM - FormFactor, Inc.

#### Basic Profile
- ticker: FORM
- company: FormFactor, Inc.
- segment: probe cards / test interface
- market_cap_bucket: mid-cap / approximate
- core_business: probe cards, analytical probes and test interfaces for wafer-level semiconductor test
- why_in_R4A: Probe-card and test-interface exposure to advanced packaging and higher test complexity
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2026-02-20 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1039399/000103939926000009/form-20251227.htm | SEC 10-K 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-19 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1039399/000103939926000025/form-20260515.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-19 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1039399/000103939926000025/form-20260515.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2026-02-20 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1039399/000103939926000009/form-20251227.htm | Revenue fact: 226.1M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2026-02-20 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1039399/000103939926000009/form-20251227.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-05 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001039399.json | Revenue: 226.1M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax); Gross profit: 86.8M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:GrossProfit); Operating cash flow: 45.0M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: probe-card and wafer-test interface complexity for HBM, chiplets and advanced nodes
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 226.1M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 45.0M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 226.1M USD (10-Q, period end 2026-03-28, filed 2026-05-05, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | NO | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Not triggered in this public-source pass. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | NO | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Not triggered in this public-source pass. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 80
- Evidence Score: 78
- Survivability / Shareholder Capture Score: 74
- Penalty Score: 24
- final_research_score: 77
- confidence_level: MEDIUM_HIGH
- R4 classification: R5_THESIS_UNDERWRITING_CANDIDATE

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Wafer-test/probe-card chokepoint is narrow, production-based, and tied to advanced packaging/test complexity.
- next action: R5 underwriting memo with full filing/IR citations

### MTSI - MACOM Technology Solutions Holdings, Inc.

#### Basic Profile
- ticker: MTSI
- company: MACOM Technology Solutions Holdings, Inc.
- segment: RF / microwave / optical semiconductors
- market_cap_bucket: mid-cap to large-cap / approximate
- core_business: high-performance analog, RF, microwave, millimeterwave and optical semiconductor products
- why_in_R4A: Optical and high-frequency component exposure to datacenter and connectivity bottlenecks
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2025-11-14 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1493594/000149359425000054/mtsi-20251003.htm | SEC 10-K 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-07 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1493594/000149359426000024/mtsi-20260507.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-07 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1493594/000149359426000024/mtsi-20260507.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2025-11-14 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1493594/000149359425000054/mtsi-20251003.htm | Revenue fact: 560.6M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:Revenues) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2025-11-14 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1493594/000149359425000054/mtsi-20251003.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-07 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001493594.json | Revenue: 560.6M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:Revenues); Gross profit: 316.2M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:GrossProfit); Operating cash flow: 121.6M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: optical and high-frequency component supply into datacenter, telecom and connectivity systems
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 560.6M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:Revenues)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 121.6M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 560.6M USD (10-Q, period end 2026-04-03, filed 2026-05-07, concept us-gaap:Revenues). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | NO | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Not triggered in this public-source pass. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | UNCLEAR | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Unresolved; must be cleared before R5 underwriting confidence can rise. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 70
- Evidence Score: 60
- Survivability / Shareholder Capture Score: 70
- Penalty Score: 30
- final_research_score: 65
- confidence_level: MEDIUM
- R4 classification: R4_PRIORITY_RESEARCH

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Optical/high-frequency component exposure is real, but AI optical thesis revenue and customer evidence need sharper separation.
- next action: Continue R4 priority/backlog evidence clearing

### FN - Fabrinet

#### Basic Profile
- ticker: FN
- company: Fabrinet
- segment: optical manufacturing services
- market_cap_bucket: mid-cap / approximate
- core_business: advanced optical, electro-mechanical and electronic manufacturing services for complex products
- why_in_R4A: Precision optical manufacturing services with possible production-scale customer programs
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2025-08-19 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1408710/000140871025000039/fn-20250627.htm | SEC 10-K 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-04 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1408710/000140871026000014/fn-20260504.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-04 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1408710/000140871026000014/fn-20260504.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2025-08-19 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1408710/000140871025000039/fn-20250627.htm | Revenue fact: 3.33B USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:Revenues) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2025-08-19 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1408710/000140871025000039/fn-20250627.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-05 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001408710.json | Revenue: 3.33B USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:Revenues); Gross profit: 398.5M USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:GrossProfit); Operating cash flow: 201.8M USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: precision optical manufacturing capacity and production execution for datacenter/telecom programs
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 3.33B USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:Revenues)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 201.8M USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 3.33B USD (10-Q, period end 2026-03-27, filed 2026-05-05, concept us-gaap:Revenues). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | YES | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Triggered or materially risked; cap/penalize classification until resolved. |
| STOP-CHINA-GEO | NO | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Not triggered in this public-source pass. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | NO | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Not triggered in this public-source pass. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 73
- Evidence Score: 68
- Survivability / Shareholder Capture Score: 63
- Penalty Score: 34
- final_research_score: 66
- confidence_level: MEDIUM
- R4 classification: R4_PRIORITY_RESEARCH

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: EMS production may be real while margins and customer bargaining power limit shareholder capture.

- main reason: Optical manufacturing revenue is production-like, but EMS economics and customer concentration limit shareholder-capture clarity.
- next action: Continue R4 priority/backlog evidence clearing

### AEHR - Aehr Test Systems

#### Basic Profile
- ticker: AEHR
- company: Aehr Test Systems
- segment: wafer-level test / burn-in
- market_cap_bucket: small-cap / approximate
- core_business: wafer-level test and burn-in systems for reliability-critical semiconductor devices
- why_in_R4A: Wafer-level test and burn-in exposure to high-reliability semiconductor production
- R3 classification: R4-A priority

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2025-07-28 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1040470/000165495425008553/aehr_10k.htm | SEC 10-K FORM 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-04-20 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1040470/000165495426003746/aehr_8k.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-04-20 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1040470/000165495426003746/aehr_8k.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2025-07-28 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1040470/000165495425008553/aehr_10k.htm | Revenue fact: 31.2M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2025-07-28 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1040470/000165495425008553/aehr_10k.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-04-08 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001040470.json | Revenue: 31.2M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax); Gross profit: 9.6M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:GrossProfit); Operating cash flow: -5.1M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: burn-in and wafer-level reliability test for high-power or high-reliability devices
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 31.2M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: -5.1M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 31.2M USD (10-Q, period end 2026-02-27, filed 2026-04-08, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CUSTOMER-UNCLEAR | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-DILUTION | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | YES | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Triggered or materially risked; cap/penalize classification until resolved. |
| STOP-CHINA-GEO | NO | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Not triggered in this public-source pass. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | UNCLEAR | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Unresolved; must be cleared before R5 underwriting confidence can rise. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 67
- Evidence Score: 55
- Survivability / Shareholder Capture Score: 52
- Penalty Score: 42
- final_research_score: 57
- confidence_level: MEDIUM_LOW
- R4 classification: R4_RESEARCH_BACKLOG

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: Customer concentration appears central; it must be cleared before any R5 underwriting.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Test bottleneck can be narrow, but revenue concentration and unclear AI/optical translation keep it below R5 readiness.
- next action: Continue R4 priority/backlog evidence clearing

### COHR - Coherent Corp.

#### Basic Profile
- ticker: COHR
- company: Coherent Corp.
- segment: optical materials / components
- market_cap_bucket: large-cap / approximate
- core_business: materials, networking, lasers, photonics and optical components
- why_in_R4A: Benchmark for optical scale cyclicality debt and execution risk
- R3 classification: R4-A benchmark / risk comparison

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2025-08-15 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/820318/000082031825000014/iivi-20250630.htm | SEC 10-K 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-06 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/820318/000119312526208972/d57080d8k.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-06 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/820318/000119312526208972/d57080d8k.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2025-08-15 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/820318/000082031825000014/iivi-20250630.htm | Revenue fact: 5.07B USD (10-Q, period end 2026-03-31, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2025-08-15 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/820318/000082031825000014/iivi-20250630.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-06 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0000820318.json | Revenue: 5.07B USD (10-Q, period end 2026-03-31, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax); Gross profit: not extracted; Operating cash flow: 10.1M USD (10-Q, period end 2026-03-31, filed 2026-05-06, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: scaled optical materials, lasers and transceiver/component production
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 5.07B USD (10-Q, period end 2026-03-31, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 10.1M USD (10-Q, period end 2026-03-31, filed 2026-05-06, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 5.07B USD (10-Q, period end 2026-03-31, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | UNCLEAR | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | NO | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Not triggered in this public-source pass. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 76
- Evidence Score: 76
- Survivability / Shareholder Capture Score: 56
- Penalty Score: 36
- final_research_score: 67
- confidence_level: MEDIUM
- R4 classification: BENCHMARK_ONLY

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Useful scaled photonics benchmark; leverage/integration/cycle issues make it a risk comparator rather than Serenity-style edge.
- next action: Keep as benchmark/risk comparator

### LITE - Lumentum Holdings Inc.

#### Basic Profile
- ticker: LITE
- company: Lumentum Holdings Inc.
- segment: optical components / photonics
- market_cap_bucket: mid-cap / approximate
- core_business: optical and photonic products for cloud, networking, telecom and industrial end markets
- why_in_R4A: Benchmark for optical component demand recovery and customer concentration
- R3 classification: R4-A benchmark / risk comparison

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2025-08-19 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1633978/000162828025040830/lite-20250628.htm | SEC 10-K 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-05 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1633978/000162828026030530/lite-20260505.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-05 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1633978/000162828026030530/lite-20260505.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2025-08-19 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1633978/000162828025040830/lite-20250628.htm | Revenue fact: 2.01B USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2025-08-19 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1633978/000162828025040830/lite-20250628.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-06 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001633978.json | Revenue: 2.01B USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax); Gross profit: 778.6M USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:GrossProfit); Operating cash flow: 388.4M USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: optical component supply and cloud/datacenter demand recovery
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 2.01B USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: 388.4M USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 2.01B USD (10-Q, period end 2026-03-28, filed 2026-05-06, concept us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | UNCLEAR | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | NO | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Not triggered in this public-source pass. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 72
- Evidence Score: 68
- Survivability / Shareholder Capture Score: 60
- Penalty Score: 34
- final_research_score: 66
- confidence_level: MEDIUM
- R4 classification: BENCHMARK_ONLY

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Good optical component benchmark for cloud/telecom cycles, customer concentration and margin recovery.
- next action: Keep as benchmark/risk comparator

### AAOI - Applied Optoelectronics, Inc.

#### Basic Profile
- ticker: AAOI
- company: Applied Optoelectronics, Inc.
- segment: optical modules
- market_cap_bucket: small-cap to mid-cap / approximate
- core_business: fiber-optic networking products and optical modules for internet datacenter, CATV and telecom markets
- why_in_R4A: Benchmark for optical module revenue volatility and customer concentration
- R3 classification: R4-A benchmark / risk comparison

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2026-02-26 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1158114/000143774926005875/aaoi20251231_10k.htm | SEC 10-K FORM 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-14 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1158114/000110465926061168/tm2614157d2_8k.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-14 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1158114/000110465926061168/tm2614157d2_8k.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2026-02-26 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1158114/000143774926005875/aaoi20251231_10k.htm | Revenue fact: 151.1M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2026-02-26 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1158114/000143774926005875/aaoi20251231_10k.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-07 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001158114.json | Revenue: 151.1M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax); Gross profit: 43.9M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:GrossProfit); Operating cash flow: -85.4M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: datacenter optical module production and customer-specific demand ramps
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 151.1M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: -85.4M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 151.1M USD (10-Q, period end 2026-03-31, filed 2026-05-07, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | YES | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Triggered or materially risked; cap/penalize classification until resolved. |
| STOP-CHINA-GEO | UNCLEAR | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-VALUATION-OVERHEAT | UNCLEAR | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-LINKAGE-WEAK | UNCLEAR | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Unresolved; must be cleared before R5 underwriting confidence can rise. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 68
- Evidence Score: 58
- Survivability / Shareholder Capture Score: 50
- Penalty Score: 46
- final_research_score: 54
- confidence_level: MEDIUM_LOW
- R4 classification: BENCHMARK_ONLY

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: Requires full 10-K/20-F risk-factor review before underwriting.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: Datacenter optical exposure is relevant, but concentration, volatility and crowding risk make it a false-positive comparator.
- next action: Keep as benchmark/risk comparator

### AXTI - AXT, Inc.

#### Basic Profile
- ticker: AXTI
- company: AXT, Inc.
- segment: compound semiconductor substrates
- market_cap_bucket: small-cap / approximate
- core_business: compound semiconductor substrates including InP, GaAs and germanium substrates
- why_in_R4A: Benchmark for substrate exposure and China/geopolitical sensitivity
- R3 classification: R4-A benchmark / risk comparison

#### Latest Evidence Pack

| category | source_type | source_date | confidence | supports | source_reference | note |
|---|---|---:|---|---|---|---|
| latest 10-K / 10-Q / 20-F | SEC annual/quarterly filing | 2026-03-17 | HIGH | Evidence / Survivability | https://www.sec.gov/Archives/edgar/data/1051627/000143774926008612/axti20251231_10k.htm | SEC 10-K FORM 10-K |
| latest earnings release | SEC 8-K/6-K current report proxy | 2026-05-15 | MEDIUM | Evidence / Confirmation | https://www.sec.gov/Archives/edgar/data/1051627/000121390026057122/ea0290937-8k_axt.htm | Current-report proxy; inspect exhibits/company IR for exact earnings release language. |
| investor presentation | company IR / SEC exhibit |  | LOW | Limitation | not located in automated SEC pass | Needs manual company IR review before R5 underwriting. |
| customer / partner announcement | SEC filings / company releases | 2026-05-15 | MEDIUM_LOW | Evidence / Penalty | https://www.sec.gov/Archives/edgar/data/1051627/000121390026057122/ea0290937-8k_axt.htm | Automated pass did not validate named customer logos beyond filings. |
| product / shipment / production evidence | SEC filings and revenue facts | 2026-03-17 | MEDIUM | Evidence | https://www.sec.gov/Archives/edgar/data/1051627/000143774926008612/axti20251231_10k.htm | Revenue fact: 26.9M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax) |
| backlog / order / LTA / prepayment evidence | SEC filings | 2026-03-17 | LOW | Evidence / Limitation | https://www.sec.gov/Archives/edgar/data/1051627/000143774926008612/axti20251231_10k.htm | Automated SEC pass did not fully extract backlog, LTA, prepayment, take-or-pay, or cancellability language. |
| segment revenue / gross margin evidence | SEC XBRL companyfacts | 2026-05-14 | MEDIUM | Evidence / Survivability | https://data.sec.gov/api/xbrl/companyfacts/CIK0001051627.json | Revenue: 26.9M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax); Gross profit: 8.0M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:GrossProfit); Operating cash flow: -11.7M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:NetCashProvidedByUsedInOperatingActivities) |
| media / analyst evidence | public media / analyst |  | LOW | Limitation | not used for positive scoring | No media/analyst evidence was used as positive evidence in this automated pass. |
| social media evidence | social media |  | N/A | Penalty only | not used | Social-media heat is crowding risk only and contributes no positive evidence. |

#### Chokepoint Thesis
- chain node: InP and compound substrate material supply for photonics and RF applications
- bottleneck type: manufacturing/test/process-control/customer-qualification/material depending on ticker; see main_chokepoint in ranking.
- narrow/scarce/hard to replace: YES for ONTO/CAMT/FORM; PARTIAL for TSEM/MTSI/FN/AEHR; benchmark-only for COHR/LITE/AAOI/AXTI.
- supplier role: Core or near-core for ONTO/CAMT/FORM; production participant for FN/COHR/LITE/AAOI; indirect or uncertain linkage for TSEM/MTSI/AEHR/AXTI.
- revenue/margin/backlog/LTA translation: Production revenue exists at company level; thesis-specific revenue/backlog/LTA separation remains the key R5 task.

#### Revenue Quality Review
- total_revenue: 26.9M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax)
- gross_margin_trend: PARTIAL: latest gross profit extracted where available; trend requires manual multi-period review.
- operating_cash_flow: -11.7M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:NetCashProvidedByUsedInOperatingActivities)
- AI_datacenter_photonics_thesis_related_revenue: Not separately quantified in automated public-source pass; must be separated from total revenue before R5 underwriting.
- legacy_revenue: Not separately quantified in automated pass.
- one_time_revenue: Not identified in automated pass; requires filing note review.
- NRE_revenue: Not identified in automated pass; requires filing note review.
- recurring_repeat_customer_revenue: Not fully extracted; requires customer/order history review.
- backlog_quality: Not fully extracted; requires backlog/order/LTA/prepayment/cancellability review.
- customer_concentration: See STOP-CUSTOMER-CONCENTRATION audit.

#### Customer / Production Validation
- customer_logo: Not treated as production proof unless filing/release supports commercial revenue.
- ecosystem_relationship: Useful context only; not scored as production evidence by itself.
- sample: Not production revenue.
- demo: Not production revenue.
- qualification: Intermediate confirmation only; not production revenue.
- design_win: Confirmation only unless paired with purchase orders/shipments/revenue.
- purchase_order: Positive if disclosed and economically material; not fully extracted in automated pass.
- production_shipment: Positive if disclosed in filings/releases; automated pass uses revenue filings as partial proxy.
- recurring_revenue: Requires repeat-order evidence; not fully extracted.
- long_term_supply_agreement: Strong if disclosed with economic terms; not fully extracted.
- prepayment_take_or_pay_cancellability: Must be audited in contracts/filings before R5 underwriting.

#### Hard STOP Gate Audit

| gate | triggered_yes_no_unclear | evidence | consequence |
|---|---|---|---|
| STOP-REV0 | NO | Public SEC pass plus local R3 risk classification. Revenue fact: 26.9M USD (10-Q, period end 2026-03-31, filed 2026-05-14, concept us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax). | Not triggered in this public-source pass. |
| STOP-DEMO-NOT-PRODUCTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-UNCLEAR | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-DILUTION | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SOCIAL-HYPE | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-CUSTOMER-CONCENTRATION | UNCLEAR | Public SEC pass plus local R3 risk classification. Customer concentration requires full filing note review; classification reflects known risk profile and automated pass limits. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-CHINA-GEO | YES | Public SEC pass plus local R3 risk classification. Geographic/manufacturing exposure requires full risk-factor review; AXTI flagged as China/geopolitical benchmark risk by local context. | Triggered or materially risked; cap/penalize classification until resolved. |
| STOP-VALUATION-OVERHEAT | NO | Public SEC pass plus local R3 risk classification. No target price or trade framing used; valuation risk treated only as crowding/expectation risk. | Not triggered in this public-source pass. |
| STOP-GOING-CONCERN | NO | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Not triggered in this public-source pass. |
| STOP-SHAREHOLDER-NOT-CAPTURED | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-GOVERNANCE-ACCOUNTING | UNCLEAR | Public SEC pass plus local R3 risk classification. No positive social or historical-price evidence used; filings reviewed at summary level. | Unresolved; must be cleared before R5 underwriting confidence can rise. |
| STOP-LINKAGE-WEAK | UNCLEAR | Public SEC pass plus local R3 risk classification. Thesis-revenue linkage must be separated from total revenue before R5 underwriting. | Unresolved; must be cleared before R5 underwriting confidence can rise. |

#### Scorecard v1.2 Deep-Dive Score
- Opportunity Score: 60
- Evidence Score: 50
- Survivability / Shareholder Capture Score: 46
- Penalty Score: 52
- final_research_score: 47
- confidence_level: MEDIUM_LOW
- R4 classification: BENCHMARK_ONLY

#### Red Team
- if_thesis_wrong: The most likely failure is that total company revenue does not map tightly enough to the AI optical / silicon photonics / test chokepoint.
- ordinary_participant_risk: Must prove the company is a narrow/scarce supplier rather than a replaceable participant.
- fully_priced_risk: Valuation/crowding risk remains unresolved because this report does not use target prices or trading signals.
- customer_concentration_risk: See STOP-CUSTOMER-CONCENTRATION; full customer note review remains required.
- cycle_risk: Semiconductor and optical infrastructure cycles can reverse orders, backlog and margins.
- margin_compression_risk: Customer bargaining power, mix shift, utilization and EMS economics can compress margins.
- capex_capacity_execution_risk: Capacity, qualification and manufacturing execution can delay thesis translation.
- litigation_governance_geopolitical_risk: China/geopolitical/sanction-linked risk is a primary benchmark concern.
- shareholder_capture_issue: A real chokepoint is insufficient unless margins, cash flow and dilution/debt allow common shareholders to capture value.

- main reason: InP substrate angle is relevant, but China/geopolitical exposure and weak direct AI optical monetization keep it benchmark/caution only.
- next action: Keep as benchmark/risk comparator

## Pairwise Comparison

### TSEM vs COHR / LITE
- TSEM may offer more foundry-specific silicon-photonics optionality, but the linkage is less visible than COHR/LITE optical revenue. COHR/LITE are better benchmarks for real optical scale; TSEM needs thesis-revenue proof before it has a Serenity-style edge.

### ONTO vs CAMT vs FORM
- FORM is the narrowest wafer-test interface chokepoint; ONTO is the broadest process-control platform; CAMT is a direct inspection/metrology advanced-packaging exposure. All three clear enough evidence for R5 underwriting, with customer concentration and valuation risk still unresolved.

### MTSI vs FN vs AAOI
- FN has more direct production manufacturing exposure, MTSI has broader component exposure, and AAOI is the best false-positive/customer-concentration comparator. FN/MTSI stay R4 priority; AAOI remains benchmark-only.

### AEHR vs FORM / ONTO / CAMT
- AEHR test optionality is narrower in theory but less robust in current evidence because customer concentration and thesis-revenue linkage are weaker than FORM/ONTO/CAMT.

### AXTI vs TSEM / COHR / LITE
- AXTI is the cleaner material-bottleneck benchmark for InP/substrates, but China/geopolitical risk and weak direct monetization block upgrade. It is useful for risk comparison, not R5 underwriting.

## Final Ranking

See `serenity_r4a_ranking.csv` for the structured ranking. Research-only classification summary:

- ONTO: R5_THESIS_UNDERWRITING_CANDIDATE | score 79 | Direct metrology/process-control exposure to advanced packaging and AI infrastructure manufacturing quality is stronger and more evidence-backed than most peers.
- FORM: R5_THESIS_UNDERWRITING_CANDIDATE | score 77 | Wafer-test/probe-card chokepoint is narrow, production-based, and tied to advanced packaging/test complexity.
- CAMT: R5_THESIS_UNDERWRITING_CANDIDATE | score 75 | Inspection/metrology linkage to advanced packaging is direct; remaining issue is concentration/geography and durability of production demand.
- COHR: BENCHMARK_ONLY | score 67 | Useful scaled photonics benchmark; leverage/integration/cycle issues make it a risk comparator rather than Serenity-style edge.
- FN: R4_PRIORITY_RESEARCH | score 66 | Optical manufacturing revenue is production-like, but EMS economics and customer concentration limit shareholder-capture clarity.
- LITE: BENCHMARK_ONLY | score 66 | Good optical component benchmark for cloud/telecom cycles, customer concentration and margin recovery.
- MTSI: R4_PRIORITY_RESEARCH | score 65 | Optical/high-frequency component exposure is real, but AI optical thesis revenue and customer evidence need sharper separation.
- TSEM: R4_PRIORITY_RESEARCH | score 63 | Real specialty foundry revenue exists, but silicon-photonics thesis revenue is not cleanly separable in the automated public-source pass.
- AEHR: R4_RESEARCH_BACKLOG | score 57 | Test bottleneck can be narrow, but revenue concentration and unclear AI/optical translation keep it below R5 readiness.
- AAOI: BENCHMARK_ONLY | score 54 | Datacenter optical exposure is relevant, but concentration, volatility and crowding risk make it a false-positive comparator.
- AXTI: BENCHMARK_ONLY | score 47 | InP substrate angle is relevant, but China/geopolitical exposure and weak direct AI optical monetization keep it benchmark/caution only.

## R5 Candidate List
- ONTO, CAMT, FORM

## R4 Priority List
- TSEM, MTSI, FN

## Benchmark-Only List
- COHR, LITE, AAOI, AXTI

## Blocked / No-Go List
- POET: NO-GO / permanent caution; not upgraded.
- LWLG: BLOCKED / near NO-GO; not upgraded.

## Limitations
- SEC/EDGAR automated pass was completed, but company IR presentations, transcripts, named-customer releases, media/analyst items, and full risk-factor language require manual R5 follow-up.
- Thesis-related revenue was not fully separable from total revenue in the automated pass.
- No target price, position sizing, entry timing, trading plan, or current buy list was produced.
- Market-cap buckets are coarse approximations and not scoring inputs.

## Next Recommended Stage
- Open R5 underwriting work only for ONTO, CAMT, and FORM, with full manual filing/IR citation packs and explicit thesis-revenue separation.
- Keep TSEM, MTSI, and FN in R4 priority evidence clearing.
- Keep AEHR in R4 backlog until customer concentration and production translation improve.
- Use COHR, LITE, AAOI, and AXTI only as benchmark/risk comparators.
