# DATA-SOURCE-001 — Ingestion Source Authority Plan (design note)

**Status:** planning / design note · guidance only, NOT yet implemented · **Date:** 2026-06-30 · **For:** the future **009 — Evidence Ingestion** layer (automated fetching that feeds Tattva's manual-MVP Observation intake) · **Governed by:** ADR-0008 (operational reality flows up as Observation; purpose never flows down)

> **Provenance note:** this file did not previously exist in the repo; it is created here to record the source-authority assumptions for 009. It is guidance only — do **not** build ingestion until explicitly instructed. No Architecture Book change, no ADR, no product-naming change.

## Core principle
**Use free/available sources aggressively, but preserve source authority and provenance.** Every
ingested **Observation** (the Tattva evidence object, see 002R) must carry: **source name · source
authority/order · timestamp (as_of) · confidence / evidence-quality · source class ∈ {canonical,
convenience, fallback, manual}**. When 009 is built, the 002R Observation format is extended with
`source_authority` and `source_class` (today it already carries `source_type`, `source_ref`,
`source_reliability`, `evidence_quality`, `novelty`, `as_of`). Authority is a property of the
*source*, distinct from the signal's strength.

## Sources (roles, allowed uses, restrictions)

### 1. SEC EDGAR / data.sec.gov — CANONICAL for filing-derived evidence
First-class in 009 ingestion. Canonical source of truth for: **10-K, 10-Q, 8-K, S-3, 424B, ATM /
shelf / offering disclosures, XBRL company facts, insider filings (Forms 3/4/5), 13F / institutional
filings, capital-structure & dilution evidence.** Free official APIs. FMP may be a *convenience copy*
of filing-derived data, but **SEC remains canonical** for anything derived from a filing.

### 2. FMP — first paid MVP convenience API (`convenience`)
Use for: financial statements · company profiles · shares / market cap · historical OHLCV · current
price · technical indicators (or raw data for internal indicator computation) · press releases / news
where available · ownership / institutional data where available · estimates where the plan supports
it. Programmatic, normalized — the primary *price/OHLCV/fundamentals* feed for the MVP. Convenience
authority for fundamentals/filings (SEC outranks it there).

### 3. yfinance — free prototype / fallback / sanity-check (`fallback` / `research-only`)
**Allowed:** exploratory notebooks · quick historical OHLCV checks · adjusted-price sanity checks ·
fallback comparison against FMP · development-time pulls · watchlist prototyping.
**Restrictions:** NOT an official source of truth · NOT the only production market-data input · NOT
canonical for filings, fundamentals, dilution, or company disclosures. **Label yfinance-derived data
low-authority / convenience / research-only unless cross-validated.**

### 4. TradingView — human charting cockpit (not a backend API)
Use as: human charting cockpit · alerting / watchlist tool · visual technical validation · UI
reference for the technical panels (see Part VIII). **Do not treat a normal TradingView subscription
as the backend data API** unless a supported export/API path is explicitly implemented.

## Source authority order (009 MVP)
| Category | Authority order (highest → lowest) |
|---|---|
| **Filings / disclosures** | SEC > company IR / filed exhibits > FMP convenience copy > other news |
| **Financial facts** | SEC XBRL > company reports > FMP normalized data > yfinance (sanity check only) |
| **Price / OHLCV / technicals** | FMP programmatic data > yfinance sanity-check fallback > TradingView visual validation |
| **Catalysts** | SEC 8-K / company IR > FMP news / press releases > other news > rumor |
| **Ownership / recognition** | SEC 13F / Forms 3-4-5 > FMP institutional/insider endpoints > yfinance (convenience, if applicable) |

These map onto the existing alpha discipline: SEC-confirmed filings are `confirmed`/`canonical`
catalysts and evidence; FMP news / other news degrade toward `probable`/`possible`; unsourced chatter
is `speculative_rumor` (raises monitoring priority only — never thesis confidence; see
[[alpha-chain-catalysts-technical-repricing]]).

## Subscription-gap report
**Already available:** TradingView subscription · FMP subscription · yfinance (free Python package) ·
SEC free official APIs.
**Assessment:** **likely no additional paid market/fundamental subscription is needed for the first
009 ingestion MVP** — SEC (canonical filings/fundamentals/ownership) + FMP (price/OHLCV/fundamentals
convenience) + yfinance (free fallback/sanity) + TradingView (human visual validation) cover the MVP
evidence surface. Re-evaluate only if a specific gap (e.g., real-time intraday, options chains,
estimate consensus depth) blocks a required 009 capability.

## How this feeds the system
- **Tattva (002R)** consumes ingested Observations; 009 replaces hand-fed structured inputs with
  fetched ones while preserving the same typed-signal contract. Authority/class ride on the
  Observation so downstream (Sphurana why-now, Nivesha repricing/red-team, Saarathi) can weight
  canonical vs convenience vs rumor exactly as today's manual `source_reliability` does.
- **Nivesha DiligenceInputs (004B)** financial/ownership/price fields become populated from SEC XBRL /
  FMP / yfinance per the authority order above, each tagged with its source class.
- **No autonomous fetching exists yet** (002R/004B/006 are all manual-MVP). 009 is where adapters are
  built — only when explicitly instructed.

## Sequence
… → 008 UI / Infinite Canvas → **009 Evidence Ingestion** (this plan). Do not implement until directed.
