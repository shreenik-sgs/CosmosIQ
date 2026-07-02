"""CLI entry point: ``python3 -m universe_ui --out <dir>``.

Builds the seven static Economic Universe pages into ``--out`` (default
``generated/universe_ui``) and prints the written paths. Generated HTML is a build
artifact -- do not commit it. Stdlib only; no network, no scheduler, no broker.
"""

from __future__ import annotations

import argparse
import sys

from .app import PAGE_ORDER, build_universe_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="universe_ui",
        description="Build the static Sudarshan Economic Universe UI (read-only).")
    parser.add_argument(
        "--out", default="generated/universe_ui",
        help="output directory for the generated static pages (default: generated/universe_ui)")
    parser.add_argument(
        "--mode", default="demo",
        choices=("demo", "evidence_ingested_fixture", "real_evidence_on_demand"),
        help="demo (hand-authored universe), evidence_ingested_fixture (REAL sparse "
             "terrain from the IREN evidence-alpha slice), or real_evidence_on_demand "
             "(REAL current SEC/FMP/yfinance data for --ticker; manual, not scheduled, "
             "not broker-connected)")
    parser.add_argument(
        "--ticker", default=None,
        help="ticker for real_evidence_on_demand mode (REQUIRED in that mode, e.g. IREN)")
    parser.add_argument(
        "--enable-yfinance", action="store_true",
        help="opt in to the yfinance fallback (research-only) in real mode")
    args = parser.parse_args(argv)

    build_kwargs = {}
    if args.mode == "real_evidence_on_demand":
        if not args.ticker:
            parser.error("--mode real_evidence_on_demand requires --ticker (e.g. --ticker IREN)")
        # Credentials are resolved from the environment by the runtime helper -- never
        # here, never printed. Missing creds become a visible in-page data gap.
        from runtime.live_evidence_run import resolve_live_credentials, credential_presence
        sec_user_agent, fmp_api_key = resolve_live_credentials()
        presence = credential_presence()
        build_kwargs = {
            "ticker": args.ticker.strip().upper(),
            "sec_user_agent": sec_user_agent,
            "fmp_api_key": fmp_api_key,
            "enable_yfinance": args.enable_yfinance,
        }
        print("Real evidence on demand · manual refresh only · not scheduled · "
              "not broker-connected · data may be incomplete")
        print("  ticker: {0}".format(build_kwargs["ticker"]))
        print("  SEC User-Agent present: {0} · FMP API key present: {1} "
              "(values never printed)".format(
                  presence["sec_user_agent_present"], presence["fmp_api_key_present"]))

    paths = build_universe_app(args.out, mode=args.mode, **build_kwargs)
    print("Built Sudarshan Economic Universe UI (read-only, mode={0}):".format(args.mode))
    for name in PAGE_ORDER:
        print("  {0}".format(paths[name]))
    print("  {0}".format(paths["assets/universe.css"]))
    print("  {0}".format(paths["assets/universe.js"]))
    print("Open {0} in a browser. Live data / scheduler / broker: not enabled.".format(
        paths["universe.html"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
