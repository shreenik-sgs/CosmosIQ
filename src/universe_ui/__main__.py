"""CLI entry point: ``python3 -m universe_ui --out <dir>``.

Builds the static Economic Universe pages (universe / dashboard / data_quality / cockpit,
plus per-ticker cockpits in watchlist mode) into ``--out`` (default
``generated/universe_ui``) and prints the written paths. Modes: ``demo`` (default),
``evidence_ingested_fixture``, ``real_evidence_on_demand`` (``--ticker`` / ``--tickers``,
optionally ``--enrich`` / ``--enable-yfinance``). Generated HTML is a build artifact -- do
not commit it. Stdlib only; no network on import, no scheduler, no broker. See
``docs/OPERATOR_GUIDE_011.md``.
"""

from __future__ import annotations

import argparse
import sys

from .app import PAGE_ORDER, build_universe_app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="universe_ui",
        description="Build the static CosmosIQ Universe Canvas UI (read-only).")
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
        help="single ticker for real_evidence_on_demand mode (010D, e.g. --ticker IREN)")
    parser.add_argument(
        "--tickers", default=None,
        help="comma-separated watchlist for real_evidence_on_demand mode (010E, e.g. "
             "--tickers IREN,AAOI,INOD). Normalised: strip / upper / dedupe, first-seen "
             "order. Builds ONE merged sparse terrain of multiple real company planets.")
    parser.add_argument(
        "--enable-yfinance", action="store_true",
        help="opt in to the yfinance fallback (research-only) in real mode")
    parser.add_argument(
        "--enrich", action="store_true",
        help="opt in to diligence enrichment in real mode (011C): overlay market cap / "
             "financials from each ticker's already-fetched SEC/FMP payloads onto the "
             "CompanyNode / Data Quality / cockpit, SOURCE-BACKED ONLY. Unsupported TAM / "
             "value-chain / bottleneck / IR / leadership stay visible gaps; nothing is "
             "fabricated; source authority preserved (manual never canonical). Default off "
             "keeps the honest unenriched sparse terrain.")
    args = parser.parse_args(argv)

    build_kwargs = {}
    if args.mode == "real_evidence_on_demand":
        if not args.ticker and not args.tickers:
            parser.error("--mode real_evidence_on_demand requires --ticker or --tickers "
                         "(e.g. --ticker IREN, or --tickers IREN,AAOI,INOD)")
        # Credentials are resolved from the environment by the runtime helper -- never
        # here, never printed. Missing creds become a visible in-page data gap.
        from runtime.live_evidence_run import resolve_live_credentials, credential_presence
        sec_user_agent, fmp_api_key = resolve_live_credentials()
        presence = credential_presence()
        build_kwargs = {
            "sec_user_agent": sec_user_agent,
            "fmp_api_key": fmp_api_key,
            "enable_yfinance": args.enable_yfinance,
            "enrich": args.enrich,
        }
        if args.tickers:
            from universe_ui.watchlist_terrain import normalize_tickers
            norm = normalize_tickers(args.tickers)
            if not norm:
                parser.error("--tickers is empty after normalisation (nothing to fetch)")
            build_kwargs["tickers"] = list(norm)
            ticker_label = ", ".join(norm)
        else:
            build_kwargs["ticker"] = args.ticker.strip().upper()
            ticker_label = build_kwargs["ticker"]
        print("Real evidence on demand · manual refresh only · not scheduled · "
              "not broker-connected · data may be incomplete")
        print("  ticker(s): {0}".format(ticker_label))
        print("  SEC User-Agent present: {0} · FMP API key present: {1} "
              "(values never printed)".format(
                  presence["sec_user_agent_present"], presence["fmp_api_key_present"]))
        print("  diligence enrichment: {0} (source-backed only; unsupported areas stay "
              "gaps)".format("ON (--enrich)" if args.enrich else "off (default)"))

    paths = build_universe_app(args.out, mode=args.mode, **build_kwargs)
    print("Built CosmosIQ Universe Canvas UI (read-only, mode={0}):".format(args.mode))
    for name in PAGE_ORDER:
        print("  {0}".format(paths[name]))
    for name in sorted(paths):
        if name.startswith("cockpit_"):
            print("  {0}".format(paths[name]))
    print("  {0}".format(paths["assets/universe.css"]))
    print("  {0}".format(paths["assets/universe.js"]))
    print("Open {0} in a browser. Live Data: Off · Scheduler: Off · Broker: Disabled.".format(
        paths["universe.html"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
