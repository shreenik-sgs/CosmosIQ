"""The machine-readable pulse summary for ``tattva_pulse`` (IMPLEMENTATION-012K).

:func:`build_pulse_summary` projects a :class:`~reality_mesh.pulse.PulseResult` into a plain,
JSON-serialisable ``dict`` of LABELS / gaps / provenance. It carries NO numeric investability
score / rank / rating and NO buy / sell / order / broker field -- only qualitative labels
(direction / magnitude / confidence / freshness / authority / corroboration / theme state) plus
the honest data gaps. Deterministic: every list is built in a stable order.
"""

from __future__ import annotations

from typing import Any, Dict

from reality_mesh.pulse import PulseResult

# The honest banner every manual pulse prints + records in its summary. Manual, on demand, not
# scheduled, not broker-connected, fixture-backed, and possibly incomplete.
PULSE_BANNER = (
    "manual pulse · on demand · not scheduled · not broker-connected · fixture-backed · "
    "data may be incomplete")


def build_pulse_summary(result: PulseResult) -> Dict[str, Any]:
    """Return a JSON-serialisable summary of ``result`` (labels + gaps + provenance; NO scores)."""
    return {
        "mode": "pulse",
        "kind": "manual_on_demand_reality_pulse",
        "banner": PULSE_BANNER,
        "scheduled": False,
        "broker_connected": False,
        "live_data": False,
        "network": False,
        "watchlist": list(result.watchlist),
        "themes": list(result.themes),
        "now": result.now,
        "fixture_dir": result.fixture_dir,
        "events_loaded": result.events_loaded,
        "coverage": {
            "covered_companies": list(result.covered_companies),
            "covered_themes": list(result.covered_themes),
        },
        "agent_runs": [
            {
                "agent_id": a.agent_id,
                "agent_name": a.agent_name,
                "discipline": a.discipline,
                "events_seen": a.events_seen,
                "findings": a.findings,
                "status": a.status,
                "finding_ids": list(a.finding_ids),
            }
            for a in result.agent_runs
        ],
        "signals": [
            {
                "signal_id": s.signal_id,
                "discipline": s.discipline,
                "direction_label": s.direction_label,
                "magnitude_label": s.magnitude_label,
                "confidence_label": s.confidence_label,
                "freshness_label": s.freshness_label,
                "corroboration_status": s.corroboration_status,
                "contradiction_status": s.contradiction_status,
                # authority is a fusion sidecar (a signal carries no authority field); absent -> a
                # visible gap, never fabricated.
                "source_authority": result.authority_by_signal.get(s.signal_id, "unknown"),
                "affected_companies": list(s.affected_companies),
                "affected_themes": list(s.affected_themes),
                "affected_sectors": list(s.affected_sectors),
                "data_gaps": list(s.data_gaps),
            }
            for s in result.signals
        ],
        "theme_pulses": [
            {
                "theme_pulse_id": p.theme_pulse_id,
                "theme_name": p.theme_name,
                "state": p.state,
                "breadth_label": p.breadth_label,
                "rotation_label": p.rotation_label,
                "crowding_label": p.crowding_label,
                "confidence_label": p.confidence_label,
                "freshness_label": p.freshness_label,
                "supporting_signals": list(p.supporting_signals),
                "contradicting_signals": list(p.contradicting_signals),
                "beneficiary_candidates": list(p.beneficiary_candidates),
                "risk_candidates": list(p.risk_candidates),
                "data_gaps": list(p.data_gaps),
                "note": "theme STATE, not a trade recommendation / price target / stock pick",
            }
            for p in result.theme_pulses
        ],
        "data_gaps": list(result.data_gaps),
        "disclaimer": (
            "These are reality SIGNALS and theme STATES (evidence), never a ranking, a decision, "
            "a position size, or an execution instruction. Weak / X-social signals stay weak "
            "(rumor, never verified). Nivesha / Saarathi / Kriya boundaries are intact: no "
            "thesis, no sizing, no execution."
        ),
    }
