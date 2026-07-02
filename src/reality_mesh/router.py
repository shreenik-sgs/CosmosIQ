"""The Buddhi Agent Router for the Reality Mesh (IMPLEMENTATION-012B).

INFRASTRUCTURE ONLY -- deterministic routing, NO synthesis. :class:`BuddhiRouter` does two
things, both from ``AGENT_MAP_012.md`` / ``HANDOFF_CONTRACT_012.md``:

* :meth:`BuddhiRouter.route_event` -- given a :class:`RealityEvent`, return the eligible sensor
  descriptors (matched by discipline / X-social source), so a macro event reaches
  ``tattva.macro_regime`` and an X/social event reaches ``tattva.narrative``.
* :meth:`BuddhiRouter.route_finding` -- wrap an :class:`AgentFinding` for its correct
  synthesizer in a :class:`HandoffEnvelope` (a Tattva finding -> ``TattvaSignalFusion``),
  rolling up the finding's authority / freshness / conflict / data-gap summaries, stamping
  ``requires_human_review`` and ``allowed_/forbidden_downstream_uses`` -- whose forbidden set
  ALWAYS includes the four defaults (broker_order / auto_execute / buy_sell_recommendation /
  hidden_score, merged by the envelope).

The router NEVER fuses, averages, upgrades, or invents a signal: it wraps and routes existing
objects only. Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no broker.
"""

from __future__ import annotations

from typing import Optional, Tuple

from . import labels as _labels
from .models import AgentFinding, HandoffEnvelope, RealityEvent

# from_layer -> (to_layer, to_synthesizer, allowed_downstream_uses). A discipline agent emits
# an AgentFinding; a Tattva finding routes to the Tattva Signal Fusion synthesizer (HANDOFF §4.2).
_FINDING_ROUTE = {
    "Tattva": ("Tattva", "TattvaSignalFusion", ("fuse",)),
}
_DEFAULT_ROUTE = ("Tattva", "TattvaSignalFusion", ("fuse",))

# Forbidden downstream uses stamped on every finding envelope (all members of the closed
# FORBIDDEN_DOWNSTREAM_USES vocab). The envelope additionally merges in the four mandatory
# defaults, so an envelope can never omit broker_order / auto_execute / buy_sell / hidden_score.
_FINDING_FORBIDDEN_USES = ("order", "place-order", "buy_sell_hold", "score_rank")


class BuddhiRouter:
    """Deterministic router. Wraps + routes handoff objects; performs NO synthesis."""

    def __init__(self, registry=None) -> None:
        # Optional AgentRegistry: used to look up the producing descriptor for a finding
        # (so requires_human_review can reflect the agent's default). Routing works without it.
        self._registry = registry

    # -- event -> eligible sensor descriptors ------------------------------ #
    def route_event(self, event: RealityEvent) -> Tuple:
        """Return the Tattva sensor descriptors eligible to sense ``event`` (deterministic).

        Eligibility is by discipline; an X/social event (narrative discipline or social
        source_type) routes to the ``narrative`` sensor regardless of its declared discipline.
        Returns an empty tuple if no registry is attached or nothing matches.
        """
        if self._registry is None:
            return tuple()
        discipline = event.discipline
        if _labels.is_social_source(source_type=event.source_type, discipline=discipline):
            discipline = _labels.NARRATIVE_DISCIPLINE
        if discipline == "":
            return tuple()
        matches = [
            d for d in self._registry.list_by_layer("Tattva")
            if d.agent_type == "sensor" and d.discipline == discipline
        ]
        return tuple(sorted(matches, key=lambda d: d.agent_id))

    # -- finding -> HandoffEnvelope ---------------------------------------- #
    def route_finding(self, finding: AgentFinding, created_at: str = "") -> HandoffEnvelope:
        """Wrap ``finding`` in a :class:`HandoffEnvelope` addressed to its synthesizer.

        Rolls up (never averages away) the finding's authority / freshness / conflict /
        data-gap summaries; stamps the allowed use for its layer and the forbidden uses
        (always including the four defaults). Raises ``TypeError`` if given a non-finding.
        """
        if not isinstance(finding, AgentFinding):
            raise TypeError(
                "route_finding expects an AgentFinding, got {0}".format(type(finding).__name__))

        to_layer, to_synth, allowed_uses = _FINDING_ROUTE.get(
            finding.agent_layer, _DEFAULT_ROUTE)

        requires_review = False
        if self._registry is not None and self._registry.has(finding.agent_id):
            requires_review = self._registry.get(
                finding.agent_id).requires_human_review_by_default

        return HandoffEnvelope(
            envelope_id="env.{0}".format(finding.finding_id),
            created_at=created_at,
            from_layer=finding.agent_layer,
            to_layer=to_layer,
            from_agent=finding.agent_id,
            to_synthesizer=to_synth,
            payload_type="AgentFinding",
            payload_ids=(finding.finding_id,),
            routing_reason="route {0} finding to {1}".format(
                finding.discipline or "discipline", to_synth),
            authority_summary=finding.source_authority_summary,
            freshness_summary=finding.freshness_label,
            conflict_summary="; ".join(finding.conflicts),
            data_gap_summary="; ".join(finding.data_gaps),
            requires_human_review=requires_review,
            allowed_downstream_uses=allowed_uses,
            forbidden_downstream_uses=_FINDING_FORBIDDEN_USES,
        )
