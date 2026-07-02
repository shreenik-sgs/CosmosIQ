"""``tattva_pulse`` -- the manual, on-demand Reality-Mesh pulse CLI (IMPLEMENTATION-012K).

A human runs ONE pulse: ``python3 -m tattva_pulse --watchlist … --themes … --out …``. It drives
:func:`reality_mesh.pulse.run_pulse` (fixtures -> sensor agents -> fusion -> Sphurana), renders the
produced signals / theme pulses into the Economic Universe Data-Quality page as EVIDENCE via
:func:`universe_ui.app.build_universe_app`, and writes a machine-readable ``pulse_summary.json``
(labels / gaps / provenance -- NO scores, NO trade fields).

MANUAL / ON-DEMAND ONLY. No scheduler, no daemon, no background job, no streaming, no live X, no
network, no broker, no order. ``--watchlist`` and ``--themes`` are REQUIRED (empty -> rejected).
Missing coverage is an explicit gap, never a silent demo fall-back and never fabricated.
"""

from __future__ import annotations

from .summary import build_pulse_summary

__all__ = ["build_pulse_summary", "main"]


def main(argv=None) -> int:
    """Console entry point (delegates to :func:`tattva_pulse.__main__.main`)."""
    from .__main__ import main as _main
    return _main(argv)
