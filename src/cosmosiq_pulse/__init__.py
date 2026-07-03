"""``cosmosiq_pulse`` -- the migrated (English-named) entry point for the manual, on-demand
Reality-Mesh pulse CLI.

This is the approved name for the pulse runner previously exposed as ``tattva_pulse``. It is a
THIN, behaviour-preserving alias: ``python3 -m cosmosiq_pulse --watchlist … --themes … --out …``
imports and re-invokes the existing :func:`tattva_pulse.__main__.main` verbatim, so byte-for-byte
demo behaviour is preserved. ``tattva_pulse`` remains a working (deprecated) alias.

MANUAL / ON-DEMAND ONLY. No scheduler, no daemon, no background job, no streaming, no live X, no
network, no broker, no order. ``--watchlist`` and ``--themes`` are REQUIRED (empty -> rejected).
Missing coverage is an explicit gap, never a silent demo fall-back and never fabricated.
"""

from __future__ import annotations

from tattva_pulse.summary import build_pulse_summary

__all__ = ["build_pulse_summary", "main"]


def main(argv=None) -> int:
    """Console entry point (delegates verbatim to :func:`tattva_pulse.__main__.main`)."""
    from tattva_pulse.__main__ import main as _main
    return _main(argv)
