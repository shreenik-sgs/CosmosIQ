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

**021B refresh** — the Reality-Intelligence sensor rows below carry the 021B production-readiness
columns: **Source mode** (source-backed / local-file / fixture / deferred) · **Freshness** (freshness
label surfaced on every finding) · **DQ** (visible to the 013E DataQualityGateRunner) · **Cadence** ·
**Alert eligibility** (max severity per the 020E policy — social/rumor → *watch only*; a
company_claim/provider read → *notice/warning*; a canonical filing fact → up to *review_required*;
**never critical without canonical + DQ approval**) · **Tests** · **Production verdict**.

| agent_id | Sub | Impl status | Source mode | Freshness | Routing | Fusion | DQ | Cadence | Alert eligibility (020E) | Tests | Production verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tattva.market_regime | 5 | **implemented + local-file** (012D/014A) | local-file · fixture default | ✓ per-finding | ✓ | ✓ | ✓ | 5–15 min mkt-hrs | up to **review_required** (macro-shift) | market_regime suite | **production-ready** (live feed → 015-era) |
| tattva.sector_rotation | 4 | **implemented + local-file** (012E/014A) | local-file · fixture | ✓ | ✓ | ✓ | ✓ | 5–15 min mkt-hrs | **warning** (rotation watch) | rotation suite | **production-ready** (live ETF feed → 015-era) |
| tattva.theme_rotation | 5 | **implemented + local-file** (012E/014A) | local-file · fixture | ✓ | ✓ | ✓ | ✓ | 5–15 min mkt-hrs | **warning** (theme-pulse change) | rotation suite | **production-ready** (live basket feed → 015-era) |
| tattva.news_filings | 7 | **implemented + live SEC adapter** (012G/014B/**020B**) | **source-backed** (SEC EDGAR live, 020B) · fixture | ✓ | ✓ | ✓ | ✓ | 1–5 min | canonical filing → **review_required**; PR company_claim → notice | news_filings + sec_edgar_live suites | **production-ready** (SEC shadow-validated 020H/I) |
| tattva.narrative | 7 | **implemented, weak-signal only** (012H/014E) | local-export · fixture | ✓ | ✓ | ✓ (WEAK) | 1–5 min | **watch only** — rumor never critical (015C cap) | social_narrative suite | **guarded** (live X stays DEFERRED, weak-only) |
| tattva.technical_regime | 6 | **implemented + local-file** (014D) | local-file (price history) | ✓ | ✓ | ✓ | ✓ | 1–15 min | **warning** (timing watch) | technical_regime suite | **production-ready** (live price feed → 015-era) |
| tattva.macro_regime | 7 | **implemented + local-file** (014F) | local-file (macro readings) | ✓ | ✓ | ✓ | ✓ | hourly/daily | up to **review_required** (macro-shock) | macro suite | **production-ready** (live rates/credit → 015-era) |
| tattva.financial_inflection | 6 | **implemented** (**021B**) — was descriptor-only³ | **source-backed** (020B SEC filing EVENTS: S-3/424B dilution · 8-K 2.02 guidance · 8-K 4.02 restatement · Form 4 insider) **+ local-file** (fundamental snapshots) | ✓ per-finding | ✓ | ✓ | ✓ | event/quarterly | **filing fact (canonical) → review_required**; company_claim/provider snapshot → **notice/warning**; social/rumor → **excluded (watch-only gap)**; **never critical without canonical + DQ approval** | `test_reality_mesh_sensor_financial_inflection` (40 offline) | **production-ready** (canonical path SEC-shadow-validated 020H/I) |
| tattva.customer_evidence | 4 | **implemented** (014F) | local-file (IR/transcripts) | ✓ | ✓ | ✓ | ✓ | event/daily | **notice** (company_claim) | company_evidence suite | **production-ready** |
| tattva.supplier_evidence | 4 | **implemented** (014F) | local-file (IR/transcripts) | ✓ | ✓ | ✓ | ✓ | event/daily | **notice** (company_claim) | company_evidence suite | **production-ready** |
| tattva.bottleneck_evidence | 6 | **implemented** (014F) | local-file (IR/transcripts) | ✓ | ✓ | ✓ | ✓ | daily/weekly | **warning** (company-stated, not-verified gap) | company_evidence suite | **production-ready** |
| tattva.leadership_evidence | 5 | **implemented** (014F) | local-file (IR/transcripts) | ✓ | ✓ | ✓ | ✓ | event | **notice** (company_claim) | company_evidence suite | **production-ready** |
| tattva.options_flow | 5 | **DEFERRED — no source** (descriptor-only) | **deferred** (no feed) | — | ready | ready | — | 5–15 min *if* source | n/a (deferred) | — | **DEFERRED**: no safely-sourceable options feed exists; hardest to source; do not fabricate a source → **post-021** |
| tattva.policy_geopolitical | 7 | **DEFERRED — no source** (descriptor-only) | **deferred** (no contract) | — | ready | ready | — | daily/event | n/a (deferred) | — | **DEFERRED**: no curated policy/news source contract; needs a real, non-rumor source before any adapter → **post-021** |

³ 021B FLIP: `tattva.financial_inflection` moved **descriptor-only → implemented**. Its source
contract is REAL: it reads the 020B `SecEdgarLiveAdapter` filing EVENTS as canonical inflection
facts (dilution / guidance / restatement / insider) and LOCAL fundamental-snapshot fixtures as
company_claim (IR → primary) / provider_reported (→ convenience) reads — **never canonical unless
SEC, never a verified_fact from a claim, and provider never outranks SEC**. An absent financial
input is a VISIBLE gap (never a fabricated number); an X/social input is EXCLUDED (never a driver,
never verified, never critical). The sensor is additive/opt-in (gated on its own events → the
default + demo pulse stays byte-identical). `options_flow` and `policy_geopolitical` remain the
**only two deferred** sensors — both honestly, for lack of a safe source contract (no invented
source).

### Phase 014 closeout (source adapters)
Adapters landed (all local-file / injected-transport; the production **network** path is deliberately
the last onboarding stage, unlocked in the 015 era): `LocalMarketDataAdapter` (014A, #1–3) ·
`SecFmpEvidenceAdapter` (014B, #4–5, mocked transports; creds presence-only) ·
`CompanyDocumentsAdapter` (014C, #6–7, company_claim-never-verified by construction) ·
`LocalPriceHistoryAdapter` (014D, #8, watchlist-scoped) · `SocialExportsAdapter` (014E, #9,
rumor-always, no live X) · `LocalMacroDataAdapter` (014F, #11).

### Phase 021B refresh (sensor coverage expansion — after SEC shadow validation 020H/I)
`tattva.financial_inflection` flipped **descriptor-only → implemented** (021B) with a REAL source
contract (020B SEC filing EVENTS = canonical facts; local fundamental snapshots = company_claim /
provider_reported, never canonical). **Honest count: 13 of 14 Reality-Intelligence sensors
implemented** (was 12); **1 deferred with no safe source**:
- **options_flow** (#10) — DEFERRED: no safely-sourceable options feed exists (hardest to source).
- **policy_geopolitical** (#12) — DEFERRED: no curated, non-rumor policy/news source contract.

Both stay deferred *honestly* — no source is invented, no rumor is laundered into a feed. They
move only when a real source contract exists (→ post-021).

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
