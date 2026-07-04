# Operator Guide — Portfolio Intelligence, READ-ONLY (Phase 018)

How to record what you hold and how to read the **`/portfolio`** page and the candidate
cockpit's **Candidate vs recorded portfolio** section. Everything in this phase is
**read-only intelligence over your own recorded statement**: the app never connects to any
external account, never imports positions from anywhere, never places or changes anything,
and never re-weights anything automatically. Phase-018 output is **bands, labels and volume
counts** — never a stored ratio, weight, or numeric correlation.

Governance: `docs/OPERATOR_GUIDE_016.md` (the app itself) · `docs/OPERATOR_GUIDE_013.md`
(persistence) · `docs/OPERATOR_GUIDE_017.md` (learning).

---

## 1. Record your holdings (by hand)

Write **`<store>/portfolio/holdings.json`** yourself — the app only ever READS it:

```json
{
  "as_of": "2026-06-30T00:00:00Z",
  "positions": [
    {"ticker": "IREN", "quantity": 100, "cost_basis": 15.0,
     "account_label": "taxable-main", "liquidity_note": "thin float"},
    {"ticker": "NVDA", "quantity": 10, "cost_basis": 100.0}
  ],
  "cash": 500
}
```

- `as_of` (required) — the instant YOUR statement describes. Compared (as a plain string)
  to the latest persisted pulse run: older → the page labels the whole statement **stale**.
- `positions` (required list) — each needs `ticker` + `quantity`; `cost_basis`,
  `account_label` and `liquidity_note` are optional. A position **without** a numeric
  `cost_basis` cannot be weighed: its band is honestly **unknown**, with a named gap.
- `cash` (optional) — counted into the recorded total when weighing.

Missing file → every portfolio surface says **"No holdings recorded"** and stays empty.
Malformed file → the parse/shape error is **named**; nothing is guessed.

## 2. Reading `/portfolio`

| Section | What it shows | Where it comes from |
|---|---|---|
| **Recorded holdings** | your statement verbatim + `as_of` + a freshness label (`current` / `stale` / `no run to compare`); per-position liquidity note or an honest **unknown** | the holdings file + the run store |
| **Exposure by theme** | which recorded positions the PERSISTED signals / theme pulses map to each theme, plus a combined-exposure **band** | signal + theme-pulse stores |
| **Concentration bands** | one **band** per position — `minimal` / `moderate` / `elevated` / `dominant` (or `unknown`) | `cost_basis × quantity` vs the recorded total, computed transiently; **only the band is kept** |
| **Co-exposure** | a **label** per pair — `co_exposed` / `partially_co_exposed` / `distinct` / `unknown` — from shared persisted-theme membership | the persisted ticker→theme mapping; **no numeric correlation exists** |
| **Rotation alignment** | each position vs the LATEST persisted theme-pulse state — `aligned` / `against` / `no_signal` | the theme-pulse store + a published state→alignment table |
| **Risk budget & sizing guardrails** | your STANDING limits (max single position %, max theme %, min cash reserve, drawdown tolerance, route limits) | the recorded `<store>/personal_profile.json` via the accepted Personal-CIO profile function; **honest absence** when none is recorded |

Band edges are published data (`PORTFOLIO_THRESHOLDS`): position bands at 5% / 10% / 20%
of the recorded total; combined theme bands at 10% / 25% / 40%. A weight AT an edge enters
the higher band.

## 3. Candidate vs recorded portfolio (`/candidates/<TICKER>`)

With holdings recorded, the candidate cockpit gains one comparison **label**:

- **`new_theme`** — every candidate theme is absent from your current exposure;
- **`adds_concentration`** — the candidate is already a recorded position, or all its
  themes are already held;
- **`diversifies`** — it shares some themes and adds others;
- **`no_theme_signal`** — nothing persisted (and no recorded input) maps the candidate to
  a theme; the comparison is honestly indeterminate.

Candidate themes come from the persisted stores; when the stores are silent, the recorded
diligence-inputs `domain` for that ticker is used. Without a holdings file the section
states the absence — nothing is compared against an assumed portfolio.

## 4. The rules (what Phase 018 will never do)

- **No external account connection** and **no import** of positions from any provider —
  the holdings file is typed by you, full stop.
- **No market action, no automatic re-weighting, no placement control of any kind** —
  there is no form, button, or endpoint on these surfaces; trade-like routes remain 403 by
  construction (Phase 016).
- **Bands and labels, not ratios** — weights are computed transiently and immediately
  collapsed; no ratio / weight / numeric-correlation field is ever stored or rendered.
- **Missing → honest** — no holdings, no profile, no theme mapping, no pulse: each surface
  says so in plain English instead of fabricating.
- **Stale → labeled** — an `as_of` older than the latest persisted run renders a visible
  `stale` badge; re-record the file to refresh.
- **Deterministic + offline** — same store + same recorded files → byte-identical pages;
  no wall clock, no network, no secrets.

## 5. Deferred (not in this phase)

A **read-only import of positions from an external account provider** is Phase **020+**,
approval-gated behind a new ADR — exactly like execution. Until then, recording holdings
stays a deliberate manual act.

## 6. Cross references
`OPERATOR_GUIDE_016.md` (app pages, candidate cockpit) · `OPERATOR_GUIDE_017.md`
(outcome learning) · `docs/product/BRAND_NOMENCLATURE.md` (naming).
