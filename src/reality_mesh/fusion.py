"""The Tattva Signal Fusion Synthesizer for the Reality Mesh (IMPLEMENTATION-012C).

The FIRST synthesizer. It consumes Tattva :class:`~reality_mesh.models.AgentFinding`s (plus the
:class:`~reality_mesh.models.RealityEvent`s they interpret, and optional Adhāra authority /
freshness / conflict summaries) and FUSES them into higher-order reality intelligence --
:class:`~reality_mesh.models.RealitySignal`s and :class:`~reality_mesh.models.SignalCluster`s --
wrapped for Sphurana in a :class:`~reality_mesh.models.HandoffEnvelope`
(``to_layer="Sphurana"``, ``payload_type="TattvaSignalPacket"``, allowed ``("hypothesize",)``).

EVIDENCE INTEGRITY (ARCHITECTURE_CONTRACT_012 §D). The synthesizer NEVER:

* averages away a contradiction -- when findings disagree BOTH sides are preserved on the
  signal (``source_findings``), ``contradiction_status="contradicted"`` is set, and the clash
  is surfaced in ``conflicts``;
* upgrades a weak signal without corroboration -- confidence is rolled up conservatively
  (weakest by default) and only raised when ``>=2`` INDEPENDENT (different-agent) findings
  agree;
* treats X/social as verified fact -- a signal built from ``narrative`` findings keeps
  ``rumor`` authority. Corroboration by a NON-social finding may improve its
  ``corroboration_status`` but MUST NOT lift its authority: **rumor stays rumor**;
* hides missing data -- ``data_gaps`` and stale findings are preserved (stale is marked, never
  dropped);
* creates a stock-first ranking, an OpportunityHypothesis / InvestmentThesis, a buy/sell/hold,
  or any numeric score / rank. It emits qualitative **labels** only (reusing the 012A
  :func:`~reality_mesh.validation.assert_no_trade_fields` guard on every output).

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no broker, no wall-clock:
grouping is sorted, ids are content-derived, and ``now`` is an injected string.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from . import labels as _labels
from .models import (
    AgentFinding,
    HandoffEnvelope,
    RealityEvent,
    RealitySignal,
    SignalCluster,
)
from .validation import assert_no_trade_fields

# --------------------------------------------------------------------------- #
# Qualitative label orderings (weakest/stalest first). Labels, NOT numbers --  #
# these tuples give a deterministic total order for conservative roll-up only. #
# --------------------------------------------------------------------------- #
_CONFIDENCE_ORDER: Tuple[str, ...] = (
    "missing", "unknown", "very_low", "low", "moderate", "high", "very_high")
_MAGNITUDE_ORDER: Tuple[str, ...] = (
    "unknown", "negligible", "minor", "moderate", "major", "extreme")
_URGENCY_ORDER: Tuple[str, ...] = (
    "unknown", "none", "low", "watch", "elevated", "high", "immediate")
# stalest .. freshest (missing/unknown handled separately as an explicit gap).
_FRESHNESS_REAL_ORDER: Tuple[str, ...] = (
    "expired", "stale", "aging", "recent", "fresh")
# fastest-decaying .. slowest.
_HALF_LIFE_ORDER: Tuple[str, ...] = (
    "minutes", "hours", "days", "weeks", "months", "quarters", "years", "permanent")

# Directional polarity. A POSITIVE finding and a NEGATIVE finding about the same subject
# CONTRADICT -- they are never averaged into a bland middle; both are preserved.
_POSITIVE_DIRECTIONS = frozenset({"improving", "accelerating", "rising"})
_NEGATIVE_DIRECTIONS = frozenset({"deteriorating", "decelerating", "falling", "reversing"})

# The confidence ceiling for an X/social (rumor) signal, even once corroborated by a
# non-social finding: corroboration lifts corroboration_status, never authority, and never to
# a high-confidence verified claim.
_SOCIAL_CONFIDENCE_CEILING = "moderate"
_SOCIAL_UNCORROBORATED_CEILING = "low"


def _index_in(order: Tuple[str, ...], value: str) -> int:
    """Position of ``value`` in ``order`` (``-1`` if absent). Order, not a numeric score."""
    return order.index(value) if value in order else -1


def _weakest(order: Tuple[str, ...], values: Iterable[str]) -> str:
    """The earliest (weakest/stalest) member of ``order`` present in ``values`` (else '')."""
    present = [v for v in values if v in order]
    if not present:
        return ""
    return min(present, key=lambda v: order.index(v))


def _strongest(order: Tuple[str, ...], values: Iterable[str]) -> str:
    """The latest (strongest/freshest) member of ``order`` present in ``values`` (else '')."""
    present = [v for v in values if v in order]
    if not present:
        return ""
    return max(present, key=lambda v: order.index(v))


def _cap(order: Tuple[str, ...], value: str, ceiling: str) -> str:
    """Return ``value`` capped so it never exceeds ``ceiling`` in ``order``."""
    vi, ci = _index_in(order, value), _index_in(order, ceiling)
    if vi < 0 or ci < 0:
        return value
    return value if vi <= ci else ceiling


def _step_up(order: Tuple[str, ...], value: str, bound: str) -> str:
    """Raise ``value`` by ONE step in ``order``, never past ``bound`` (corroboration lift)."""
    vi = _index_in(order, value)
    bi = _index_in(order, bound)
    if vi < 0:
        return value
    target = min(vi + 1, bi) if bi >= 0 else vi + 1
    target = min(target, len(order) - 1)
    return order[max(target, vi)]


def _opposes(d1: str, d2: str) -> bool:
    """True iff two direction labels are on opposite polarity (a contradiction)."""
    return (
        (d1 in _POSITIVE_DIRECTIONS and d2 in _NEGATIVE_DIRECTIONS)
        or (d1 in _NEGATIVE_DIRECTIONS and d2 in _POSITIVE_DIRECTIONS)
    )


def _is_social_finding(finding: AgentFinding) -> bool:
    """True iff a finding is X/social narrative (rumor authority / narrative discipline)."""
    return (
        finding.discipline == _labels.NARRATIVE_DISCIPLINE
        or finding.source_authority_summary == "rumor"
    )


def _source_key(finding: AgentFinding) -> str:
    """The independence key for corroboration (different agent/source = independent)."""
    if finding.agent_id.strip():
        return finding.agent_id
    if finding.source_refs:
        return "|".join(finding.source_refs)
    return finding.finding_id


def _subject_of(finding: AgentFinding) -> Tuple[str, Tuple[str, ...]]:
    """The primary subject a finding is ABOUT (company > theme > sector > value_chain).

    Returns ``(kind, sorted_values)``; falls back to the discipline itself when a finding
    carries no company/theme/sector/value-chain, so a discipline-only finding still groups.
    """
    for kind, values in (
        ("company", finding.affected_companies),
        ("theme", finding.affected_themes),
        ("sector", finding.affected_sectors),
        ("value_chain", finding.affected_value_chains),
    ):
        if values:
            return kind, tuple(sorted(values))
    return "discipline", (finding.discipline or "unscoped",)


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text).strip("-").lower() or "x"


# --------------------------------------------------------------------------- #
# FusionResult -- the synthesizer's output bundle                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FusionResult:
    """The signals + clusters + Sphurana envelope a fuse() call produces.

    Iterable as ``(signals, clusters, envelope)`` for convenient unpacking, while
    :attr:`authority_by_signal` / :attr:`freshness_by_signal` expose the per-signal
    provenance roll-up so callers can prove ``rumor stays rumor`` (a signal object itself
    carries NO authority field -- authority is summarised on the envelope + here).
    """

    signals: Tuple[RealitySignal, ...] = field(default_factory=tuple)
    clusters: Tuple[SignalCluster, ...] = field(default_factory=tuple)
    envelope: Optional[HandoffEnvelope] = None
    authority_by_signal: Dict[str, str] = field(default_factory=dict)
    freshness_by_signal: Dict[str, str] = field(default_factory=dict)
    corroboration_by_signal: Dict[str, str] = field(default_factory=dict)

    def __iter__(self):
        return iter((self.signals, self.clusters, self.envelope))


# --------------------------------------------------------------------------- #
# TattvaSignalFusionSynthesizer                                               #
# --------------------------------------------------------------------------- #
class TattvaSignalFusionSynthesizer:
    """Deterministically fuse AgentFindings into RealitySignals + SignalClusters.

    Stateless + side-effect free. One public method, :meth:`fuse`; everything else is a pure
    helper. Never mutates its inputs; never averages a contradiction away; never invents data.
    """

    to_layer = "Sphurana"
    payload_type = "TattvaSignalPacket"
    allowed_downstream_uses: Tuple[str, ...] = ("hypothesize",)
    # All members of the closed FORBIDDEN_DOWNSTREAM_USES vocab; the envelope additionally
    # merges the four mandatory defaults (broker_order / auto_execute / buy_sell_recommendation
    # / hidden_score) so a fusion packet can never authorise a decision / sizing / order.
    forbidden_downstream_uses: Tuple[str, ...] = ("final-decision", "size", "order")

    # -- public API -------------------------------------------------------- #
    def fuse(
        self,
        events: Tuple[RealityEvent, ...] = (),
        findings: Tuple[AgentFinding, ...] = (),
        *,
        authority_summaries: Optional[Iterable[str]] = None,
        freshness_summaries: Optional[Iterable[str]] = None,
        conflict_records: Optional[Iterable[str]] = None,
        now: str = "",
    ) -> FusionResult:
        """Fuse ``findings`` (interpreting ``events``) into signals + clusters + an envelope.

        Optional ``authority_summaries`` / ``freshness_summaries`` (Adhāra roll-up hints) and
        ``conflict_records`` (Adhāra conflict notes) are preserved into the envelope summaries
        -- never used to average or launder a signal. Deterministic: ``now`` is injected and
        never read from the wall clock.
        """
        findings = tuple(f for f in findings if isinstance(f, AgentFinding))
        events = tuple(e for e in events if isinstance(e, RealityEvent))

        # Subject -> every independent (source, direction, is_social) datum about it, so
        # corroboration can be evaluated ACROSS disciplines (a non-social finding may
        # corroborate a social signal) without merging the two into one authority.
        subject_view: Dict[Tuple[str, Tuple[str, ...]], List[Tuple[str, str, bool]]] = {}
        for f in findings:
            subject_view.setdefault(_subject_of(f), []).append(
                (_source_key(f), f.direction_label, _is_social_finding(f)))

        # Group findings into signals by (discipline, subject) -- a signal is the fused view of
        # the findings about the SAME subject within one discipline.
        groups: Dict[Tuple[str, str, Tuple[str, ...]], List[AgentFinding]] = {}
        for f in findings:
            kind, values = _subject_of(f)
            groups.setdefault((f.discipline, kind, values), []).append(f)

        signals: List[RealitySignal] = []
        authority_by_signal: Dict[str, str] = {}
        freshness_by_signal: Dict[str, str] = {}
        corroboration_by_signal: Dict[str, str] = {}
        for key in sorted(groups, key=lambda k: (k[0], k[1], k[2])):
            discipline, kind, values = key
            signal, authority, corroboration = self._build_signal(
                discipline, kind, values, sorted(
                    groups[key], key=lambda f: f.finding_id), subject_view)
            signals.append(signal)
            authority_by_signal[signal.signal_id] = authority
            freshness_by_signal[signal.signal_id] = signal.freshness_label
            corroboration_by_signal[signal.signal_id] = corroboration

        clusters = self._build_clusters(signals)

        for out in list(signals) + list(clusters):
            assert_no_trade_fields(out)   # reuse the 012A structural guard on every output

        envelope = self._build_envelope(
            signals, clusters, authority_by_signal,
            self._norm(authority_summaries), self._norm(freshness_summaries),
            self._norm(conflict_records), now)

        return FusionResult(
            signals=tuple(signals),
            clusters=tuple(clusters),
            envelope=envelope,
            authority_by_signal=authority_by_signal,
            freshness_by_signal=freshness_by_signal,
            corroboration_by_signal=corroboration_by_signal,
        )

    # -- signal construction ---------------------------------------------- #
    def _build_signal(self, discipline, kind, values, group, subject_view):
        """Fuse one same-subject, same-discipline group into a RealitySignal.

        Returns ``(signal, authority_label, corroboration_status)``. Authority is the BEST
        authority among the group's OWN findings (a narrative group is all-``rumor``, so it is
        never lifted above ``rumor``); corroboration is evaluated across every independent
        finding about the subject (so a non-social finding can corroborate a social signal).
        """
        subject = (kind, values)
        is_social = discipline == _labels.NARRATIVE_DISCIPLINE or all(
            _is_social_finding(f) for f in group)

        directions = [f.direction_label for f in group if f.direction_label]
        contradicted = any(
            _opposes(a, b) for i, a in enumerate(directions) for b in directions[i + 1:])

        # Lead finding = strongest magnitude then confidence then id (deterministic).
        lead = max(
            group,
            key=lambda f: (
                _index_in(_MAGNITUDE_ORDER, f.magnitude_label),
                _index_in(_CONFIDENCE_ORDER, f.confidence_label),
                f.finding_id),
        )
        direction_label = "mixed" if contradicted else (lead.direction_label or "")
        magnitude_label = _strongest(_MAGNITUDE_ORDER, (f.magnitude_label for f in group))
        urgency_label = _strongest(_URGENCY_ORDER, (f.urgency_label for f in group))

        # Authority: best among the group's OWN findings; rumor never lifted to a fact-tier.
        own_authorities = [
            f.source_authority_summary for f in group if f.source_authority_summary]
        authority = ""
        if own_authorities:
            authority = max(own_authorities, key=_labels.authority_rank)
        if is_social:
            authority = "rumor"

        # Corroboration: distinct independent sources about the subject whose direction does
        # NOT oppose the signal's direction. >=2 independent agreeing sources -> corroborated.
        agreeing_sources = set()
        non_social_corroborator = False
        for source, sdir, s_is_social in subject_view.get(subject, []):
            if contradicted or direction_label in ("", "mixed") or not _opposes(
                    sdir, direction_label):
                agreeing_sources.add(source)
                if not s_is_social:
                    non_social_corroborator = True
        own_sources = {_source_key(f) for f in group}
        corroborated = len(agreeing_sources) >= 2
        if corroborated:
            # A social signal corroborated ONLY by other social sources stays weak.
            if is_social and not non_social_corroborator:
                corroboration = "partially_corroborated"
                corroborated = False
            else:
                corroboration = "corroborated"
        elif len(own_sources) == 1:
            corroboration = "uncorroborated"
        else:
            corroboration = "uncorroborated"
        contradiction = "contradicted" if contradicted else "unopposed"

        # Confidence -- conservative: weakest by default, never upgraded without corroboration.
        confs = [f.confidence_label for f in group if f.confidence_label not in ("", "missing")]
        confidence = _weakest(_CONFIDENCE_ORDER, confs) or "missing"
        if contradicted:
            confidence = _cap(_CONFIDENCE_ORDER, confidence, "low")
        elif corroborated:
            strongest_conf = _strongest(_CONFIDENCE_ORDER, confs) or confidence
            confidence = _step_up(_CONFIDENCE_ORDER, confidence, strongest_conf)
            if is_social:
                confidence = _cap(_CONFIDENCE_ORDER, confidence, _SOCIAL_CONFIDENCE_CEILING)
        elif is_social:
            confidence = _cap(_CONFIDENCE_ORDER, confidence, _SOCIAL_UNCORROBORATED_CEILING)

        # Freshness -- reflect the STALEST finding; stale is surfaced, never dropped.
        real_fresh = [
            f.freshness_label for f in group
            if f.freshness_label in _FRESHNESS_REAL_ORDER]
        freshness = _weakest(_FRESHNESS_REAL_ORDER, real_fresh) or "missing"
        half_life = _weakest(_HALF_LIFE_ORDER, (f.half_life for f in group)) or ""

        # Evidence preserved end-to-end: union of refs / conflicts / gaps + fused notes.
        evidence_refs = _union(f.evidence_refs for f in group)
        source_refs = _union(f.source_refs for f in group)
        source_events = _union(f.input_events for f in group)
        conflicts = list(_union(f.conflicts for f in group))
        data_gaps = list(_union(f.data_gaps for f in group))
        if contradicted:
            conflicts.append(
                "contradiction: findings disagree on direction ({0}) [{1}]".format(
                    "/".join(sorted(set(directions))),
                    ", ".join(sorted(f.finding_id for f in group))))
        stale_ids = sorted(
            f.finding_id for f in group
            if f.freshness_label in ("stale", "expired"))
        if stale_ids:
            data_gaps.append("stale findings preserved: {0}".format(", ".join(stale_ids)))
        if is_social and corroboration != "corroborated":
            data_gaps.append("uncorroborated X/social (rumor) -- weak, needs corroboration")

        signal_id = "sig.{0}.{1}.{2}".format(
            _slug(discipline), _slug(kind), _slug("-".join(values)))
        signal = RealitySignal(
            signal_id=signal_id,
            signal_type="{0}_fused_signal".format(discipline or "cross_discipline"),
            source_findings=tuple(sorted(f.finding_id for f in group)),
            source_events=source_events,
            discipline=discipline,
            affected_companies=_union(f.affected_companies for f in group),
            affected_themes=_union(f.affected_themes for f in group),
            affected_sectors=_union(f.affected_sectors for f in group),
            affected_value_chains=_union(f.affected_value_chains for f in group),
            direction_label=direction_label,
            magnitude_label=magnitude_label,
            urgency_label=urgency_label,
            confidence_label=confidence,
            freshness_label=freshness,
            half_life=half_life,
            corroboration_status=corroboration,
            contradiction_status=contradiction,
            evidence_refs=evidence_refs,
            source_refs=source_refs,
            conflicts=tuple(dict.fromkeys(conflicts)),
            data_gaps=tuple(dict.fromkeys(data_gaps)),
            routing_targets=("Sphurana",),
        )
        return signal, authority, corroboration

    # -- cluster construction --------------------------------------------- #
    def _build_clusters(self, signals):
        """Group related signals (shared theme > sector > value_chain) into SignalClusters.

        A cluster forms for any shared dimension carrying ``>=2`` signals; conflicts and data
        gaps are preserved onto the cluster (never averaged away).
        """
        buckets: Dict[Tuple[str, str], List[RealitySignal]] = {}
        for sig in signals:
            for kind, values in (
                ("theme", sig.affected_themes),
                ("sector", sig.affected_sectors),
                ("value_chain", sig.affected_value_chains),
            ):
                if values:
                    for v in values:
                        buckets.setdefault((kind, v), []).append(sig)
                    break

        clusters: List[SignalCluster] = []
        for (kind, value) in sorted(buckets):
            members = sorted(buckets[(kind, value)], key=lambda s: s.signal_id)
            if len(members) < 2:
                continue
            companies = _union(s.affected_companies for s in members)
            member_dirs = [s.direction_label for s in members if s.direction_label]
            member_conflicted = any(
                s.contradiction_status == "contradicted" for s in members)
            cross_opposed = any(
                _opposes(a, b)
                for i, a in enumerate(member_dirs) for b in member_dirs[i + 1:])
            has_conflict = member_conflicted or cross_opposed
            if has_conflict:
                momentum = "mixed"
            else:
                pos = [d for d in member_dirs if d in _POSITIVE_DIRECTIONS]
                neg = [d for d in member_dirs if d in _NEGATIVE_DIRECTIONS]
                if pos and not neg:
                    momentum = sorted(pos)[0]
                elif neg and not pos:
                    momentum = sorted(neg)[0]
                elif member_dirs:
                    momentum = sorted(member_dirs)[0]
                else:
                    momentum = ""
            breadth = self._breadth_label(len(members), len(companies))
            conflict_label = "major" if (
                sum(1 for s in members if s.contradiction_status == "contradicted") >= 2
            ) else ("moderate" if has_conflict else "negligible")

            clusters.append(SignalCluster(
                cluster_id="cluster.{0}.{1}".format(_slug(kind), _slug(value)),
                cluster_type=kind,
                theme=value if kind == "theme" else "",
                sector=value if kind == "sector" else "",
                value_chain=value if kind == "value_chain" else "",
                companies=companies,
                signals=tuple(s.signal_id for s in members),
                breadth_label=breadth,
                crowding_label="unknown",
                momentum_label=momentum,
                conflict_label=conflict_label,
                confidence_label=_weakest(
                    _CONFIDENCE_ORDER, (s.confidence_label for s in members)) or "missing",
                freshness_label=_weakest(
                    _FRESHNESS_REAL_ORDER, (
                        s.freshness_label for s in members
                        if s.freshness_label in _FRESHNESS_REAL_ORDER)) or "missing",
                evidence_refs=_union(s.evidence_refs for s in members),
                source_refs=_union(s.source_refs for s in members),
                conflicts=_union(s.conflicts for s in members),
                data_gaps=_union(s.data_gaps for s in members),
            ))
        return clusters

    @staticmethod
    def _breadth_label(n_signals: int, n_companies: int) -> str:
        n = max(n_signals, n_companies)
        if n <= 1:
            return "minor"
        if n == 2:
            return "moderate"
        if n <= 4:
            return "major"
        return "extreme"

    # -- envelope construction -------------------------------------------- #
    def _build_envelope(
        self, signals, clusters, authority_by_signal,
        authority_hints, freshness_hints, conflict_records, now,
    ):
        payload_ids = tuple(
            sorted([s.signal_id for s in signals] + [c.cluster_id for c in clusters]))

        authorities = list(authority_by_signal.values()) + list(authority_hints)
        authority_summary = (
            max([a for a in authorities if a in _labels.SOURCE_AUTHORITIES],
                key=_labels.authority_rank)
            if any(a in _labels.SOURCE_AUTHORITIES for a in authorities) else "")

        fresh_values = [s.freshness_label for s in signals] + list(freshness_hints)
        freshness_summary = _weakest(
            _FRESHNESS_REAL_ORDER,
            [f for f in fresh_values if f in _FRESHNESS_REAL_ORDER]) or "missing"

        all_conflicts = []
        for s in signals:
            all_conflicts.extend(s.conflicts)
        all_conflicts.extend(conflict_records)
        all_gaps = []
        for s in signals:
            all_gaps.extend(s.data_gaps)

        requires_review = any(
            authority_by_signal.get(s.signal_id) == "rumor"
            or s.contradiction_status == "contradicted"
            for s in signals)

        token = "|".join(payload_ids) + "|" + now
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()[:12]

        return HandoffEnvelope(
            envelope_id="env.fusion.{0}".format(digest),
            created_at=now,
            from_layer="Tattva",
            to_layer=self.to_layer,
            from_agent="tattva.signal_fusion",
            to_synthesizer="Sphurana",
            payload_type=self.payload_type,
            payload_ids=payload_ids,
            routing_reason="fused {0} signal(s) + {1} cluster(s) for Sphurana hypothesis".format(
                len(signals), len(clusters)),
            authority_summary=authority_summary,
            freshness_summary=freshness_summary,
            conflict_summary="; ".join(dict.fromkeys(all_conflicts)),
            data_gap_summary="; ".join(dict.fromkeys(all_gaps)),
            requires_human_review=requires_review,
            allowed_downstream_uses=self.allowed_downstream_uses,
            forbidden_downstream_uses=self.forbidden_downstream_uses,
        )

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _norm(values: Optional[Iterable[str]]) -> Tuple[str, ...]:
        if values is None:
            return ()
        return tuple(str(v) for v in values)


def _union(iterables) -> Tuple[str, ...]:
    """Sorted, de-duplicated union of several ref/label tuples (deterministic, gap-preserving)."""
    seen = set()
    for it in iterables:
        for v in it:
            seen.add(v)
    return tuple(sorted(seen))
