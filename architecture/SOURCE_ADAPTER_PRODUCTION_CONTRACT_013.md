# SOURCE ADAPTER PRODUCTION CONTRACT — 013

Status: **Draft for architect review** · Companion to `SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md`,
`SECURITY_POLICY_CONTRACT_013.md`. Defines the production source-adapter interface. **No runtime code
and no production network path exist yet** — this is the contract any future adapter must satisfy.

Source adapters emit **`RealityEvent`s only** (never `AgentFinding`s — they observe, they do not
interpret). They live in the source/ingestion plane and never bypass provenance.

## 1. SourceAdapterDescriptor
| field | type | semantics |
|---|---|---|
| `adapter_id` | str | stable id |
| `source_name` / `source_type` | str | e.g. "SEC EDGAR" / "filing"; "FMP" / "market_data"; "X" / "social" |
| `source_authority` | label | canonical / primary / convenience / fallback / manual / rumor |
| `credential_requirements` | Tuple[str] | env var names required (never values) |
| `network_required` | bool | true → only runs behind an explicit real pulse (never on import, never in tests) |
| `rate_limit_policy` | str/label | how the adapter self-limits |
| `outputs` | Tuple[label] | RealityEvent event_types it produces |
| `claim_status_rules` | Tuple[str] | how it stamps claim_status per output (see §3) |
| `failure_modes` | Tuple[label] | credentials_missing / rate_limited / source_unavailable / parse_error |

## 2. SourceAdapterResult
| field | type | semantics |
|---|---|---|
| `adapter_id` / `run_id` | str | which adapter / pulse |
| `status` | label | success / partial / failed / skipped |
| `raw_payload_refs` | Tuple[ref] | pointers into RawSourceStore (never inlined payloads) |
| `events_created` | int | RealityEvents produced |
| `warnings` / `errors` | Tuple[str] | non-fatal / fatal (no secrets) |
| `credentials_status` | label | present / missing (boolean-ish label; never the value) |
| `rate_limit_status` | label | ok / throttled / exhausted |
| `source_health` | label | healthy / degraded / failed / rate_limited / source_unavailable |

## 3. Rules
```
source adapters emit RealityEvents, not AgentFindings
credentials never printed; never written to HTML; env-only
source failure becomes a gap (never a fabricated value; never a silent demo fallback)
source authority is explicit and assigned immediately
company IR = company_claim unless independently verified
X/social = weak / narrative / rumor / crowding — never verified_fact
manual input = manual/analyst — never canonical
raw payloads are captured (RawSourceStore) before interpretation
```

## 4. Production onboarding sequence (for EVERY source)
A source is promoted through these stages in order — a production network path is the LAST step, only
after everything before it is green:
```
1. fixture parser            (offline, deterministic; parses a saved sample)
2. manual/on-demand adapter  (behind an explicit pulse; no scheduler)
3. mocked tests              (network mocked; suite stays offline)
4. rate-limit / failure tests(credentials-missing, throttled, unavailable → gaps, not crashes)
5. Data Quality integration  (coverage/gaps/authority surfaced)
6. production network path    ← only now, and only behind an explicit real pulse
```
This mirrors how 009/010/011 onboarded SEC/FMP/yfinance: fixtures and mocks first, a single lazy
network boundary, offline tests throughout, credentials env-only. No source skips ahead.

## Cross references
`SPEC-013_AGENT_RUNTIME_PRODUCTION_READINESS.md` · `SECURITY_POLICY_CONTRACT_013.md` ·
`DATA_QUALITY_GATE_CONTRACT_013.md` · `PERSISTENCE_REPLAY_CONTRACT_013.md` (RawSourceStore/EventStore)
· (012) `ARCHITECTURE_CONTRACT_012.md` §C/§H.
