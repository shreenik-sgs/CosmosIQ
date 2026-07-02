"""Orchestrator: assemble a :class:`DiligenceEnrichmentBundle` from fixtures (011A).

``build_diligence_enrichment_bundle`` runs the fixture-backed parsers in
:mod:`diligence_enrichment.adapters`, stamps every value with its explicit source
authority + claim status, and records an explicit DATA GAP for every area a fixture did
not supply. It NEVER fetches, scrapes or invents; it only re-expresses what was passed in.

Deterministic, stdlib-only, Python 3.9. No network, no clock dependency (``now`` is an
optional explicit argument used only for a provenance timestamp string).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .adapters import (
    bottleneck_from_fixture,
    company_profile_from_fmp,
    ir_from_fixture,
    leadership_from_fixture,
    market_snapshot,
    tam_estimate_from_manual,
    value_chain_from_fixture,
)
from .models import DiligenceEnrichmentBundle
from .source_contract import authority_for_category


def _coverage(bundle_parts) -> Dict[str, int]:
    """Count data-bearing values by SOURCE AUTHORITY (an honest coverage tally, not a score)."""
    counts: Dict[str, int] = {}

    def bump(auth: str) -> None:
        if auth:
            counts[auth] = counts.get(auth, 0) + 1

    profile, market, tam, vc, bn, ir, leadership = bundle_parts
    for ev in (profile.company_name, profile.sector, profile.industry,
               profile.description, profile.website):
        if ev.present:
            bump(ev.authority)
    for ev in (market.market_cap, market.price, market.shares_outstanding,
               market.latest_revenue):
        if ev.present:
            bump(ev.authority)
    if tam.present:
        bump(tam.amount.authority)
    if vc.present:
        bump(vc.authority)
    if bn.present:
        bump(bn.authority)
    if ir.present:
        bump(ir.authority)
    if leadership.present:
        bump(leadership.authority)
    return counts


def build_diligence_enrichment_bundle(
    ticker: str, *,
    sec_facts: Any = None,
    fmp_profile: Any = None,
    fmp_income: Any = None,
    slice_result: Any = None,
    manual_tam: Any = None,
    ir_fixture: Any = None,
    leadership_fixture: Any = None,
    value_chain_fixture: Any = None,
    bottleneck_fixture: Any = None,
    now: Optional[float] = None,
) -> DiligenceEnrichmentBundle:
    """Assemble a :class:`DiligenceEnrichmentBundle` for ``ticker`` from supplied fixtures.

    Populates the company profile + market/valuation snapshot from EXISTING SEC / FMP
    fixture outputs where present (shares / revenue prefer SEC canonical; market cap / sector
    from the FMP profile marked convenience). TAM, value-chain, bottleneck, company IR and
    leadership are explicit DATA GAPS unless a fixture supplies them; a ``manual_tam`` is
    always ``estimate_type="manual"`` with ``manual`` authority -- never canonical.

    ``slice_result`` (an evidence-alpha slice) is optional and used ONLY to enrich the
    provenance trail; it is never mutated and contributes no invented values.
    """
    ticker = str(ticker or "").strip().upper()

    profile = company_profile_from_fmp(ticker, fmp_profile)
    market = market_snapshot(
        ticker, fmp_profile=fmp_profile, sec_facts=sec_facts, fmp_income=fmp_income)
    tam = tam_estimate_from_manual(ticker, manual_tam)
    value_chain = value_chain_from_fixture(ticker, value_chain_fixture)
    bottleneck = bottleneck_from_fixture(ticker, bottleneck_fixture)
    ir = ir_from_fixture(ticker, ir_fixture)
    leadership = leadership_from_fixture(ticker, leadership_fixture)

    parts = (profile, market, tam, value_chain, bottleneck, ir, leadership)
    coverage = _coverage(parts)

    # Aggregate every area's own data gaps into one honest, de-duped list.
    gaps: List[str] = []
    for part in parts:
        gaps.extend(getattr(part, "data_gaps", ()) or ())
    gaps = list(dict.fromkeys(gaps))

    # Provenance: fixture-origin markers + (optionally) the slice's subject id.
    prov: List[str] = []
    if fmp_profile is not None:
        prov.append("FMP profile fixture ({0})".format(ticker))
    if sec_facts is not None:
        prov.append("SEC companyfacts fixture ({0})".format(ticker))
    if fmp_income is not None:
        prov.append("FMP income-statement fixture ({0})".format(ticker))
    if manual_tam is not None:
        prov.append("manual TAM input (authority {0}, not canonical)".format(
            authority_for_category("manual")))
    if slice_result is not None:
        subj = getattr(slice_result, "subject", "") or ""
        if subj:
            prov.append("evidence-alpha slice subject {0}".format(subj))
    if now is not None:
        prov.append("enriched_at {0}".format(
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(now)))))

    # completeness LABEL (never a score): count populated AREAS out of the seven.
    areas_present = sum(1 for flag in (
        market.market_cap_value is not None, tam.present, value_chain.present,
        bottleneck.present,
        ir.present, leadership.present, profile.company_name.present) if flag)
    if areas_present == 0:
        status = "empty"
    elif areas_present <= 3:
        status = "sparse"
    else:
        status = "partial"

    return DiligenceEnrichmentBundle(
        ticker=ticker, profile=profile, market=market, tam_estimate=tam,
        value_chain=value_chain, bottleneck=bottleneck, ir=ir, leadership=leadership,
        source_coverage=coverage, data_gaps=tuple(gaps), provenance_refs=tuple(prov),
        enrichment_status=status)
