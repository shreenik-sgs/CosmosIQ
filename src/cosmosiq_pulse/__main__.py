"""CLI entry point: ``PYTHONPATH=src python3 -m cosmosiq_pulse --watchlist … --themes … --out …``.

The migrated (English) name for the manual, on-demand Reality-Mesh pulse. By default it delegates
VERBATIM to :func:`tattva_pulse.__main__.main`, so the produced evidence pages + ``pulse_summary.
json`` are byte-for-byte identical to the legacy ``python3 -m tattva_pulse`` invocation. See
``docs/OPERATOR_GUIDE_012.md``.

PROD-LIVE-1 adds an OPT-IN ``--live`` flag (default OFF): when passed it runs a REAL, credential-
gated LIVE pulse (SEC EDGAR + FMP) via :func:`reality_mesh.run_live_pulse` into ``--persist-dir``
instead of the fixture pulse. It is built from credential PRESENCE only: with neither
``SEC_USER_AGENT`` nor ``FMP_API_KEY`` set it fetches NOTHING (offline-safe -- no network is
attempted), persists NO run, and prints an honest "no live sources configured" summary. A live
fetch failure is a visible source gap, never a fixture fallback. Secrets are presence-only (a value
is never printed). Record/refresh-only -- no broker / order / trade affordance. The DEFAULT (no
``--live``) path is untouched and byte-identical.
"""

from __future__ import annotations

import sys


def main(argv=None) -> int:
    """Console entry point.

    Default: delegates VERBATIM to :func:`tattva_pulse.__main__.main` (byte-identical). When
    ``--live`` is present, runs the opt-in credential-gated LIVE pulse instead.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if "--live" in args:
        return _run_live(args)
    from tattva_pulse.__main__ import main as _main
    return _main(args)


def _run_live(argv) -> int:
    """Run ONE opt-in, credential-gated LIVE pulse and print an honest summary. Offline-safe.

    Requires ``--persist-dir`` (the live run is persisted into the cockpit store). Builds the live
    adapters from credential PRESENCE; with neither credential set it prints the honest "no live
    sources configured" note and attempts NO network. ``now`` is injected via ``--now`` (defaults
    to the wall clock read ONCE here at the shell boundary). Secrets are never printed.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="cosmosiq_pulse --live",
        description=("Run ONE REAL, credential-gated LIVE pulse (SEC EDGAR + FMP) into a local "
                     "store. Opt-in, record-only, shadow-marked; not scheduled, no broker, no "
                     "orders. With no credentials set it fetches nothing (offline-safe)."))
    parser.add_argument("--live", action="store_true", default=False,
                        help="run the credential-gated LIVE pulse (this flag).")
    parser.add_argument("--watchlist", default="",
                        help="REQUIRED comma-separated tickers, e.g. --watchlist IREN,AAOI.")
    parser.add_argument("--themes", default="",
                        help="REQUIRED comma-separated themes, e.g. --themes physical-ai.")
    parser.add_argument("--persist-dir", default=None,
                        help="REQUIRED for --live: the local append-only store the live run is "
                             "persisted into (the cockpit reads it). Local files only.")
    parser.add_argument("--run-id", default="",
                        help="optional stable run id (default: derived deterministically from "
                             "the scope + --now).")
    parser.add_argument("--now", default=None,
                        help="injected ISO-8601 instant (default: the wall clock, read ONCE "
                             "here at the shell boundary).")
    args = parser.parse_args(argv)

    from reality_mesh import run_live_pulse

    if not args.persist_dir:
        parser.error("--live requires --persist-dir (the local store the live run persists "
                     "into; the cockpit reads it)")
    watch = [t for t in (args.watchlist or "").split(",") if t.strip()]
    themes = [t for t in (args.themes or "").split(",") if t.strip()]
    if not watch:
        parser.error("--watchlist is required and must be non-empty (e.g. --watchlist IREN,AAOI)")
    if not themes:
        parser.error("--themes is required and must be non-empty (e.g. --themes physical-ai)")

    now = args.now
    if not now:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("ONE LIVE pulse (PROD-LIVE-1) · credential-gated · record-only · shadow-marked · "
          "not scheduled, no broker, no orders. Secrets are presence-only (never printed).")
    print("  now (injected): {0}".format(now))

    result = run_live_pulse(watch, themes, store_dir=args.persist_dir, now=now,
                            run_id=args.run_id)

    print("  live source configuration (presence only -- values never read):")
    for note in result.config_notes:
        print("    - {0}".format(note))

    if not result.configured:
        print("  {0}".format(result.summary_line()))
        print("No live sources configured -- nothing fetched, nothing persisted, no network "
              "attempted, no fixture fallback. Set the env var(s) above and re-run.")
        return 0

    print("  sources configured: {0}".format(", ".join(result.sources_configured)))
    print("  source health (labels + counts only):")
    for h in result.source_health:
        print("    - {0} [{1}]: status={2} · health={3} · rate_limit={4} · events={5}".format(
            h.adapter_id, h.authority, h.status, h.health, h.rate_limit_status,
            h.events_created))
    print("  events loaded: {0} · findings: {1} · signals: {2} · theme pulses: {3}".format(
        result.events_loaded, result.findings, result.signals, result.theme_pulses))
    if result.data_gaps:
        print("  data gaps ({0}) -- honest, never fabricated:".format(len(result.data_gaps)))
        for g in result.data_gaps:
            print("    - {0}".format(g))
    else:
        print("  data gaps: none recorded in this pulse")
    print("  run persisted (append-only): run_id={0} · store={1} · replay deterministic_match={2}"
          .format(result.run_id, args.persist_dir, result.replay_deterministic_match))
    print("Live pulse complete (shadow) -- refresh only. Production 24x7 / broker / orders: "
          "NOT enabled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
