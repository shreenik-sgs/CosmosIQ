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
| tattva.market_regime | 5 | **fixture-backed** (012D) | fixture | ✓ | ✓ | ✓ | via signals | 5–15 min mkt-hrs | real market-data adapter → **014 (#1)** |
| tattva.sector_rotation | 4 | **fixture-backed** (012E) | fixture | ✓ | ✓ | ✓ | via signals | 5–15 min mkt-hrs | sector-ETF adapter → **014 (#2)** |
| tattva.theme_rotation | 5 | **fixture-backed** (012E) | fixture | ✓ | ✓ | ✓ | via pulses | 5–15 min mkt-hrs | theme-basket adapter → **014 (#3)** |
| tattva.news_filings | 7 | **fixture-backed** (012G) | fixture | ✓ | ✓ | ✓ | via signals | 1–5 min | SEC/FMP live adapter (transports exist) → **014 (#4/#5)** |
| tattva.narrative | 7 | **fixture-backed, weak-signal only** (012H) | fixture | ✓ | ✓ (WEAK-marked) | via pulses | 1–5 min active themes | live X strictly weak-signal, LAST → **014 (#9)** |
| tattva.technical_regime | 6 | descriptor-only | — | ready | ready | — | — | 1–15 min | price-history adapter → **014 (#8)** |
| tattva.macro_regime | 7 | descriptor-only | — | ready | ready | — | — | hourly/daily | rates/curve/credit sources → **014 (#11)** |
| tattva.policy_geopolitical | 7 | descriptor-only | — | ready | ready | — | — | daily/event | policy/news sources → **014 (#12)** |
| tattva.options_flow | 5 | descriptor-only | — | ready | ready | — | — | 5–15 min if source | options source unresolved (hardest to source safely) → **014 (#10)** |
| tattva.financial_inflection | 6 | descriptor-only³ | — | ready | ready | ✓ via enrichment | ✓ via terrain | event/quarterly | SEC/FMP fundamentals live via 011 enrichment; agent form → **014 (#5)** |
| tattva.customer_evidence | 4 | descriptor-only | — | ready | ready | — | — | event/daily | IR/transcript sources (local-file-first) → **014 (#13)** |
| tattva.supplier_evidence | 4 | descriptor-only | — | ready | ready | — | — | event/daily | IR/transcript sources → **014 (#14)** |
| tattva.bottleneck_evidence | 6 | descriptor-only | — | ready | ready | — | ✓ (Star nodes) | daily/weekly | lead-time/capacity sources → **014 (#15)** |
| tattva.leadership_evidence | 5 | descriptor-only | — | ready | ready | — | — | event | transcript/insider sources → **014 (#16)** |

³ The *evidence* is production-backed via 011 diligence-enrichment (real SEC/FMP on demand); the sensor-agent wrapper is deferred.

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
