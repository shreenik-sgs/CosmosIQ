"""Infinite Canvas -- READ-ONLY view models + projection builders (IMPLEMENTATION-008A).

This module is a pure PROJECTION layer. It takes the canonical pipeline objects
(Observation -> IntelligenceAssessment -> OpportunityHypothesis -> InvestmentThesis
-> InvestmentAction -> PersonalizedAction -> ManualExecutionIntent -> ManualTradeTicket)
and re-presents their *already-computed* fields as UI-facing panel view models.

Discipline (the acceptance crux):

* **Read-only & no recomputation.** Every value on a view model is COPIED verbatim
  from a source object field. Nothing here averages, re-scores, or derives a number.
  A panel's ``suitability_score`` ``==`` the PersonalizedAction's; a player's
  ``winner_score`` ``==`` the WinnerScore's. The only logic permitted is copying,
  formatting, and assembling provenance + honest missing-data flags.
* **No fabricated data.** Where a panel field has no backing source field (TAM,
  market share, moat depth, supplier-of-supplier depth, VWAP, anchored VWAP,
  overhead supply, extreme-bull, valuation method, sensitivity drivers, ...), the
  value is ``None`` and its name is listed in that panel's ``missing_fields`` with a
  note -- never invented.
* **Never mutate source objects.** All view models are ``frozen`` dataclasses; the
  builders only read.
* **Boundary preserved.** The personalized panel shows a sizing RANGE / max-exposure
  % only (no orders / exact shares / contracts); the technical panel uses
  timing-confirmation language; the value-chain/players panel notes that security
  mapping FOLLOWS winner mapping; positive vs negative catalysts are kept separate
  and ``speculative_rumor`` is flagged in its own field.

Stdlib only, Python 3.9, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields as dc_fields
from typing import Any, Optional, Tuple

# Source-layer (book namespace) labels for the DATA-SOURCE provenance vocabulary.
LAYER_TATTVA = "Tattva"        # Reality Intelligence
LAYER_SPHURANA = "Sphurana"    # Genesis
LAYER_NIVESHA = "Nivesha"      # Prometheus
LAYER_SAARATHI = "Saarathi"    # Personal CIO
LAYER_KRIYA = "Kriya"          # Execution (manual)

# DATA-SOURCE-001 source_class vocabulary. For this MVP there is no 009 ingestion,
# so every panel's data origin is honestly "manual".
SOURCE_CLASS_MANUAL = "manual"

_REQUIRES_009 = "requires 009 ingestion / manual entry"


# --------------------------------------------------------------------------- #
# Shared provenance primitives                                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EvidenceRef:
    """An immutable (id, version, kind) provenance pointer to a source object."""

    object_id: str
    version: int
    kind: str


@dataclass(frozen=True)
class PanelProvenance:
    """The source objects a panel was projected from, plus the upstream Observations."""

    sources: Tuple[EvidenceRef, ...] = field(default_factory=tuple)
    upstream_observation_ids: Tuple[str, ...] = field(default_factory=tuple)


def evidence_ref(obj: Any, kind: str) -> EvidenceRef:
    """Build an :class:`EvidenceRef` from a canonical object's id/version + a kind."""
    return EvidenceRef(
        object_id=str(getattr(obj, "id", "")),
        version=int(getattr(obj, "version", 1)),
        kind=kind,
    )


@dataclass(frozen=True)
class PanelView:
    """Base for every panel view model -- the cross-cutting fields every panel carries.

    All fields default, so subclasses may add their own (also defaulted) fields and
    builders construct by keyword.
    """

    panel_id: str = ""
    source_layer: str = ""
    source_class: str = SOURCE_CLASS_MANUAL
    source_object_ids: Tuple[str, ...] = field(default_factory=tuple)
    source_object_versions: Tuple[int, ...] = field(default_factory=tuple)
    confidence: Optional[float] = None
    evidence_quality: Optional[float] = None
    provenance: PanelProvenance = field(default_factory=PanelProvenance)
    missing_fields: Tuple[str, ...] = field(default_factory=tuple)
    data_notes: Tuple[str, ...] = field(default_factory=tuple)


def _xc(panel_id, layer, sources, upstream_obs,
        confidence=None, evidence_quality=None, missing=(), notes=()):
    """Assemble the cross-cutting kwargs shared by every panel.

    ``sources`` is an iterable of ``(object, kind)`` pairs. The panel's
    ``source_object_ids`` / ``source_object_versions`` / ``provenance`` are derived
    purely from those source objects -- nothing is recomputed.
    """
    refs = tuple(evidence_ref(obj, kind) for (obj, kind) in sources if obj is not None)
    return dict(
        panel_id=panel_id,
        source_layer=layer,
        source_class=SOURCE_CLASS_MANUAL,
        source_object_ids=tuple(r.object_id for r in refs),
        source_object_versions=tuple(r.version for r in refs),
        confidence=confidence,
        evidence_quality=evidence_quality,
        provenance=PanelProvenance(
            sources=refs, upstream_observation_ids=tuple(upstream_obs)
        ),
        missing_fields=tuple(missing),
        data_notes=tuple(notes),
    )


# --------------------------------------------------------------------------- #
# Nested (non-panel) item view models                                         #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ValueChainNodeView:
    node_id: str
    tier: int
    role: str
    choke_point: bool
    substitution_difficulty: float
    pricing_power: float
    margin_capture_potential: float
    capital_intensity: float
    economic_leverage_score: float


@dataclass(frozen=True)
class PlayerRoleView:
    name: str
    ticker: str
    value_chain_role: str
    tier: int
    winner_score: float
    exposure_directness: float
    margin_capture_ability: float
    pricing_power: float
    competitive_position: float
    execution_capability: float
    financing_dilution_risk: float
    balance_sheet_risk: float
    customer_concentration: float
    leadership_quality: float
    key_risks: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CatalystItemView:
    catalyst_type: Optional[str]
    catalyst_status: Optional[str]
    expected_direction: Optional[str]
    expected_timing_window: Optional[str] = None
    expected_business_impact: Optional[str] = None
    affected_value_chain_node: Optional[str] = None
    novelty: Optional[float] = None
    evidence_quality: Optional[float] = None
    monitoring_only: Optional[bool] = None
    dilution_flag: Optional[bool] = None


@dataclass(frozen=True)
class RedTeamCheckView:
    check: str
    verdict: str
    rationale: str


# --------------------------------------------------------------------------- #
# 1. Opportunity Map panel  (Sphurana / OpportunityHypothesis)                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OpportunityMapPanel(PanelView):
    theme: str = ""
    theme_maturity: str = ""
    megatrend_context: Tuple[str, ...] = field(default_factory=tuple)
    cross_domain_convergence: Tuple[str, ...] = field(default_factory=tuple)
    why_now: str = ""
    why_before_obvious: str = ""
    opportunity_timing: str = ""
    opportunity_maturity: str = ""
    opportunity_magnitude: str = ""
    bottleneck_driven: bool = False
    driving_constraint: str = ""
    value_chain_position: str = ""
    false_positive_risk: str = ""
    bubble_hype_risk: str = ""
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)


def build_opportunity_map_panel(opportunity_hypothesis) -> OpportunityMapPanel:
    oh = opportunity_hypothesis
    return OpportunityMapPanel(
        **_xc(
            "opportunity_map", LAYER_SPHURANA,
            [(oh, "OpportunityHypothesis")],
            getattr(oh, "upstream_observation_ids", ()),
            confidence=getattr(oh, "confidence", None),
            evidence_quality=getattr(oh, "evidence_strength", None),
        ),
        theme=oh.theme,
        theme_maturity=oh.theme_maturity,
        megatrend_context=tuple(oh.megatrend_context),
        cross_domain_convergence=tuple(oh.cross_domain_convergence),
        why_now=oh.why_now,
        why_before_obvious=oh.why_before_obvious,
        opportunity_timing=oh.opportunity_timing,
        opportunity_maturity=oh.opportunity_maturity,
        opportunity_magnitude=oh.opportunity_magnitude,
        bottleneck_driven=oh.bottleneck_driven,
        driving_constraint=oh.driving_constraint,
        value_chain_position=oh.value_chain_position,
        false_positive_risk=oh.false_positive_risk,
        bubble_hype_risk=oh.bubble_hype_risk,
        monitoring_signals=tuple(oh.monitoring_signals),
    )


# --------------------------------------------------------------------------- #
# 2. Value-Chain + Bottleneck panel (MERGED)  (Nivesha / InvestmentThesis)    #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ValueChainBottleneckPanel(PanelView):
    # value chain
    value_chain_nodes: Tuple[ValueChainNodeView, ...] = field(default_factory=tuple)
    value_chain_capture: Optional[float] = None
    capture_role: str = ""
    # players (security mapping FOLLOWS winners)
    players: Tuple[PlayerRoleView, ...] = field(default_factory=tuple)
    security_or_instrument_mapping: str = ""
    security_mapping_follows_winners: bool = True
    # bottleneck
    bottleneck_type: str = ""
    constrained_node: str = ""
    severity: Optional[float] = None
    duration: str = ""
    resolution_risk: Optional[float] = None
    bottleneck_evidence_quality: Optional[float] = None
    direct_beneficiaries: Tuple[str, ...] = field(default_factory=tuple)
    indirect_beneficiaries: Tuple[str, ...] = field(default_factory=tuple)
    constrained_losers: Tuple[str, ...] = field(default_factory=tuple)
    timing_window: str = ""
    bottleneck_leverage: Optional[float] = None


def _value_chain_node_view(n) -> ValueChainNodeView:
    return ValueChainNodeView(
        node_id=n.node_id,
        tier=n.tier,
        role=n.role,
        choke_point=n.choke_point,
        substitution_difficulty=n.substitution_difficulty,
        pricing_power=n.pricing_power,
        margin_capture_potential=n.margin_capture_potential,
        capital_intensity=n.capital_intensity,
        economic_leverage_score=n.economic_leverage_score,
    )


def _player_view(w) -> PlayerRoleView:
    return PlayerRoleView(
        name=w.name,
        ticker=w.ticker,
        value_chain_role=w.value_chain_role,
        tier=w.tier,
        winner_score=w.winner_score,
        exposure_directness=w.exposure_directness,
        margin_capture_ability=w.margin_capture_ability,
        pricing_power=w.pricing_power,
        competitive_position=w.competitive_position,
        execution_capability=w.execution_capability,
        financing_dilution_risk=w.financing_dilution_risk,
        balance_sheet_risk=w.balance_sheet_risk,
        customer_concentration=w.customer_concentration,
        leadership_quality=w.leadership_quality,
        key_risks=tuple(w.key_risks),
    )


def build_value_chain_bottleneck_panel(investment_thesis) -> ValueChainBottleneckPanel:
    t = investment_thesis
    vc = t.value_chain_summary
    bn = t.bottleneck_summary
    winners = tuple(t.winner_mapping)

    nodes = tuple(_value_chain_node_view(n) for n in getattr(vc, "nodes", ()))
    players = tuple(_player_view(w) for w in winners)

    notes = (
        "security/instrument mapping FOLLOWS winner mapping (computed after scoring)",
        "leadership_quality is an MVP placeholder (0.5 for every candidate)",
        "customer_concentration is an MVP placeholder (not yet modelled)",
    )
    # Honest gaps -- the current pipeline carries no moat/supplier-depth detail.
    missing = (
        "moat_details ({0})".format(_REQUIRES_009),
        "supplier_of_supplier_depth ({0})".format(_REQUIRES_009),
    )

    return ValueChainBottleneckPanel(
        **_xc(
            "value_chain_bottleneck", LAYER_NIVESHA,
            [(t, "InvestmentThesis")],
            getattr(t, "upstream_observation_ids", ()),
            confidence=getattr(t, "thesis_confidence", None),
            evidence_quality=getattr(bn, "evidence_quality", None),
            missing=missing,
            notes=notes,
        ),
        value_chain_nodes=nodes,
        value_chain_capture=getattr(vc, "value_chain_capture", None),
        capture_role=getattr(vc, "capture_role", ""),
        players=players,
        security_or_instrument_mapping=t.security_or_instrument_mapping,
        security_mapping_follows_winners=True,
        bottleneck_type=getattr(bn, "bottleneck_type", ""),
        constrained_node=getattr(bn, "constrained_node", ""),
        severity=getattr(bn, "severity", None),
        duration=getattr(bn, "duration", ""),
        resolution_risk=getattr(bn, "resolution_risk", None),
        bottleneck_evidence_quality=getattr(bn, "evidence_quality", None),
        direct_beneficiaries=tuple(getattr(bn, "direct_beneficiaries", ())),
        indirect_beneficiaries=tuple(getattr(bn, "indirect_beneficiaries", ())),
        constrained_losers=tuple(getattr(bn, "constrained_losers", ())),
        timing_window=getattr(bn, "timing_window", ""),
        bottleneck_leverage=getattr(bn, "bottleneck_leverage", None),
    )


# --------------------------------------------------------------------------- #
# 3. Catalyst panel  (Tattva IA catalysts + Nivesha repricing/red-team)       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CatalystPanel(PanelView):
    # positive / negative kept SEPARATE; speculative rumours in their own field.
    positive_catalysts: Tuple[CatalystItemView, ...] = field(default_factory=tuple)
    negative_catalysts: Tuple[CatalystItemView, ...] = field(default_factory=tuple)
    speculative_rumors: Tuple[CatalystItemView, ...] = field(default_factory=tuple)
    repricing_key_trigger_events: Tuple[str, ...] = field(default_factory=tuple)
    red_team_catalyst_check: Optional[RedTeamCheckView] = None


def _positive_catalyst_view(c: dict) -> CatalystItemView:
    return CatalystItemView(
        catalyst_type=c.get("catalyst_type"),
        catalyst_status=c.get("catalyst_status"),
        expected_direction=c.get("expected_direction"),
        expected_timing_window=c.get("expected_timing_window"),
        expected_business_impact=c.get("expected_business_impact"),
        affected_value_chain_node=c.get("affected_value_chain_node"),
        novelty=c.get("novelty"),
        evidence_quality=c.get("evidence_quality"),
        monitoring_only=c.get("monitoring_only"),
    )


def _negative_catalyst_view(c: dict) -> CatalystItemView:
    return CatalystItemView(
        catalyst_type=c.get("risk_type"),
        catalyst_status=c.get("catalyst_status"),
        expected_direction=c.get("expected_direction"),
        evidence_quality=c.get("evidence_quality"),
        dilution_flag=c.get("dilution_flag"),
    )


def build_catalyst_panel(investment_thesis, intelligence_assessment=None) -> CatalystPanel:
    t = investment_thesis
    ia = intelligence_assessment

    positives = []
    rumors = []
    negatives = []
    missing = []
    notes = []

    if ia is not None:
        for c in getattr(ia, "catalysts", ()):
            view = _positive_catalyst_view(c)
            if view.catalyst_status == "speculative_rumor":
                # Separated, never merged with confirmed/probable/possible, and never
                # promoted into the positive list.
                rumors.append(view)
            else:
                positives.append(view)
        for c in getattr(ia, "capital_structure_risks", ()):
            view = _negative_catalyst_view(c)
            if view.catalyst_status == "speculative_rumor":
                rumors.append(view)
            else:
                negatives.append(view)
        if not positives:
            missing.append("positive_catalysts (no confirmed/probable in this assessment)")
        if not negatives:
            missing.append("negative_catalysts (no capital-structure risks in this assessment)")
        notes.append(
            "speculative_rumor catalysts are isolated and carry only their discounted "
            "source evidence_quality -- they raise no confidence value here")
    else:
        missing.append("catalysts ({0}; no IntelligenceAssessment supplied)".format(_REQUIRES_009))

    repricing = t.repricing_trigger_summary
    red = t.red_team_summary
    rt_check = None
    for ch in getattr(red, "checks", ()):
        if ch.check == "catalyst_doesnt_materialize":
            rt_check = RedTeamCheckView(check=ch.check, verdict=ch.verdict, rationale=ch.rationale)
            break

    sources = [(t, "InvestmentThesis")]
    upstream = list(getattr(t, "upstream_observation_ids", ()))
    if ia is not None:
        sources.insert(0, (ia, "IntelligenceAssessment"))
        for oid in getattr(ia, "grounding_observation_ids", ()):
            if oid not in upstream:
                upstream.append(oid)

    return CatalystPanel(
        **_xc(
            "catalyst", LAYER_TATTVA, sources, upstream,
            missing=missing, notes=notes,
        ),
        positive_catalysts=tuple(positives),
        negative_catalysts=tuple(negatives),
        speculative_rumors=tuple(rumors),
        repricing_key_trigger_events=tuple(getattr(repricing, "key_trigger_events", ())),
        red_team_catalyst_check=rt_check,
    )


# --------------------------------------------------------------------------- #
# 4. Financial Inflection panel  (Nivesha / financial_inflection_summary)     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FinancialInflectionPanel(PanelView):
    revenue_inflection: Optional[float] = None
    margin_expansion: Optional[float] = None
    guidance_adjustment: Optional[float] = None
    dilution_penalty: Optional[float] = None
    financing_penalty: Optional[float] = None
    financial_inflection_probability: Optional[float] = None
    financial_inflection_score: Optional[float] = None
    notes: Tuple[str, ...] = field(default_factory=tuple)
    # Absent in the current FinancialInflectionResult (honest gaps):
    operating_leverage: Optional[float] = None
    ebitda: Optional[float] = None
    fcf: Optional[float] = None
    backlog: Optional[float] = None
    guidance: Optional[str] = None
    capex: Optional[float] = None
    cash_runway: Optional[float] = None
    unit_economics: Optional[float] = None
    customer_concentration: Optional[float] = None
    inflection_timing: Optional[str] = None


def build_financial_inflection_panel(investment_thesis) -> FinancialInflectionPanel:
    t = investment_thesis
    f = t.financial_inflection_summary
    missing = tuple(
        "{0} ({1})".format(name, _REQUIRES_009)
        for name in (
            "operating_leverage", "ebitda", "fcf", "backlog", "guidance", "capex",
            "cash_runway", "unit_economics", "customer_concentration", "inflection_timing",
        )
    )
    return FinancialInflectionPanel(
        **_xc(
            "financial_inflection", LAYER_NIVESHA,
            [(t, "InvestmentThesis")],
            getattr(t, "upstream_observation_ids", ()),
            confidence=getattr(f, "financial_inflection_probability", None),
            missing=missing,
        ),
        revenue_inflection=getattr(f, "revenue_inflection", None),
        margin_expansion=getattr(f, "margin_expansion", None),
        guidance_adjustment=getattr(f, "guidance_adjustment", None),
        dilution_penalty=getattr(f, "dilution_penalty", None),
        financing_penalty=getattr(f, "financing_penalty", None),
        financial_inflection_probability=getattr(f, "financial_inflection_probability", None),
        financial_inflection_score=getattr(f, "financial_inflection_score", None),
        notes=tuple(getattr(f, "notes", ())),
    )


# --------------------------------------------------------------------------- #
# 5. Scenario / Asymmetry panel  (Nivesha / asymmetry_summary)                #
# --------------------------------------------------------------------------- #
_DISTINCTION = (
    "A good COMPANY is not a good THESIS; a good thesis is not a good STOCK; "
    "a good stock is not necessarily an ASYMMETRIC stock -- this panel frames the "
    "payoff (asymmetry), not the narrative.",
)


@dataclass(frozen=True)
class ScenarioAsymmetryPanel(PanelView):
    downside_risk: Optional[float] = None
    upside_potential: Optional[float] = None
    upside_downside_ratio: Optional[float] = None
    prob_weighted_ev: Optional[float] = None
    asymmetry_score: Optional[float] = None
    asymmetry_label: str = ""
    effective_bear_price: Optional[float] = None
    notes: Tuple[str, ...] = field(default_factory=tuple)
    # Scenario anchors are NOT carried on the thesis summary -> honest gaps.
    bear_price: Optional[float] = None
    base_price: Optional[float] = None
    bull_price: Optional[float] = None
    extreme_bull_price: Optional[float] = None
    valuation_method: Optional[str] = None
    sensitivity_drivers: Optional[Tuple[str, ...]] = None
    invalidation_triggers: Optional[Tuple[str, ...]] = None
    current_tam: Optional[float] = None
    implied_market_share: Optional[float] = None


def build_scenario_asymmetry_panel(investment_thesis) -> ScenarioAsymmetryPanel:
    t = investment_thesis
    a = t.asymmetry_summary
    missing = tuple(
        "{0} ({1})".format(name, _REQUIRES_009)
        for name in (
            "bear_price", "base_price", "bull_price", "extreme_bull_price",
            "valuation_method", "sensitivity_drivers", "invalidation_triggers",
            "current_tam", "implied_market_share",
        )
    )
    return ScenarioAsymmetryPanel(
        **_xc(
            "scenario_asymmetry", LAYER_NIVESHA,
            [(t, "InvestmentThesis")],
            getattr(t, "upstream_observation_ids", ()),
            missing=missing,
            notes=_DISTINCTION,
        ),
        downside_risk=getattr(a, "downside_risk", None),
        upside_potential=getattr(a, "upside_potential", None),
        upside_downside_ratio=getattr(a, "upside_downside_ratio", None),
        prob_weighted_ev=getattr(a, "prob_weighted_ev", None),
        asymmetry_score=getattr(a, "asymmetry_score", None),
        asymmetry_label=getattr(a, "asymmetry_label", ""),
        effective_bear_price=getattr(a, "effective_bear_price", None),
        notes=tuple(getattr(a, "notes", ())),
    )


# --------------------------------------------------------------------------- #
# 6. Technical Confirmation panel  (Nivesha / technical_inflection_summary)   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TechnicalConfirmationPanel(PanelView):
    ema_stack_status: str = ""
    trend_alignment: Optional[bool] = None
    compression_breakout_status: str = ""
    breakout: Optional[bool] = None
    volume_confirmation: Optional[bool] = None
    relative_strength_confirmation: Optional[bool] = None
    failed_breakout_risk: Optional[bool] = None
    dilution_overhang_penalty: Optional[float] = None
    technical_setup_score: Optional[float] = None
    timing_quality: str = ""
    # timing-confirmation flag (NEVER "action-ready").
    technical_timing_confirmation: Optional[bool] = None
    notes: Tuple[str, ...] = field(default_factory=tuple)
    # Absent on the result (honest gaps):
    vwap: Optional[float] = None
    anchored_vwap: Optional[float] = None
    overhead_supply: Optional[float] = None
    invalidation_level: Optional[float] = None


def build_technical_confirmation_panel(investment_thesis) -> TechnicalConfirmationPanel:
    t = investment_thesis
    tech = t.technical_inflection_summary
    missing = tuple(
        "{0} ({1})".format(name, _REQUIRES_009)
        for name in ("vwap", "anchored_vwap", "overhead_supply", "invalidation_level")
    )
    return TechnicalConfirmationPanel(
        **_xc(
            "technical_confirmation", LAYER_NIVESHA,
            [(t, "InvestmentThesis")],
            getattr(t, "upstream_observation_ids", ()),
            confidence=getattr(tech, "technical_setup_score", None),
            missing=missing,
            notes=("timing-confirmation flag only -- this is NOT an action / order signal",),
        ),
        ema_stack_status=getattr(tech, "ema_stack_status", ""),
        trend_alignment=getattr(tech, "trend_alignment", None),
        compression_breakout_status=getattr(tech, "compression_breakout_status", ""),
        breakout=getattr(tech, "breakout", None),
        volume_confirmation=getattr(tech, "volume_confirmation", None),
        relative_strength_confirmation=getattr(tech, "relative_strength_confirmation", None),
        failed_breakout_risk=getattr(tech, "failed_breakout_risk", None),
        dilution_overhang_penalty=getattr(tech, "dilution_overhang_penalty", None),
        technical_setup_score=getattr(tech, "technical_setup_score", None),
        timing_quality=getattr(tech, "timing_quality", ""),
        technical_timing_confirmation=getattr(tech, "technical_confirmation", None),
        notes=tuple(getattr(tech, "notes", ())),
    )


# --------------------------------------------------------------------------- #
# 7. Red Team panel  (Nivesha / red_team_summary)                             #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RedTeamPanel(PanelView):
    checks: Tuple[RedTeamCheckView, ...] = field(default_factory=tuple)
    red_team_verdict: str = ""
    confidence_haircut: Optional[float] = None
    false_positive_label: str = ""
    kill_risks: Optional[Tuple[str, ...]] = None


def build_red_team_panel(investment_thesis) -> RedTeamPanel:
    t = investment_thesis
    red = t.red_team_summary
    checks = tuple(
        RedTeamCheckView(check=ch.check, verdict=ch.verdict, rationale=ch.rationale)
        for ch in getattr(red, "checks", ())
    )
    return RedTeamPanel(
        **_xc(
            "red_team", LAYER_NIVESHA,
            [(t, "InvestmentThesis")],
            getattr(t, "upstream_observation_ids", ()),
            missing=("kill_risks ({0})".format(_REQUIRES_009),),
        ),
        checks=checks,
        red_team_verdict=getattr(red, "red_team_verdict", ""),
        confidence_haircut=getattr(red, "confidence_haircut", None),
        false_positive_label=getattr(red, "false_positive_label", ""),
    )


# --------------------------------------------------------------------------- #
# 8. Personalized Action panel  (Saarathi / PersonalizedAction)               #
#    RANGE / max-exposure % only -- NO exact size / order / shares.           #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PersonalizedActionPanel(PanelView):
    recommendation_status: str = ""
    suitability_score: Optional[float] = None
    concentration_score: Optional[float] = None
    liquidity_score: Optional[float] = None
    risk_fit_score: Optional[float] = None
    portfolio_fit_score: Optional[float] = None
    recommended_max_exposure_pct: Optional[float] = None
    suggested_sizing_range_pct: Tuple[float, float] = (0.0, 0.0)
    blocking_conditions: Tuple[str, ...] = field(default_factory=tuple)
    risk_warnings: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)
    required_user_confirmations: Tuple[str, ...] = field(default_factory=tuple)
    review_triggers: Tuple[str, ...] = field(default_factory=tuple)


def build_personalized_action_panel(personalized_action) -> PersonalizedActionPanel:
    p = personalized_action
    return PersonalizedActionPanel(
        **_xc(
            "personalized_action", LAYER_SAARATHI,
            [(p, "PersonalizedAction")],
            getattr(p, "upstream_observation_ids", ()),
            confidence=getattr(p, "suitability_score", None),
            notes=("recommends a sizing RANGE / max-exposure % only -- never an exact "
                   "order, share count, or contract count (cognition/actuation boundary)",),
        ),
        recommendation_status=p.recommendation_status,
        suitability_score=p.suitability_score,
        concentration_score=p.concentration_score,
        liquidity_score=p.liquidity_score,
        risk_fit_score=p.risk_fit_score,
        portfolio_fit_score=p.portfolio_fit_score,
        recommended_max_exposure_pct=p.recommended_max_exposure_pct,
        suggested_sizing_range_pct=tuple(p.suggested_sizing_range_pct),
        blocking_conditions=tuple(p.blocking_conditions),
        risk_warnings=tuple(p.risk_warnings),
        monitoring_signals=tuple(p.monitoring_signals),
        required_user_confirmations=tuple(p.required_user_confirmations),
        review_triggers=tuple(p.review_triggers),
    )


# --------------------------------------------------------------------------- #
# 9. Manual Execution panel  (Kriya / ManualExecutionIntent + optional ticket)#
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ManualExecutionPanel(PanelView):
    execution_intent_id: str = ""
    selected_instrument: str = ""
    # The user's explicit chosen size FIRST exists here (downstream of Saarathi).
    user_selected_allocation_amount: Optional[float] = None
    user_selected_allocation_pct: Optional[float] = None
    execution_side: str = ""
    account: str = ""
    user_confirmation_required: Optional[bool] = None
    stale_check_required: Optional[bool] = None
    preview_required: Optional[bool] = None
    # Optional Kriya ticket PREVIEW (operational; manual placement only).
    ticket_id: Optional[str] = None
    ticket_state: Optional[str] = None
    ticket_quantity: Optional[int] = None
    order_type: Optional[str] = None
    limit_price: Optional[float] = None
    estimated_cost: Optional[float] = None
    preview_hash: Optional[str] = None
    # broker_order_id is a record the USER fills in after placing the trade by hand;
    # it is NOT created by the system and triggers no automated submission.
    broker_order_id: Optional[str] = None
    reconciliation_all_reconciled: Optional[bool] = None
    audit_entry_count: Optional[int] = None
    manual_execution_only: bool = True


def build_manual_execution_panel(manual_execution_intent, *, ticket=None,
                                 reconciliation=None, audit_trail=None) -> ManualExecutionPanel:
    intent = manual_execution_intent
    sources = [(intent, "ManualExecutionIntent")]
    missing = []
    notes = [
        "execution is MANUAL and outside the system: no broker adapter, no automated "
        "submission. broker_order_id is recorded by the user only after a hand-placed trade.",
    ]

    ticket_kwargs = dict(
        ticket_id=None, ticket_state=None, ticket_quantity=None, order_type=None,
        limit_price=None, estimated_cost=None, preview_hash=None, broker_order_id=None,
    )
    if ticket is not None:
        sources.append((ticket, "ManualTradeTicket"))
        ticket_kwargs = dict(
            ticket_id=ticket.id,
            ticket_state=ticket.state,
            ticket_quantity=ticket.quantity,
            order_type=ticket.order_type,
            limit_price=ticket.limit_price,
            estimated_cost=ticket.estimated_cost,
            preview_hash=ticket.preview_hash,
            broker_order_id=ticket.broker_order_id,
        )
    else:
        missing.append("ticket_preview (no ManualTradeTicket supplied)")

    recon = None
    if reconciliation is not None:
        recon = bool(getattr(reconciliation, "all_reconciled", False))

    audit_count = None
    if audit_trail is not None:
        audit_count = len(audit_trail)

    return ManualExecutionPanel(
        **_xc(
            "manual_execution", LAYER_KRIYA, sources,
            getattr(intent, "upstream_observation_ids", ()),
            missing=missing, notes=notes,
        ),
        execution_intent_id=intent.id,
        selected_instrument=intent.selected_instrument,
        user_selected_allocation_amount=intent.user_selected_allocation_amount,
        user_selected_allocation_pct=intent.user_selected_allocation_pct,
        execution_side=intent.execution_side,
        account=intent.account,
        user_confirmation_required=intent.user_confirmation_required,
        stale_check_required=intent.stale_check_required,
        preview_required=intent.preview_required,
        reconciliation_all_reconciled=recon,
        audit_entry_count=audit_count,
        manual_execution_only=True,
        **ticket_kwargs,
    )


def panel_field_names(panel) -> Tuple[str, ...]:
    """The declared dataclass field names of a panel (used by adversarial tests)."""
    return tuple(f.name for f in dc_fields(panel))
