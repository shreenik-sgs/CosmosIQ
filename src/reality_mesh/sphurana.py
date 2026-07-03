"""The Sphurana Theme Pulse Synthesizer for the Reality Mesh (IMPLEMENTATION-012F).

The SECOND synthesizer. It consumes the Tattva Signal Fusion output -- the
:class:`~reality_mesh.models.SignalCluster`s and :class:`~reality_mesh.models.RealitySignal`s
that describe *what appears to be changing* -- and synthesizes OPPORTUNITY-GENERATION
intelligence for the next layer:

* :class:`~reality_mesh.models.ThemePulse` -- a theme's qualitative *state* (from the CLOSED
  ``theme_pulse_state`` vocabulary ``Dormant .. Data insufficient``), with supporting AND
  contradicting signals preserved side by side (never averaged, never hidden);
* :class:`~reality_mesh.models.OpportunityHypothesisPacket` -- something for Nivesha to TEST
  (NOT a thesis): an opportunity summary + placeholder value-chain / bottleneck hypotheses +
  possible beneficiary / loser CANDIDATES (roles, not a ranked pick list) + the
  ``required_diligence_questions`` Nivesha must answer + both-sided evidence refs;
* a :class:`~reality_mesh.models.HandoffEnvelope` to Nivesha
  (``to_layer="investment_diligence"``, ``payload_type="OpportunityHypothesisPacket"``, allowed
  ``("diligence-input", "test")``), ``requires_human_review=True``.

DISCIPLINE baked into the shape (ARCHITECTURE_CONTRACT_012 §A/§E/§F). Sphurana may form
opportunity HYPOTHESES and identify POSSIBLE beneficiaries / losers. It may NOT:

* create an Investment Thesis / any Nivesha output / a buy-sell-hold / order / a stock-first
  ranking / a numeric score or rank -- it emits qualitative **labels** only, and every output
  passes the 012A :func:`~reality_mesh.validation.assert_no_trade_fields` guard;
* average away a contradiction -- an opposing (risk-off / exhausting) signal is PRESERVED on the
  pulse in ``contradicting_signals`` and the pulse reads ``Conflicted`` (both sides kept);
* let a NARROW one-stock move read as ``Broadening`` -- broadening requires breadth across
  MULTIPLE (>= 3) participating members;
* let SOCIAL-only / thin narrative become a high-confidence ``Igniting`` -- a social-only theme
  reads ``Data insufficient`` (or ``Conflicted``), never a confident ignition.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no broker, no wall-clock:
grouping is sorted, ids are content-derived, and ``now`` is an injected string.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import (
    HandoffEnvelope,
    OpportunityHypothesisPacket,
    RealitySignal,
    SignalCluster,
    ThemePulse,
)
from .validation import assert_no_trade_fields

# --------------------------------------------------------------------------- #
# Qualitative orderings (weakest first). Labels give a deterministic total     #
# order for conservative roll-up only -- NOT numeric scores.                   #
# --------------------------------------------------------------------------- #
_MAGNITUDE_ORDER: Tuple[str, ...] = (
    "unknown", "negligible", "minor", "moderate", "major", "extreme")
_CONFIDENCE_ORDER: Tuple[str, ...] = (
    "missing", "unknown", "very_low", "low", "moderate", "high", "very_high")
_FRESHNESS_REAL_ORDER: Tuple[str, ...] = (
    "expired", "stale", "aging", "recent", "fresh")

_POSITIVE_DIRECTIONS = frozenset({"improving", "accelerating", "rising"})
_NEGATIVE_DIRECTIONS = frozenset({"deteriorating", "decelerating", "falling", "reversing"})

# Disciplines that describe the WHOLE tape rather than a single theme; a risk-off signal in one
# of these is a market-wide overlay that CONTRADICTS a rising theme (kept, never averaged).
_GLOBAL_DISCIPLINES = frozenset({"market_regime", "macro_regime"})

# A social / narrative signal never lifts a pulse into a confident ignition.
_SOCIAL_DISCIPLINES = frozenset({"narrative"})

# Breadth across at least this many distinct participating members is required to call a move
# "broadening"; below it a rising move is (at most) a narrow ignition, NEVER a broadening.
_BROADENING_MIN_MEMBERS = 3

# Confidence ceiling for a social-only (rumor) theme pulse -- weak by construction.
_SOCIAL_CONFIDENCE_CEILING = "low"


def _index_in(order: Tuple[str, ...], value: str) -> int:
    return order.index(value) if value in order else -1


def _weakest(order: Tuple[str, ...], values) -> str:
    present = [v for v in values if v in order]
    return min(present, key=lambda v: order.index(v)) if present else ""


def _strongest(order: Tuple[str, ...], values) -> str:
    present = [v for v in values if v in order]
    return max(present, key=lambda v: order.index(v)) if present else ""


def _cap(order: Tuple[str, ...], value: str, ceiling: str) -> str:
    vi, ci = _index_in(order, value), _index_in(order, ceiling)
    if vi < 0 or ci < 0:
        return value
    return value if vi <= ci else ceiling


def _union(iterables) -> Tuple[str, ...]:
    seen = set()
    for it in iterables:
        for v in it:
            seen.add(v)
    return tuple(sorted(seen))


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text).strip("-").lower() or "x"


def _is_social(signal: RealitySignal) -> bool:
    return signal.discipline in _SOCIAL_DISCIPLINES


def _signal_subject(signal: RealitySignal) -> str:
    """The theme/sector/value-chain a signal is ABOUT ('' if it is a market-wide overlay)."""
    for values in (signal.affected_themes, signal.affected_sectors, signal.affected_value_chains):
        if values:
            return sorted(values)[0]
    return ""


def _cluster_subject(cluster: SignalCluster) -> str:
    for value in (cluster.theme, cluster.sector, cluster.value_chain):
        if value:
            return value
    return ""


def _breadth_from_count(n_members: int) -> str:
    if n_members <= 1:
        return "minor"
    if n_members == 2:
        return "moderate"
    if n_members <= 4:
        return "major"
    return "extreme"


# --------------------------------------------------------------------------- #
# SphuranaResult -- the synthesizer's output bundle                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SphuranaResult:
    """The theme pulses + opportunity hypotheses + Nivesha envelope a synthesize() call yields.

    Iterable as ``(theme_pulses, hypotheses, envelope)`` for convenient unpacking.
    """

    theme_pulses: Tuple[ThemePulse, ...] = field(default_factory=tuple)
    hypotheses: Tuple[OpportunityHypothesisPacket, ...] = field(default_factory=tuple)
    envelope: Optional[HandoffEnvelope] = None

    def __iter__(self):
        return iter((self.theme_pulses, self.hypotheses, self.envelope))


# --------------------------------------------------------------------------- #
# Internal per-theme working view (pure data, never emitted)                    #
# --------------------------------------------------------------------------- #
class _ThemeView:
    __slots__ = ("subject", "signals", "clusters")

    def __init__(self, subject: str):
        self.subject = subject
        self.signals: List[RealitySignal] = []
        self.clusters: List[SignalCluster] = []


# --------------------------------------------------------------------------- #
# ThemePulseSynthesizer                                                        #
# --------------------------------------------------------------------------- #
class ThemePulseSynthesizer:
    """Deterministically synthesize ThemePulses + OpportunityHypothesisPackets.

    Stateless + side-effect free. One public method, :meth:`synthesize`; everything else is a
    pure helper. Never mutates inputs; never averages a contradiction away; never invents data;
    never emits a thesis / decision / ranking / score.
    """

    from_layer = "opportunity_discovery"
    to_layer = "investment_diligence"
    from_agent = "sphurana.theme_pulse"
    payload_type = "OpportunityHypothesisPacket"
    allowed_downstream_uses: Tuple[str, ...] = ("diligence-input", "test")
    # All members of the closed FORBIDDEN_DOWNSTREAM_USES vocab; the envelope additionally merges
    # the four mandatory defaults so a hypothesis packet can never authorise a decision/size/order.
    forbidden_downstream_uses: Tuple[str, ...] = ("final-decision", "size", "order")

    # -- public API -------------------------------------------------------- #
    def synthesize(
        self,
        clusters: Tuple[SignalCluster, ...] = (),
        signals: Tuple[RealitySignal, ...] = (),
        *,
        now: str = "",
    ) -> SphuranaResult:
        """Synthesize theme pulses + opportunity hypotheses from fused clusters/signals.

        Market-wide (``market_regime`` / ``macro_regime``) signals with no theme are treated as a
        risk overlay that can CONTRADICT a rising theme (both sides preserved). Deterministic:
        ``now`` is injected and never read from the wall clock.
        """
        clusters = tuple(c for c in clusters if isinstance(c, SignalCluster))
        signals = tuple(s for s in signals if isinstance(s, RealitySignal))

        # Split signals into theme-scoped members and market-wide risk overlays.
        context_signals: List[RealitySignal] = []
        views: Dict[str, _ThemeView] = {}
        for s in signals:
            subject = _signal_subject(s)
            if subject == "" and s.discipline in _GLOBAL_DISCIPLINES:
                context_signals.append(s)
                continue
            if subject == "":
                continue
            views.setdefault(subject, _ThemeView(subject)).signals.append(s)
        for c in clusters:
            subject = _cluster_subject(c)
            if subject == "":
                continue
            views.setdefault(subject, _ThemeView(subject)).clusters.append(c)

        context_signals.sort(key=lambda s: s.signal_id)

        pulses: List[ThemePulse] = []
        hypotheses: List[OpportunityHypothesisPacket] = []
        for subject in sorted(views):
            pulse = self._build_pulse(views[subject], tuple(context_signals))
            pulses.append(pulse)
            if pulse.state != "Dormant":
                hypotheses.append(self._build_hypothesis(pulse, views[subject]))

        for out in list(pulses) + list(hypotheses):
            assert_no_trade_fields(out)   # reuse the 012A structural guard on every output

        envelope = self._build_envelope(pulses, hypotheses, context_signals, now)
        return SphuranaResult(
            theme_pulses=tuple(pulses),
            hypotheses=tuple(hypotheses),
            envelope=envelope,
        )

    # -- theme pulse construction ----------------------------------------- #
    def _build_pulse(self, view: _ThemeView, context_signals: Tuple[RealitySignal, ...]) -> ThemePulse:
        subject = view.subject
        msigs = sorted(view.signals, key=lambda s: s.signal_id)
        mclusters = sorted(view.clusters, key=lambda c: c.cluster_id)

        pos_sigs = [s for s in msigs if s.direction_label in _POSITIVE_DIRECTIONS]
        neg_sigs = [s for s in msigs if s.direction_label in _NEGATIVE_DIRECTIONS]
        social_sigs = [s for s in msigs if _is_social(s)]
        real_sigs = [s for s in msigs if not _is_social(s)]

        # Market-wide risk overlays only contradict a theme that is actually rising.
        risk_off_context = (
            [s for s in context_signals if s.direction_label in _NEGATIVE_DIRECTIONS]
            if pos_sigs else [])

        contradicted_signal = any(s.contradiction_status == "contradicted" for s in msigs)
        cluster_conflict = any(
            c.conflict_label in ("moderate", "major", "extreme") for c in mclusters)
        opposing = (
            (bool(pos_sigs) and bool(neg_sigs))
            or bool(risk_off_context)
            or contradicted_signal
            or cluster_conflict)

        social_only = bool(social_sigs) and not real_sigs

        # Breadth: distinct participating members among rising signals + positive clusters.
        pos_members = set()
        for s in pos_sigs:
            pos_members.update(s.affected_companies)
        for c in mclusters:
            if c.momentum_label in _POSITIVE_DIRECTIONS:
                pos_members.update(c.companies)
        breadth_count = len(pos_members)

        cluster_breadth = _strongest(_MAGNITUDE_ORDER, (c.breadth_label for c in mclusters))
        breadth_label = cluster_breadth or (
            _breadth_from_count(breadth_count) if pos_members else "unknown")

        # Crowding: excessive positioning from a cluster crowding label OR a reversing rotation
        # signal (theme_rotation crowding signature) whose magnitude is major/extreme.
        crowd_values = [c.crowding_label for c in mclusters]
        crowd_values += [
            s.magnitude_label for s in msigs
            if s.direction_label == "reversing" and "rotation" in s.discipline]
        crowding_label = _strongest(_MAGNITUDE_ORDER, crowd_values) or "unknown"
        crowded = crowding_label in ("major", "extreme")

        corroborated = any(s.corroboration_status == "corroborated" for s in msigs)
        confs = [s.confidence_label for s in msigs if s.confidence_label not in ("", "missing")]
        confidence = _weakest(_CONFIDENCE_ORDER, confs) or "missing"
        if social_only:
            confidence = _cap(_CONFIDENCE_ORDER, confidence, _SOCIAL_CONFIDENCE_CEILING)

        thin = social_only or (
            confidence in ("missing", "very_low") and not corroborated and breadth_count < 2)

        # Exhaustion severity (a negative-dominant theme rolling over).
        neg_dominant = bool(neg_sigs) and not pos_sigs
        severe = any(s.magnitude_label in ("major", "extreme") for s in neg_sigs)

        state = self._derive_state(
            has_members=bool(msigs) or bool(mclusters),
            opposing=opposing,
            thin=thin,
            neg_dominant=neg_dominant,
            severe=severe,
            crowded=crowded,
            has_pos=bool(pos_sigs) or any(
                c.momentum_label in _POSITIVE_DIRECTIONS for c in mclusters),
            breadth_count=breadth_count,
            corroborated=corroborated,
            confidence=confidence,
            n_members=len(msigs),
        )

        # rotation direction label (mixed when opposing; else the dominant polarity).
        if opposing:
            rotation_label = "mixed"
        elif pos_sigs:
            rotation_label = "accelerating" if any(
                s.direction_label == "accelerating" for s in pos_sigs) else "improving"
        elif neg_sigs:
            rotation_label = "decelerating" if any(
                s.direction_label == "decelerating" for s in neg_sigs) else "deteriorating"
        else:
            rotation_label = "stable"

        # Supporting vs contradicting signals -- BOTH preserved on the pulse.
        supporting = sorted(s.signal_id for s in pos_sigs)
        contradicting = sorted(
            {s.signal_id for s in neg_sigs}
            | {s.signal_id for s in risk_off_context}
            | {s.signal_id for s in msigs if s.contradiction_status == "contradicted"})

        beneficiaries = _union(s.affected_companies for s in pos_sigs) or _union(
            c.companies for c in mclusters if c.momentum_label in _POSITIVE_DIRECTIONS)
        risks = _union(s.affected_companies for s in neg_sigs)

        freshness = _weakest(
            _FRESHNESS_REAL_ORDER,
            (s.freshness_label for s in msigs if s.freshness_label in _FRESHNESS_REAL_ORDER)
        ) or "missing"

        evidence_refs = _union([s.evidence_refs for s in msigs]
                               + [c.evidence_refs for c in mclusters]
                               + [s.evidence_refs for s in risk_off_context])
        source_refs = _union([s.source_refs for s in msigs]
                             + [c.source_refs for c in mclusters]
                             + [s.source_refs for s in risk_off_context])

        conflicts = list(_union([s.conflicts for s in msigs] + [c.conflicts for c in mclusters]))
        data_gaps = list(_union([s.data_gaps for s in msigs] + [c.data_gaps for c in mclusters]))
        if opposing:
            conflicts.append(
                "theme '{0}' conflicted: supporting {1} vs contradicting {2} -- both sides "
                "preserved (not averaged)".format(
                    subject, supporting or ["-"], contradicting or ["-"]))
        if social_only:
            data_gaps.append(
                "theme '{0}' is social-only narrative -- weak; NOT a high-confidence ignition; "
                "needs corroboration by primary/canonical evidence".format(subject))
        if (bool(pos_sigs)) and breadth_count < _BROADENING_MIN_MEMBERS:
            data_gaps.append(
                "theme '{0}' is a narrow move: {1} participating member(s) -- not yet a broad "
                "theme (not Broadening)".format(subject, breadth_count))

        return ThemePulse(
            theme_pulse_id="pulse.{0}".format(_slug(subject)),
            theme_id=_slug(subject),
            theme_name=subject,
            state=state,
            source_signal_clusters=tuple(sorted(c.cluster_id for c in mclusters)),
            supporting_signals=tuple(supporting),
            contradicting_signals=tuple(contradicting),
            breadth_label=breadth_label,
            rotation_label=rotation_label,
            crowding_label=crowding_label,
            bottleneck_label="unknown",
            beneficiary_candidates=beneficiaries,
            risk_candidates=risks,
            confidence_label=confidence,
            freshness_label=freshness,
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            conflicts=tuple(dict.fromkeys(conflicts)),
            data_gaps=tuple(dict.fromkeys(data_gaps)),
        )

    @staticmethod
    def _derive_state(
        *, has_members, opposing, thin, neg_dominant, severe, crowded, has_pos,
        breadth_count, corroborated, confidence, n_members,
    ) -> str:
        """Map the aggregated theme view onto the CLOSED theme_pulse_state vocabulary.

        Precedence (first match wins): a contradiction is surfaced as ``Conflicted`` before
        anything else; a social-only / thin read is ``Data insufficient`` (never a confident
        ignition); exhaustion, crowding, breadth, then the warming->igniting progression.
        """
        if not has_members:
            return "Dormant"
        if opposing:
            return "Conflicted"
        if thin:
            return "Data insufficient"
        if neg_dominant:
            return "Breaking down" if severe else "Exhausting"
        if crowded:
            return "Crowded"
        if has_pos and breadth_count >= _BROADENING_MIN_MEMBERS:
            return "Broadening"
        if has_pos:
            strong = (
                (corroborated or n_members >= 2 or breadth_count >= 2)
                and confidence not in ("missing", "unknown", "very_low"))
            return "Igniting" if strong else "Warming"
        return "Dormant"

    # -- opportunity hypothesis construction ------------------------------ #
    def _build_hypothesis(
        self, pulse: ThemePulse, view: _ThemeView,
    ) -> OpportunityHypothesisPacket:
        subject = pulse.theme_name
        msigs = sorted(view.signals, key=lambda s: s.signal_id)

        supporting_evidence = _union(
            s.evidence_refs for s in msigs if s.signal_id in pulse.supporting_signals)
        contradicting_evidence = _union(
            s.evidence_refs for s in msigs if s.signal_id in pulse.contradicting_signals)

        opportunity_summary = (
            "Theme '{0}' is {1} (rotation {2}, breadth {3}, crowding {4}). A hypothesis for "
            "Nivesha to TEST -- NOT an investment thesis, decision, ranking, or size.".format(
                subject, pulse.state, pulse.rotation_label,
                pulse.breadth_label, pulse.crowding_label))

        # Placeholder hypotheses -- structure for Nivesha to fill; no specifics invented.
        value_chain_hypothesis = (
            "Value chain for theme '{0}' not yet mapped -- Nivesha to decompose into layers "
            "(inputs -> constrained layer -> beneficiaries) from primary evidence.".format(subject))
        bottleneck_hypothesis = (
            "Bottleneck for theme '{0}' not identified from available signals -- candidate "
            "constrained resource requires diligence (placeholder).".format(subject))

        questions = self._diligence_questions(pulse, subject)

        return OpportunityHypothesisPacket(
            hypothesis_id="hyp.{0}".format(_slug(subject)),
            theme_pulse=pulse.theme_pulse_id,
            opportunity_summary=opportunity_summary,
            value_chain_hypothesis=value_chain_hypothesis,
            bottleneck_hypothesis=bottleneck_hypothesis,
            beneficiary_candidates=pulse.beneficiary_candidates,
            loser_candidates=pulse.risk_candidates,
            required_diligence_questions=questions,
            supporting_evidence_refs=supporting_evidence,
            contradicting_evidence_refs=contradicting_evidence,
            evidence_refs=pulse.evidence_refs,
            source_refs=pulse.source_refs,
            confidence_label=pulse.confidence_label,
            conflicts=pulse.conflicts,
            data_gaps=pulse.data_gaps,
        )

    @staticmethod
    def _diligence_questions(pulse: ThemePulse, subject: str) -> Tuple[str, ...]:
        """The questions Nivesha MUST test. Always present; contradictions become questions."""
        questions: List[str] = [
            "Is the '{0}' theme corroborated by non-narrative (primary/canonical) evidence, or "
            "is it social-only?".format(subject),
            "Which companies are GENUINE beneficiaries of '{0}' vs merely narrative-associated?"
            .format(subject),
            "Is the move broad (multiple members) or a narrow single-name move mislabeled as a "
            "theme?",
            "What is the actual value chain and constrained bottleneck for '{0}'?".format(subject),
        ]
        if pulse.state == "Conflicted" or pulse.contradicting_signals:
            questions.append(
                "Resolve the contradiction on '{0}': supporting vs contradicting signals are "
                "both present -- which side does primary evidence support?".format(subject))
        if pulse.state in ("Crowded",) or pulse.crowding_label in ("major", "extreme"):
            questions.append(
                "Is positioning in '{0}' crowded such that the opportunity is already priced in?"
                .format(subject))
        if pulse.state in ("Exhausting", "Breaking down"):
            questions.append(
                "Is '{0}' exhausting / rolling over rather than igniting?".format(subject))
        if pulse.state == "Data insufficient":
            questions.append(
                "What primary/canonical evidence would be required before '{0}' is investable at "
                "all?".format(subject))
        # De-duplicate, order-stable.
        return tuple(dict.fromkeys(questions))

    # -- envelope construction -------------------------------------------- #
    def _build_envelope(self, pulses, hypotheses, context_signals, now) -> HandoffEnvelope:
        payload_ids = tuple(sorted(h.hypothesis_id for h in hypotheses))

        # Authority: signals carry no authority field, so we roll up only what is honestly known
        # -- a social/narrative member means the pulse rests (partly) on rumor.
        authority_summary = "rumor" if any(
            p.confidence_label in ("very_low", "low") and any(
                "social-only" in g for g in p.data_gaps) for p in pulses) else ""

        freshness_summary = _weakest(
            _FRESHNESS_REAL_ORDER,
            [p.freshness_label for p in pulses if p.freshness_label in _FRESHNESS_REAL_ORDER]
        ) or "missing"

        all_conflicts: List[str] = []
        all_gaps: List[str] = []
        for p in pulses:
            all_conflicts.extend(p.conflicts)
            all_gaps.extend(p.data_gaps)

        token = "|".join(payload_ids) + "|" + now
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()[:12]

        return HandoffEnvelope(
            envelope_id="env.sphurana.{0}".format(digest),
            created_at=now,
            from_layer=self.from_layer,
            to_layer=self.to_layer,
            from_agent=self.from_agent,
            to_synthesizer="Nivesha",
            payload_type=self.payload_type,
            payload_ids=payload_ids,
            routing_reason=(
                "{0} theme pulse(s) -> {1} opportunity hypothesis(es) for Nivesha to TEST "
                "(diligence-input only; no decision/size/order)".format(
                    len(pulses), len(hypotheses))),
            authority_summary=authority_summary,
            freshness_summary=freshness_summary,
            conflict_summary="; ".join(dict.fromkeys(all_conflicts)),
            data_gap_summary="; ".join(dict.fromkeys(all_gaps)),
            requires_human_review=True,
            allowed_downstream_uses=self.allowed_downstream_uses,
            forbidden_downstream_uses=self.forbidden_downstream_uses,
        )


# Migrated (English) name for the opportunity-discovery synthesizer result bundle. The legacy
# ``SphuranaResult`` name is retained as the definition; new code should use this alias.
OpportunityDiscoveryResult = SphuranaResult
