"""Infinite Canvas -- the assembled, READ-ONLY ``AlphaDecisionCockpitView``.

Projects the full pipeline into the nine 008A panels and binds them together with
a complete provenance chain (Observation -> IntelligenceAssessment ->
OpportunityHypothesis -> InvestmentThesis -> InvestmentAction -> PersonalizedAction
-> ManualExecutionIntent -> ManualTradeTicket) and the union of every panel's
missing-data flags (``data_gaps``).

Pure projection: it copies fields, never recomputes; it never mutates a source
object; and where the pipeline has no backing field it surfaces a missing-data
flag rather than inventing a value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from .view_models import (
    EvidenceRef,
    OpportunityMapPanel,
    ValueChainBottleneckPanel,
    CatalystPanel,
    FinancialInflectionPanel,
    ScenarioAsymmetryPanel,
    TechnicalConfirmationPanel,
    RedTeamPanel,
    PersonalizedActionPanel,
    ManualExecutionPanel,
    evidence_ref,
    build_opportunity_map_panel,
    build_value_chain_bottleneck_panel,
    build_catalyst_panel,
    build_financial_inflection_panel,
    build_scenario_asymmetry_panel,
    build_technical_confirmation_panel,
    build_red_team_panel,
    build_personalized_action_panel,
    build_manual_execution_panel,
)


@dataclass(frozen=True)
class AlphaDecisionCockpitView:
    """The end-to-end Infinite Canvas read-model for one alpha decision.

    ``subject`` is the candidate security/instrument mapping (copied verbatim from
    the thesis). The seven cognition panels are always present; the personalized and
    manual-execution panels are present only when their source objects were supplied.
    """

    subject: str
    opportunity_map: OpportunityMapPanel
    value_chain_bottleneck: ValueChainBottleneckPanel
    catalyst: CatalystPanel
    financial_inflection: FinancialInflectionPanel
    scenario_asymmetry: ScenarioAsymmetryPanel
    technical_confirmation: TechnicalConfirmationPanel
    red_team: RedTeamPanel
    personalized_action: Optional[PersonalizedActionPanel] = None
    manual_execution: Optional[ManualExecutionPanel] = None
    provenance_chain: Tuple[EvidenceRef, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def panels(self) -> Tuple[Any, ...]:
        """Every panel present on the cockpit, in display order."""
        ordered = [
            self.opportunity_map,
            self.value_chain_bottleneck,
            self.catalyst,
            self.financial_inflection,
            self.scenario_asymmetry,
            self.technical_confirmation,
            self.red_team,
            self.personalized_action,
            self.manual_execution,
        ]
        return tuple(p for p in ordered if p is not None)


def _provenance_chain(*, observations, intelligence_assessment, opportunity_hypothesis,
                      investment_thesis, investment_action, personalized_action,
                      manual_execution_intent, ticket) -> Tuple[EvidenceRef, ...]:
    """Ordered Observation -> ... -> Ticket evidence refs for whatever is present."""
    chain = []
    for obs in observations or ():
        chain.append(evidence_ref(obs, "Observation"))
    for obj, kind in (
        (intelligence_assessment, "IntelligenceAssessment"),
        (opportunity_hypothesis, "OpportunityHypothesis"),
        (investment_thesis, "InvestmentThesis"),
        (investment_action, "InvestmentAction"),
        (personalized_action, "PersonalizedAction"),
        (manual_execution_intent, "ManualExecutionIntent"),
        (ticket, "ManualTradeTicket"),
    ):
        if obj is not None:
            chain.append(evidence_ref(obj, kind))
    return tuple(chain)


def _data_gaps(panels) -> Tuple[str, ...]:
    """The union of every panel's missing_fields, prefixed by panel_id, sorted."""
    gaps = []
    for p in panels:
        for name in p.missing_fields:
            gaps.append("{0}.{1}".format(p.panel_id, name))
    return tuple(sorted(set(gaps)))


def build_alpha_decision_cockpit_view(*, opportunity_hypothesis, investment_thesis,
                                      investment_action=None, personalized_action=None,
                                      manual_execution_intent=None, intelligence_assessment=None,
                                      observations=(), ticket=None, reconciliation=None,
                                      audit_trail=None) -> AlphaDecisionCockpitView:
    """Assemble the cockpit from already-computed pipeline objects (pure projection)."""
    opportunity_map = build_opportunity_map_panel(opportunity_hypothesis)
    value_chain_bottleneck = build_value_chain_bottleneck_panel(investment_thesis)
    catalyst = build_catalyst_panel(investment_thesis, intelligence_assessment)
    financial_inflection = build_financial_inflection_panel(investment_thesis)
    scenario_asymmetry = build_scenario_asymmetry_panel(investment_thesis)
    technical_confirmation = build_technical_confirmation_panel(investment_thesis)
    red_team = build_red_team_panel(investment_thesis)

    personalized_panel = (
        build_personalized_action_panel(personalized_action)
        if personalized_action is not None else None
    )
    manual_panel = (
        build_manual_execution_panel(
            manual_execution_intent, ticket=ticket,
            reconciliation=reconciliation, audit_trail=audit_trail,
        )
        if manual_execution_intent is not None else None
    )

    cockpit = AlphaDecisionCockpitView(
        subject=investment_thesis.security_or_instrument_mapping,
        opportunity_map=opportunity_map,
        value_chain_bottleneck=value_chain_bottleneck,
        catalyst=catalyst,
        financial_inflection=financial_inflection,
        scenario_asymmetry=scenario_asymmetry,
        technical_confirmation=technical_confirmation,
        red_team=red_team,
        personalized_action=personalized_panel,
        manual_execution=manual_panel,
        provenance_chain=_provenance_chain(
            observations=observations,
            intelligence_assessment=intelligence_assessment,
            opportunity_hypothesis=opportunity_hypothesis,
            investment_thesis=investment_thesis,
            investment_action=investment_action,
            personalized_action=personalized_action,
            manual_execution_intent=manual_execution_intent,
            ticket=ticket,
        ),
    )
    # data_gaps is a function of the assembled panels.
    return AlphaDecisionCockpitView(
        subject=cockpit.subject,
        opportunity_map=cockpit.opportunity_map,
        value_chain_bottleneck=cockpit.value_chain_bottleneck,
        catalyst=cockpit.catalyst,
        financial_inflection=cockpit.financial_inflection,
        scenario_asymmetry=cockpit.scenario_asymmetry,
        technical_confirmation=cockpit.technical_confirmation,
        red_team=cockpit.red_team,
        personalized_action=cockpit.personalized_action,
        manual_execution=cockpit.manual_execution,
        provenance_chain=cockpit.provenance_chain,
        data_gaps=_data_gaps(cockpit.panels),
    )


def from_slice(slice_result) -> AlphaDecisionCockpitView:
    """Convenience: build the cockpit from a runtime ``SliceResult``."""
    return build_alpha_decision_cockpit_view(
        opportunity_hypothesis=slice_result.hypothesis,
        investment_thesis=slice_result.thesis,
        investment_action=slice_result.action,
        personalized_action=slice_result.personalized_action,
        manual_execution_intent=slice_result.execution_intent,
        intelligence_assessment=slice_result.assessment,
        observations=slice_result.observations,
        ticket=slice_result.ticket_placed,
        reconciliation=slice_result.reconciliation,
        audit_trail=slice_result.audit_trail,
    )
