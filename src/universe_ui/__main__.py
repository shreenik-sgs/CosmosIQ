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
    args = parser.parse_args(argv)

    paths = build_universe_app(args.out)
    print("Built Sudarshan Economic Universe UI (read-only, fixture/demo):")
    for name in PAGE_ORDER:
        print("  {0}".format(paths[name]))
    print("  {0}".format(paths["assets/universe.css"]))
    print("  {0}".format(paths["assets/universe.js"]))
    print("Open {0} in a browser. Live data / scheduler / broker: not enabled.".format(
        paths["universe.html"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
