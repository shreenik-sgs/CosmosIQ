# Part VIII — UI / Infinite Canvas (design note)

**Status:** design note · guidance only, NOT yet implemented · **Date:** 2026-06-30 · **Governed by:** ADR-0008 (purpose flows up, never down) + ADR-0010 (cognition–actuation boundary)

This note records architectural guidance for the future UI / **Infinite Canvas** layer (the
008 milestone). It is **guidance, not a build order** — do **not** implement UI until explicitly
instructed. It does not modify the Architecture Book and introduces no ADR.

## Priority sequence
`006 Saarathi / Personal CIO` → `007 Kriya integration cleanup` → `008 UI / Infinite Canvas MVP`.
The UI is built only after Saarathi (✓ accepted, 006) and the Kriya integration cleanup (007).

## What Part VIII is — an alpha decision cockpit, not a dashboard
The UI's job is to **expose Sudarshan's alpha reasoning chain visually** so the user can *inspect*
the reasoning, not just read a verdict. It is **not** a generic stock dashboard and must never be a
pretty surface that hides the reasoning.

**Load-bearing principle — evidence-linked.** Every major score, scenario, catalyst, bottleneck,
projection, and recommendation must be **traceable back to a source object and its provenance chain**
(Observation → IA → OH → Thesis → Action → PersonalizedAction). The UI is a *view over the canonical
reasoning objects*; it originates no reasoning of its own (ADR-0008: it never injects purpose
downward).

## UI acceptance standard
The UI is accepted only if it lets the user see, each evidence-linked to its source:
- what changed in reality · why the opportunity exists · why it may be early · where the bottleneck is ·
  who captures the economics · whether the financial inflection is real · whether the market already
  priced it in · whether the stock has asymmetry · whether technical timing confirms · what could kill
  the thesis · whether the action is personally suitable.

## Cross-cutting boundary rules (load-bearing)
- **Security mapping appears only AFTER winner mapping.** The ticker is never the starting point; the
  user reaches a security through theme → bottleneck → value chain → winner.
- **Speculative rumor is visually separated from confirmed/probable catalysts.** A rumor may raise
  *monitoring priority* but must **never visually inflate thesis confidence**.
- **The UI must not invent TAM or market share.** If TAM/share is not supplied or evidence-inferred,
  label it **missing / manual / low-confidence**.
- **Timing-confirmation language, not action-ready language** (Nivesha/technical panels).
- **The personalized panel may show sizing-range % and max-exposure %, never broker orders, exact share
  quantities, exact contracts, or execution instructions** (ADR-0010).
- **Kriya is manual execution only — no automated broker submission.**
- The UI must distinguish **good company vs good thesis vs good stock vs asymmetric stock.**

## Panels (each bound to its source layer/object)

1. **Opportunity map** — theme, megatrend context, why-now, why-before-obvious, opportunity timing,
   opportunity maturity, false-positive risk, bubble/hype-cycle risk, monitoring signals.
   *Source:* Sphurana / Opportunity Hypothesis.

2. **Value-chain graph** — value-chain layers; Tier 1 direct beneficiaries, Tier 2 suppliers, Tier 3
   supplier-of-supplier, Tier 4 enabling constraints; upstream dependencies; downstream demand; economic
   capture points; dependency edges; substitution difficulty; margin-capture potential; pricing power;
   capital intensity. *Source:* Nivesha / Value Chain Graph.
   *Behavior:* graph view · layer view · player cards · click a node → evidence, confidence, risks,
   suppliers/customers.

3. **Players by value layer** — role in value chain, directness of exposure, bottleneck leverage,
   margin-capture ability, pricing power, competitive position, execution capability,
   financing/dilution risk, customer concentration, winner score, key risks.
   *Source:* Nivesha / Winner-Loser Mapping. *(Security mapping only AFTER winner mapping.)*

4. **Bottlenecks / chokepoints** — bottleneck type, constrained node, severity, duration, resolution
   risk, direct beneficiaries, indirect beneficiaries, constrained losers, timing window, evidence
   quality (power/energy, grid interconnect, manufacturing capacity, component scarcity, permitting,
   land/site, construction/labor, capital availability, customer demand, regulatory).
   *Source:* Nivesha / Bottleneck Analysis.
   *Behavior:* severity heatmap · bottleneck timeline · beneficiary/loser mapping · "what resolves this
   bottleneck?" section.

5. **Supplier analysis** — direct suppliers, supplier-of-supplier exposure, capacity constraints,
   dependency risk, substitution risk, margin capture at each tier, critical supplier concentration,
   who benefits if the bottleneck persists, who loses if it resolves.
   *Source:* Nivesha / Value Chain + Bottleneck + Winner Mapping.

6. **TAM, market share & share-gain runway** — current TAM, projected TAM, company current revenue,
   implied market share, potential share under bear/base/bull/extreme-bull, revenue runway,
   capacity-constrained revenue potential, share-capture assumptions, TAM assumption provenance,
   sensitivity to TAM growth and share capture. *Source:* Nivesha / Financial Inflection + Asymmetry.
   *(Must not invent TAM/share — label missing/manual/low-confidence.)*

7. **Moat / defensibility** — physical moat, power/site control, supply access, customer lock-in,
   switching cost, scale advantage, regulatory advantage, cost advantage, technology advantage,
   data/learning advantage, execution/leadership placeholder, moat durability, moat erosion risks.
   *Source:* Nivesha / Winner Mapping + Red Team.

8. **Catalyst panel** — positive and negative catalysts shown **separately**. Positive: imminent
   contract, customer win, strategic partnership, offtake, capacity reservation, energization
   milestone, regulatory award, product launch, guidance raise. Negative: stock offering, ATM, shelf
   registration, convertible debt, warrant overhang, refinancing pressure, debt maturity, cash-runway
   risk, dilution risk, insider selling/registration overhang. Per catalyst: confirmed/probable/
   possible/speculative-rumor, expected timing window, expected business impact, expected financial
   impact, market recognition level, evidence quality, confirming signals, disconfirming signals,
   monitoring priority. *Sources:* Tattva / Catalyst Signals · Sphurana / why-now · Nivesha /
   Repricing Trigger + Red Team. *(Rumor visually separated; never inflates confidence.)*

9. **Financial inflection panel** — revenue acceleration, backlog/contracted demand, guidance change,
   margin expansion, operating leverage, EBITDA/cash-flow inflection, capex burden, cash runway,
   debt/financing constraint, dilution risk, unit economics, customer concentration, timing of
   financial recognition. *Source:* Nivesha / Financial Inflection.

10. **Bear / base / bull / extreme-bull projections** — per scenario: revenue assumptions, margin
    assumptions, valuation multiple, market-share assumption, TAM assumption, dilution assumption,
    probability, implied value, upside/downside, sensitivity drivers, invalidation triggers.
    *Source:* Nivesha / Stock-Price Asymmetry. *(Distinguish good company / good thesis / good stock /
    asymmetric stock.)*

11. **Technical confirmation panel** — EMA 9/20/50/200, EMA stack status, EMA slope alignment,
    compression/base duration, breakout level, volume confirmation, relative strength, VWAP/anchored
    VWAP, failed-breakout risk, invalidation level, overhead-supply risk, dilution/ATM overhang impact.
    *Source:* Nivesha / Technical Inflection. *(Use timing-confirmation language, not action-ready.)*

12. **Repricing trigger panel** — catalyst score, financial inflection score, market recognition
    score, asymmetry score, technical trigger score, repricing probability, repricing timing window,
    key trigger events, invalidation conditions, monitoring signals.
    *Source:* Nivesha / Repricing Trigger Setup.

13. **Red-team panel** — why this may not be a 10x, what could kill the thesis, bottleneck resolves
    too soon, company fails to capture economics, dilution destroys upside, valuation already prices
    upside, theme already crowded, bubble/hype-cycle analog, catalyst does not materialize, financial
    inflection fails, technical breakout fails. *Source:* Nivesha / Red Team Review.

14. **Personalized action panel** (after Saarathi, ✓ 006) — recommendation status, suitability score,
    concentration score, liquidity score, risk-fit score, portfolio-fit score, suggested sizing range
    %, recommended max exposure %, blocking conditions, risk warnings, monitoring signals, required
    user confirmations. *Source:* Saarathi / Personal CIO. *(Sizing range % only — no broker orders,
    exact shares, exact contracts, or execution instructions.)*

15. **Manual execution panel** (only after 007 Kriya integration cleanup) — user confirmation
    checklist, stale-check status, manual ticket preview (if approved downstream), broker_order_id
    input, fill recording, reconciliation status, audit trail. *Source:* Kriya. *(Manual execution
    only — no automated broker submission.)*

## Mapping summary (panel → source layer/object)
| Panels | Source layer |
|---|---|
| 1 | Sphurana / Opportunity Hypothesis |
| 2–7, 9–13 | Nivesha / Investment Thesis stage results (value chain, bottleneck, winner mapping, financial inflection, asymmetry, technical, repricing, red team) |
| 8 | Tattva (catalyst signals) + Sphurana (why-now) + Nivesha (repricing/red-team) |
| 14 | Saarathi / Personalized Action |
| 15 | Kriya / manual execution objects |

Every panel renders **structured fields already produced and provenance-bound** by the layers above; the
UI adds visualization, not reasoning.
