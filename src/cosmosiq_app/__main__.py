"""Operator entry point: ``python3 -m cosmosiq_app --store-dir ... [--port N]``.

Argparse + start, nothing else. The server shell (:mod:`cosmosiq_app.server`) binds
127.0.0.1 by default, refuses a non-local host without an explicit ``--allow-remote``,
prints its honest banner, and serves until Ctrl-C. Nothing here (or anywhere else) starts
this process automatically -- an operator does, every time.
"""

from __future__ import annotations

import argparse
from typing import List, Optional

from .server import DEFAULT_HOST, DEFAULT_PORT, serve


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cosmosiq_app",
        description="CosmosIQ local operator app: an operator-started, localhost-only shell "
                    "over the pure dispatcher. Read-only evidence plus explicit manual "
                    "actions; no scheduler daemon, no broker, no trading endpoint.")
    parser.add_argument(
        "--store-dir", required=True,
        help="the local append-only JSONL store directory (the 013B/015 stores; keep it out "
             "of Git, e.g. generated/pulse_store)")
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help="bind host (default {0}; non-local values are refused without "
             "--allow-remote)".format(DEFAULT_HOST))
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help="bind port (default {0})".format(DEFAULT_PORT))
    parser.add_argument(
        "--allow-remote", action="store_true",
        help="explicitly allow binding a non-local host (prints a warning; CosmosIQ has no "
             "authentication -- prefer the localhost default)")
    args = parser.parse_args(argv)
    serve(args.store_dir, host=args.host, port=args.port, allow_remote=args.allow_remote)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
