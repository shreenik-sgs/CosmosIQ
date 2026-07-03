# CosmosIQ — Universal Intelligence OS

**Map reality across domains. Detect emerging signals. Synthesize opportunity. Decide with discipline.**

CosmosIQ is a **Universal Intelligence OS** that maps reality across domains, detects emerging
signals, synthesizes opportunity, and supports high-quality decisions through specialized agentic
intelligence layers.

**CosmosIQ Capital** is the first vertical application of CosmosIQ — a **Personal CIO / Investment
Intelligence** product that turns real-world signals, market structure, sector rotation, value
chains, forward scenarios, and portfolio context into disciplined capital-allocation intelligence.
Trades are always prepared for **manual** review — CosmosIQ never submits orders to a broker.

## The stack

The agentic sensor/synthesis architecture is the **Reality Mesh**; the interactive visualization is
the **Universe Canvas**. The public intelligence stack:

```
Foundation Layer            — identity, provenance, authority, freshness, conflicts, security, storage
→ Intelligence Governance Layer — orchestration, routing, boundary enforcement, policy gates, mode control
→ Reality Intelligence Layer    — source sensing, real-world events, agent findings, reality signals
→ Signal Fusion                 — freshness, authority, corroboration, contradiction, clustering
→ Opportunity Discovery Layer   — theme pulse, megatrends, value chains, bottlenecks, beneficiaries, hypotheses
→ Investment Diligence Layer    — company positioning, forward scenarios, valuation, red team, timing, capital candidate
→ Portfolio Intelligence Layer  — portfolio fit, exposure, concentration, risk budget, sizing guardrails
→ Execution Preview Layer       — manual execution preview only, execution risk, audit
→ Learning & Feedback Layer     — outcomes, signal reliability, thesis review, timing review, archetype learning
```

**CosmosIQ** is the public platform name and **CosmosIQ Capital** the first vertical. Future
verticals: CosmosIQ Health · CosmosIQ Defense · CosmosIQ Supply Chain · CosmosIQ Food Systems ·
CosmosIQ Security · CosmosIQ Energy. See
[`docs/product/BRAND_NOMENCLATURE.md`](docs/product/BRAND_NOMENCLATURE.md) for the canonical
nomenclature and the retired legacy names.

## Repository

- **`architecture/`** — the architecture design record (SPEC / contract / test-matrix / plan
  documents). The canonical Architecture Book and `specification/` remain the internal source of
  truth for architecture semantics.
- **`specification/`** — the compiled architecture, normative.
- **`src/` · `tests/`** — the runtime: the Reality Mesh substrate (agents → fusion → opportunity →
  diligence), the Universe Canvas UI, evidence ingestion, and the durable pulse runtime (runs,
  stores, replay, health, data-quality gates), with the manual-execution safeguards under test.
- **`docs/`** — product and developer documentation.

Trades are placed **manually by the user**; the system prepares, validates, gates, records,
reconciles, audits, and learns — it never submits orders to a broker, runs a scheduler, or trades
automatically.

> **Naming note.** Public terminology has migrated to **CosmosIQ** and the English layer names above.
> The earlier public names (*Sudarshan* product label, the Sanskrit layer names, and *EIOS* as a
> public label) are **retired from all public-facing surfaces**. Some internal module/package
> identifiers (e.g. `src/reality_mesh/` internals, `src/tattva_pulse/`, `src/prometheus/`, and the
> `EIOS` architecture ID) retain legacy names temporarily for backward compatibility and
> traceability — see `docs/product/BRAND_NOMENCLATURE.md`.
