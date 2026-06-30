# Sudarshan

**Clear vision for decisive capital action.**

*Powered by EIOS.*

Sudarshan is an Economic Intelligence Operating System: it understands reality, discovers emerging
asymmetric opportunities before they become obvious, turns them into disciplined capital
allocation, personalizes that guidance to one investor, and supports gated, fully auditable
**manual** execution — then learns from what actually happened.

## The layers

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

**Sudarshan** is the user-facing product name; **EIOS** is the internal architecture and engine.
The Sanskrit names are the product-facing layer names; the internal architecture continues to use
`EIOS / GEN / PROM / CIO / EXEC` and its numbered identifiers for precision and traceability. See
[`docs/product/BRAND_NOMENCLATURE.md`](docs/product/BRAND_NOMENCLATURE.md).

## Repository

- **`architecture/EIOS_Architecture_Book.md`** — the canonical source of truth (the Architecture
  Book). Everything in `specification/` is generated from it.
- **`specification/`** — the compiled architecture (Parts I–VII), normative.
- **`implementation/`** — implementation artifacts, beginning with **manual execution** (`Kriya`).
- **`src/` · `tests/`** — the first runtime scaffold: a vertical slice from observation to gated
  manual execution and back, with the manual-execution safeguards under test.
- **`docs/`** — product and developer documentation.

Trades are placed **manually by the user**; the system prepares, validates, gates, records,
reconciles, audits, and learns — it never submits orders to a broker.
