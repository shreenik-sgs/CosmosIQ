"""Staged adapters that BUILD terrain nodes from pipeline outputs (fixture/demo).

IMPLEMENTATION-010B seam, extended by IMPLEMENTATION-010C. These are PURE mapping
functions from prior, already-computed pipeline objects (an investment thesis, an
intelligence assessment, a red-team summary, the IREN evidence-alpha slice) into the
typed terrain nodes of :mod:`universe_ui.terrain`.

They do NOT perform any live data access, scheduling, broker automation, or new scoring,
and they do NOT mutate the upstream reasoning objects -- they only READ existing fields
and re-express them as metadata.

``terrain_from_slice`` now builds a REAL, sparse :class:`UniverseTerrain` (mode
``evidence_ingested_fixture``) from the accepted 009G evidence-alpha slice: ONE galaxy /
theme (the candidate's), one value chain, a constraint-context bottleneck, and the IREN
company planet -- all projected from the ALREADY-COMPUTED artifacts. Where the pipeline
did not produce a field (TAM, supplier-of-supplier coverage, a discrete bottleneck,
market cap) the builder records an explicit data gap and a neutral encoding -- it never
fabricates a value. The terrain is deliberately incomplete; that incompleteness is
surfaced as data gaps + missing-data placeholders, not hidden.

Deterministic, stdlib-only, Python 3.9. No network, no clock, no secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from .demo_terrain import _catalyst_status
from .demo_universe import build_demo_universe
from .terrain import (
    BottleneckNode,
    CatalystNode,
    CompanyNode,
    DependencyNode,
    GalaxyNode,
    RiskNode,
    ThemeNode,
    UniverseTerrain,
    ValueChainNode,
    VisualEncoding,
)
from .view_models import (
    assign_buckets,
    card_label_for,
    glow_level,
    planet_universe_path,
    slugify,
    visual_size,
)


def _get(obj: Any, name: str, default=None):
    """Read a field from a dataclass/object OR a dict, without mutating it."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def company_node_from_thesis(thesis: Any, *, node_id: str, ticker: str,
                             company_name: str = "", theme_id: str = "",
                             value_chain_id: str = "", bottleneck_id: str = "",
                             value_chain_role: str = "", directness_to_bottleneck: str = "",
                             market_cap: Optional[float] = None, data_quality: str = "medium",
                             is_real: bool = False, cockpit_link: Optional[str] = None,
                             source_refs: Tuple[str, ...] = (),
                             recommendation_label: str = "") -> CompanyNode:
    """Map an already-computed investment thesis into a :class:`CompanyNode`.

    Reads EXISTING thesis fields (investability_assessment / timing_confirmation /
    red-team verdict); introduces no new score. Does not modify ``thesis``.
    """
    investability = _get(thesis, "investability_assessment", "") or ""
    timing = ("timing confirmed" if bool(_get(thesis, "timing_confirmation", False))
              else "timing not confirmed")
    red_team = _get(_get(thesis, "red_team_summary"), "red_team_verdict", "") or ""
    severe = (red_team or "").lower() in ("concern", "fail")

    primary, _cross = assign_buckets(
        investability_label=investability, timing_label=timing, red_team_label=red_team,
        recommendation_label=recommendation_label, catalyst_label="",
        capital_structure_risk=severe, data_quality=data_quality, evidence_count=0)
    bucket = "{0} ({1})".format(primary, card_label_for(primary, investability))

    return CompanyNode(
        id=node_id, ticker=ticker, company_name=company_name or ticker, theme_id=theme_id,
        value_chain_id=value_chain_id, bottleneck_id=bottleneck_id,
        value_chain_role=value_chain_role, directness_to_bottleneck=directness_to_bottleneck,
        market_cap=market_cap, candidate_bucket=bucket, thesis_status=investability,
        timing_confirmation_status=timing, red_team_status=red_team,
        dilution_or_capital_structure_warnings=(
            ("capital-structure / dilution risk flagged",) if severe else ()),
        data_quality=data_quality, is_real=is_real, cockpit_link=cockpit_link,
        source_refs=tuple(source_refs),
        visual_encoding=VisualEncoding(
            size_value=visual_size(market_cap, "planet"),
            size_basis="market_cap (economic magnitude)",
            glow_level=glow_level(investability_label=investability, timing_label=timing,
                                  recommendation_label=recommendation_label),
            glow_basis="thesis status", red_shadow=severe,
            dashed_outline=(market_cap is None), layout_group="company"),
    )


def catalyst_nodes_from_assessment(assessment: Any, *, related_object_id: str = "",
                                   evidence_quality: str = "") -> Tuple[CatalystNode, ...]:
    """Map catalyst-like entries from an assessment/cockpit panel into CatalystNodes.

    Accepts a catalyst panel (``positive_catalysts`` / ``negative_catalysts``) or a plain
    iterable of catalyst descriptions. Reads only; mutates nothing.
    """
    positives = _get(assessment, "positive_catalysts", None)
    negatives = _get(assessment, "negative_catalysts", None)
    if positives is None and negatives is None and assessment is not None:
        # A plain iterable of descriptions.
        try:
            positives = tuple(assessment)
        except TypeError:
            positives = ()
    out = []
    for i, c in enumerate(tuple(positives or ())):
        out.append(CatalystNode(
            id="cat-pos-{0}".format(i), related_object_id=related_object_id,
            catalyst_type="positive", description=str(c), status=_catalyst_status(str(c)),
            evidence_quality=evidence_quality))
    for i, c in enumerate(tuple(negatives or ())):
        out.append(CatalystNode(
            id="cat-neg-{0}".format(i), related_object_id=related_object_id,
            catalyst_type="negative", description=str(c), status=_catalyst_status(str(c)),
            evidence_quality=evidence_quality))
    return tuple(out)


def risk_nodes_from_red_team(red_team: Any, *, related_object_id: str = "",
                             evidence_quality: str = "") -> Tuple[RiskNode, ...]:
    """Map a red-team summary (or an iterable of concern strings) into RiskNodes."""
    verdict = _get(red_team, "red_team_verdict", "") or ""
    concerns = _get(red_team, "concerns", None)
    if concerns is None and red_team is not None and not verdict:
        try:
            concerns = tuple(red_team)
        except TypeError:
            concerns = ()
    concerns = tuple(concerns or ())
    if not concerns and verdict:
        concerns = (verdict,)
    return tuple(
        RiskNode(id="risk-{0}".format(i), related_object_id=related_object_id,
                 risk_type="red-team", description=str(c),
                 red_team_status=verdict or "concern", evidence_quality=evidence_quality)
        for i, c in enumerate(concerns))


# =========================================================================== #
# IMPLEMENTATION-010C: build a REAL terrain from the evidence-alpha slice       #
# =========================================================================== #
@dataclass(frozen=True)
class EvidenceTerrainBuildInput:
    """The narrow, typed set of ALREADY-COMPUTED artifacts the terrain builder reads.

    Every field is an object produced upstream by the accepted evidence-alpha slice; the
    builder only READS them (never mutates) and re-expresses them as terrain metadata.
    """
    subject: str = ""
    domain: str = ""
    ingestion_result: Optional[Any] = None
    intelligence_assessment: Optional[Any] = None
    opportunity_hypothesis: Optional[Any] = None
    investment_thesis: Optional[Any] = None
    investment_action: Optional[Any] = None
    personalized_action: Optional[Any] = None
    manual_execution_intent: Optional[Any] = None
    manual_trade_ticket: Optional[Any] = None
    cockpit_link: Optional[str] = None
    cockpit_view: Optional[Any] = None
    conflict_warnings: Tuple[str, ...] = ()
    data_gaps: Tuple[Tuple[str, str], ...] = ()
    provenance_chain: dict = field(default_factory=dict)


def build_input_from_evidence_slice(slice_result: Any) -> EvidenceTerrainBuildInput:
    """Capture the already-computed artifacts of an evidence-alpha slice (no mutation)."""
    return EvidenceTerrainBuildInput(
        subject=_get(slice_result, "subject", "") or "",
        domain=_get(_get(slice_result, "opportunity_hypothesis"), "domain", "") or "",
        ingestion_result=_get(slice_result, "ingestion_result"),
        intelligence_assessment=_get(slice_result, "intelligence_assessment"),
        opportunity_hypothesis=_get(slice_result, "opportunity_hypothesis"),
        investment_thesis=_get(slice_result, "investment_thesis"),
        investment_action=_get(slice_result, "investment_action"),
        personalized_action=_get(slice_result, "personalized_action"),
        manual_execution_intent=_get(slice_result, "manual_execution_intent"),
        manual_trade_ticket=_get(slice_result, "manual_trade_ticket"),
        cockpit_link=("cockpit.html" if _get(slice_result, "cockpit_view") is not None
                      else None),
        cockpit_view=_get(slice_result, "cockpit_view"),
        conflict_warnings=tuple(_get(slice_result, "conflict_warnings", ()) or ()),
        data_gaps=tuple(_get(slice_result, "data_gaps", ()) or ()),
        provenance_chain=dict(_get(slice_result, "provenance_chain", {}) or {}),
    )


def _real_status(bi: EvidenceTerrainBuildInput) -> dict:
    """Copy IREN's already-computed statuses out of the captured artifacts (no compute)."""
    th = bi.investment_thesis
    pa = bi.personalized_action
    ing = bi.ingestion_result
    timing = bool(_get(th, "timing_confirmation", False))
    rt = _get(_get(th, "red_team_summary"), "red_team_verdict", "") or ""
    catalyst_panel = _get(bi.cockpit_view, "catalyst")
    positives = tuple(_get(catalyst_panel, "positive_catalysts", ()) or ())
    catalyst_label = ("repricing triggers tracked (real evidence slice)" if positives else "")
    authority = _get(ing, "authority_summary", {}) or {}
    badges = (
        "SEC canonical ×{0}".format(authority.get("canonical", 0)),
        "FMP convenience ×{0}".format(authority.get("convenience", 0)),
        "yfinance fallback ×{0}".format(authority.get("fallback", 0)),
    )
    return {
        "investability_label": _get(th, "investability_assessment", "") or "",
        "timing_label": "timing confirmed" if timing else "timing not confirmed",
        "red_team_label": rt,
        "recommendation_label": _get(pa, "recommendation_status", "") or "",
        "catalyst_label": catalyst_label,
        "capital_structure_risk": rt in ("concern", "fail"),
        "ordering_value": float(_get(th, "thesis_confidence", 0.0) or 0.0),
        "source_authority_badges": badges,
    }


def _sizing_guardrail_text(pa: Any) -> str:
    """A RANGE-only sizing guardrail from Saarathi (never an exact size)."""
    rng = _get(pa, "suggested_sizing_range_pct")
    mx = _get(pa, "recommended_max_exposure_pct")
    if rng and len(tuple(rng)) == 2:
        lo, hi = rng
        base = "Saarathi sizing guardrail: {0:.2f}-{1:.2f}% of portfolio (range only)".format(
            float(lo), float(hi))
    else:
        base = "Saarathi sizing guardrail: range not provided"
    if mx is not None:
        base += "; max exposure {0:.2f}%".format(float(mx))
    return base


def _kriya_preview_text(bi: EvidenceTerrainBuildInput) -> str:
    """The Kriya manual-execution PREVIEW state (never an order)."""
    tk = bi.manual_trade_ticket
    mei = bi.manual_execution_intent
    state = _get(tk, "state", "previewed") or "previewed"
    broker = _get(tk, "broker_order_id")
    amt = _get(mei, "user_selected_allocation_amount")
    amt_txt = ("user-selected amount ${0:,.0f} (explicit)".format(float(amt))
               if amt is not None else "no user-selected amount")
    return ("Kriya: manual execution PREVIEW only (ticket {0}; broker order {1}); {2}".format(
        state, "none" if broker is None else broker, amt_txt))


def _catalyst_nodes(bi: EvidenceTerrainBuildInput, related_id: str,
                    ev_quality: str) -> Tuple[CatalystNode, ...]:
    """Catalyst nodes from the thesis repricing triggers + OH why-now (status-classified)."""
    th = bi.investment_thesis
    oh = bi.opportunity_hypothesis
    out = []
    events = tuple(_get(_get(th, "repricing_trigger_summary"), "key_trigger_events", ()) or ())
    for i, ev in enumerate(events):
        out.append(CatalystNode(
            id="{0}--cat-{1}".format(related_id, i), related_object_id=related_id,
            catalyst_type="repricing-trigger", description=str(ev),
            status=_catalyst_status(str(ev)), evidence_quality=ev_quality))
    why = _get(oh, "why_now", "") or ""
    if why:
        out.append(CatalystNode(
            id="{0}--cat-whynow".format(related_id), related_object_id=related_id,
            catalyst_type="positive", description="Why-now: {0}".format(why),
            status=_catalyst_status(why), evidence_quality=ev_quality))
    return tuple(out)


def _risk_nodes(bi: EvidenceTerrainBuildInput, related_id: str,
                ev_quality: str) -> Tuple[RiskNode, ...]:
    """Risk nodes from the red-team checks (non-pass) + thesis key_risks. Never suppressed."""
    th = bi.investment_thesis
    rt = _get(th, "red_team_summary")
    verdict = _get(rt, "red_team_verdict", "") or ""
    out = []
    for i, chk in enumerate(tuple(_get(rt, "checks", ()) or ())):
        v = _get(chk, "verdict", "") or ""
        if v.lower() == "pass":
            continue
        out.append(RiskNode(
            id="{0}--rt-{1}".format(related_id, i), related_object_id=related_id,
            risk_type="red-team", description="{0}: {1}".format(
                _get(chk, "check", ""), _get(chk, "rationale", "")),
            severity=v, red_team_status=v or verdict or "concern",
            evidence_quality=ev_quality))
    for i, kr in enumerate(tuple(_get(th, "key_risks", ()) or ())):
        out.append(RiskNode(
            id="{0}--kr-{1}".format(related_id, i), related_object_id=related_id,
            risk_type="thesis-risk", description=str(kr),
            red_team_status=verdict or "note", evidence_quality=ev_quality))
    return tuple(out)


# =========================================================================== #
# IMPLEMENTATION-011C: Company IR evidence -> catalyst / risk / evidence cards.  #
# Populated ONLY when a source-backed IR enrichment profile is supplied; company #
# statements (disclosed catalysts, guidance) are stamped ``company_claim`` and   #
# never presented as verified facts; rumors would stay rumor via _catalyst_status.#
# When ``enrichment`` is None (or IR absent) both helpers return () -> the pre-   #
# 011C terrain is byte-identical.                                                 #
# =========================================================================== #
def _ir_catalyst_nodes(enrichment: Any, related_id: str,
                       ev_quality: str) -> Tuple[CatalystNode, ...]:
    """Company-IR catalysts + guidance as CatalystNodes (company_claim, not verified)."""
    ir = (enrichment.ir if enrichment is not None else None)
    if ir is None or not ir.present:
        return ()
    refs = tuple(ir.source_refs)
    out = []
    for i, c in enumerate(tuple(ir.disclosed_catalysts)):
        out.append(CatalystNode(
            id="{0}--ir-cat-{1}".format(related_id, i), related_object_id=related_id,
            catalyst_type="positive",
            description="Company-disclosed catalyst (company_claim): {0}".format(c),
            status=_catalyst_status(str(c)), evidence_quality=ev_quality,
            source_refs=refs))
    for i, g in enumerate(tuple(ir.guidance_statements)):
        gv = getattr(g, "value", g)
        out.append(CatalystNode(
            id="{0}--ir-guid-{1}".format(related_id, i), related_object_id=related_id,
            catalyst_type="positive",
            description="Company guidance (company_claim): {0}".format(gv),
            status="possible", evidence_quality=ev_quality,
            source_refs=tuple(getattr(g, "source_refs", ())) or refs))
    return tuple(out)


def _ir_risk_nodes(enrichment: Any, related_id: str,
                   ev_quality: str) -> Tuple[RiskNode, ...]:
    """Company-IR disclosed risks as RiskNodes (company_claim context, never suppressed)."""
    ir = (enrichment.ir if enrichment is not None else None)
    if ir is None or not ir.present:
        return ()
    refs = tuple(ir.source_refs)
    return tuple(
        RiskNode(id="{0}--ir-risk-{1}".format(related_id, i), related_object_id=related_id,
                 risk_type="company-disclosed-risk",
                 description="Company-disclosed risk (company_claim): {0}".format(r),
                 red_team_status="disclosed", evidence_quality=ev_quality,
                 source_refs=refs)
        for i, r in enumerate(tuple(ir.disclosed_risks)))


def _source_coverage(bi: EvidenceTerrainBuildInput) -> dict:
    """ACTUAL source-authority + factual/signal counts from the ingestion + assessment."""
    ing = bi.ingestion_result
    ia = bi.intelligence_assessment
    authority = _get(ing, "authority_summary", {}) or {}
    signal_n = len(_get(ia, "signals", ()) or ()) if ia is not None else 0
    factual_n = len(_get(ia, "factual_observation_ids", ()) or ()) if ia is not None else 0
    return {
        "canonical": int(authority.get("canonical", 0)),
        "convenience": int(authority.get("convenience", 0)),
        "fallback": int(authority.get("fallback", 0)),
        "signal": signal_n,
        "factual": factual_n,
    }


def _provenance_refs(bi: EvidenceTerrainBuildInput) -> Tuple[str, ...]:
    """Preserve originating ids: IA -> OH -> ... -> ticket + a few observation ids."""
    out = []
    ia = bi.intelligence_assessment
    if ia is not None:
        out.append("IntelligenceAssessment {0} (v{1})".format(
            _get(ia, "id", ""), _get(ia, "version", "")))
    for d in tuple(bi.provenance_chain.get("downstream", ()) or ()):
        out.append("{0}: {1} (v{2})".format(
            d.get("stage", ""), d.get("object_id", ""), d.get("object_version", "")))
    for ref in tuple(_get(bi.cockpit_view, "provenance_chain", ()) or ())[:3]:
        out.append("{0} {1} (v{2})".format(
            _get(ref, "kind", "Observation"), _get(ref, "object_id", ""),
            _get(ref, "version", "")))
    return tuple(out)


def _data_gaps(bi: EvidenceTerrainBuildInput, enrichment: Any = None) -> Tuple[str, ...]:
    """Coverage gaps from the slice + explicit terrain-incompleteness gaps (nothing faked).

    When a diligence-enrichment bundle (011A) sourced market cap / TAM / bottleneck
    severity, the corresponding "not surfaced" placeholder line is replaced by an honest
    "sourced from ..." line; anything the enrichment still lacks stays an explicit gap.
    """
    mc = _enrichment_market_cap(enrichment)
    tam = _enrichment_tam(enrichment)
    bn_present = (enrichment is not None and enrichment.bottleneck.present)

    gaps = [
        "terrain incomplete — single candidate ({0}); value-chain, "
        "bottleneck, TAM and supplier coverage are sparse (missing-data placeholders "
        "shown, nothing fabricated)".format(bi.subject or "candidate"),
    ]
    if mc is None:
        gaps.append("market cap not surfaced by the pipeline reasoning objects — neutral "
                    "size + gap marker (no fabricated magnitude)")
    else:
        gaps.append("market cap sourced from diligence enrichment ({0}) — economic "
                    "magnitude now sized".format(enrichment.market.market_cap.authority))
    if tam is None:
        gaps.append("theme TAM / revenue pool not quantified by the thesis")
    else:
        gaps.append("theme TAM / revenue pool sourced from diligence enrichment "
                    "(estimate_type={0}, {1} — not canonical)".format(
                        enrichment.tam_estimate.estimate_type,
                        enrichment.tam_estimate.amount.authority))
    if bn_present:
        gaps.append("bottleneck severity / duration sourced from diligence enrichment "
                    "(labelled, {0})".format(enrichment.bottleneck.authority))
    else:
        gaps.append("discrete bottleneck not identified by the thesis (bottleneck_type=none) — "
                    "constraint context shown as a placeholder")
    if enrichment is None or not enrichment.value_chain.present:
        gaps.append("supplier-of-supplier / dependency coverage absent (no invented moons)")
    if enrichment is not None:
        for g in enrichment.data_gaps:
            gaps.append("enrichment: {0}".format(g))
    for kind, detail in bi.data_gaps:
        gaps.append("{0}: {1}".format(kind, detail))
    return tuple(gaps)


# =========================================================================== #
# IMPLEMENTATION-011A: OPTIONAL diligence-enrichment overlay. When an           #
# ``enrichment`` bundle is supplied the builder uses its (sourced, traced)      #
# market cap / TAM / value-chain / bottleneck evidence to REPLACE the neutral   #
# data-gap placeholders -- via the SAME ``visual_size`` helper, so size stays a #
# magnitude projection and NO new metric/score is introduced. When enrichment   #
# is None every function below is byte-identical to its pre-011A behaviour.      #
# =========================================================================== #
def _enrichment_market_cap(enrichment: Any) -> Optional[float]:
    return enrichment.market_cap_value if enrichment is not None else None


def _enrichment_tam(enrichment: Any) -> Optional[float]:
    return enrichment.tam_value if enrichment is not None else None


def _enrichment_flow_layers(enrichment: Any, vc_id: str):
    """Terrain ValueChainLayers from enrichment value-chain evidence (empty when absent)."""
    from .terrain import ValueChainLayer
    if enrichment is None or not enrichment.value_chain.present:
        return ()
    out = []
    for i, ly in enumerate(enrichment.value_chain.layers):
        seq = ly.sequence if ly.sequence is not None else i
        out.append(ValueChainLayer(
            id="{0}--layer-{1}".format(vc_id, seq),
            label=ly.label, order=seq, description=ly.description,
            companies=ly.companies,
            dependencies=ly.suppliers + ly.customers,
            bottleneck_exposure=ly.bottleneck_exposure,
            data_quality="partial"))
    return tuple(out)


def _iren_company_node(bi: EvidenceTerrainBuildInput, *, gslug: str, vc_id: str,
                       bottleneck_id: str, universe_path: str,
                       enrichment: Any = None) -> CompanyNode:
    st = _real_status(bi)
    th = bi.investment_thesis
    pa = bi.personalized_action
    winner = (tuple(_get(th, "winner_mapping", ()) or ()) or (None,))[0]
    role = _get(winner, "value_chain_role", "") or "candidate"
    exposure = _get(winner, "exposure_directness", None)
    directness = ("at the bottleneck" if (exposure or 0) >= 0.75
                  else ("one hop" if (exposure or 0) >= 0.4 else "indirect"))
    investability = st["investability_label"]
    timing = st["timing_label"]
    red_team = st["red_team_label"]
    recommendation = st["recommendation_label"]
    catalyst_label = st["catalyst_label"]
    severe = st["capital_structure_risk"]
    # market cap: still a data gap UNLESS a diligence-enrichment bundle sourced it (011A).
    market_cap = _enrichment_market_cap(enrichment)
    mc_authority = (enrichment.market.market_cap.authority
                    if (market_cap is not None) else "")
    evidence_count = len(_get(bi.intelligence_assessment, "signals", ()) or ())
    data_quality = "medium"

    primary, _cross = assign_buckets(
        investability_label=investability, timing_label=timing, red_team_label=red_team,
        recommendation_label=recommendation, catalyst_label=catalyst_label,
        capital_structure_risk=severe, data_quality=data_quality,
        evidence_count=evidence_count)
    bucket = "{0} ({1})".format(primary, card_label_for(primary, investability))

    dilution = ()
    if any("dilution" in str(kr).lower() or "capital-structure" in str(kr).lower()
           for kr in tuple(_get(th, "key_risks", ()) or ())) or severe:
        dilution = ("dilution / capital-structure overhang flagged (thesis red-team)",)

    events = tuple(_get(_get(th, "repricing_trigger_summary"), "key_trigger_events", ()) or ())
    top_reasons = tuple(x for x in (
        "value-chain role: {0}".format(role),
        "directness to constraint: {0}".format(directness),
        "Nivesha investability: {0}; timing-confirmation: {1}".format(investability, timing),
        _sizing_guardrail_text(pa),
        _kriya_preview_text(bi),
    ) if x)[:6]
    top_risks = tuple(x for x in (
        ("red-team verdict: {0}".format(red_team) if red_team.lower() in ("concern", "fail")
         else ""),
        (dilution[0] if dilution else ""),
        "manual review required before any action (Kriya boundary)",
    ) if x)

    catalysts = _catalyst_nodes(bi, universe_path, data_quality)

    size_basis = ("market_cap (economic magnitude; {0})".format(mc_authority)
                  if market_cap is not None else "market_cap (economic magnitude)")
    enc = VisualEncoding(
        size_value=visual_size(market_cap, "planet"),
        size_basis=size_basis,
        glow_level=glow_level(investability_label=investability, timing_label=timing,
                              recommendation_label=recommendation),
        glow_basis="investability / timing / recommendation status",
        color_class=("ev-low" if data_quality in ("low", "sparse") else ""),
        opacity_level=data_quality, opacity_basis="evidence quality",
        halo_type="catalyst" if catalyst_label else "", halo_basis="catalyst presence",
        red_shadow=bool(severe), dashed_outline=(market_cap is None),
        orbit_distance_basis="directness_to_bottleneck: {0}".format(directness),
        layout_group="company",
        visual_notes="size=magnitude only; glow=status; decoupled from ranking")

    return CompanyNode(
        id=universe_path, ticker=bi.subject or "IREN",
        company_name=_get(winner, "name", bi.subject) or bi.subject or "IREN",
        theme_id=gslug, value_chain_id=vc_id, bottleneck_id=bottleneck_id,
        value_chain_role=role, directness_to_bottleneck=directness, market_cap=market_cap,
        candidate_bucket=bucket, thesis_status=investability,
        timing_confirmation_status=timing, red_team_status=red_team,
        top_reasons=top_reasons, top_risks=top_risks, catalysts=catalysts,
        dilution_or_capital_structure_warnings=dilution, data_quality=data_quality,
        is_real=True, cockpit_link=bi.cockpit_link, evidence_count=evidence_count,
        source_refs=st["source_authority_badges"], visual_encoding=enc)


def _dependency_nodes(bi: EvidenceTerrainBuildInput, vc_id: str) -> Tuple[DependencyNode, ...]:
    """Dependency moons for KNOWN suppliers/customers only.

    The thesis value-chain summary carries no named nodes for this slice, so there are no
    known suppliers to place -- the absence is recorded as a data gap on the value chain,
    NOT filled with invented moons.
    """
    th = bi.investment_thesis
    nodes = tuple(_get(_get(th, "value_chain_summary"), "nodes", ()) or ())
    out = []
    for i, n in enumerate(nodes):
        name = _get(n, "role", "") or _get(n, "name", "") or "node-{0}".format(i)
        out.append(DependencyNode(
            id="{0}--dep-{1}".format(vc_id, i), parent_bottleneck_id=vc_id, name=name,
            dependency_type=_get(n, "tier", ""), tier=str(_get(n, "tier", "")),
            exposure_type="value-chain node", evidence_quality="medium",
            visual_encoding=VisualEncoding(
                size_value=visual_size(None, "moon"), dashed_outline=True,
                layout_group="dependency")))
    return tuple(out)


def _bottleneck_node(bi: EvidenceTerrainBuildInput, *, gslug: str, vc_id: str,
                     enrichment: Any = None) -> BottleneckNode:
    """A constraint-CONTEXT bottleneck (evidence-derived from the winner role + OH megatrend).

    The thesis did not identify a discrete quantified bottleneck (bottleneck_type=none),
    so severity / importance stay UNQUANTIFIED (neutral, dashed) and the gap is explicit --
    UNLESS a diligence-enrichment bundle (011A) supplies labelled severity / duration
    evidence, in which case those LABELS populate the node (still no numeric metric).
    """
    oh = bi.opportunity_hypothesis
    th = bi.investment_thesis
    winner = (tuple(_get(th, "winner_mapping", ()) or ()) or (None,))[0]
    role = _get(winner, "value_chain_role", "") or "capacity owner"

    bn_ev = (enrichment.bottleneck if enrichment is not None else None)
    if bn_ev is not None and bn_ev.present:
        name = bn_ev.name or "Secured power / data-center compute capacity"
        btype = bn_ev.bottleneck_type or "constraint (from diligence enrichment)"
        severity = bn_ev.severity
        duration = bn_ev.expected_duration
        resource = bn_ev.constrained_resource or "secured power / compute capacity"
        beneficiaries = (bn_ev.beneficiaries
                         or ("{0} ({1})".format(bi.subject or "IREN", role),))
        evidence = (tuple(bn_ev.evidence) or tuple(_get(oh, "megatrend_context", ()) or ()))
        gaps = () if (severity and duration) else (
            "bottleneck severity / duration partially specified — add capacity data",)
        enc = VisualEncoding(
            size_value=visual_size(None, "star"),
            size_basis="bottleneck importance (labelled: severity={0})".format(
                severity or "unspecified"),
            glow_level=2, glow_basis="severity: {0}".format(severity or "unspecified"),
            dashed_outline=False, layout_group="bottleneck")
        return BottleneckNode(
            id="{0}--star-0".format(gslug), value_chain_id=vc_id, name=name,
            bottleneck_type=btype, severity=severity, expected_duration=duration,
            constrained_resource=resource, beneficiaries=tuple(beneficiaries),
            losers_or_risks=(), resolution_risk="not assessed", evidence=evidence,
            economic_importance=None, data_gaps=gaps,
            evidence_quality="medium", source_refs=tuple(bn_ev.source_refs),
            visual_encoding=enc)

    return BottleneckNode(
        id="{0}--star-0".format(gslug), value_chain_id=vc_id,
        name="Secured power / data-center compute capacity",
        bottleneck_type="constraint context (not quantified by thesis)",
        severity="", expected_duration="",
        constrained_resource="secured power / compute capacity",
        beneficiaries=("{0} ({1})".format(bi.subject or "IREN", role),),
        losers_or_risks=(), resolution_risk="not assessed",
        evidence=tuple(_get(oh, "megatrend_context", ()) or ()),
        economic_importance=None,
        data_gaps=("thesis bottleneck_type=none — discrete bottleneck not identified",
                   "severity / duration / economic importance not quantified"),
        evidence_quality="medium",
        visual_encoding=VisualEncoding(
            size_value=visual_size(None, "star"), size_basis="bottleneck importance (unquantified)",
            glow_level=2, glow_basis="severity (unquantified)", dashed_outline=True,
            layout_group="bottleneck"))


def _value_chain_node(bi: EvidenceTerrainBuildInput, *, gslug: str,
                      enrichment: Any = None) -> ValueChainNode:
    vc_id = "{0}--ai-compute-hosting".format(gslug)
    bottleneck = _bottleneck_node(bi, gslug=gslug, vc_id=vc_id, enrichment=enrichment)
    deps = _dependency_nodes(bi, vc_id)
    tam = _enrichment_tam(enrichment)
    flow_layers = _enrichment_flow_layers(enrichment, vc_id)

    gaps = ["value-chain node coverage absent (thesis value_chain_summary has no nodes)"]
    if tam is None:
        gaps.append("TAM / revenue pool not quantified")
    else:
        gaps.append("TAM / revenue pool sourced from diligence enrichment (manual/analyst — "
                    "not canonical)")
    gaps.append("moat / pricing-power not quantified")
    if not flow_layers:
        gaps.append("supplier-of-supplier coverage absent")
    if not deps and not flow_layers:
        gaps.append("no named suppliers/customers mapped — no dependency moons placed")

    sized = tam is not None or bool(flow_layers)
    enc = VisualEncoding(
        size_value=visual_size(tam, "solar_system"),
        size_basis=("value-chain revenue pool (TAM, {0})".format(
            enrichment.tam_estimate.amount.authority) if tam is not None else ""),
        dashed_outline=not sized,
        glow_level=2, glow_basis="value-chain (neutral)", layout_group="value_chain")
    return ValueChainNode(
        id=vc_id, theme_id=gslug, name="AI compute-hosting value chain",
        description="Secured-power neocloud compute hosting (coverage incomplete).",
        flow_layers=flow_layers, bottlenecks=(bottleneck,), companies=(), dependencies=deps,
        revenue_pool_or_tam=tam, data_gaps=tuple(gaps),
        visual_encoding=enc)


def _galaxy_node(bi: EvidenceTerrainBuildInput, enrichment: Any = None) -> GalaxyNode:
    oh = bi.opportunity_hypothesis
    gslug = slugify(bi.domain or _get(oh, "domain", "") or "ai-infrastructure")
    vc = _value_chain_node(bi, gslug=gslug, enrichment=enrichment)
    bottleneck_id = vc.bottlenecks[0].id if vc.bottlenecks else "{0}--star-0".format(gslug)
    universe_path = planet_universe_path(gslug, vc.id, bottleneck_id, bi.subject or "IREN")
    company = _iren_company_node(
        bi, gslug=gslug, vc_id=vc.id, bottleneck_id=bottleneck_id, universe_path=universe_path,
        enrichment=enrichment)
    # Base catalysts / risks from the thesis + red-team, plus (011C) source-backed company
    # IR evidence as company_claim catalyst / risk cards (empty when enrichment is None).
    catalysts = _catalyst_nodes(bi, gslug, "medium") + _ir_catalyst_nodes(
        enrichment, gslug, "medium")
    risks = _risk_nodes(bi, gslug, "medium") + _ir_risk_nodes(enrichment, gslug, "medium")

    # TAM (manual/analyst, never canonical) is the theme/galaxy magnitude BASIS when supplied.
    tam = _enrichment_tam(enrichment)
    tam_auth = (enrichment.tam_estimate.amount.authority if tam is not None else "")

    convergence = tuple(_get(oh, "cross_domain_convergence", ()) or ())
    theme = ThemeNode(
        id=gslug, galaxy_id=gslug,
        name=_get(oh, "theme", "") or "{0} theme".format(gslug),
        thesis=_get(oh, "opportunity_mechanism", "") or "",
        evidence_convergence=("converging signal families: {0}".format(", ".join(convergence))
                              if convergence else "single evidence-ingested candidate"),
        why_now=_get(oh, "why_now", "") or "",
        why_before_obvious=_get(oh, "why_before_obvious", "") or "",
        value_chains=(vc,), candidate_planets=(company,), catalysts=catalysts,
        red_team_risks=risks, data_gaps=tuple(vc.data_gaps),
        visual_encoding=VisualEncoding(
            size_value=visual_size(tam, "galaxy"), dashed_outline=(tam is None),
            size_basis=("theme TAM ({0})".format(tam_auth) if tam is not None else ""),
            glow_level=2, glow_basis="opportunity magnitude", layout_group="galaxy"))

    galaxy_enc = VisualEncoding(
        size_value=visual_size(tam, "galaxy"),
        size_basis=("theme TAM ({0}, not canonical)".format(tam_auth) if tam is not None
                    else "theme TAM (not quantified)"),
        glow_level=2, glow_basis="opportunity magnitude", opacity_level="medium",
        opacity_basis="evidence quality", dashed_outline=(tam is None), layout_group="galaxy",
        visual_notes="size=magnitude (missing -> neutral); glow=heat; NOT a ranking")
    return GalaxyNode(
        id=gslug, name=_get(oh, "theme", "") or gslug,
        description="Evidence-ingested candidate theme (capital cycle not yet mapped).",
        thesis_summary=_get(oh, "opportunity_mechanism", "") or "",
        why_now=_get(oh, "why_now", "") or "",
        why_before_obvious=_get(oh, "why_before_obvious", "") or "",
        economic_magnitude=tam, heat_status="warm", data_quality="medium",
        candidate_count=1, themes=(theme,), risks=risks, catalysts=catalysts,
        visual_encoding=galaxy_enc)


def terrain_from_slice(iren_slice, *, mode: str = "evidence_ingested_fixture",
                       title: Optional[str] = None,
                       extra_data_gaps: Tuple[str, ...] = (),
                       enrichment: Any = None) -> UniverseTerrain:
    """Build a REAL, sparse :class:`UniverseTerrain` from an evidence-alpha slice.

    Default mode ``evidence_ingested_fixture``: ONE galaxy / theme (the candidate's), one
    value chain, a constraint-context bottleneck, and the company planet -- all projected
    from the ALREADY-COMPUTED slice artifacts. No cross-theme edges are invented (a single
    theme supports none), so there is no centre and ``validate()`` is clean. The terrain
    is deliberately incomplete; the incompleteness is surfaced as data gaps + neutral
    (dashed) encodings, never fabricated.

    ``mode`` may be overridden to ``real_evidence_on_demand`` (IMPLEMENTATION-010D) so the
    exact same node-mapping approach projects a terrain built from REAL, on-demand source
    data. ``extra_data_gaps`` lets the on-demand builder append per-source status gaps.

    ``enrichment`` (IMPLEMENTATION-011A) is an OPTIONAL
    :class:`~diligence_enrichment.models.DiligenceEnrichmentBundle`. When supplied, its
    sourced/traced market cap, TAM, value-chain layers and bottleneck severity/duration
    REPLACE the neutral data-gap placeholders (via the same ``visual_size`` helper -- size
    stays a magnitude, no new metric). When ``None`` the output is byte-identical to the
    pre-011A builder, so demo / evidence-fixture / enrichment-free real builds are unchanged.
    """
    bi = build_input_from_evidence_slice(iren_slice)
    galaxy = _galaxy_node(bi, enrichment)
    build_id = "{0}-terrain-{1}".format(
        "real" if mode == "real_evidence_on_demand" else "evidence",
        slugify(bi.subject or "candidate"))
    resolved_title = title or (
        "Economic Universe (real evidence, on demand)"
        if mode == "real_evidence_on_demand" else "Economic Universe (evidence-ingested)")
    return UniverseTerrain(
        terrain_id="economic-universe", title=resolved_title,
        mode=mode, build_id=build_id,
        galaxies=(galaxy,), relationship_edges=(),
        source_coverage=_source_coverage(bi),
        data_gaps=_data_gaps(bi, enrichment) + tuple(extra_data_gaps),
        provenance_refs=_provenance_refs(bi),
        visual_legend=(
            ("size", "economic magnitude (missing here -> neutral, dashed)"),
            ("glow", "signal heat / conviction (from existing status)"),
            ("red_shadow", "red-team / dilution flag"),
            ("dashed_outline", "missing data (a data gap, never a fabricated value)"),
        ),
        warnings=())  # kept empty so validate() stays clean; incompleteness is a data gap
