# ADR-CANDIDATE-011 — Diligence Enrichment is an Evidence Layer, not a Scoring or Execution Layer

Status: **CANDIDATE** (proposed; not yet entered in the ADR register `ARCHITECTURE_DECISIONS.md`)
Date: proposed during Phase 011 · Supersedes: none · Related: ADR-0008 (understanding→judgment→action),
ADR-0010 (cognition–actuation boundary), SPEC-011, ARCHITECTURE_CONTRACT_011.

> This is a **candidate** for architect review. It does not modify the frozen ADR register and does
> not increment the next-ADR number. If accepted, it should be entered as a formal ADR with the next
> available number and this candidate retired.

## Context

Phase 011 adds a diligence **input enrichment** layer (`src/diligence_enrichment/`, established in
011A) that collects and normalizes the inputs Nivesha and the Economic Universe terrain need:
market cap / EV, TAM / revenue pool, value-chain layers, suppliers/customers, bottleneck
severity/duration/capacity, company IR / investor presentations / transcripts, and leadership
evidence. These inputs are today mostly missing, which is why real/watchlist terrain is honestly
sparse.

There is a real temptation, as inputs improve, to let this layer start *deciding*: to compute a
composite "diligence score", to rank tickers, to emit buy/sell/hold, or to feed a broker path. That
would collapse the layer boundaries (ADR-0008/0010), reintroduce stock-first ranking, and cross the
execution boundary — all of which this project has deliberately forbidden.

## Decision

**Diligence enrichment is an evidence layer. It may collect, normalize, trace, and expose
evidence-backed diligence inputs; it must not make investment decisions.**

Specifically, the enrichment layer:

- **MAY**: gather facts from disciplined sources with explicit **source authority** and **claim
  status**; normalize them into typed evidence models; produce **data gaps**, **trust/completeness
  labels**, and **provenance**; feed **existing** terrain fields and `VisualEncoding` bases (via
  existing helpers such as `visual_size`); and hand structured inputs to Nivesha.
- **MUST NOT**: create investment decisions, alpha rankings, a composite/master score, buy/sell/hold
  actions, forced position sizes, or broker orders; relabel manual/analyst data as canonical;
  override higher-authority facts with lower-authority ones; or introduce any numeric investability
  metric.

Authority and judgment remain where they belong: **Nivesha** performs diligence/judgment with its
existing gauntlet; **Saarathi** provides ranges/guardrails; **Kriya** provides a manual execution
**preview** only. Enrichment improves the *quality and completeness of inputs*, not the *decision*.

## Consequences

**Positive**
- Layer boundaries (ADR-0008/0010) and the "stocks are output" chain stay intact.
- The execution boundary stays closed (no order path); real-mode honesty is preserved (missing →
  visible gap, never a silent demo/score substitute).
- Enrichment can grow (more sources, richer profiles) without ever becoming a ranking engine.
- Trust/completeness stay **labels**, keeping visual cues explainable and non-numeric-investability.

**Negative / accepted costs**
- The universe/terrain remains **sparse** until real diligence sources are added — by design, shown
  as gaps rather than hidden by a synthesized score.
- Operators must interpret evidence + gaps themselves; the system does not hand them a ranked list.

**Enforcement**
- `diligence_enrichment` models carry no decision/score field (test-asserted).
- `source_contract` keeps manual ≠ canonical and stamps `company_claim`.
- No `def *score`/`*rank`; no numeric investability field; VisualEncoding stays decoupled from
  ranking. See `ARCHITECTURE_CONTRACT_011.md` §E and `GATE-011` §4/§7/§12.

## Alternatives considered

1. **Enrichment produces a diligence score** — rejected: violates layer boundaries + no-hidden-
   scoring; reintroduces stock-first ranking.
2. **Enrichment feeds a broker/order path once inputs are complete** — rejected: crosses the
   execution boundary (ADR-0010); Kriya stays preview-only.
3. **Auto-fill missing inputs with model estimates to reduce sparseness** — rejected: fabricates
   data; the honest behaviour is a visible gap + a data-sourcing action.

## Review note

On acceptance, enter as the next formal ADR (increment the register), cross-reference SPEC-011 and
ARCHITECTURE_CONTRACT_011, and retire this candidate file.
