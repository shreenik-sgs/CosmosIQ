# CosmosIQ — Product Nomenclature

**Status:** product-naming layer (non-architectural) · **Supersedes** the retired *Sudarshan / EIOS*
public naming.

This document locks the **user-facing product nomenclature**. It is a *naming layer*, not an
architecture change: no architecture ID, namespace, filename, generated `specification/` path, ADR,
Architectural Rule (`AR-`), or Requirement (`REQ-`) is renamed by this document. Layer
responsibilities are unchanged — only the public names.

## Platform, category, and architecture

| Register | Name |
|---|---|
| **Parent platform** (public) | **CosmosIQ** |
| **Category / tagline** | **Universal Intelligence OS** |
| **Agentic architecture** | **Reality Mesh** |
| **Interactive UI / visualization** | **Universe Canvas** |
| **First vertical product** | **CosmosIQ Capital — Personal CIO / Investment Intelligence** |

**Positioning.** *CosmosIQ is a Universal Intelligence OS that maps reality across domains, detects
emerging signals, synthesizes opportunity, and supports high-quality decisions through specialized
agentic intelligence layers.*

**Investment vertical.** *CosmosIQ Capital is the first vertical application of CosmosIQ — a Personal
CIO / Investment Intelligence product that turns real-world signals, market structure, sector
rotation, value chains, forward scenarios, and portfolio context into disciplined capital-allocation
intelligence.*

**Future verticals:** CosmosIQ Health · CosmosIQ Defense · CosmosIQ Supply Chain · CosmosIQ Food
Systems · CosmosIQ Security · CosmosIQ Energy.

## Canonical English layer names (public-facing)

| Public layer name | Responsibility (unchanged) | Retired name |
|---|---|---|
| **Foundation Layer** | identity, provenance, authority, freshness, conflicts, security, storage | Adhara |
| **Intelligence Governance Layer** | orchestration, routing, boundary enforcement, policy gates, mode control | Buddhi |
| **Reality Intelligence Layer** | source sensing, real-world events, agent findings, reality signals | Tattva |
| **Signal Fusion** | freshness, authority, corroboration, contradiction, clustering | (Tattva Signal Fusion) |
| **Opportunity Discovery Layer** | theme pulse, megatrends, value chains, bottlenecks, beneficiaries, opportunity hypotheses | Sphurana |
| **Investment Diligence Layer** | company positioning, forward scenarios, valuation, red team, timing, capital candidate | Nivesha |
| **Portfolio Intelligence Layer** | portfolio fit, exposure, concentration, risk budget, sizing guardrails | Saarathi |
| **Execution Preview Layer** | manual execution preview only, execution risk, audit | Kriya |
| **Learning & Feedback Layer** | outcomes, signal reliability, thesis review, timing review, archetype learning | Anubhava |

Public stack order: **Foundation → Intelligence Governance → Reality Intelligence → Signal Fusion →
Opportunity Discovery → Investment Diligence → Portfolio Intelligence → Execution Preview → Learning &
Feedback.**

## App navigation & Universe Canvas terms

Public nav labels: **Universe Canvas** · **CosmosIQ Capital** · **Trust & Data Quality** · **Reality
Mesh** (future/internal until implemented). Retired: *Economic Universe* → Universe Canvas; *CIO
Dashboard* → CosmosIQ Capital; *Data Quality* → Trust & Data Quality.

Universe Canvas celestial mapping: Universe = full CosmosIQ intelligence space · **Galaxy = Mega
Theme** (not a generic domain) · Milky Way = Theme · Solar System = Value Chain · Star = Bottleneck ·
Planet = Company / Capital Candidate · Moon = Supplier / Customer / Dependency · Comet = Catalyst ·
Black Hole = Major Risk / Red-Team Hazard · Nebula = Emerging Weak Signal / Early Theme Cloud.

## Retired public names

The following are **retired from all public-facing surfaces** (UI, generated reports, diagrams,
public docs, operator docs): the **Sudarshan / Sudarshana** product label; **EIOS** as a *public*
product label; and the Sanskrit layer names **Adhara, Buddhi, Tattva, Sphurana, Nivesha, Saarathi,
Kriya, Anubhava**.

> Legacy Sanskrit layer names were retired in favor of English product terminology for clarity,
> marketability, and user comprehension.

## Internal legacy aliases (backward compatibility)

Some internal module identifiers temporarily retain legacy names for backward compatibility and
architectural traceability. Public-facing terminology has migrated to CosmosIQ and the English layer
names above; these internal identifiers do **not** appear in any public output:

- `src/reality_mesh/` internals and some symbol names (e.g. `tattva_*` fusion, `sphurana.py`,
  `nivesha_forward.py`) — the Reality Mesh implementation.
- `src/tattva_pulse/` — the manual pulse CLI package (its user-facing output uses CosmosIQ terms).
- `src/prometheus/`, `src/genesis/`, `src/personal_cio/`, `src/execution_manual/` — internal engines.
- `EIOS` and the `EIOS / GEN / PROM / CIO / EXEC` identifiers + numbered IDs in
  `architecture/` / `specification/` — the internal architecture source of truth and its ADR/AR/REQ
  traceability, which remain stable and are not renamed by this naming layer.

Renaming these internal identifiers is deferred to a later, separately-gated pass so imports and
architecture traceability are not broken. This document is the single source of naming truth; where
an internal identifier is surfaced to a user, it is mapped to the public names above.
