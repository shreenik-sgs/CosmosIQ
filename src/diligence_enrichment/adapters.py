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
    description = val("description")
    website = val("website")
    for label, ev in (("sector", sector), ("industry", industry),
                      ("description", description)):
        if not ev.present:
            gaps.append("company {0} not in FMP profile".format(label))

    return CompanyDiligenceProfile(
        ticker=ticker, company_name=name, sector=sector, industry=industry,
        description=description, website=website, source_refs=(ref,),
        data_gaps=tuple(gaps),
        confidence_label=("partial" if name.present else "weak"))


# --------------------------------------------------------------------------- #
# MarketAndValuationSnapshot <- FMP profile (market cap) + SEC facts (shares /   #
# revenue, canonical) with FMP income as convenience fallback.                  #
# --------------------------------------------------------------------------- #
def market_snapshot(ticker: str, *, fmp_profile: Any = None, sec_facts: Any = None,
                    fmp_income: Any = None) -> MarketAndValuationSnapshot:
    prof = _first_profile(fmp_profile)
    gaps: List[str] = []
    refs: List[str] = []

    # market cap: FMP convenience (SEC does not publish a market cap).
    market_cap = EnrichmentValue()
    if prof is not None and prof.get("mktCap") not in (None, "", 0):
        ref = "FMP profile ({0})".format(ticker)
        market_cap = EnrichmentValue(
            value=float(prof["mktCap"]), unit="USD",
            authority=authority_for_category("fmp"),
            claim_status=claim_status_for_category("fmp"), source_refs=(ref,))
        refs.append(ref)
    else:
        gaps.append("market cap not available (no FMP profile mktCap) — a data gap")

    # price: only if a source carries it (the FMP profile fixture does not) -> gap.
    price = EnrichmentValue()
    if prof is not None and prof.get("price") not in (None, "", 0):
        price = EnrichmentValue(
            value=float(prof["price"]), unit="USD",
            authority=authority_for_category("fmp"),
            claim_status=claim_status_for_category("fmp"),
            source_refs=("FMP profile ({0})".format(ticker),))
    else:
        gaps.append("current price not surfaced by the supplied sources — a data gap")

    # shares outstanding: prefer SEC canonical, else FMP convenience.
    shares = EnrichmentValue()
    sec_shares = _latest_companyfact(sec_facts, "CommonStockSharesOutstanding", "shares")
    if sec_shares is not None:
        shares = EnrichmentValue(
            value=float(sec_shares["val"]), unit="shares",
            authority=authority_for_category("sec_filing"),
            claim_status=claim_status_for_category("sec_filing"),
            as_of=str(sec_shares.get("end", "")),
            source_refs=(_accession_ref(sec_shares),))
        refs.append(_accession_ref(sec_shares))
    elif prof is not None and prof.get("sharesOutstanding") not in (None, "", 0):
        shares = EnrichmentValue(
            value=float(prof["sharesOutstanding"]), unit="shares",
            authority=authority_for_category("fmp"),
            claim_status=claim_status_for_category("fmp"),
            source_refs=("FMP profile ({0})".format(ticker),))
    else:
        gaps.append("shares outstanding not available from SEC or FMP — a data gap")

    # latest revenue: prefer SEC canonical, else FMP income convenience.
    revenue = EnrichmentValue()
    as_of = ""
    sec_rev = _latest_companyfact(sec_facts, "Revenues", "USD")
    if sec_rev is None:
        sec_rev = _latest_companyfact(sec_facts, "RevenueFromContractWithCustomerExcludingAssessedTax", "USD")
    if sec_rev is not None:
        as_of = str(sec_rev.get("end", ""))
        revenue = EnrichmentValue(
            value=float(sec_rev["val"]), unit="USD",
            authority=authority_for_category("sec_filing"),
            claim_status=claim_status_for_category("sec_filing"),
            as_of=as_of, source_refs=(_accession_ref(sec_rev),))
        refs.append(_accession_ref(sec_rev))
    else:
        inc = fmp_income
        row = None
        if isinstance(inc, (list, tuple)) and inc:
            rows = [r for r in inc if isinstance(r, dict) and r.get("revenue") is not None]
            if rows:
                rows.sort(key=lambda r: str(r.get("date", "")))
                row = rows[-1]
        if row is not None:
            as_of = str(row.get("date", ""))
            revenue = EnrichmentValue(
                value=float(row["revenue"]), unit="USD",
                authority=authority_for_category("fmp"),
                claim_status=claim_status_for_category("fmp"),
                as_of=as_of, source_refs=("FMP income statement ({0})".format(ticker),))
        else:
            gaps.append("latest revenue not available from SEC or FMP — a data gap")

    present_n = sum(1 for e in (market_cap, price, shares, revenue) if e.present)
    confidence = "missing" if present_n == 0 else ("partial" if present_n < 4 else "sufficient")
    return MarketAndValuationSnapshot(
        ticker=ticker, market_cap=market_cap, price=price, shares_outstanding=shares,
        latest_revenue=revenue, currency="USD", as_of=as_of,
        source_refs=tuple(dict.fromkeys(refs)), data_gaps=tuple(gaps),
        confidence_label=confidence)


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
