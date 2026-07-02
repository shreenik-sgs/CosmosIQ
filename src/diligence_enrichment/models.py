"""Typed ENRICHMENT models for investment diligence INPUTS (IMPLEMENTATION-011A).

Frozen dataclasses, stdlib only, Python 3.9, deterministic. These describe the diligence
INPUTS that terrain / Nivesha need but the pipeline does not yet surface -- market cap,
TAM / revenue pool, value-chain evidence, bottleneck evidence, company IR evidence and
leadership evidence.

CRITICAL DISCIPLINE baked into the shape:

* **Evidence, not a decision.** There is NO ``buy`` / ``sell`` / ``hold`` field, NO
  ``rank`` / ``score`` / ``rating`` field, and NO numeric investability metric anywhere.
  ``confidence_label`` and ``claim_status`` are QUALITATIVE labels, never numbers, never a
  ranking key.
* **Every value carries its provenance.** A data-bearing value is an
  :class:`EnrichmentValue` that records its source ``authority`` (canonical / primary /
  convenience / fallback / manual) and its ``claim_status`` (verified_fact / company_claim
  / analyst_estimate / inferred / manual). A company statement is ``company_claim``, never
  ``verified_fact``; a manual / analyst estimate is ``manual`` / ``analyst_estimate``
  authority, never canonical.
* **Missing is explicit.** Every model is trivially constructible with all-empty defaults,
  and an everything-missing bundle yields explicit ``data_gaps`` -- never an invented value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# --------------------------------------------------------------------------- #
# The one provenance-carrying value wrapper. NOT a score -- a labelled datum.  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EnrichmentValue:
    """A single enrichment datum with EXPLICIT source authority + claim status.

    ``value`` is the raw datum (a number, a string, or None when absent). ``authority``
    and ``claim_status`` are the provenance labels; ``source_refs`` names the origin. A
    missing datum (``value is None``) is a DATA GAP, never fabricated.
    """
    value: Optional[object] = None
    unit: str = ""
    authority: str = ""          # canonical / primary / convenience / fallback / manual
    claim_status: str = ""       # verified_fact / company_claim / analyst_estimate / inferred / manual
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    as_of: str = ""
    note: str = ""

    @property
    def present(self) -> bool:
        return self.value is not None and self.value != ""

    @property
    def is_canonical(self) -> bool:
        return self.authority == "canonical"


# --------------------------------------------------------------------------- #
# 1. Company profile evidence.                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CompanyDiligenceProfile:
    """Basic descriptive company evidence (name / sector / industry / description)."""
    ticker: str = ""
    company_name: EnrichmentValue = field(default_factory=EnrichmentValue)
    sector: EnrichmentValue = field(default_factory=EnrichmentValue)
    industry: EnrichmentValue = field(default_factory=EnrichmentValue)
    description: EnrichmentValue = field(default_factory=EnrichmentValue)
    website: EnrichmentValue = field(default_factory=EnrichmentValue)
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"


# --------------------------------------------------------------------------- #
# 2. Market & valuation snapshot (the market-cap magnitude terrain needs).     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MarketAndValuationSnapshot:
    """Market cap / price / shares / latest revenue -- each with its own provenance.

    ``market_cap`` typically comes from FMP (convenience); ``shares_outstanding`` and
    ``latest_revenue`` prefer SEC company facts (canonical). Every field is an
    :class:`EnrichmentValue`, so the authority mix is explicit and never flattened.
    """
    ticker: str = ""
    market_cap: EnrichmentValue = field(default_factory=EnrichmentValue)
    price: EnrichmentValue = field(default_factory=EnrichmentValue)
    shares_outstanding: EnrichmentValue = field(default_factory=EnrichmentValue)
    latest_revenue: EnrichmentValue = field(default_factory=EnrichmentValue)
    currency: str = "USD"
    as_of: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"

    @property
    def market_cap_value(self) -> Optional[float]:
        if not self.market_cap.present:
            return None
        try:
            return float(self.market_cap.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None


# --------------------------------------------------------------------------- #
# 3. TAM / revenue-pool estimate. estimate_type keeps the SOURCE KIND explicit. #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TAMRevenuePoolEstimate:
    """A TAM / revenue-pool magnitude estimate with an EXPLICIT ``estimate_type``.

    ``estimate_type`` is one of ``reported`` / ``analyst`` / ``company_guidance`` /
    ``inferred`` / ``manual``. A manual estimate carries ``authority == "manual"`` and
    ``claim_status == "manual"`` on its :class:`EnrichmentValue` -- it is NEVER promoted to
    canonical.
    """
    market_label: str = ""
    estimate_type: str = "inferred"   # reported / analyst / company_guidance / inferred / manual
    amount: EnrichmentValue = field(default_factory=EnrichmentValue)
    methodology_note: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"

    @property
    def present(self) -> bool:
        return self.amount.present

    @property
    def amount_value(self) -> Optional[float]:
        if not self.amount.present:
            return None
        try:
            return float(self.amount.value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None


# --------------------------------------------------------------------------- #
# 4. Value-chain evidence (ordered layers + supplier / customer evidence).      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ValueChainLayerEvidence:
    """One ordered value-chain layer (upstream .. downstream) as EVIDENCE, not a score.

    ``sequence`` is the upstream->downstream position (0 = most upstream). It is deliberately
    NOT named ``order`` so no field on any enrichment model collides with trade vocabulary.
    """
    label: str = ""
    sequence: int = 0
    description: str = ""
    companies: Tuple[str, ...] = field(default_factory=tuple)
    suppliers: Tuple[str, ...] = field(default_factory=tuple)
    customers: Tuple[str, ...] = field(default_factory=tuple)
    bottleneck_exposure: str = ""
    authority: str = ""
    claim_status: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ValueChainEvidenceProfile:
    """Ordered value-chain layers + supplier / customer evidence for one company."""
    ticker: str = ""
    chain_name: str = ""
    layers: Tuple[ValueChainLayerEvidence, ...] = field(default_factory=tuple)
    suppliers: Tuple[str, ...] = field(default_factory=tuple)
    customers: Tuple[str, ...] = field(default_factory=tuple)
    authority: str = ""
    claim_status: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"

    @property
    def present(self) -> bool:
        return bool(self.layers)


# --------------------------------------------------------------------------- #
# 5. Bottleneck evidence (labelled severity / duration -- never a number).      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BottleneckEvidenceProfile:
    """Evidence of a scarce, constrained node. Severity / duration are LABELS."""
    ticker: str = ""
    name: str = ""
    bottleneck_type: str = ""
    severity: str = ""              # label: e.g. acute / moderate / mild (never a number)
    expected_duration: str = ""     # label: e.g. multi_year / transient
    constrained_resource: str = ""
    beneficiaries: Tuple[str, ...] = field(default_factory=tuple)
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    authority: str = ""
    claim_status: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"

    @property
    def present(self) -> bool:
        return bool(self.name or self.severity or self.expected_duration)


# --------------------------------------------------------------------------- #
# 6. Company IR evidence -> catalyst / risk / evidence CONTEXT (company_claim).  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CompanyIREvidenceProfile:
    """Investor-relations evidence: decks, transcripts, guidance, disclosed catalysts.

    Guidance statements are ``company_claim`` -- a claim the company MADE, not a verified
    fact. They are context for catalysts / risks, never an investment recommendation.
    """
    ticker: str = ""
    investor_presentation_refs: Tuple[str, ...] = field(default_factory=tuple)
    earnings_transcript_refs: Tuple[str, ...] = field(default_factory=tuple)
    ir_page_refs: Tuple[str, ...] = field(default_factory=tuple)
    guidance_statements: Tuple[EnrichmentValue, ...] = field(default_factory=tuple)
    disclosed_catalysts: Tuple[str, ...] = field(default_factory=tuple)
    disclosed_risks: Tuple[str, ...] = field(default_factory=tuple)
    authority: str = ""
    claim_status: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"

    @property
    def present(self) -> bool:
        return bool(self.investor_presentation_refs or self.earnings_transcript_refs
                    or self.ir_page_refs or self.guidance_statements
                    or self.disclosed_catalysts or self.disclosed_risks)


# --------------------------------------------------------------------------- #
# 7. Leadership evidence (diagnostics only -- never touches an alpha metric).    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LeadershipMember:
    """One named leader as EVIDENCE (name / role / tenure). No score."""
    name: str = ""
    role: str = ""
    since: str = ""
    note: str = ""


@dataclass(frozen=True)
class LeadershipEvidenceProfile:
    """Leadership / management evidence -- surfaced in diagnostics only."""
    ticker: str = ""
    members: Tuple[LeadershipMember, ...] = field(default_factory=tuple)
    tenure_note: str = ""
    authority: str = ""
    claim_status: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    confidence_label: str = "missing"

    @property
    def present(self) -> bool:
        return bool(self.members)


# --------------------------------------------------------------------------- #
# 8. The whole bundle: ticker + all the above + coverage / gaps / provenance.    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DiligenceEnrichmentBundle:
    """All diligence-input enrichment for ONE ticker, with explicit coverage + gaps.

    ``enrichment_status`` is a completeness LABEL (``empty`` / ``sparse`` / ``partial``),
    never a score. ``source_coverage`` counts data-bearing values by authority. Anything
    not supplied by a fixture / source is an explicit ``data_gaps`` entry, never invented.
    """
    ticker: str = ""
    profile: CompanyDiligenceProfile = field(default_factory=CompanyDiligenceProfile)
    market: MarketAndValuationSnapshot = field(default_factory=MarketAndValuationSnapshot)
    tam_estimate: TAMRevenuePoolEstimate = field(default_factory=TAMRevenuePoolEstimate)
    value_chain: ValueChainEvidenceProfile = field(default_factory=ValueChainEvidenceProfile)
    bottleneck: BottleneckEvidenceProfile = field(default_factory=BottleneckEvidenceProfile)
    ir: CompanyIREvidenceProfile = field(default_factory=CompanyIREvidenceProfile)
    leadership: LeadershipEvidenceProfile = field(default_factory=LeadershipEvidenceProfile)
    source_coverage: Dict[str, int] = field(default_factory=dict)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: Tuple[str, ...] = field(default_factory=tuple)
    enrichment_status: str = "empty"

    # --- convenience readers (magnitudes only; never a metric) --------------- #
    @property
    def market_cap_value(self) -> Optional[float]:
        return self.market.market_cap_value

    @property
    def tam_value(self) -> Optional[float]:
        return self.tam_estimate.amount_value

    def has_market_cap(self) -> bool:
        return self.market_cap_value is not None

    def has_tam(self) -> bool:
        return self.tam_value is not None
