# End-to-End Evidence-to-Candidate Trial -- IMPLEMENTATION-020H

Filled from the PERSISTED append-only stores of ONE actual end-to-end trial driven by `cosmosiq_ops.e2e_trace.run_e2e_trial`. Every id below is a real persisted record read back from the stores -- never invented. The candidate outcome is whatever HONESTLY occurred; nothing is forced.

> HONESTY: no live SEC fetch (SEC_USER_AGENT unconfigured -> visible source gap); the evidence is LOCAL research fixtures, labelled NOT-live / NOT-canonical; a Capital Candidate is never fabricated.

---

## 0. Run identity

| Field | Value |
|-------|-------|
| Run id (persisted) | `e2e.20260629T143000Z` |
| Mode | `pulse` |
| Injected now | 2026-06-29T14:30:00Z |
| Report prepared at (injected) | 2026-06-29T14:30:00Z |
| Store dir | `reports/e2e_020h/store` |
| Watchlist (monitored input, NOT a recommendation) | IREN, AAOI, INOD |
| Themes | ai-infrastructure, power-and-grid, optical-networking, physical-ai, space-and-defense |
| Focus ticker (strongest evidence -- canonical signal) | IREN |
| Fixture source | `/Users/srinivaskodavatiganti/Desktop/SGS Investing/SGS Genesis/tests/fixtures/reality_mesh/pulse` |

## 1. What source data came in -- authority, claim status, freshness

| Source | Authority | Claim status | Freshness | Provenance | Note |
|--------|-----------|--------------|-----------|------------|------|
| `offline_pulse_fixtures` | mixed (per-event: canonical / convenience / rumor -- see the signal ledger) | fixture-backed inputs modelling primary filings, market data + social | static (injected now; NOT a live measurement) | repo LOCAL offline fixtures (tests/fixtures/reality_mesh/pulse) -- NOT live, NOT a network fetch | 16 event(s) loaded into this pulse |
| `evidence.sec_edgar_live` | would be canonical / primary-regulatory IF fetched | skipped | n/a -- no live fetch was made | SEC EDGAR live adapter, credentials_missing (SEC_USER_AGENT absent) | VISIBLE source gap: no live SEC fetch, no fixture fall-back, nothing fabricated |
| `local_research_diligence_fixture` | local research fixture (offline) | research inputs to the accepted diligence engines (thesis is real) | static (injected deterministic instant) | runtime.vertical_slice_runner bundled research fixture -- NOT live, NOT canonical | the produced InvestmentThesis is real; its INPUTS are labelled research fixtures |

SEC EDGAR live source health: **credentials_missing** (configured=no, status=skipped, events_created=0). SEC gap detail:
- SEC_USER_AGENT missing (presence flag false): SEC EDGAR live fetch skipped this pulse -- filings have NO coverage; visible gap (credentials_missing), nothing fabricated, no silent fixture/demo fallback

## 2. What RealityEvents, findings and RealitySignals were produced

| Stage | Count | Sample persisted ids |
|-------|-------|----------------------|
| RealityEvents (inputs agents saw) | 16 | `pulse.mr.advdecl`, `pulse.mr.breadth`, `pulse.mr.smallcap`, `pulse.mr.volatility`, `pulse.narr.rumor.oust.buyout`, `pulse.narr.theme.robotics` |
| AgentFindings (per-agent, in-discipline) | 9 | `finding.market_regime.breadth_improvement`, `finding.market_regime.risk_on`, `finding.market_regime.small_cap_risk_appetite`, `finding.narrative.rumorfinding.oust`, `finding.narrative.themenarrativevelocityfinding.robotics`, `finding.news_filings.contract_validation.iren` |
| RealitySignals (fused) | 6 | see the signal ledger below |
| SignalClusters (multi-signal) | 0 | none -- no multi-signal cluster formed this run (honest) |

Signal ledger (authority / freshness / corroboration are honest per-signal labels):

| Signal id | Discipline | Companies | Themes | Authority | Freshness | Corroboration |
|-----------|------------|-----------|--------|-----------|-----------|---------------|
| `sig.market-regime.discipline.market-regime` | market_regime | - | - | convenience | fresh | uncorroborated |
| `sig.narrative.company.oust` | narrative | OUST | - | rumor | fresh | uncorroborated |
| `sig.narrative.theme.robotics` | narrative | - | robotics | rumor | fresh | uncorroborated |
| `sig.news-filings.company.iren` | news_filings | IREN | - | canonical | fresh | uncorroborated |
| `sig.sector-rotation.sector.semiconductors` | sector_rotation | - | - | convenience | fresh | uncorroborated |
| `sig.theme-rotation.company.aaoi-amba-iren-oust` | theme_rotation | AAOI, AMBA, IREN, OUST | physical-ai | convenience | fresh | uncorroborated |

> A rumor/social signal stays rumor: it is labelled `rumor` + `uncorroborated` and can never be laundered into canonical evidence or a candidate.

## 3. Which ThemePulse changed (and which themes are Data insufficient)

| ThemePulse id | Theme | State | Breadth | Supporting signals |
|---------------|-------|-------|---------|--------------------|
| `pulse.semiconductors` | semiconductors | **Warming** | unknown | `sig.sector-rotation.sector.semiconductors` |
| `pulse.physical-ai` | physical-ai | **Broadening** | major | `sig.theme-rotation.company.aaoi-amba-iren-oust` |
| `pulse.robotics` | robotics | **Data insufficient** | unknown | `sig.narrative.theme.robotics` |

Requested themes that produced NO covering signal (honest **Data insufficient**): ai-infrastructure, power-and-grid, optical-networking, space-and-defense.

## 4. Was an OpportunityHypothesis created?

Yes -- the pulse's fused signals produced these OpportunityHypothesisPackets (a thing to TEST, never a thesis / decision / rank):

| Hypothesis id | For ThemePulse | Confidence | Beneficiary candidates |
|---------------|----------------|------------|------------------------|
| `hyp.semiconductors` | `pulse.semiconductors` | moderate | - |
| `hyp.physical-ai` | `pulse.physical-ai` | moderate | AAOI, AMBA, IREN, OUST |
| `hyp.robotics` | `pulse.robotics` | low | - |

## 5. Was Investment Diligence triggered? (input -> output)

| Ticker | Diligence produced? | Opportunity hypothesis ref | Investment diligence ref (thesis) | Investability | Forward | Provenance / gap |
|--------|---------------------|----------------------------|---------------------------|---------------|---------|------------------|
| IREN | yes | `OPH-418cfe5a625e68fd` | `THS-f35bc4b0da68f4d2` | thesis_worthy_timing_confirmed | present | diligence run over the bundled LOCAL RESEARCH FIXTURE (offline; real thesis, fixture inputs -- NOT live / NOT canonical) |
| AAOI | no | - | - | - | - | no diligence produced: no bundled research fixture / recorded diligence inputs for AAOI -- explicit gap, no thesis fabricated |
| INOD | no | - | - | - | - | no diligence produced: no bundled research fixture / recorded diligence inputs for INOD -- explicit gap, no thesis fabricated |

## 6. ForwardScenario state (or explicit gap)

Focus ticker forward-scenario state: **present**. forward inputs supplied with the diligence thesis -> forward scenario PRESENT (sidecar-only; never laundered into a present fact)

## 7. Was a CapitalCandidate published? Eligible or blocked -- and WHY

**Honest outcome: `all_blocked`.** every published candidate is blocked; verdicts: ineligible_missing_provenance, ineligible_stale. Focus ticker IREN: ineligible_stale -- full lineage present but the producing run's data quality is 'degraded' (not healthy) -- ineligible until a healthy current run confirms it

| Candidate id | Ticker | State | Eligible? | Signal refs | Hypothesis ref | Diligence ref | Trust/DQ | Exact basis / reason |
|--------------|--------|-------|-----------|-------------|----------------|-----------|----------|----------------------|
| `cc:e2e.20260629T143000Z:IREN` | IREN | ineligible_stale | no | 2 | `OPH-418cfe5a625e68fd` | `THS-f35bc4b0da68f4d2` | degraded | full lineage present but the producing run's data quality is 'degraded' (not healthy) -- ineligible until a healthy current run confirms it |
| `cc:e2e.20260629T143000Z:AAOI` | AAOI | ineligible_missing_provenance | no | 1 | - | - | degraded | no current-run provenance: opportunity_hypothesis_ref absent -- a candidate without the fused reality signals AND the opportunity-hypothesis packet can never be eligible |
| `cc:e2e.20260629T143000Z:INOD` | INOD | ineligible_missing_provenance | no | 0 | - | - | degraded | no current-run provenance: reality_signal_refs absent; opportunity_hypothesis_ref absent -- a candidate without the fused reality signals AND the opportunity-hypothesis packet can never be eligible |

Eligible: 0. Blocked: 3. Forged-eligible (MUST be 0): 0.

> Every candidate went through the store + the 019B eligibility gate. An eligible candidate is UNFORGEABLE without full real provenance AND a healthy producing run; a blocked candidate carries its EXACT missing-lineage reason -- nothing hidden, nothing fabricated.

## 8. Trust / Data-Quality verdict

Run `gate_overall`: **degraded**.

Degraded / failing gate categories (the honest reason a candidate off this run cannot be eligible):
- social_weak_signal: degraded (6 uncorroborated social/rumor record(s) -- weak by design, kept weak)

> DQ gates the run BEFORE any candidate can be eligible. A degraded run (e.g. carrying uncorroborated social/rumor records, kept weak by design) blocks every candidate at `ineligible_stale` -- the evidence lineage may be complete, but eligibility requires a healthy run.

## 9. Did any alert fire? (Shadow Mode -- inbox only)

| Alert id | Category | Severity | Review action | dq_state | Candidate ref | Marked Shadow? | Delivery |
|----------|----------|----------|---------------|----------|---------------|----------------|----------|
| (none) | - | - | - | - | - | - | - |

Shadow alerts: 0 (baseline first run: yes). Forbidden action-phrase hits (MUST be 0): 0. External delivery: no. Production escalation: no.

> Zero alerts on a first run is the HONEST answer: the diff-based engine has no prior run to diff against, so it stays quiet (it never floods a baseline).

## 10. Was replay successful?

Deterministic replay of the run: `deterministic_match = yes`. Differences: none.

## 11. Where in the app this renders (exact routes, dispatch-verified)

Launch the local operator app read-only with:

```
python3 -m cosmosiq_app --store-dir reports/e2e_020h/store
```

| Page / surface | Route | Dispatch status | Names focus ticker? |
|----------------|-------|-----------------|---------------------|
| Home / index | `/` | 200 | no |
| Runs list | `/runs` | 200 | no |
| Run detail (source health + agent health + DQ panel) | `/runs/e2e.20260629T143000Z` | 200 | yes |
| Trust / Data-Quality (JSON, gate_overall + dq records) | `/api/runs/e2e.20260629T143000Z` | 200 | yes |
| Source + agent health (JSON) | `/api/health` | 200 | no |
| Agent coverage / health (JSON) | `/api/coverage` | 200 | no |
| Capital Candidates page (blocked reason / empty state) | `/candidates` | 200 | yes |
| Company Cockpit for the focus ticker | `/companies/IREN` | 200 | yes |
| Capital-candidate cockpit for the focus ticker | `/candidates/IREN` | 200 | yes |
| Alert Inbox | `/alerts` | 200 | no |
| Replay Viewer | `/replay/e2e.20260629T143000Z` | 200 | no |

> The default product UI never leaks a fixture ticker: an EMPTY store renders `/`, `/runs` and `/candidates` clean. There is NO buy/sell/order/submit surface anywhere -- a trade-like path is refused (403) before routing.

## 12. Honesty caveats + data gaps (stated plainly)

- No live SEC fetch: SEC_USER_AGENT is unconfigured, so the SEC EDGAR live adapter ran only in its honest credentials_missing state -- a VISIBLE source gap, never fabricated, never a fixture fall-back dressed as live.
- The evidence comes from the repo's LOCAL research fixtures. Each source record is labelled with its REAL authority / claim / freshness: a local research fixture is NOT canonical and NOT live.
- No Capital Candidate is forced: a candidate is eligible ONLY with full REAL provenance (current run_id + RealitySignal refs + OpportunityHypothesis ref + Investment Diligence ref) AND a healthy Trust/Data-Quality state; otherwise it is blocked WITH its exact reason.
- Shadow mode only: alerts land in the in-app inbox, marked Shadow Mode -- no external delivery, no production escalation, no trade control on any surface.
- Deterministic + offline: injected now, deterministic run_id, no network; the SEC probe reached no endpoint.

Data gaps recorded on this pulse:
- institutional flow proxy missing (no flow_proxy input; not fabricated)
- no fixture coverage for theme 'ai-infrastructure' in this pulse -- honest gap, not fabricated (no signals; requires a real source)
- no fixture coverage for theme 'optical-networking' in this pulse -- honest gap, not fabricated (no signals; requires a real source)
- no fixture coverage for theme 'power-and-grid' in this pulse -- honest gap, not fabricated (no signals; requires a real source)
- no fixture coverage for theme 'space-and-defense' in this pulse -- honest gap, not fabricated (no signals; requires a real source)
- no fixture coverage for watchlist ticker INOD in this pulse -- honest gap, not fabricated (a real source would be required)
- rumor about OUST is uncorroborated -- requires primary/canonical confirmation before any use
- theme 'Semiconductors' is a narrow move: 0 participating member(s) -- not yet a broad theme (not Broadening)
- theme 'robotics' is a narrow move: 0 participating member(s) -- not yet a broad theme (not Broadening)
- theme 'robotics' is social-only narrative -- weak; NOT a high-confidence ignition; needs corroboration by primary/canonical evidence
- uncorroborated X/social (rumor) -- weak, needs corroboration

