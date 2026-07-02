"""ENRICHMENT COVERAGE diagnostics for the Data-Quality panel (IMPLEMENTATION-011A).

Given one or more :class:`DiligenceEnrichmentBundle`, derive an AVAILABLE-vs-MISSING map
per diligence area (market cap / TAM / value-chain / bottleneck / company IR / leadership),
the SOURCE AUTHORITY per area, and the per-ticker enrichment GAPS + recommended DATA
actions. Reuses the 010F diagnostics label style.

These are DATA-QUALITY diagnostics, NOT alpha: every field is a label / string / tuple /
bool -- there is no score, no rank, no rating, and the action list is strictly
DATA-SOURCING actions (add an investor presentation, an earnings transcript, a company IR
source, a TAM source, a supplier-customer source, a bottleneck-capacity source, a
leadership source) -- never a trade / buy / sell instruction. Pure, offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Tuple

from .models import DiligenceEnrichmentBundle

# Financial magnitude areas (each a MarketAndValuationSnapshot metric), surfaced
# populated-or-gap with the SOURCE AUTHORITY backing them. ``market_key`` is the metric
# key exposed by ``MarketAndValuationSnapshot.metric_items``.
_MARKET_AREAS = (
    ("market_cap", "market cap", "add a market-cap source"),
    ("enterprise_value", "enterprise value", "add an enterprise-value source"),
    ("shares", "shares outstanding", "add a shares-outstanding source (SEC / FMP)"),
    ("revenue", "revenue", "add a revenue source (SEC / FMP)"),
    ("gross_margin", "gross margin", "add a gross-margin source (SEC / FMP income)"),
    ("operating_margin", "operating margin",
     "add an operating-margin source (SEC / FMP income)"),
    ("cash", "cash", "add a cash / balance-sheet source (SEC / FMP)"),
    ("debt", "debt", "add a debt / balance-sheet source (SEC / FMP)"),
)

# The diligence areas surfaced in the coverage panel, in display order: the financial
# magnitudes first, then the qualitative evidence areas.
AREAS = tuple(k for k, _l, _a in _MARKET_AREAS) + (
    "tam", "value_chain", "bottleneck", "company_ir", "leadership",
)

_AREA_LABELS = {k: l for k, l, _a in _MARKET_AREAS}
_AREA_LABELS.update({
    "tam": "TAM / revenue pool",
    "value_chain": "value chain",
    "bottleneck": "bottleneck",
    "company_ir": "company IR",
    "leadership": "leadership",
})

# DATA-SOURCING action per missing area (never a trade instruction).
_AREA_ACTIONS = {k: a for k, _l, a in _MARKET_AREAS}
_AREA_ACTIONS.update({
    "tam": "add a TAM / revenue-pool source",
    "value_chain": "add a supplier / customer (value-chain) source",
    "bottleneck": "add a bottleneck / capacity source",
    "company_ir": "add an investor presentation / earnings transcript / company IR source",
    "leadership": "add a leadership / management source",
})

# metric_key -> the MarketAndValuationSnapshot metric_items key.
_MARKET_AREA_KEYS = frozenset(k for k, _l, _a in _MARKET_AREAS)


@dataclass(frozen=True)
class EnrichmentAreaCoverage:
    """One diligence area's coverage: available-vs-missing + its source authority."""
    area: str = ""
    area_label: str = ""
    available: bool = False
    authority: str = ""       # source authority backing the area (empty when missing)
    claim_status: str = ""
    confidence_label: str = "missing"
    detail: str = ""
    gap: str = ""
    data_action: str = ""


@dataclass(frozen=True)
class TickerEnrichmentCoverage:
    """Per-ticker enrichment coverage across the six areas."""
    ticker: str = ""
    enrichment_status: str = "empty"
    areas: Tuple[EnrichmentAreaCoverage, ...] = field(default_factory=tuple)
    gaps: Tuple[str, ...] = field(default_factory=tuple)
    data_actions: Tuple[str, ...] = field(default_factory=tuple)
    source_coverage: Tuple[Tuple[str, int], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EnrichmentCoverageDiagnostic:
    """Whole-run enrichment coverage: per-ticker + an areas summary + data actions."""
    per_ticker: Tuple[TickerEnrichmentCoverage, ...] = field(default_factory=tuple)
    areas_summary: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)
    recommended_data_actions: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def present(self) -> bool:
        return bool(self.per_ticker)


def _market_metric_value(bundle: DiligenceEnrichmentBundle, area: str):
    for key, _label, ev in bundle.market.metric_items():
        if key == area:
            return ev
    return None


def _format_metric(label: str, ev) -> str:
    unit = ev.unit or ""
    if unit == "ratio":
        try:
            return "{0} {1:.1%}".format(label, float(ev.value))
        except (TypeError, ValueError):
            return "{0} {1}".format(label, ev.value)
    try:
        return "{0} {1:,.0f} {2}".format(label, float(ev.value), unit).strip()
    except (TypeError, ValueError):
        return "{0} {1}".format(label, ev.value)


def _area_from_bundle(bundle: DiligenceEnrichmentBundle, area: str) -> EnrichmentAreaCoverage:
    label = _AREA_LABELS[area]
    action = _AREA_ACTIONS[area]
    if area in _MARKET_AREA_KEYS:
        ev = _market_metric_value(bundle, area)
        available = bool(ev is not None and ev.present)
        detail = (_format_metric(label, ev) if available
                  else "{0} not surfaced".format(label))
        return EnrichmentAreaCoverage(
            area=area, area_label=label, available=available,
            authority=(ev.authority if available else ""),
            claim_status=(ev.claim_status if available else ""),
            confidence_label=("partial" if available else "missing"),
            detail=detail, gap=("" if available else "{0} missing".format(label)),
            data_action=("" if available else action))
    if area == "tam":
        tam = bundle.tam_estimate
        available = tam.present
        detail = ("TAM {0} (estimate_type={1}, {2})".format(
            tam.market_label, tam.estimate_type, tam.amount.authority)
            if available else "TAM / revenue pool not quantified")
        return EnrichmentAreaCoverage(
            area=area, area_label=label, available=available,
            authority=(tam.amount.authority if available else ""),
            claim_status=(tam.amount.claim_status if available else ""),
            confidence_label=tam.confidence_label,
            detail=detail, gap=("" if available else "TAM missing"),
            data_action=("" if available else action))
    if area == "value_chain":
        vc = bundle.value_chain
        available = vc.present
        detail = ("{0} value-chain layer(s)".format(len(vc.layers))
                  if available else "value-chain layers absent")
        return EnrichmentAreaCoverage(
            area=area, area_label=label, available=available,
            authority=(vc.authority if available else ""),
            claim_status=(vc.claim_status if available else ""),
            confidence_label=vc.confidence_label,
            detail=detail, gap=("" if available else "value chain missing"),
            data_action=("" if available else action))
    if area == "bottleneck":
        bn = bundle.bottleneck
        available = bn.present
        detail = ("{0} (severity={1}, duration={2})".format(
            bn.name or bn.bottleneck_type, bn.severity or "—", bn.expected_duration or "—")
            if available else "bottleneck evidence absent")
        return EnrichmentAreaCoverage(
            area=area, area_label=label, available=available,
            authority=(bn.authority if available else ""),
            claim_status=(bn.claim_status if available else ""),
            confidence_label=bn.confidence_label,
            detail=detail, gap=("" if available else "bottleneck missing"),
            data_action=("" if available else action))
    if area == "company_ir":
        ir = bundle.ir
        available = ir.present
        detail = ("{0} deck(s), {1} transcript(s), {2} guidance claim(s)".format(
            len(ir.investor_presentation_refs), len(ir.earnings_transcript_refs),
            len(ir.guidance_statements)) if available else "no IR evidence")
        return EnrichmentAreaCoverage(
            area=area, area_label=label, available=available,
            authority=(ir.authority if available else ""),
            claim_status=(ir.claim_status if available else ""),
            confidence_label=ir.confidence_label,
            detail=detail, gap=("" if available else "company IR missing"),
            data_action=("" if available else action))
    # leadership
    ld = bundle.leadership
    available = ld.present
    detail = ("{0} leader(s)".format(len(ld.members)) if available else "no leadership evidence")
    return EnrichmentAreaCoverage(
        area=area, area_label=label, available=available,
        authority=(ld.authority if available else ""),
        claim_status=(ld.claim_status if available else ""),
        confidence_label=ld.confidence_label,
        detail=detail, gap=("" if available else "leadership missing"),
        data_action=("" if available else action))


def _ticker_coverage(bundle: DiligenceEnrichmentBundle) -> TickerEnrichmentCoverage:
    areas = tuple(_area_from_bundle(bundle, a) for a in AREAS)
    gaps = tuple(bundle.data_gaps)
    actions = tuple(dict.fromkeys(a.data_action for a in areas if a.data_action))
    coverage = tuple(sorted(bundle.source_coverage.items()))
    return TickerEnrichmentCoverage(
        ticker=bundle.ticker, enrichment_status=bundle.enrichment_status,
        areas=areas, gaps=gaps, data_actions=actions, source_coverage=coverage)


def build_enrichment_coverage(
    bundles: Iterable[DiligenceEnrichmentBundle],
) -> EnrichmentCoverageDiagnostic:
    """Build the whole-run enrichment coverage diagnostic from one or more bundles."""
    per_ticker = tuple(_ticker_coverage(b) for b in bundles if b is not None)

    # areas summary: "market cap: 1/2 available", derived by counting availability.
    summary: List[Tuple[str, str]] = []
    for area in AREAS:
        avail = sum(1 for tc in per_ticker for a in tc.areas
                    if a.area == area and a.available)
        summary.append((_AREA_LABELS[area],
                        "{0}/{1} available".format(avail, len(per_ticker))))

    actions: List[str] = []
    for tc in per_ticker:
        actions.extend(tc.data_actions)
    actions = list(dict.fromkeys(actions))

    return EnrichmentCoverageDiagnostic(
        per_ticker=per_ticker, areas_summary=tuple(summary),
        recommended_data_actions=tuple(actions))
