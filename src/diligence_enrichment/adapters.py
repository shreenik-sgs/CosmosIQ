"""Fixture-backed PARSERS that map EXISTING SEC / FMP outputs into enrichment values.

Adapter SCAFFOLDING only: these are pure, offline parsers over the SAME fixture shapes the
evidence-ingestion slice already consumes (SEC ``companyfacts``, FMP ``profile`` /
``income-statement``) plus small optional IR / leadership fixtures. There is NO network, NO
scraping, NO scheduled ingestion, NO OCR and NO user-PDF ingestion here -- a value is only
produced when a supplied fixture contains it; otherwise the caller records a DATA GAP.

Source authority is stamped at the point of extraction:

* SEC company facts   -> ``canonical`` / ``verified_fact``
* FMP profile / income -> ``convenience`` / ``verified_fact``
* company IR / decks   -> ``primary`` / ``company_claim``
* a manual TAM         -> ``manual`` / ``manual`` (NEVER canonical)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .models import (
    BottleneckEvidenceProfile,
    CompanyDiligenceProfile,
    CompanyIREvidenceProfile,
    EnrichmentValue,
    LeadershipEvidenceProfile,
    LeadershipMember,
    MarketAndValuationSnapshot,
    TAMRevenuePoolEstimate,
    ValueChainEvidenceProfile,
    ValueChainLayerEvidence,
)
from .source_contract import (
    ClaimStatus,
    assert_manual_not_canonical,
    authority_for_category,
    claim_status_for_category,
    mark_company_claim,
)


# --------------------------------------------------------------------------- #
# tiny, defensive readers over the fixture dicts (never raise on shape drift). #
# --------------------------------------------------------------------------- #
def _first_profile(fmp_profile: Any) -> Optional[Dict[str, Any]]:
    """FMP profile is a list of one dict (or a bare dict). Return the dict or None."""
    if fmp_profile is None:
        return None
    if isinstance(fmp_profile, dict):
        return fmp_profile
    if isinstance(fmp_profile, (list, tuple)) and fmp_profile:
        head = fmp_profile[0]
        return head if isinstance(head, dict) else None
    return None


def _latest_companyfact(sec_facts: Any, concept: str, unit: str) -> Optional[Dict[str, Any]]:
    """Return the LATEST (by ``end`` date) us-gaap fact row for ``concept`` / ``unit``.

    Deterministic: sort by ``end`` then ``accn`` and take the last. Returns None when the
    fixture does not carry the concept -- the caller turns that into a data gap.
    """
    if not isinstance(sec_facts, dict):
        return None
    facts = sec_facts.get("facts", {})
    for namespace in ("us-gaap", "ifrs-full", "dei"):
        ns = facts.get(namespace, {})
        entry = ns.get(concept)
        if not entry:
            continue
        rows = entry.get("units", {}).get(unit, [])
        rows = [r for r in rows if isinstance(r, dict) and r.get("val") is not None]
        if not rows:
            continue
        rows.sort(key=lambda r: (str(r.get("end", "")), str(r.get("accn", ""))))
        return rows[-1]
    return None


def _accession_ref(row: Dict[str, Any]) -> str:
    form = row.get("form", "")
    accn = row.get("accn", "")
    end = row.get("end", "")
    return "SEC {0} {1} (period {2})".format(form or "filing", accn, end).strip()


# --------------------------------------------------------------------------- #
# CompanyDiligenceProfile <- FMP profile (convenience).                        #
# --------------------------------------------------------------------------- #
def company_profile_from_fmp(ticker: str, fmp_profile: Any) -> CompanyDiligenceProfile:
    prof = _first_profile(fmp_profile)
    if prof is None:
        return CompanyDiligenceProfile(
            ticker=ticker, confidence_label="missing",
            data_gaps=("company profile absent — no FMP profile supplied",))

    auth = authority_for_category("fmp")
    claim = claim_status_for_category("fmp")
    ref = "FMP profile ({0})".format(ticker)

    def val(key: str) -> EnrichmentValue:
        raw = prof.get(key)
        return EnrichmentValue(
            value=(raw if raw not in (None, "") else None),
            authority=auth, claim_status=claim, source_refs=(ref,))

    gaps: List[str] = []
    name = val("companyName")
    sector = val("sector")
    industry = val("industry")
    exchange = val("exchange")
    description = val("description")
    website = val("website")
    for label, ev in (("sector", sector), ("industry", industry),
                      ("exchange", exchange), ("description", description)):
        if not ev.present:
            gaps.append("company {0} not in FMP profile".format(label))

    return CompanyDiligenceProfile(
        ticker=ticker, company_name=name, sector=sector, industry=industry,
        exchange=exchange, description=description, website=website, source_refs=(ref,),
        data_gaps=tuple(gaps),
        confidence_label=("partial" if name.present else "weak"))


# SEC us-gaap concept candidates per financial metric (first PRESENT wins, aligned with
# ``evidence_ingestion.sec_edgar``). SEC is CANONICAL and always preferred over FMP.
_SEC_METRIC_CONCEPTS = {
    "revenue": (("Revenues", "USD"),
                ("RevenueFromContractWithCustomerExcludingAssessedTax", "USD")),
    "net_income": (("NetIncomeLoss", "USD"),),
    "gross_profit": (("GrossProfit", "USD"),),
    "operating_income": (("OperatingIncomeLoss", "USD"),),
    "cash": (("CashAndCashEquivalentsAtCarryingValue", "USD"),),
    "debt": (("LongTermDebtNoncurrent", "USD"), ("Liabilities", "USD")),
    "shares": (("CommonStockSharesOutstanding", "shares"),
               ("EntityCommonStockSharesOutstanding", "shares")),
}


def _sec_fact(sec_facts: Any, metric: str) -> Optional[Dict[str, Any]]:
    """Latest SEC company-facts row for a metric (first candidate concept present)."""
    for concept, unit in _SEC_METRIC_CONCEPTS.get(metric, ()):  # deterministic order
        row = _latest_companyfact(sec_facts, concept, unit)
        if row is not None:
            return row
    return None


def _sec_value(row: Dict[str, Any], unit: str) -> EnrichmentValue:
    """Wrap a SEC company-facts row as a CANONICAL verified_fact enrichment value."""
    return EnrichmentValue(
        value=float(row["val"]), unit=unit,
        authority=authority_for_category("sec_filing"),
        claim_status=claim_status_for_category("sec_filing"),
        as_of=str(row.get("end", "")), source_refs=(_accession_ref(row),))


def _fmp_value(raw: Any, unit: str, ticker: str, origin: str,
               *, as_of: str = "", claim: str = "", note: str = "") -> EnrichmentValue:
    """Wrap an FMP datum as a CONVENIENCE value (never overrides SEC for the same metric)."""
    return EnrichmentValue(
        value=float(raw), unit=unit,
        authority=authority_for_category("fmp"),
        claim_status=(claim or claim_status_for_category("fmp")),
        as_of=as_of, source_refs=("FMP {0} ({1})".format(origin, ticker),), note=note)


def _latest_income_row(fmp_income: Any) -> Optional[Dict[str, Any]]:
    """Latest FMP income-statement row by ``date`` (deterministic). None when absent."""
    if isinstance(fmp_income, (list, tuple)) and fmp_income:
        rows = [r for r in fmp_income if isinstance(r, dict)]
        if rows:
            rows.sort(key=lambda r: str(r.get("date", "")))
            return rows[-1]
    return None


def _num(d: Any, key: str) -> Optional[float]:
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if v in (None, "", 0):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# MarketAndValuationSnapshot <- SEC facts (shares / revenue / net income / cash / #
# debt / margins, CANONICAL) preferred, with FMP profile + income statement as   #
# CONVENIENCE for the market cap / EV / price and for metrics SEC does not carry. #
# --------------------------------------------------------------------------- #
def market_snapshot(ticker: str, *, fmp_profile: Any = None, sec_facts: Any = None,
                    fmp_income: Any = None) -> MarketAndValuationSnapshot:
    prof = _first_profile(fmp_profile)
    inc_row = _latest_income_row(fmp_income)
    gaps: List[str] = []
    refs: List[str] = []

    def record(ev: EnrichmentValue) -> None:
        if ev.present:
            refs.extend(ev.source_refs)

    # -- market cap: FMP convenience only (SEC does not publish a market cap). -----
    market_cap = EnrichmentValue()
    if _num(prof, "mktCap") is not None:
        market_cap = _fmp_value(prof["mktCap"], "USD", ticker, "profile")
    else:
        gaps.append("market cap not available (no FMP profile mktCap) — a data gap")

    # -- enterprise value: FMP convenience (profile / income) or gap. -------------
    enterprise_value = EnrichmentValue()
    ev_raw = _num(prof, "enterpriseValue")
    if ev_raw is None:
        ev_raw = _num(inc_row, "enterpriseValue")
    if ev_raw is not None:
        origin = "profile" if _num(prof, "enterpriseValue") is not None else "income statement"
        enterprise_value = _fmp_value(ev_raw, "USD", ticker, origin)
    else:
        gaps.append("enterprise value not surfaced by the supplied sources — a data gap")

    # -- price: FMP convenience or gap (the profile fixture carries none). --------
    price = EnrichmentValue()
    if _num(prof, "price") is not None:
        price = _fmp_value(prof["price"], "USD", ticker, "profile")
    else:
        gaps.append("current price not surfaced by the supplied sources — a data gap")

    # -- shares outstanding: SEC canonical, else FMP convenience (profile/income). -
    shares = EnrichmentValue()
    sec_shares = _sec_fact(sec_facts, "shares")
    if sec_shares is not None:
        shares = _sec_value(sec_shares, "shares")
    elif _num(prof, "sharesOutstanding") is not None:
        shares = _fmp_value(prof["sharesOutstanding"], "shares", ticker, "profile")
    elif _num(inc_row, "weightedAverageShsOut") is not None:
        shares = _fmp_value(inc_row["weightedAverageShsOut"], "shares", ticker,
                            "income statement", as_of=str(inc_row.get("date", "")))
    else:
        gaps.append("shares outstanding not available from SEC or FMP — a data gap")

    # -- latest revenue: SEC canonical, else FMP income convenience. --------------
    revenue = EnrichmentValue()
    sec_rev = _sec_fact(sec_facts, "revenue")
    if sec_rev is not None:
        revenue = _sec_value(sec_rev, "USD")
    elif _num(inc_row, "revenue") is not None:
        revenue = _fmp_value(inc_row["revenue"], "USD", ticker, "income statement",
                             as_of=str(inc_row.get("date", "")))
    else:
        gaps.append("latest revenue not available from SEC or FMP — a data gap")

    # -- net income: SEC canonical, else FMP income convenience. ------------------
    net_income = EnrichmentValue()
    sec_ni = _sec_fact(sec_facts, "net_income")
    if sec_ni is not None:
        net_income = _sec_value(sec_ni, "USD")
    elif _num(inc_row, "netIncome") is not None:
        net_income = _fmp_value(inc_row["netIncome"], "USD", ticker, "income statement",
                                as_of=str(inc_row.get("date", "")))
    else:
        gaps.append("net income not available from SEC or FMP — a data gap")

    # -- cash: SEC canonical, else FMP income convenience, else gap. --------------
    cash = EnrichmentValue()
    sec_cash = _sec_fact(sec_facts, "cash")
    if sec_cash is not None:
        cash = _sec_value(sec_cash, "USD")
    elif _num(inc_row, "cashAndCashEquivalents") is not None:
        cash = _fmp_value(inc_row["cashAndCashEquivalents"], "USD", ticker,
                          "income statement", as_of=str(inc_row.get("date", "")))
    else:
        gaps.append("cash / cash-equivalents not surfaced by SEC or FMP — a data gap")

    # -- debt: SEC canonical, else FMP income convenience, else gap. --------------
    debt = EnrichmentValue()
    sec_debt = _sec_fact(sec_facts, "debt")
    if sec_debt is not None:
        debt = _sec_value(sec_debt, "USD")
    elif _num(inc_row, "totalDebt") is not None:
        debt = _fmp_value(inc_row["totalDebt"], "USD", ticker, "income statement",
                          as_of=str(inc_row.get("date", "")))
    elif _num(inc_row, "totalLiabilities") is not None:
        debt = _fmp_value(inc_row["totalLiabilities"], "USD", ticker, "income statement",
                          as_of=str(inc_row.get("date", "")))
    else:
        gaps.append("total debt not surfaced by SEC or FMP — a data gap")

    # -- margins: SEC canonical when it carries both numerator + revenue for the
    #    same period; else derived from FMP income (convenience, INFERRED ratio);
    #    else gap. A derived ratio is never a directly reported fact.
    gross_margin = _margin(
        "gross margin", sec_facts, sec_rev, "gross_profit", inc_row, "grossProfit",
        "grossProfitRatio", ticker, gaps)
    operating_margin = _margin(
        "operating margin", sec_facts, sec_rev, "operating_income", inc_row,
        "operatingIncome", "operatingIncomeRatio", ticker, gaps)

    for ev in (market_cap, enterprise_value, price, shares, revenue, net_income,
               cash, debt, gross_margin, operating_margin):
        record(ev)
    as_of = revenue.as_of or (net_income.as_of if net_income.present else "")

    present_n = sum(1 for e in (market_cap, enterprise_value, price, shares, revenue,
                                net_income, gross_margin, operating_margin, cash, debt)
                    if e.present)
    confidence = ("missing" if present_n == 0
                  else ("sufficient" if present_n >= 6 else "partial"))
    return MarketAndValuationSnapshot(
        ticker=ticker, market_cap=market_cap, enterprise_value=enterprise_value,
        price=price, shares_outstanding=shares, latest_revenue=revenue,
        net_income=net_income, gross_margin=gross_margin, op_margin=operating_margin,
        cash=cash, debt=debt, currency="USD", as_of=as_of,
        source_refs=tuple(dict.fromkeys(refs)), data_gaps=tuple(gaps),
        confidence_label=confidence)


def _margin(label: str, sec_facts: Any, sec_rev_row: Optional[Dict[str, Any]],
            sec_numer_metric: str, inc_row: Optional[Dict[str, Any]],
            fmp_numer_key: str, fmp_ratio_key: str, ticker: str,
            gaps: List[str]) -> EnrichmentValue:
    """Build a margin ratio. SEC canonical (numerator + revenue, same period) wins; else
    FMP-provided ratio / FMP-derived ratio (convenience, INFERRED); else a data gap."""
    # SEC canonical: only when SEC carries BOTH the numerator and a revenue for the same
    # period end -- never mixing sources for one ratio.
    sec_numer = _sec_fact(sec_facts, sec_numer_metric)
    if (sec_numer is not None and sec_rev_row is not None
            and sec_numer.get("end") == sec_rev_row.get("end")):
        rev = float(sec_rev_row["val"])
        if rev:
            return EnrichmentValue(
                value=float(sec_numer["val"]) / rev, unit="ratio",
                authority=authority_for_category("sec_filing"),
                claim_status=ClaimStatus.INFERRED,
                as_of=str(sec_rev_row.get("end", "")),
                source_refs=(_accession_ref(sec_numer), _accession_ref(sec_rev_row)),
                note="derived from SEC canonical facts (numerator / revenue)")
    # FMP-provided ratio.
    ratio = _num(inc_row, fmp_ratio_key)
    if ratio is not None:
        return _fmp_value(ratio, "ratio", ticker, "income statement",
                          as_of=str(inc_row.get("date", "")))
    # FMP-derived ratio (numerator / revenue from the same income row).
    numer = _num(inc_row, fmp_numer_key)
    rev = _num(inc_row, "revenue")
    if numer is not None and rev:
        return _fmp_value(numer / rev, "ratio", ticker, "income statement",
                          as_of=str(inc_row.get("date", "")),
                          claim=ClaimStatus.INFERRED,
                          note="derived from FMP {0} / revenue".format(fmp_numer_key))
    gaps.append("{0} not surfaced by SEC or FMP — a data gap".format(label))
    return EnrichmentValue()


# --------------------------------------------------------------------------- #
# TAMRevenuePoolEstimate <- a MANUAL estimate only (never canonical).           #
# --------------------------------------------------------------------------- #
def tam_estimate_from_manual(ticker: str, manual_tam: Any) -> TAMRevenuePoolEstimate:
    """Build a TAM estimate from an explicit MANUAL input. Always ``manual`` authority.

    ``manual_tam`` may be a number (the amount) or a dict with ``amount`` / ``market`` /
    ``methodology`` / ``source``. The result is ``estimate_type="manual"`` with a
    ``manual`` authority + claim status -- asserted to never be canonical.
    """
    if manual_tam is None:
        return TAMRevenuePoolEstimate(
            confidence_label="missing",
            data_gaps=("TAM / revenue pool not supplied — a data gap (never invented)",))

    if isinstance(manual_tam, dict):
        amount = manual_tam.get("amount")
        market_label = str(manual_tam.get("market", "") or "")
        methodology = str(manual_tam.get("methodology", "") or "")
        src = str(manual_tam.get("source", "") or "manual analyst estimate")
    else:
        amount = manual_tam
        market_label = ""
        methodology = ""
        src = "manual analyst estimate"

    auth = authority_for_category("manual")
    claim = ClaimStatus.MANUAL
    assert_manual_not_canonical(auth, claim)
    try:
        amt_val = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amt_val = None

    ev = EnrichmentValue(
        value=amt_val, unit="USD", authority=auth, claim_status=claim,
        source_refs=(src,), note="manual estimate — not canonical, not a forecast")
    gaps = () if ev.present else ("TAM amount missing / unparseable — a data gap",)
    return TAMRevenuePoolEstimate(
        market_label=market_label or "addressable revenue pool (manual)",
        estimate_type="manual", amount=ev, methodology_note=methodology,
        source_refs=(src,), data_gaps=gaps,
        confidence_label=("partial" if ev.present else "missing"))


# --------------------------------------------------------------------------- #
# Value-chain / bottleneck evidence <- optional fixtures only.                  #
# --------------------------------------------------------------------------- #
def value_chain_from_fixture(ticker: str, fixture: Any) -> ValueChainEvidenceProfile:
    if not fixture:
        return ValueChainEvidenceProfile(
            ticker=ticker, confidence_label="missing",
            data_gaps=("value-chain evidence not supplied — a data gap (no invented layers)",))
    category = str(fixture.get("category", "investor_presentation")) if isinstance(fixture, dict) else "investor_presentation"
    try:
        auth = authority_for_category(category)
        claim = claim_status_for_category(category)
    except ValueError:
        auth, claim = authority_for_category("investor_presentation"), ClaimStatus.COMPANY_CLAIM
    refs = tuple(fixture.get("source_refs", ())) if isinstance(fixture, dict) else ()
    raw_layers = fixture.get("layers", ()) if isinstance(fixture, dict) else ()
    layers: List[ValueChainLayerEvidence] = []
    for i, ly in enumerate(raw_layers):
        if not isinstance(ly, dict):
            continue
        layers.append(ValueChainLayerEvidence(
            label=str(ly.get("label", "layer-{0}".format(i))),
            sequence=int(ly.get("sequence", ly.get("order", i))),
            description=str(ly.get("description", "")),
            companies=tuple(str(c) for c in ly.get("companies", ())),
            suppliers=tuple(str(c) for c in ly.get("suppliers", ())),
            customers=tuple(str(c) for c in ly.get("customers", ())),
            bottleneck_exposure=str(ly.get("bottleneck_exposure", "")),
            authority=auth, claim_status=claim, source_refs=refs))
    layers.sort(key=lambda l: l.sequence)
    suppliers = tuple(str(s) for s in fixture.get("suppliers", ())) if isinstance(fixture, dict) else ()
    customers = tuple(str(s) for s in fixture.get("customers", ())) if isinstance(fixture, dict) else ()
    gaps: List[str] = []
    if not suppliers:
        gaps.append("supplier evidence still thin — add a supplier / customer source")
    return ValueChainEvidenceProfile(
        ticker=ticker,
        chain_name=str(fixture.get("chain_name", "")) if isinstance(fixture, dict) else "",
        layers=tuple(layers), suppliers=suppliers, customers=customers,
        authority=auth, claim_status=claim, source_refs=refs, data_gaps=tuple(gaps),
        confidence_label=("partial" if layers else "missing"))


def bottleneck_from_fixture(ticker: str, fixture: Any) -> BottleneckEvidenceProfile:
    if not fixture or not isinstance(fixture, dict):
        return BottleneckEvidenceProfile(
            ticker=ticker, confidence_label="missing",
            data_gaps=("bottleneck evidence not supplied — a data gap "
                       "(severity / duration not invented)",))
    category = str(fixture.get("category", "investor_presentation"))
    try:
        auth = authority_for_category(category)
        claim = claim_status_for_category(category)
    except ValueError:
        auth, claim = authority_for_category("investor_presentation"), ClaimStatus.COMPANY_CLAIM
    refs = tuple(fixture.get("source_refs", ()))
    return BottleneckEvidenceProfile(
        ticker=ticker, name=str(fixture.get("name", "")),
        bottleneck_type=str(fixture.get("bottleneck_type", "")),
        severity=str(fixture.get("severity", "")),
        expected_duration=str(fixture.get("expected_duration", "")),
        constrained_resource=str(fixture.get("constrained_resource", "")),
        beneficiaries=tuple(str(b) for b in fixture.get("beneficiaries", ())),
        evidence=tuple(str(e) for e in fixture.get("evidence", ())),
        authority=auth, claim_status=claim, source_refs=refs,
        confidence_label="partial")


# --------------------------------------------------------------------------- #
# Company IR / leadership evidence <- optional fixtures only (company_claim).    #
# --------------------------------------------------------------------------- #
def ir_from_fixture(ticker: str, fixture: Any) -> CompanyIREvidenceProfile:
    if not fixture or not isinstance(fixture, dict):
        return CompanyIREvidenceProfile(
            ticker=ticker, confidence_label="missing",
            data_gaps=(
                "company IR evidence not supplied — a data gap (add an investor "
                "presentation / earnings transcript / IR source)",))
    auth = authority_for_category("company_ir")
    decks = tuple(str(x) for x in fixture.get("investor_presentation_refs", ()))
    transcripts = tuple(str(x) for x in fixture.get("earnings_transcript_refs", ()))
    ir_pages = tuple(str(x) for x in fixture.get("ir_page_refs", ()))
    guidance = tuple(
        mark_company_claim(EnrichmentValue(
            value=str(g), authority=auth, source_refs=decks + transcripts + ir_pages))
        for g in fixture.get("guidance_statements", ()))
    catalysts = tuple(str(c) for c in fixture.get("disclosed_catalysts", ()))
    risks = tuple(str(r) for r in fixture.get("disclosed_risks", ()))
    return CompanyIREvidenceProfile(
        ticker=ticker, investor_presentation_refs=decks,
        earnings_transcript_refs=transcripts, ir_page_refs=ir_pages,
        guidance_statements=guidance, disclosed_catalysts=catalysts,
        disclosed_risks=risks, authority=auth, claim_status=ClaimStatus.COMPANY_CLAIM,
        source_refs=decks + transcripts + ir_pages, confidence_label="partial")


def leadership_from_fixture(ticker: str, fixture: Any) -> LeadershipEvidenceProfile:
    if not fixture:
        return LeadershipEvidenceProfile(
            ticker=ticker, confidence_label="missing",
            data_gaps=("leadership evidence not supplied — a data gap "
                       "(add a leadership / management source)",))
    members_raw = fixture.get("members", ()) if isinstance(fixture, dict) else fixture
    members: List[LeadershipMember] = []
    for m in members_raw:
        if isinstance(m, dict):
            members.append(LeadershipMember(
                name=str(m.get("name", "")), role=str(m.get("role", "")),
                since=str(m.get("since", "")), note=str(m.get("note", ""))))
    auth = authority_for_category("company_ir")
    tenure = str(fixture.get("tenure_note", "")) if isinstance(fixture, dict) else ""
    refs = tuple(fixture.get("source_refs", ())) if isinstance(fixture, dict) else ()
    return LeadershipEvidenceProfile(
        ticker=ticker, members=tuple(members), tenure_note=tenure,
        authority=auth, claim_status=ClaimStatus.COMPANY_CLAIM, source_refs=refs,
        confidence_label=("partial" if members else "missing"))
