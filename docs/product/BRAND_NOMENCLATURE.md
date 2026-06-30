# Sudarshan — Product Nomenclature

**Status:** product-naming layer (non-architectural) · **Date:** 2026-06-30

This document locks the **user-facing product nomenclature** for the platform. It is a *naming
layer*, not an architecture change. No architecture ID, namespace, filename, generated
specification path, ADR, Architectural Rule (`AR-`), or Requirement (`REQ-`) is renamed by this
document.

## The two naming registers

| Register | Name | Where it is used |
|----------|------|------------------|
| **Product (user-facing)** | **Sudarshan** | UI, product copy, user-facing docs, investor-facing explanations, marketing |
| **Architecture (internal)** | **EIOS** — Economic Intelligence Operating System | `specification/`, `architecture/EIOS_Architecture_Book.md`, ADRs, code, all IDs/namespaces |

- **Sudarshan** is the user-facing product name. *Sudarshan* — clear/auspicious vision (the discus of clear sight).
- **EIOS** remains the internal architecture / engine name and the canonical source of truth.
- The Sanskrit names below are **product-facing layer names**; the `EIOS / GEN / PROM / CIO / EXEC`
  identifiers remain **canonical internally** and stable.
- Use the product names externally; **internal specs continue using `EIOS / GEN / PROM / CIO / EXEC`
  for precision and traceability.** The two registers coexist; neither overrides the other.

## Naming map

```
Sudarshan
├── Adhara    = Foundation
├── Buddhi    = Cognitive Architecture
├── Tattva    = Reality Intelligence
├── Sphurana  = Opportunity Generation / Genesis
├── Nivesha   = Capital Allocation / Prometheus
├── Saarathi  = Personal CIO
├── Kriya     = Manual Execution
└── Anubhava  = Feedback / Learning
```

| Product name | Meaning (Sanskrit/Vedic) | Architecture layer | Internal ID / namespace |
|--------------|--------------------------|--------------------|--------------------------|
| **Sudarshan** | clear vision | the platform | **EIOS** |
| **Adhara** | foundation, support | Foundation (Part I) | `EIOS-000`…`EIOS-006` |
| **Buddhi** | intellect, cognition | Cognitive Architecture (Part II) | `EIOS-007`…`EIOS-009` |
| **Tattva** | reality, essence | Reality Intelligence (Part III) | `EIOS-010`…`EIOS-014` |
| **Sphurana** | emergence, flashing-forth | Opportunity Generation / Genesis (Part IV) | `GEN` |
| **Nivesha** | investment, placement | Capital Allocation / Prometheus (Part V) | `PROM` |
| **Saarathi** | charioteer, guide | Personal CIO (Part VI) | `CIO` |
| **Kriya** | action, doing | Manual Execution (Part VII) | `EXEC` |
| **Anubhava** | experience, learning from it | Feedback / Learning Loop | the upward Observation flow (EXEC-001 AR-1913) |

## Rules of use

- **External / product / investor:** prefer the product names (Sudarshan, Adhara, Buddhi, Tattva,
  Sphurana, Nivesha, Saarathi, Kriya, Anubhava). "Powered by EIOS" is the approved attribution.
- **Internal / engineering / specification:** continue to use `EIOS`, `GEN`, `PROM`, `CIO`, `EXEC`
  and the numbered chapter/AR/REQ identifiers. These are the traceability backbone and **do not
  change**.
- This naming layer **adds vocabulary; it renames nothing.** The Architecture Book remains the
  single source of truth, and its identifiers are authoritative for any architectural reference.
