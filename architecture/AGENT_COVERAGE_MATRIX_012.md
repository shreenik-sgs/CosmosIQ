# AGENT COVERAGE MATRIX — Phase 012 Closeout

Status: **Phase-012 closeout deliverable** · Generated from the LIVE `build_default_registry()` (26
descriptors, 78 subagents) + the synthesizer chain (AGENT_MAP_012 §3.4–3.9). Public layer names are
the locked English terms; `agent_id`s are opaque **stable identifiers** (legacy prefixes retained by
design — see `docs/product/BRAND_NOMENCLATURE.md`).

**Legend — implementation status:** `production-backed` (real reasoning/logic in the accepted
engines) · `fixture-backed` (active agent, fixture/mock data; real adapter deferred to 014) ·
`adapter` (handoff adapter into an accepted engine) · `descriptor-only` (registered contract, no
runtime yet) · `deferred` (not yet registered; reason + phase given). **Routing/Fusion/DQ/Canvas**
= wired through BuddhiRouter / Signal Fusion / Trust & Data Quality / Universe Canvas today.

## 1. Foundation Layer (6 top-level; 0 subagents)

| agent_id | Impl status | Data mode | Routing | Fusion | T&DQ | Canvas | Cadence rec. | Deferred reason → phase |
|---|---|---|---|---|---|---|---|---|
| adhara.identity | descriptor-only¹ | n/a | n/a | n/a | indirect | — | per-pulse | runtime record types exist (013A/B stores stamp ids); dedicated agent → **014** |
| adhara.provenance | descriptor-only¹ | n/a | n/a | n/a | ✓ (provenance chain) | — | per-pulse | provenance enforced structurally (source_refs everywhere); agent form → **014** |
| adhara.authority | descriptor-only¹ | n/a | n/a | n/a | ✓ (authority matrix) | — | per-pulse | authority ladder enforced in labels/conflict.py + gates (013E); agent form → **014** |
| adhara.freshness | descriptor-only¹ | n/a | n/a | n/a | ✓ (freshness labels) | — | per-pulse | freshness/half-life enforced in fusion; agent form → **014** |
| adhara.conflict | descriptor-only¹ | n/a | n/a | n/a | ✓ (conflict panel) | — | per-pulse | conflict preservation enforced in fusion + gates; agent form → **014** |
| adhara.security_boundary | descriptor-only¹ | n/a | n/a | n/a | ✓ (SecurityGateResult) | — | per-run | enforced by 013E security gate + offline suite; agent form → **014** |

¹ Foundation responsibilities are **live as infrastructure** (013A–E) even where the *agent wrapper* is descriptor-only.

## 2. Intelligence Governance Layer (6 top-level; 0 subagents)

| agent_id | Impl status | Data mode | Routing | Fusion | T&DQ | Canvas | Cadence rec. | Deferred reason → phase |
|---|---|---|---|---|---|---|---|---|
| buddhi.router | **implemented** (BuddhiRouter, 012B) | in-memory | ✓ (is the router) | ✓ | ✓ | — | per-pulse | — |
| buddhi.layer_boundary | descriptor-only² | n/a | n/a | n/a | ✓ (policy gate) | — | per-run | enforced by descriptor layer-emit validation + run_checked; agent form → **014** |
| buddhi.gatekeeper | descriptor-only² | n/a | n/a | n/a | ✓ (PolicyGateResult) | — | per-run | enforced by 013E gate runner; agent form → **014** |
| buddhi.fusion_coordinator | descriptor-only² | n/a | n/a | n/a | — | — | per-pulse | fusion is invoked directly by the pulse orchestrator; coordinator → **015** (scheduler-era) |
| buddhi.hypothesis_discipline | descriptor-only² | n/a | n/a | n/a | ✓ (conflicted pulses) | — | per-pulse | enforced inside Sphurana state machine; agent form → **014** |
| buddhi.mode_controller | descriptor-only² | n/a | n/a | n/a | ✓ (mode labels) | — | per-run | modes enforced by app/CLI + demo-fallback gate; agent form → **015** |

² Governance responsibilities are **live as enforcement code** (validation, gates, router); agent wrappers deferred.

## 3. Reality Intelligence Layer (14 top-level; 78 subagents)

| agent_id | Sub | Impl status | Data mode | Routing | Fusion | T&DQ | Canvas | Cadence rec. | Deferred reason → phase |
|---|---|---|---|---|---|---|---|---|---|
| tattva.market_regime | 5 | **implemented + local-file-backed** (012D/014A) | fixture default · local-file opt-in | ✓ | ✓ | ✓ | via signals | 5–15 min mkt-hrs | live feed → adapter stage 6, **015-era** |
| tattva.sector_rotation | 4 | **implemented + local-file-backed** (012E/014A) | fixture · local-file | ✓ | ✓ | ✓ | via signals | 5–15 min mkt-hrs | live sector-ETF feed → stage 6, **015-era** |
| tattva.theme_rotation | 5 | **implemented + local-file-backed** (012E/014A) | fixture · local-file | ✓ | ✓ | ✓ | via pulses | 5–15 min mkt-hrs | live theme-basket feed → stage 6, **015-era** |
| tattva.news_filings | 7 | **implemented + injected-transport adapter** (012G/014B) | fixture · mocked SEC/FMP transports | ✓ | ✓ | ✓ | via signals | 1–5 min | production network path = adapter stage 6, **015-era** (transports + creds handling exist) |
| tattva.narrative | 7 | **implemented + local-export adapter, weak-signal only** (012H/014E) | fixture · operator export files | ✓ | ✓ (WEAK-marked) | via pulses | 1–5 min active themes | live X remains DEFERRED (weak-signal-only even then) → **post-015 + approval** |
| tattva.technical_regime | 6 | **implemented + local-file-backed** (014D) | local price-history files | ✓ | ✓ | ✓ | via signals | 1–15 min | live price feed → stage 6, **015-era** |
| tattva.macro_regime | 7 | **implemented + local-file-backed** (014F) | local macro readings | ✓ | ✓ | ✓ | via signals | hourly/daily | live rates/credit feed → stage 6, **015-era** |
| tattva.policy_geopolitical | 7 | **DEFERRED** (descriptor-only) | — | ready | ready | — | — | daily/event | no policy/news source contract yet; needs a curated source before any adapter → **post-014** |
| tattva.options_flow | 5 | **DEFERRED** (descriptor-only) | — | ready | ready | — | — | 5–15 min if source | no safely-sourceable options feed exists; hardest to source; deferred until a source contract exists → **post-014** |
| tattva.financial_inflection | 6 | descriptor-only³ (evidence flows) | 011 enrichment + 014B events | ready | ready | ✓ via enrichment | ✓ via terrain | event/quarterly | sensor wrapper deferred (evidence already production-backed; 014B events land with an honest gap) → **post-014** |
| tattva.customer_evidence | 4 | **implemented** (014F, via company docs) | 014C local IR/transcripts | ✓ | ✓ | ✓ | via signals | event/daily | further sources (surveys/channel checks) → later |
| tattva.supplier_evidence | 4 | **implemented** (014F, via company docs) | 014C local IR/transcripts | ✓ | ✓ | ✓ | via signals | event/daily | supplier-of-supplier mapping → later |
| tattva.bottleneck_evidence | 6 | **implemented** (014F, via company docs) | 014C local IR/transcripts | ✓ | ✓ | ✓ | ✓ (Star nodes) | daily/weekly | independent lead-time/capacity sources → later (company-stated carries a not-verified gap) |
| tattva.leadership_evidence | 5 | **implemented** (014F, via company docs) | 014C local IR/transcripts | ✓ | ✓ | ✓ | via signals | event | insider-transaction source (SEC Form 4 via 014B) → later |

³ The *evidence* is production-backed via 011 diligence-enrichment (real SEC/FMP on demand) + 014B fundamental-snapshot events; the sensor-agent wrapper is the only deferred piece (its absence is an honest gap on every pulse).

### Phase 014 closeout (source adapters)
Adapters landed (all local-file / injected-transport; the production **network** path is deliberately
the last onboarding stage, unlocked in the 015 era): `LocalMarketDataAdapter` (014A, #1–3) ·
`SecFmpEvidenceAdapter` (014B, #4–5, mocked transports; creds presence-only) ·
`CompanyDocumentsAdapter` (014C, #6–7, company_claim-never-verified by construction) ·
`LocalPriceHistoryAdapter` (014D, #8, watchlist-scoped) · `SocialExportsAdapter` (014E, #9,
rumor-always, no live X) · `LocalMacroDataAdapter` (014F, #11). **12 of 14 Reality-Intelligence
sensors implemented** (was 5); explicitly deferred with reasons: options_flow (#10, no safe source),
policy_geopolitical (#12, no source contract), financial_inflection wrapper (evidence already flows).

## 4. Synthesizers (Signal Fusion → Opportunity Discovery → Investment Diligence → Portfolio Intelligence → Execution Preview → Learning & Feedback)

| Role (AGENT_MAP §) | Impl status | Data mode | T&DQ | Canvas | Deferred reason → phase |
|---|---|---|---|---|---|
| **Signal Fusion** (§3.4, 7 subagents) | **implemented** (012C `TattvaSignalFusionSynthesizer` = `RealityIntelligenceSignalFusion`) | in-memory | ✓ | via signals | — |
| sphurana.theme_pulse + opportunity_hypothesis (§3.5) | **implemented** (012F ThemePulseSynthesizer → ThemePulse + OpportunityHypothesisPacket) | in-memory | ✓ | via pulses | — |
| sphurana.megatrend / value_chain_discovery / bottleneck / beneficiary / loser_disruption / crowding (§3.5, 6 roles) | deferred | — | — | — | need more sensor coverage first → **014** |
| nivesha.* diligence gauntlet (§3.6, 10 roles) | **production-backed** (accepted `prometheus` engines: thesis, red team, timing, valuation, scenarios) + **adapter** (011D + 012I forward-scenario sidecar) | real-on-demand via 011 enrichment | ✓ | cockpit | agentic wrappers → **014**; runs on demand, not in pulse |
| saarathi.* portfolio fit (§3.7, 7 roles) | **production-backed** (accepted `personal_cio`: fit, sizing guardrail RANGES, PersonalizedAction) | profile/portfolio input | ✓ | dashboard | real portfolio import → **018** |
| kriya.* manual preview (§3.8, 5 roles) | **production-backed** (accepted `execution_manual`: ManualExecutionPreview, `broker_order_id` always None) | manual intent | ✓ | cockpit | stays manual preview only (020+ approval-gated for anything more) |
| anubhava.* learning (§3.9, 7 roles) | deferred | — | — | — | needs persisted run history (013) + outcomes over time → **017** |

## 5. Totals

- **Registered top-level roles:** 26 registry descriptors + Signal Fusion + 2 Opportunity Discovery + 10 Investment Diligence + 7 Portfolio Intelligence + 5 Execution Preview ≈ **51 live-registered/engine-backed of the ~64 target** (13 deferred: 6 Sphurana discovery roles + 7 Anubhava).
- **Subagents:** 78 registered (of the ~88 target; the remainder ride with their deferred parents).
- **Implemented today:** 5 fixture-backed sensors + router + fusion + theme-pulse synthesizer + the production-backed Investment Diligence / Portfolio Intelligence / Execution Preview engines + the 013A–E runtime (stores/replay/health/gates).
- **Every deferred role carries a reason + its productionization phase above** (014 adapters in priority order, 015 scheduler-era coordination, 017 learning, 018 portfolio, 020+ execution).

## 6. Phase-012 final acceptance (proven at closeout)

Agent registry ✓ (26) · SensorAgent interface ✓ · Intelligence Governance router ✓ · Signal Fusion ✓
(conflicts preserved, weak stays weak) · Market Regime ✓ · Sector Rotation ✓ · Theme Rotation ✓ ·
News/Filings ✓ (SEC canonical, PR company_claim) · X/Social ✓ weak-signal-only (rumor never
verified_fact) · Opportunity Discovery Theme Pulse ✓ (narrow≠Broadening, social→Data insufficient) ·
Investment Diligence forward adapter ✓ (prometheus untouched, no target-price laundering) · Trust &
Data Quality integration ✓ (012J panel) · Universe Canvas integration ✓ (P1 celestial) · manual pulse
CLI ✓ (`cosmosiq_pulse`) · all outputs trace to evidence ✓ · no scheduler / broker / trading / hidden
score / verified-fact laundering ✓ — full suite green (1356 offline).

## Cross references
`AGENT_MAP_012.md` · `HANDOFF_CONTRACT_012.md` · `ARCHITECTURE_CONTRACT_012.md` ·
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `docs/product/BRAND_NOMENCLATURE.md`.
