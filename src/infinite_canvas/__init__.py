"""Infinite Canvas -- READ-ONLY UI view-model / read-model layer (IMPLEMENTATION-008A).

A pure PROJECTION of the existing EIOS pipeline objects into nine UI-facing panel
view models, assembled into one end-to-end ``AlphaDecisionCockpitView``. No
rendering, no new reasoning, no scoring, no recomputation, no ingestion, no broker.
Every value is copied verbatim from a source field; absent data is surfaced as an
honest missing-data flag, never invented; source objects are never mutated.
"""

from __future__ import annotations

from .view_models import (
    EvidenceRef,
    PanelProvenance,
    PanelView,
    ValueChainNodeView,
    PlayerRoleView,
    CatalystItemView,
    RedTeamCheckView,
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
    panel_field_names,
    build_opportunity_map_panel,
    build_value_chain_bottleneck_panel,
    build_catalyst_panel,
    build_financial_inflection_panel,
    build_scenario_asymmetry_panel,
    build_technical_confirmation_panel,
    build_red_team_panel,
    build_personalized_action_panel,
    build_manual_execution_panel,
    LAYER_TATTVA,
    LAYER_SPHURANA,
    LAYER_NIVESHA,
    LAYER_SAARATHI,
    LAYER_KRIYA,
    SOURCE_CLASS_MANUAL,
)
from .cockpit import (
    AlphaDecisionCockpitView,
    build_alpha_decision_cockpit_view,
    from_slice,
)
from .render_html import (
    render_cockpit_html,
    render_slice_to_html,
    write_cockpit_html,
)

__all__ = [
    "EvidenceRef",
    "PanelProvenance",
    "PanelView",
    "ValueChainNodeView",
    "PlayerRoleView",
    "CatalystItemView",
    "RedTeamCheckView",
    "OpportunityMapPanel",
    "ValueChainBottleneckPanel",
    "CatalystPanel",
    "FinancialInflectionPanel",
    "ScenarioAsymmetryPanel",
    "TechnicalConfirmationPanel",
    "RedTeamPanel",
    "PersonalizedActionPanel",
    "ManualExecutionPanel",
    "evidence_ref",
    "panel_field_names",
    "build_opportunity_map_panel",
    "build_value_chain_bottleneck_panel",
    "build_catalyst_panel",
    "build_financial_inflection_panel",
    "build_scenario_asymmetry_panel",
    "build_technical_confirmation_panel",
    "build_red_team_panel",
    "build_personalized_action_panel",
    "build_manual_execution_panel",
    "AlphaDecisionCockpitView",
    "build_alpha_decision_cockpit_view",
    "from_slice",
    "render_cockpit_html",
    "render_slice_to_html",
    "write_cockpit_html",
    "LAYER_TATTVA",
    "LAYER_SPHURANA",
    "LAYER_NIVESHA",
    "LAYER_SAARATHI",
    "LAYER_KRIYA",
    "SOURCE_CLASS_MANUAL",
]
