"""Genesis (Sphurana) -- the Opportunity Hypothesis (reasoning object).

The first real Genesis runtime behaviour. ``generate_opportunity_hypothesis``
performs deterministic OPPORTUNITY REASONING over the *enriched, structured*
signals of one or more Intelligence Assessments (the 002R Tattva products). It
does NOT relabel an assessment's scores into an opportunity; it reasons about
*alpha*: where rising demand/readiness/adoption runs INTO a tightening constraint
(the bottleneck), whether several independent signal families CONVERGE, whether
the move is still BEFORE-OBVIOUS (novel, weakly-recognised), and whether the
apparent edge is actually a thin / rumour-driven / crowded false positive.

The reasoning is a pure function of the structured upstream fields:

* per-family net direction is computed strength-weighted across every assessment's
  ``signals`` (monitoring-only signals are excluded -- a speculative rumour cannot
  manufacture convergence);
* a *bottleneck* is rising demand-side families converging into a tightening
  ``constraint`` family; the value-chain position is derived from the constraint's
  affected node, never from a security or ticker;
* timing, theme maturity, magnitude, false-positive risk and bubble/hype risk are
  INFERRED from novelty, market-recognition, convergence count, contradictions and
  evidence thinness -- not looked up from a label.

Boundary (ADR-0008): Genesis says WHAT opportunity is emerging and WHY now /
why-before-obvious; it must NOT say HOW to invest. The Opportunity Hypothesis
names no security, recommends no trade / allocation / entry / exit / position
size, and carries no valuation or order language. Two protections enforce this:

* the object has no thesis / security / instrument / allocation / order field; and
* the generator synthesises its own text from the *structured* fields of the
  upstream assessments (never their free text) and then refuses
  (``_assert_no_leakage``) to emit any hypothesis whose own text carries
  security / valuation / trade / allocation / action language.

Determinism: every output is a pure function of the input Assessments and the
explicit ``now``; no wall clock and no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from eios_core.canonical_objects import ReasoningObject
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

# Security / valuation / trade / allocation / action language that must never
# appear in an opportunity's synthesised text. (Genesis may say "opportunity",
# "theme", "before-obvious", "bottleneck", "value-chain position", and
# "secured-power capacity owners".)
_FORBIDDEN_TERMS = (
    "buy", "sell", "hold", "target price", "price target", "allocat",
    "position size", "portfolio", "security", "ticker", "valuation", "$",
    "entry point", "exit point", "trade", "order", "action readiness",
    "action-ready", "repricing",
)

_SIGNIFICANCE = {"low": 0.34, "moderate": 0.67, "high": 1.0}
_MAGNITUDE_RANKS = ("negligible", "small", "moderate", "large", "transformational")

# The demand-side families whose *improvement* contributes to convergence. The
# constraint family contributes when it is *tightening* (deteriorating) -- demand
# rising into a tightening constraint is the bottleneck opportunity.
_IMPROVING_FAMILIES = ("readiness", "adoption", "economic_inflection",
                       "catalyst", "supply_chain")

# Per-domain megatrend context (structured, purpose-free).
_MEGATREND_BY_DOMAIN = {
    "ai-infrastructure": (
        "AI infrastructure buildout",
        "data-center power constraint",
        "compute capacity demand expansion",
    ),
}

# Default driving constraint per domain, used when no constraint node is carried
# in the structured signals.
_DOMAIN_CONSTRAINT_DEFAULT = {"ai-infrastructure": "power/energy"}

# Value-chain position implied by a driving constraint. NEVER a security/ticker.
_VALUE_CHAIN_POSITION = {"power/energy": "secured-power capacity owners"}

# Canonical theme per (domain, driving constraint).
_THEME = {("ai-infrastructure", "power/energy"): "secured power capacity for AI infrastructure"}

_THEME_MATURITIES = ("hidden", "emerging", "accelerating", "crowded", "euphoric")
_TIMINGS = ("before_obvious", "emerging", "recognized", "late")
_RISK_LEVELS = ("low", "moderate", "high")

_EPS = 1e-9


@dataclass(frozen=True)
class OpportunityHypothesis(ReasoningObject):
    """A deterministic alpha-reasoning statement of an emerging opportunity,
    grounded in (and version-bound to) one or more Intelligence Assessments."""

    # identity (mirrors the canonical id/version for downstream readability)
    opportunity_id: str = ""
    opportunity_version: int = 1
    # provenance / binding
    triggering_assessment_ids: Tuple[str, ...] = field(default_factory=tuple)
    triggering_assessment_versions: Tuple[int, ...] = field(default_factory=tuple)
    upstream_observation_ids: Tuple[str, ...] = field(default_factory=tuple)
    entities: Tuple[str, ...] = field(default_factory=tuple)
    # what & where
    domain: str = ""
    theme: str = ""
    theme_maturity: str = "emerging"
    megatrend_context: Tuple[str, ...] = field(default_factory=tuple)
    cross_domain_convergence: Tuple[str, ...] = field(default_factory=tuple)
    opportunity_mechanism: str = ""
    why_now: str = ""
    why_before_obvious: str = ""
    bottleneck_driven: bool = False
    driving_constraint: str = ""
    value_chain_position: str = ""
    opportunity_timing: str = "emerging"
    opportunity_maturity: str = "emerging"
    opportunity_magnitude: str = "negligible"
    # scoring
    evidence_strength: float = 0.0
    confidence: float = 0.0
    uncertainty: Tuple[str, ...] = field(default_factory=tuple)
    false_positive_risk: str = "low"
    bubble_hype_risk: str = "low"
    # graph + monitoring
    opportunity_graph_relationships: Tuple[dict, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)


def _clamp(x: float, lo: float = 0.0, hi: float = 0.95) -> float:
    return max(lo, min(hi, x))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _sign(direction: str) -> float:
    return 1.0 if direction == "improving" else -1.0 if direction == "deteriorating" else 0.0


def _risk_from_score(score: int) -> str:
    return "high" if score >= 3 else "moderate" if score >= 1 else "low"


def _assert_no_leakage(*texts: str) -> None:
    blob = " ".join(t for t in texts if t).lower()
    hits = [t for t in _FORBIDDEN_TERMS if t in blob]
    if hits:
        raise ValueError(
            "Opportunity Hypothesis must carry no security/valuation/trade/allocation/"
            "action language (found {0}); Genesis says WHAT opportunity is emerging and "
            "WHY, not HOW to invest (ADR-0008).".format(hits)
        )


def generate_opportunity_hypothesis(assessments, *, domain: Optional[str] = None,
                                    actor: str = "genesis", now: float) -> OpportunityHypothesis:
    """Reason over the enriched Tattva signals of one or more Intelligence
    Assessments and synthesise an Opportunity Hypothesis.

    Validation: at least one assessment; binds the exact ``(id, version)`` of each;
    never mutates assessments; carries no security/valuation/trade/allocation/action
    language.
    """
    items = list(assessments)
    if not items:
        raise ValueError(
            "an Opportunity Hypothesis requires at least one Intelligence Assessment"
        )

    domains = {getattr(a, "domain", "") for a in items if getattr(a, "domain", "")}
    if domain is None:
        domain = domains.pop() if len(domains) == 1 else "unspecified"
    domain = str(domain)

    # --- 1. flatten signals; compute per-family strength-weighted net -------
    # Monitoring-only signals (speculative/possible catalysts) are EXCLUDED from
    # the family aggregation: a rumour cannot manufacture convergence or confidence.
    active_signals = [s for a in items for s in getattr(a, "signals", ())
                      if not getattr(s, "monitoring_only", False)]
    all_signals = [s for a in items for s in getattr(a, "signals", ())]
    all_weak = [s for a in items for s in getattr(a, "weak_signals", ())]

    net_by_family = {}
    for s in active_signals:
        net_by_family[s.signal_type] = (
            net_by_family.get(s.signal_type, 0.0) + _sign(s.direction) * float(s.strength)
        )

    def _improving(fam):
        return net_by_family.get(fam, 0.0) > _EPS

    def _deteriorating(fam):
        return net_by_family.get(fam, 0.0) < -_EPS

    constraint_present = "constraint" in net_by_family
    constraint_tightening = constraint_present and _deteriorating("constraint")
    constraint_easing = constraint_present and _improving("constraint")

    # --- 2. cross-domain convergence ---------------------------------------
    conv = {fam for fam in _IMPROVING_FAMILIES if _improving(fam)}
    if constraint_tightening:
        conv.add("constraint")
    cross_domain_convergence = tuple(sorted(conv))
    convergence_count = len(conv)

    # --- 3. bottleneck + driving constraint + value-chain position ---------
    bottleneck_driven = constraint_tightening
    # The constraint's affected value-chain node only survives structurally on the
    # enriched catalyst records; fall back to a per-domain default.
    nodes = sorted({
        c.get("affected_value_chain_node")
        for a in items for c in getattr(a, "catalysts", ())
        if c.get("affected_value_chain_node")
    })
    if nodes:
        driving_constraint = str(nodes[0])
    elif bottleneck_driven:
        driving_constraint = _DOMAIN_CONSTRAINT_DEFAULT.get(domain, "")
    else:
        driving_constraint = ""

    if driving_constraint in _VALUE_CHAIN_POSITION:
        value_chain_position = _VALUE_CHAIN_POSITION[driving_constraint]
    elif driving_constraint:
        value_chain_position = "{0}-advantaged operators".format(driving_constraint)
    else:
        value_chain_position = ""

    # --- 4. theme + megatrend ----------------------------------------------
    dominant_improving = ""
    best = 0.0
    for fam in _IMPROVING_FAMILIES:
        v = net_by_family.get(fam, 0.0)
        if v > best:
            best, dominant_improving = v, fam

    if driving_constraint and (domain, driving_constraint) in _THEME:
        theme = _THEME[(domain, driving_constraint)]
    elif driving_constraint:
        theme = "{0} bottleneck beneficiaries in {1}".format(driving_constraint, domain)
    elif dominant_improving:
        theme = "{0} {1} theme".format(domain, dominant_improving)
    else:
        theme = "{0} emerging theme".format(domain)
    megatrend_context = _MEGATREND_BY_DOMAIN.get(domain, ())

    # --- 5. catalysts: confirmed/probable boost; rumours surface only ------
    all_catalysts = [c for a in items for c in getattr(a, "catalysts", ())]
    has_conf_prob_positive = any(
        c.get("catalyst_status") in ("confirmed", "probable")
        and c.get("expected_direction") == "positive"
        for c in all_catalysts
    )
    rumor_driven = bool(all_catalysts) and all(
        c.get("monitoring_only") for c in all_catalysts
    )
    catalyst_boost = 0.10 if has_conf_prob_positive else 0.0

    # --- 6. evidence strength ----------------------------------------------
    confs = [float(getattr(a, "confidence", 0.0)) for a in items]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    evidence_strength = round(
        _clamp(mean_conf * (0.5 + 0.5 * min(1.0, convergence_count / 3.0))), 4
    )

    # --- 7. contradictions / capital-structure penalties -------------------
    num_contradicting_assessments = sum(
        1 for a in items if getattr(a, "direction", "mixed") == "deteriorating"
    )
    contradictions_present = any(getattr(a, "contradictions", ()) for a in items)
    cap_risk_present = any(getattr(a, "capital_structure_risks", ()) for a in items)

    # --- 8. confidence ------------------------------------------------------
    confidence = round(_clamp(
        evidence_strength * min(1.0, convergence_count / 3.0)
        + catalyst_boost
        - 0.10 * num_contradicting_assessments
        - 0.10 * (1 if cap_risk_present else 0)
        - 0.20 * (1 if convergence_count <= 1 else 0)
    ), 4)

    # --- 9. recognition + before-obvious + timing --------------------------
    rec_signals = [s for s in active_signals if s.signal_type == "market_recognition"]
    rec_net = net_by_family.get("market_recognition", 0.0)
    if not rec_signals:
        recognition_level = 0.0
    elif rec_net > _EPS:
        max_str = max((float(s.strength) for s in rec_signals if _sign(s.direction) > 0),
                      default=0.0)
        recognition_level = _clamp01(0.6 + 0.4 * max_str)
    elif rec_net < -_EPS:
        recognition_level = 0.2
    else:
        recognition_level = 0.4
    recognition_rising = rec_net > _EPS

    signal_novelty = max((float(getattr(a, "signal_novelty", 0.0)) for a in items), default=0.0)
    num_signals = len(all_signals)
    weak_ratio = (len(all_weak) / num_signals) if num_signals else 0.0
    weak_dominant = num_signals > 0 and len(all_weak) * 2 >= num_signals

    before_obvious_score = _clamp01(
        0.4 * signal_novelty + 0.3 * weak_ratio + 0.3 * (1.0 - recognition_level)
    )

    # --- 10. theme maturity (inferred) -------------------------------------
    bubble_cues = recognition_level >= 0.85 and evidence_strength < 0.5
    if recognition_level >= 0.85 and bubble_cues:
        theme_maturity = "euphoric"
    elif recognition_level >= 0.66:
        theme_maturity = "crowded"
    elif convergence_count >= 3 and has_conf_prob_positive and recognition_rising:
        theme_maturity = "accelerating"
    elif (signal_novelty >= 0.7 and recognition_level < 0.34
          and (convergence_count < 2 or weak_dominant)):
        theme_maturity = "hidden"
    else:
        theme_maturity = "emerging"
    opportunity_maturity = theme_maturity

    # --- 11. opportunity timing (inferred, not a lookup) -------------------
    if before_obvious_score >= 0.6 and recognition_level < 0.34:
        opportunity_timing = "before_obvious"
    elif recognition_level >= 0.66:
        opportunity_timing = "recognized"
    elif theme_maturity in ("crowded", "euphoric"):
        opportunity_timing = "late"
    else:
        opportunity_timing = "emerging"

    # --- 12. magnitude ------------------------------------------------------
    sig_val = max((_SIGNIFICANCE.get(getattr(a, "significance", "low"), 0.34) for a in items),
                  default=0.0)
    magnitude_score = (sig_val * min(1.0, convergence_count / 3.0)
                       * (1.2 if bottleneck_driven else 1.0))
    raw_rank = (4 if magnitude_score >= 0.85 else 3 if magnitude_score >= 0.60
                else 2 if magnitude_score >= 0.34 else 1 if magnitude_score > 0 else 0)
    cap_rank = 4 if convergence_count >= 2 else 3  # < 2 families caps at "large"
    opportunity_magnitude = _MAGNITUDE_RANKS[min(raw_rank, cap_rank)]

    # --- 13. false-positive risk -------------------------------------------
    fp_score = 0
    if evidence_strength < 0.3:
        fp_score += 1
    if rumor_driven:
        fp_score += 1
    if contradictions_present:
        fp_score += 1
    if cap_risk_present:
        fp_score += 1
    if convergence_count <= 1:
        fp_score += 1
    if constraint_easing:  # the bottleneck is resolving -> edge may be gone
        fp_score += 1
    false_positive_risk = _risk_from_score(fp_score)

    # --- 14. bubble / hype risk --------------------------------------------
    if theme_maturity == "euphoric":
        bubble_hype_risk = "high"
    elif theme_maturity == "crowded":
        bubble_hype_risk = "moderate"
    else:
        bubble_hype_risk = "low"
    if recognition_level >= 0.66 and evidence_strength < 0.3 and bubble_hype_risk == "moderate":
        bubble_hype_risk = "high"

    # --- 15. synthesised purpose-free narrative ----------------------------
    adoption_up = _improving("adoption")
    readiness_up = _improving("readiness")
    econ_up = _improving("economic_inflection")
    demand_fam = ("adoption" if adoption_up else "readiness" if readiness_up
                  else "economic_inflection" if econ_up else "demand-side")

    why_now_parts = []
    if has_conf_prob_positive:
        why_now_parts.append("a confirmed/probable positive catalyst is pending")
    if readiness_up:
        why_now_parts.append("capacity-expansion readiness is rising")
    if econ_up:
        why_now_parts.append("economic inflection is strengthening")
    if adoption_up:
        why_now_parts.append("demand adoption is accelerating")
    if bottleneck_driven:
        why_now_parts.append("the {0} constraint is tightening".format(
            driving_constraint or "binding"))
    why_now = "; ".join(why_now_parts) or "no decisive near-term trigger yet"

    why_bo_parts = []
    if signal_novelty >= 0.5:
        why_bo_parts.append("the signals are highly novel (novelty {0:.2f})".format(signal_novelty))
    if all_weak:
        why_bo_parts.append("the read rests partly on {0} weak/early signal(s)".format(len(all_weak)))
    if recognition_level < 0.34:
        why_bo_parts.append("market recognition is still low")
    if contradictions_present:
        why_bo_parts.append("the reading is non-consensus (opposing-direction signals present)")
    why_before_obvious = "; ".join(why_bo_parts) or "the opportunity is already broadly recognised"

    if bottleneck_driven and value_chain_position:
        opportunity_mechanism = (
            "tightening {0} into rising {1} demand favours {2}".format(
                driving_constraint or "the binding constraint", demand_fam, value_chain_position)
        )
    elif cross_domain_convergence:
        opportunity_mechanism = (
            "converging {0} signal family(ies) favour early advantage in the {1}".format(
                ", ".join(cross_domain_convergence), theme)
        )
    else:
        opportunity_mechanism = "no converging mechanism identified in {0}".format(domain)

    # --- 16. graph relationships -------------------------------------------
    rels = []
    if megatrend_context:
        rels.append({"relation": "part_of", "target": megatrend_context[0]})
    if bottleneck_driven and driving_constraint:
        rels.append({"relation": "driven_by", "target": driving_constraint})
    for fam in cross_domain_convergence:
        rels.append({"relation": "converges", "target": fam})
    opportunity_graph_relationships = tuple(rels)

    # --- 17. monitoring signals --------------------------------------------
    mon = []
    for a in items:
        mon.extend(getattr(a, "monitoring_signals", ()))
    weak_types = sorted({s.signal_type for s in all_weak})
    if weak_types:
        mon.append("watch: weak/early {0} signal(s)".format(", ".join(weak_types)))
    if rumor_driven:
        mon.append("watch: opportunity rests on unconfirmed/rumoured catalyst(s) only")
    if cap_risk_present:
        mon.append("watch: capital-structure risk present upstream")
    if contradictions_present:
        mon.append("watch: opposing-direction signals not yet resolved")
    if constraint_easing:
        mon.append("watch: the binding constraint may be easing")
    mon.append("false-positive risk assessed {0}; bubble/hype risk assessed {1}".format(
        false_positive_risk, bubble_hype_risk))
    monitoring_signals = tuple(mon)

    uncertainty = (
        "reasoned from {0} intelligence assessment(s) across {1} converging signal "
        "family(ies); {2} contradicting assessment(s); evidence strength {3}; "
        "deterministic alpha-reasoning MVP -- identifies an emerging opportunity and "
        "why-now / why-before-obvious only, and makes no recommendation to act on it".format(
            len(items), convergence_count, num_contradicting_assessments, evidence_strength),
    )

    # --- 18. boundary guard over synthesised text --------------------------
    _assert_no_leakage(
        theme, opportunity_mechanism, why_now, why_before_obvious,
        driving_constraint, value_chain_position, theme_maturity, opportunity_timing,
        opportunity_maturity, opportunity_magnitude, false_positive_risk, bubble_hype_risk,
        " ".join(megatrend_context), " ".join(cross_domain_convergence),
        " ".join(uncertainty), " ".join(monitoring_signals),
        " ".join(str(r.get("target", "")) for r in opportunity_graph_relationships),
        str(domain),
    )

    # --- 19. binding + provenance ------------------------------------------
    sources = tuple(a.ref("IntelligenceAssessment") for a in items)  # exact (id, version)
    trig_ids = tuple(a.id for a in items)
    trig_versions = tuple(int(getattr(a, "version", 1)) for a in items)
    upstream_observation_ids = tuple(sorted({
        oid for a in items for oid in getattr(a, "grounding_observation_ids", ())
    }))
    entities = tuple(sorted({e for a in items for e in getattr(a, "entities", ())}))
    oid = stable_id("OPH", domain, theme, *trig_ids)
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=sources)
    return OpportunityHypothesis(
        id=oid,
        version=1,
        provenance=prov,
        opportunity_id=oid,
        opportunity_version=1,
        triggering_assessment_ids=trig_ids,
        triggering_assessment_versions=trig_versions,
        upstream_observation_ids=upstream_observation_ids,
        entities=entities,
        domain=domain,
        theme=theme,
        theme_maturity=theme_maturity,
        megatrend_context=megatrend_context,
        cross_domain_convergence=cross_domain_convergence,
        opportunity_mechanism=opportunity_mechanism,
        why_now=why_now,
        why_before_obvious=why_before_obvious,
        bottleneck_driven=bottleneck_driven,
        driving_constraint=driving_constraint,
        value_chain_position=value_chain_position,
        opportunity_timing=opportunity_timing,
        opportunity_maturity=opportunity_maturity,
        opportunity_magnitude=opportunity_magnitude,
        evidence_strength=evidence_strength,
        confidence=confidence,
        uncertainty=uncertainty,
        false_positive_risk=false_positive_risk,
        bubble_hype_risk=bubble_hype_risk,
        opportunity_graph_relationships=opportunity_graph_relationships,
        monitoring_signals=monitoring_signals,
    )


def make_opportunity_hypothesis(assessment, subject="", hypothesis="", actor="genesis",
                                now=0, confidence=None, domain=None):
    """Backward-compatible convenience constructor (single assessment) used to thread
    the slice and the generic threading tests. Delegates to the real generator;
    ``subject`` is taken as the domain hint and ``hypothesis`` is accepted for
    source compatibility (the opportunity is reasoned from the assessment's signals,
    not from this label). ``confidence`` is accepted but ignored -- Genesis infers it.
    """
    return generate_opportunity_hypothesis(
        [assessment],
        domain=(domain if domain is not None else (subject or None)),
        actor=actor,
        now=now,
    )
