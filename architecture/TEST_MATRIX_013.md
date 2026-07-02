# TEST MATRIX — 013

Status: **Draft for architect review** · Companion to the SPEC-013 contracts. Extends
`TEST_MATRIX_012.md` (its §I global guardrails still apply to every 013 slice). Tests for FUTURE
implementation — every row must exist and pass **offline, deterministic, fixture/mock only** before a
slice touching its area is accepted. Owner slice noted.

## A. Runtime object tests
| # | Test | Owner |
|---|------|-------|
| A1 | PulseRun / AgentRunContext / AgentRunResult / AgentHealthRecord / ReplayRequest / ReplayResult construct; frozen; defaults | 013A |
| A2 | PulseRun.trigger_type accepts `manual`; **`scheduled`/`streaming` rejected (reserved)** | 013A |
| A3 | AgentRunContext.network_allowed False in tests; no `broker_allowed` true / no order/score field | 013A |
| A4 | AgentRunResult.status ∈ {success,partial,failed,skipped,blocked_by_policy}; no trade/score field | 013A |
| A5 | counts are volumes; no investability/score/rank field on any runtime object | 013A |

## B. Store contract tests
| # | Test | Owner |
|---|------|-------|
| B1 | RunStore / EventStore / FindingStore / SignalStore / ThemePulseStore / DataQualityStore / AuditStore append + read | 013B |
| B2 | EventStore/FindingStore/SignalStore query by run / ticker / theme / window | 013B |
| B3 | schema_version preserved on every record | 013B |
| B4 | **append-only** — a historical record is never mutated; a correction is a new AuditStore record | 013B |
| B5 | no secret / raw credential / score-rank field in any stored record | 013B |

## C. Replay tests
| # | Test | Owner |
|---|------|-------|
| C1 | replay by run_id / ticker / theme / time-window | 013C |
| C2 | same fixture inputs + schema + code → deterministic outputs (`deterministic_match=True`) | 013C |
| C3 | conflicts preserved through replay | 013C |
| C4 | data gaps preserved through replay | 013C |
| C5 | source refs + raw payload refs preserved; forbidden uses preserved | 013C |

## D. Agent runtime tests
| # | Test | Owner |
|---|------|-------|
| D1 | agent run logged to AgentRunLedger | 013D |
| D2 | **one failed agent does not crash the run** (failure isolated → health record + gap) | 013D |
| D3 | agent timeout recorded (not a crash) | 013D |
| D4 | agent skipped recorded | 013D |
| D5 | blocked_by_policy recorded (policy gate refusal) | 013D |

## E. Observability tests
| # | Test | Owner |
|---|------|-------|
| E1 | RunHealthSummary renders (agents/sources/gaps/conflicts) | 013D |
| E2 | AgentHealthRecord created; failed agent visible | 013D |
| E3 | SourceHealthRecord created; failed source visible | 013D |
| E4 | a degraded/partial run still produces Data Quality | 013D |

## F. Data Quality gate tests
| # | Test | Owner |
|---|------|-------|
| F1 | **X/social verified_fact fails** | 013E |
| F2 | **manual/analyst canonical fails** | 013E |
| F3 | hidden score/rank field fails | 013E |
| F4 | buy/sell/order field/affordance fails | 013E |
| F5 | API key in output fails; network-on-import fails | 013E |
| F6 | **real/pulse mode silently using demo data fails** | 013E |
| F7 | missing data filled without source fails | 013E |
| F8 | scheduler/broker/streaming added fails (guardrail gate) | 013E |

## G. Source adapter tests (no production network)
| # | Test | Owner |
|---|------|-------|
| G1 | fixture parser works (offline) | 013F (or 014) |
| G2 | credential missing → visible gap (not a crash/leak) | 013F |
| G3 | rate-limit status captured; source failure captured | 013F |
| G4 | raw payload ref preserved; source authority preserved | 013F |

## H. UI / product integration tests
| # | Test | Owner |
|---|------|-------|
| H1 | Data Quality shows run health / source health / agent health | 013F |
| H2 | Data Quality shows replay link/metadata | 013F |
| H3 | Economic Universe can show latest pulse summary; Cockpit shows signal history **without a trade action** | 013F |
| H4 | every rendered `data-intel` resolves; no dead anchors | 013F |

## I. Guardrail tests (rerun EVERY slice)
| # | Test |
|---|------|
| I1 | no scheduler / background daemon / streaming process |
| I2 | no broker automation / order placement |
| I3 | no buy/sell/order/submit affordance |
| I4 | no hidden score/rank/investability metric |
| I5 | no secrets in output/commits; `.env` not tracked |
| I6 | no network on import; whole suite offline (socket kill-switch) |
| I7 | demo remains DEFAULT and byte-identical; pulse/real modes explicit; no silent demo fallback |
| I8 | source authority preserved (SEC wins; manual never canonical; rumor never verified_fact) |
| I9 | deterministic (injected `now`; byte-identical); append-only stores; correction-not-mutation |
| I10 | existing 010 / 011 / 012 paths remain green |

## Notes
Structural over brittle: reuse the AST guards, socket kill-switch, `HtmlLinkGraph`, authority-rank
comparisons, and label-vocabulary checks. Mock/fixture only; injected `now`; never a live endpoint —
any future production network path stays behind an explicit real pulse and is never exercised in the
suite.

## Cross references
`SPEC-013_…READINESS.md` · `RUNTIME_CONTRACT_013.md` · `PERSISTENCE_REPLAY_CONTRACT_013.md` ·
`OBSERVABILITY_CONTRACT_013.md` · `DATA_QUALITY_GATE_CONTRACT_013.md` ·
`SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md` · `SECURITY_POLICY_CONTRACT_013.md` ·
`IMPLEMENTATION_PLAN_013.md` · (012) `TEST_MATRIX_012.md`.
