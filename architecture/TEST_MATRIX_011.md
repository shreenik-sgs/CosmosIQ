# TEST MATRIX — 011

Status: **Draft for architect review** · Companion to `GATE-011_BUILD_ACCEPTANCE_CHECKLIST.md`.

The required tests for Phase 011. Every row must exist and pass (offline, deterministic, mocked/
fixtured) before a slice that touches its area is accepted. "Present since" notes rows already
covered by the accepted 010/011A suite (680 tests); "Owner slice" is where the row is expected to be
added/hardened. All tests: **no real network, no secrets, socket-safe**.

| # | Test | Assertion (in one line) | Present since | Owner slice |
|---|------|-------------------------|---------------|-------------|
| 1 | enrichment models construct | all 8 models build; defaults; everything-missing → data gaps | 011A | 011A/B |
| 2 | models carry no decision/score field | no buy/sell/hold/order/trade/score/rank/rating field | 011A | 011A/B |
| 3 | source authority explicit | every enrichment value has authority + claim_status | 011A | 011A/B |
| 4 | company_claim ≠ verified_fact | company statements stamped company_claim | 011A | 011A/B |
| 5 | manual ≠ canonical | manual/analyst never ranks canonical (`assert_manual_not_canonical`) | 011A | 011A/B |
| 6 | SEC canonical over FMP | same metric/period/unit → SEC value kept, FMP overridden + warned | ≤010D | 011B |
| 7 | data gaps preserved | missing field → explicit gap, never invented | 011A | 011B/C |
| 8 | VisualEncoding semantics | size=magnitude (visual_size); decoupled from ranking/heat; no new metric | 010B/F | 011C |
| 9 | Nivesha handoff adapter | enrichment→Nivesha inputs; no fabricated field; gaps stay gaps; no new score | — | 011D |
| 10 | no credentials | missing SEC UA / FMP key → visible gap, no leak, no crash | 010D | 011B |
| 11 | SEC-only | build with SEC canonical only; FMP/yfinance absent → gaps visible | ~010D | 011B |
| 12 | SEC + FMP mocked | canonical + convenience populate; authority preserved | 010D | 011B |
| 13 | multi-ticker watchlist | one merged terrain; companies as nodes; no centre; endpoints resolve | 010E | 011C |
| 14 | failed ticker | recorded + visible failure diagnostic; run continues; not dropped | 010E/F | 011C |
| 15 | missing market cap | neutral size + dashed + gap + data action | 011A | 011B/C |
| 16 | missing TAM | gap + data action; manual TAM stays manual | 011A | 011B/C |
| 17 | missing value chain | gap + data action; layers absent honestly | 011A | 011B/C |
| 18 | missing bottleneck | gap + data action; placeholder/constraint-context only | 011A | 011B/C |
| 19 | missing IR / transcript | gap + "add investor presentation / transcript" action | 011A | 011B/C |
| 20 | missing supplier/customer | gap + "add supplier/customer source" action; no invented moons | 011A | 011B/C |
| 21 | missing leadership evidence | gap + "add leadership/capital-allocation source" action | 011A | 011B/C |
| 22 | universe render | universe.html builds from terrain; hero + below-fold pane | 010A–G | 011C |
| 23 | dashboard render | per-company candidate cards; Locate + Open-Cockpit; no buy/sell | 010A/E | 011C |
| 24 | Data Quality render | pipeline + matrix + status + coverage + diagnostics + enrichment panel | 010D–011A | 011B/C |
| 25 | cockpit render | via accepted render_cockpit_html; conditional; broker_order_id None | 009G/010 | 011C |
| 26 | every data-intel resolves | all data-intel → intel-store id (single + watchlist) | 010A/G | 011C |
| 27 | no dead anchors | href/#focus/#path/target-path all resolve or are known-safe | 010G | 011C |
| 28 | no secrets | no api key in any generated HTML; none printed; none committed | 010D | all |
| 29 | no scheduler | no scheduler/background-job/automated-refresh import or path | all | all |
| 30 | no broker | no broker automation/order placement/routing/recording | all | all |
| 31 | no buy/sell/order/submit | no such affordance (button/form/onclick/submit) in HTML | all | all |
| 32 | no new score/rank functions | no `def *score`/`*rank`/`*rating`; no numeric investability metric | all | all |
| 33 | offline suite | whole suite passes under a socket kill-switch | 010D+ | all |
| 34 | demo default byte-identical | two demo builds identical; demo carries no real/enrichment panels | 010+ | all |
| 35 | real single + watchlist still build | both modes build a closed-graph terrain | 010D/E | all |
| 36 | end-to-end integration | on-demand (mock) → ingest → Tattva → Sphurana → Nivesha → Saarathi → Kriya → terrain → render, honest & gap-visible | — | 011E |

## Notes

- **Structural over brittle**: prefer reusable helpers (e.g. the 010G `HtmlLinkGraph`, AST guards,
  authority-rank comparisons) over exact-string assertions, so tests are not over-fitted.
- **Mock transports**: real-mode rows use injected `transports` / `transports_by_ticker` + an
  injected `now`; never a live endpoint.
- **Determinism**: same inputs + injected `now` ⇒ byte-identical output (real-mode timestamp
  injectable).
- Rows 28–35 are **global guardrails** — re-run for every slice, not just its owner.
