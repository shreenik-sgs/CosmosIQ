"""CLI entry point: ``PYTHONPATH=src python3 -m tattva_pulse --watchlist … --themes … --out …``.

Runs ONE manual, on-demand Reality-Mesh pulse and writes its evidence into ``--out``: the static
Economic Universe pages (with the produced signals / theme pulses rendered into the Data-Quality
page as EVIDENCE, via ``build_universe_app`` in demo mode) plus a machine-readable
``pulse_summary.json`` (labels / gaps / provenance -- no scores).

MANUAL / ON-DEMAND ONLY. ``--watchlist`` and ``--themes`` are REQUIRED and must be non-empty
(empty -> the CLI errors and nothing is produced). No scheduler, no daemon, no streaming, no live
X, no network, no broker, no order affordance. Missing coverage is an explicit gap, never a silent
demo fall-back. Generated HTML + JSON are build ARTIFACTS -- do not commit them. See
``docs/OPERATOR_GUIDE_012.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from reality_mesh.pulse import run_pulse
from universe_ui.app import PAGE_ORDER, build_universe_app

from .summary import PULSE_BANNER, build_pulse_summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tattva_pulse",
        description=("Run ONE manual, on-demand Reality-Mesh pulse (fixture-backed, offline). "
                     "Not scheduled, not broker-connected, no orders."))
    parser.add_argument(
        "--watchlist", default="",
        help="REQUIRED comma-separated tickers, e.g. --watchlist IREN,AAOI,AMBA,OUST "
             "(normalised: strip / upper / dedupe). Empty is rejected.")
    parser.add_argument(
        "--themes", default="",
        help="REQUIRED comma-separated themes, e.g. --themes physical-ai,robotics,ai-power "
             "(normalised: strip / lower / dedupe). Empty is rejected.")
    parser.add_argument(
        "--out", default="generated/tattva_pulse",
        help="output directory for the generated evidence pages + pulse_summary.json "
             "(default: generated/tattva_pulse). A build artifact -- do not commit it.")
    parser.add_argument(
        "--fixture-dir", default=None,
        help="optional override for the bundled pulse fixture directory (OFFLINE JSON only; "
             "there is no live/network source).")
    args = parser.parse_args(argv)

    watch = [t for t in (args.watchlist or "").split(",") if t.strip()]
    themes = [t for t in (args.themes or "").split(",") if t.strip()]
    if not watch:
        parser.error("--watchlist is required and must be non-empty (e.g. --watchlist "
                     "IREN,AAOI,AMBA,OUST); a manual pulse needs an explicit universe")
    if not themes:
        parser.error("--themes is required and must be non-empty (e.g. --themes "
                     "physical-ai,robotics,ai-power); a manual pulse needs explicit themes")

    # Honest banner FIRST -- so it is never mistaken for a scheduled / live / broker-connected feed.
    print(PULSE_BANNER)

    result = run_pulse(watch, themes, fixture_dir=args.fixture_dir)

    # Render the produced signals / clusters / theme pulses into the Economic Universe Data-Quality
    # page as EVIDENCE (012J panel). Demo mode + the opt-in pulse args only -- the demo default
    # stays byte-identical when no pulse args are passed. No network, no scheduler, no broker.
    paths = build_universe_app(
        args.out, mode="demo",
        pulse_signals=result.signals,
        signal_clusters=result.clusters,
        theme_pulses=result.theme_pulses,
        pulse_authority_by_signal=result.authority_by_signal)

    # Machine-readable summary (labels / gaps / provenance; no scores).
    summary = build_pulse_summary(result)
    summary_path = os.path.join(args.out, "pulse_summary.json")
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")
    paths["pulse_summary.json"] = summary_path

    # -- report ------------------------------------------------------------------------------- #
    print("Manual pulse complete (mode=pulse · offline · fixture-backed):")
    print("  watchlist: {0}".format(", ".join(result.watchlist)))
    print("  themes:    {0}".format(", ".join(result.themes)))
    print("  events loaded: {0} · findings: {1} · signals: {2} · theme pulses: {3}".format(
        result.events_loaded, len(result.findings), len(result.signals),
        len(result.theme_pulses)))
    print("  sensor agents:")
    for a in result.agent_runs:
        print("    {0} [{1}]: {2} finding(s) from {3} event(s) -- {4}".format(
            a.agent_id, a.discipline, a.findings, a.events_seen, a.status))
    print("  theme pulses (STATE, not a recommendation):")
    for p in result.theme_pulses:
        print("    {0}: {1}".format(p.theme_name, p.state))
    if result.data_gaps:
        print("  data gaps ({0}) -- honest, never fabricated:".format(len(result.data_gaps)))
        for g in result.data_gaps:
            print("    - {0}".format(g))
    else:
        print("  data gaps: none recorded in this pulse")
    print("Outputs written under {0}:".format(args.out))
    for name in PAGE_ORDER:
        print("  {0}".format(paths[name]))
    print("  {0}".format(paths["pulse_summary.json"]))
    print("Open {0} -> Data Quality for the reality-signal evidence panel.".format(
        paths["universe.html"]))
    print("Live data / scheduler / broker / orders: NOT enabled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
