# ARCHITECTURE CONTRACT — 012

Status: **Draft for architect review** · Governs: 012A–012K · Companions: `AGENT_MAP_012.md`,
`HANDOFF_CONTRACT_012.md`, `SPEC-012_REAL_TIME_REALITY_INTELLIGENCE_SENSOR_MESH.md`. Extends and does
not weaken `ARCHITECTURE_CONTRACT_011.md`.

Non-negotiable invariants. Any violation ⇒ **NO** at the gate. Each states its enforcement point.

---

## A. Agentic discipline (the core invariant)

```
Agents OBSERVE and ANALYZE within their discipline → emit AgentFinding (or a foundation/governance record) ONLY.
Synthesizers COMBINE evidence → emit the fused/higher packet.
Only DOWNSTREAM LAYERS decide meaning.
No agent jumps directly from signal to trade.
```

- A discipline agent must NOT emit a `RealitySignal`, `ThemePulse`, `OpportunityHypothesis`,
  `InvestmentThesis`, size, order, or buy/sell/hold. Cross-layer packets come from **synthesizers only**.
- Every cross-layer transfer is wrapped in a `HandoffEnvelope` with explicit `allowed_/
  forbidden_downstream_uses`; a consumer performing a forbidden use is a violation.
**Enforcement**: `buddhi.layer_boundary` + `buddhi.gatekeeper`; agent-output-type tests; envelope
allowed/forbidden-use tests.

## B. Layer boundaries & "stocks are output" (inherited from 011)

Adhāra=Foundation · Buddhi=Cognitive Governance · Tattva=Reality Intelligence (understanding only;
factual ≠ signal) · Sphurana=Opportunity Generation · **Nivesha=Investment Diligence / Capital
Candidate** (never "Capital Allocation"; no final user sizing) · **Saarathi=Personal CIO / Portfolio
Fit / Sizing Guardrails** (ranges, not orders) · **Kriya=Manual Execution Preview** · Anubhava=
Feedback/Learning. Reason `Reality → Technology → Adoption → Supply Chains → Bottlenecks → Corporate
Winners → Financial Inflection → Institutional Accumulation → Stock Price`. No stock-first ranking;
ticker/security mapping only after value-chain/winner mapping.
**Enforcement**: 011 boundary tests + AGENT_MAP consume/emit contracts.

## C. Source authority (inherited; extended for narrative)

`SEC canonical > company IR primary (a company_claim, not auto-verified) > FMP convenience > yfinance
fallback > manual/analyst (never canonical) > rumor (X/social)`. Lower cannot override higher for the
same metric/period/unit. **X/social is `rumor` — it never confirms a fact, emits weak/narrative
signals only, and requires corroboration before any high-confidence downstream use.** Company
statements are `company_claim`; unsupported fields become data gaps.
**Enforcement**: `evidence_ingestion/conflict.py` reused; `adhara.authority`; narrative-corroboration
tests.

## D. Synthesizer behaviour (evidence integrity)

Every synthesizer MUST:
- NOT average away contradictions; NOT upgrade weak signals without corroboration; NOT treat
  X/social as verified fact; NOT hide missing data; NOT create stock-first ranking; NOT create
  buy/sell/hold except where an accepted downstream semantic already allows it; NOT create broker/
  order actions.
- Preserve `source_refs`, conflict records, and data gaps end-to-end; emit `confidence_` and
  `freshness_` labels; keep weak signals weak and minority hypotheses alive.
**Enforcement**: preserve-conflict / preserve-gap / no-average tests; `buddhi.hypothesis_discipline`.

## E. No hidden scoring (labels, not numbers)

No numeric investability/score/rank/rating field on ANY agent output, finding, signal, cluster,
pulse, hypothesis, packet, or diagnostic. Quality/state are **labels** from closed vocabularies.
VisualEncoding presents existing labels/facts; it creates no score.
**Enforcement**: no `def *score`/`*rank`; no numeric-investability field; label-vocabulary tests.

## F. Execution boundary

No broker automation / order placement / routing / recording. No buy/sell/order/submit button/form
anywhere. Kriya = manual execution **preview** only (`broker_order_id` always None; ticket
`previewed`). Explicit user-selected size only in `ManualExecutionIntent`/Kriya. Saarathi shows
**ranges/guardrails**. No agent or synthesizer emits an order.
**Enforcement**: no-affordance-in-HTML tests; ticket-preview tests; handoff forbidden-uses.

## G. Manual / on-demand (no scheduler, no real-time default)

No scheduler, background job, automated refresh, streaming, or automated trading. Phase 012 runs in
**manual/on-demand pulse** mode: a human triggers one pulse. Continuous real-time mode is NOT the
default and requires separate approval + a new ADR. No silent fallback to demo; modes (demo/fixture/
real/enriched/**pulse**) stay separate and honestly labelled.
**Enforcement**: no scheduler/asyncio-loop/threading-timer import; `buddhi.mode_controller`; mode-
label + no-silent-demo tests.

## H. Runtime / security (inherited from 011)

No network on import; whole suite offline (socket kill-switch); real fetch (if any new source is
wired) only behind an explicit manual pulse via a single lazily-imported transport boundary. No
secrets committed; no API keys in generated HTML or logs (presence booleans only); missing creds →
visible gap, not a leak/crash.
**Enforcement**: AST single-network-boundary tests; offline suite; no-key-in-HTML/commits tests.

## I. Determinism & outcome integrity

Deterministic + offline: handoff objects build from fixtures/mocks; no wall-clock in id/replay paths
(timestamps injectable). Anubhava never rewrites history or retroactively fabricates certainty;
outcome records are append-only.
**Enforcement**: byte-identical build tests; Anubhava append-only / no-retro-certainty tests.

---

## Invariant → enforcement quick map

| Inv | Enforcement |
|---|---|
| A agentic discipline | agent-output-type + envelope allowed/forbidden-use tests; layer_boundary/gatekeeper |
| B layer / stocks-output | 011 boundary tests; AGENT_MAP contracts; after-winners qualifier |
| C authority (+ rumor) | conflict.py; adhara.authority; narrative-corroboration tests |
| D synthesizer integrity | preserve-conflict/gap; no-average; hypothesis_discipline |
| E no hidden scoring | no `*score`/`*rank`; label-vocabulary tests |
| F execution boundary | no-affordance; ticket-preview; forbidden-uses |
| G manual/on-demand | no-scheduler; mode_controller; no-silent-demo |
| H runtime/security | offline suite; single network boundary; no secret leak |
| I determinism/outcome | byte-identical builds; Anubhava append-only |

Any change to these invariants requires a new ADR, not a build patch.
