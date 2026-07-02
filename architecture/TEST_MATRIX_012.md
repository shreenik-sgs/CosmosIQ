# TEST MATRIX — 012

Status: **Draft for architect review** · Companion to `ARCHITECTURE_CONTRACT_012.md`,
`AGENT_MAP_012.md`, `HANDOFF_CONTRACT_012.md`. Extends `TEST_MATRIX_011.md` (its global guardrail rows
28–35 still apply to every 012 slice).

Required tests for Phase 012. Every row must exist and pass — **offline, deterministic, fixture/mock
only** — before a slice touching its area is accepted. Owner slice = where the row is added.

## A. Handoff-object contracts
| # | Test | Owner |
|---|------|-------|
| A1 | RealityEvent / AgentFinding / HandoffEnvelope / RealitySignal / SignalCluster / ThemePulse / OpportunityHypothesisPacket / DiligenceInputBundle all construct; frozen; defaults | 012A |
| A2 | no numeric investability/score/rank/rating field on ANY handoff object (label-only) | 012A |
| A3 | every object preserves `evidence_refs`/`source_refs`, `conflicts`, `data_gaps`; missing → explicit gap | 012A |
| A4 | HandoffEnvelope carries `allowed_/forbidden_downstream_uses`; forbidden always includes order/broker/auto-execute/buy-sell/hidden-score | 012A |
| A5 | timestamps injectable; no wall-clock in id/replay path; two builds byte-identical | 012A |

## B. Agent registry & discipline
| # | Test | Owner |
|---|------|-------|
| B1 | every agent has a stable `agent_id`, one layer, one discipline, typed consume/emit | 012B |
| B2 | a discipline agent emits `AgentFinding` (or foundation/governance record) ONLY — never signal/opportunity/thesis/order/buy-sell | 012B |
| B3 | SensorAgent interface: consumes RealityEvent → emits AgentFinding within its discipline scope | 012B |
| B4 | Buddhi router wraps every cross-layer transfer in a HandoffEnvelope with correct allowed/forbidden uses | 012B |
| B5 | boundary agent blocks an agent that tries to emit outside its contract (violation is caught) | 012B |

## C. Tattva Signal Fusion
| # | Test | Owner |
|---|------|-------|
| C1 | findings+events → RealitySignal/SignalCluster; no thesis/buy-sell produced | 012C |
| C2 | contradictions preserved (a contradicting finding is NOT averaged away; `contradiction_status` set) | 012C |
| C3 | weak signal stays weak (no corroboration → not upgraded); corroboration marks `corroborated` | 012C |
| C4 | half-life/freshness applied; stale finding marked stale, not silently dropped | 012C |
| C5 | X/social (rumor) never becomes verified_fact; needs corroboration for high-confidence | 012C/H |

## D. Sensor agents (fixture-backed)
| # | Test | Owner |
|---|------|-------|
| D1 | Market Regime Agent → MarketRegimeFinding from fixtures; labels only; no trade | 012D |
| D2 | Sector Rotation + Theme Rotation Agents → findings from fixtures; theme movement/ignition/exhaustion as labels | 012E |
| D3 | News/Filings/Press-Release Agent → NewsFilingFinding (8-K/S-3/insider/guidance); dilution risk flagged; company_claim marked | 012G |
| D4 | X/Social Narrative Agent → NarrativeFinding, authority=rumor, weak-signal-only, corroboration-required, bot/promoter flagged | 012H |
| D5 | each sensor agent stays within discipline (no cross-discipline conclusions); missing input → gap | 012D–H |

## E. Sphurana Theme Pulse
| # | Test | Owner |
|---|------|-------|
| E1 | SignalClusters → ThemePulse with a valid `state` (Dormant…Data insufficient) | 012F |
| E2 | contradicting signals preserved on the pulse; conflicted → `Conflicted`/`Data insufficient` | 012F |
| E3 | OpportunityHypothesisPacket carries required_diligence_questions + supporting/contradicting refs; no final decision | 012F |

## F. Nivesha forward scenario
| # | Test | Owner |
|---|------|-------|
| F1 | Forward-Scenario engine builds base/upside/downside/delay/dilution scenarios from evidence-backed inputs only | 012I |
| F2 | insufficient inputs → honest limited thesis (Nivesha semantics unchanged; not padded); prometheus reasoning untouched | 012I |
| F3 | no new score/rank; red-team + timing preserved as labels | 012I |

## G. Data Quality + Economic Universe integration
| # | Test | Owner |
|---|------|-------|
| G1 | signals/pulses surface as evidence (labels + gaps + provenance + conflicts), not a ranking | 012J |
| G2 | every rendered `data-intel` resolves; no dead anchors; no centre hub | 012J |
| G3 | pulse mode is a distinct, honestly-labelled mode; no silent fallback to demo; demo default byte-identical | 012J |
| G4 | Data-Quality data-actions only (never trade recs); no key in HTML | 012J |

## H. CLI / operator + E2E
| # | Test | Owner |
|---|------|-------|
| H1 | `tattva_pulse` (or `--mode pulse`) requires explicit watchlist/themes; manual/on-demand; no scheduler | 012K |
| H2 | full pulse chain (fixtures): sources → Adhāra → sensor agents → fusion → Sphurana → Nivesha → Saarathi → Kriya preview → Anubhava, honest & gap-visible, broker_order_id None | 012K |
| H3 | operator docs commands actually build (offline) | 012K |

## I. Global guardrails (rerun EVERY slice — from TEST_MATRIX_011 §28–35 + 012)
| # | Test |
|---|------|
| I1 | whole suite OFFLINE under a socket kill-switch (no network in tests) |
| I2 | no secrets/API keys in any generated HTML; no `.env` committed |
| I3 | **no scheduler / background job / streaming / automated refresh / automated trading** |
| I4 | no broker automation / order placement / routing / recording |
| I5 | no `<button>`/`<form>`/`onclick`/`type=submit`/place-order/buy/sell affordance |
| I6 | no new `def *score`/`*rank`/`*rating`; no numeric investability metric |
| I7 | conflicts / weak signals / data gaps preserved end-to-end (no averaging, no laundering) |
| I8 | source authority preserved (SEC wins; manual never canonical; rumor never verified_fact) |
| I9 | demo default byte-identical; real/enriched/pulse modes explicit; no silent demo fallback |
| I10 | deterministic (same fixtures + injected `now` → byte-identical); Anubhava append-only |

## Notes
- Structural over brittle: reuse AST guards, the 010G `HtmlLinkGraph`, authority-rank comparisons,
  and label-vocabulary membership checks; avoid exact-string over-fitting.
- Mock/fixture only; injected `now`; never a live endpoint. New real transports (if any) go behind an
  explicit pulse via a single lazily-imported boundary, never exercised in tests.
