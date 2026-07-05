"""``python3 -m cosmosiq_service <start|stop|status|pause|resume|run-once>`` (IMPLEMENTATION-020C).

The OPERATOR-STARTED process. This module is the ONLY place in the service with a ``while`` +
``time.sleep`` supervised loop, and it runs ONLY because an operator explicitly started it -- it is
never imported by the tests, never auto-started on import, and never imported by
:mod:`reality_mesh`. The pure state logic lives in :mod:`cosmosiq_service.service`; this file is the
thin shell around it: argparse, the wall-clock boundary, the supervised loop, and the honest banner.

Commands:

* ``start``    -- acquire the single-instance lock and run the supervised loop (MANUAL, or
                  continuous SHADOW_24X7 which Phase-020D activated -- shadow alerts land in the
                  in-app inbox only, never escalated). Continuous PRODUCTION_24X7 stays gated to
                  Phase-020F and is REFUSED here. ``OFF`` runs nothing.
* ``stop``     -- release the single-instance lockfile (recover a crashed loop's lock).
* ``status``   -- print the sanitized health snapshot.
* ``pause``    -- journal ``paused_all`` (a paused service's ticks run nothing).
* ``resume``   -- lift the pause (an unexpired per-policy backoff still holds).
* ``run-once`` -- run exactly ONE supervised tick through the 015B orchestrator + 013 chain, exit.

Stdlib-only, Python 3.9. The wall clock is read HERE (the shell boundary) only; the CORE stays
clock-free (injected ``now``). No broker, no trading endpoint, execution stays a manual preview
(the 017 execution-manual slice); continuous production operation requires the Phase-020F gate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

from reality_mesh.orchestrator import subscription_from_dict
from reality_mesh.scheduler import DEFAULT_MARKET_HOURS, calendar_from_dict

from .service import (
    LockError,
    ServiceConfig,
    ServiceMode,
    acquire_lock,
    continuous_activation_gate,
    pause,
    read_lock,
    release_lock,
    requires_activation_gate,
    resume,
    run_once,
    service_status,
)

BANNER = (
    "CosmosIQ supervised operator service (Phase 020C) -- a LOCAL operator service, not a cloud "
    "daemon.\n"
    "  * local operator service: it runs only because you started it; there is no hosted daemon.\n"
    "  * scheduler tick only: each tick calls the accepted 015B one-tick orchestrator through the\n"
    "    full 013 chain (stores / ledger / health / DQ gates / replay) -- it never bypasses them.\n"
    "  * no broker: read-only evidence plus explicit manual actions; no trading endpoint exists.\n"
    "  * execution is a MANUAL PREVIEW only (the 017 execution-manual slice) -- nothing is sent.\n"
    "  * default mode is OFF; continuous SHADOW_24X7 is activated (Phase-020D, inbox-only alerts, "
    "no escalation); continuous PRODUCTION_24X7 operation still requires the Phase-020F activation "
    "gate and is refused until it passes.")


def wall_clock_now() -> str:
    """Wall-clock ``now`` -- read at the SHELL BOUNDARY ONLY, never inside the CORE."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_subscriptions(path: Optional[str]):
    """Load subscriptions + optional calendar / max_runs_per_hour from a local JSON file."""
    if not path:
        return (), DEFAULT_MARKET_HOURS, 60
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    subscriptions = tuple(subscription_from_dict(entry)
                          for entry in config.get("subscriptions", ()) or ())
    calendar = (calendar_from_dict(config["calendar"])
                if config.get("calendar") else DEFAULT_MARKET_HOURS)
    return subscriptions, calendar, int(config.get("max_runs_per_hour", 60))


def _build_config(args: argparse.Namespace) -> ServiceConfig:
    subscriptions, calendar, max_runs = _load_subscriptions(getattr(args, "subscriptions", None))
    return ServiceConfig(
        mode=ServiceMode.parse(args.mode),
        store_dir=args.store_dir,
        subscriptions=subscriptions,
        calendar=calendar,
        max_runs_per_hour=max_runs,
        max_pulses=args.max_pulses,
        poll_interval_seconds=args.poll_interval)


def _now_for(args: argparse.Namespace) -> str:
    """The injected ``--now`` if given, else the wall clock (read at this boundary only)."""
    return getattr(args, "now", None) or wall_clock_now()


# --------------------------------------------------------------------------- #
# start -- the supervised loop (the ONLY while + time.sleep in the service)      #
# --------------------------------------------------------------------------- #
def _supervise(config: ServiceConfig) -> int:
    """Run the supervised loop (MANUAL only). SHADOW_24X7 / PRODUCTION_24X7 continuous are gated."""
    if config.mode is ServiceMode.OFF:
        print("Service mode is OFF -- nothing to run continuously. Set --mode manual for the "
              "attended supervised loop, or use `run-once` for a single tick.")
        return 0
    if requires_activation_gate(config.mode):
        gate = continuous_activation_gate(config.mode)
        print("REFUSED: continuous {0} operation requires the {1} activation gate, which is not "
              "part of Phase-020C. This slice provides the machinery + safe defaults only. Use "
              "`run-once` to exercise a single tick.".format(config.mode.value, gate))
        return 2

    pid = os.getpid()
    try:
        handle = acquire_lock(config.lock_path, pid=pid, now=wall_clock_now(),
                              stale_after_seconds=config.lock_stale_seconds)
    except LockError as exc:
        print("REFUSED: {0}".format(exc))
        return 2

    print(BANNER)
    print("  supervised loop: MANUAL (attended) · poll every {0}s · Ctrl-C to stop · lock {1}"
          .format(config.poll_interval_seconds, config.lock_path))
    try:
        while True:                     # the ONE supervised loop -- __main__ only, never the CORE
            now = wall_clock_now()
            health = run_once(config, now=now, is_running=True, pid=pid)
            print("  tick {0}: mode={1} failures={2} last_ok={3}".format(
                now, health.service_mode, health.consecutive_failures,
                health.last_successful_run_id or "-"))
            time.sleep(config.poll_interval_seconds)    # the ONE sleep -- __main__ only
    except KeyboardInterrupt:
        print("\nCtrl-C received -- supervised service stopped.")
    finally:
        release_lock(handle)
    return 0


# --------------------------------------------------------------------------- #
# command handlers                                                              #
# --------------------------------------------------------------------------- #
def _cmd_start(args: argparse.Namespace) -> int:
    return _supervise(_build_config(args))


def _cmd_stop(args: argparse.Namespace) -> int:
    config = _build_config(args)
    lock = read_lock(config.lock_path)
    if lock is None:
        print("No service lock held at {0} -- nothing to stop.".format(config.lock_path))
        return 0
    try:
        os.remove(config.lock_path)
    except FileNotFoundError:
        pass
    print("Released service lock at {0} (was held by pid {1}). If a loop is still attached, stop "
          "that process (Ctrl-C).".format(config.lock_path, lock.get("pid", "?")))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    health = service_status(_build_config(args))
    print(json.dumps(health.to_dict(), sort_keys=True, indent=2))
    return 0


def _cmd_pause(args: argparse.Namespace) -> int:
    health = pause(_build_config(args), now=_now_for(args))
    print("Service paused (paused_all journaled). A paused service's ticks run nothing until "
          "resume. is_paused={0}".format(health.is_paused))
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    health = resume(_build_config(args), now=_now_for(args))
    print("Service resumed. An unexpired per-policy failure backoff still holds. is_paused={0}"
          .format(health.is_paused))
    return 0


def _cmd_run_once(args: argparse.Namespace) -> int:
    config = _build_config(args)
    health = run_once(config, now=_now_for(args), pid=os.getpid())
    print(BANNER)
    print("  one supervised tick -- mode={0}".format(health.service_mode))
    print(json.dumps(health.to_dict(), sort_keys=True, indent=2))
    print("One tick only -- exiting. Run this command again for the next tick.")
    return 0 if not health.last_error_class or health.last_successful_run_id else 0


# --------------------------------------------------------------------------- #
# argparse                                                                      #
# --------------------------------------------------------------------------- #
def _add_common(parser: argparse.ArgumentParser, *, needs_now: bool = False) -> None:
    parser.add_argument("--store-dir", required=True,
                        help="the append-only local store directory (013B/015 stores)")
    parser.add_argument("--mode", default=ServiceMode.OFF.value,
                        help="off | manual | shadow_24x7 | production_24x7 (default: off)")
    parser.add_argument("--subscriptions", default=None,
                        help="local JSON file of watchlist/theme subscriptions (the tick scope)")
    parser.add_argument("--max-pulses", type=int, default=1, dest="max_pulses",
                        help="at most this many pulse attempts per tick (default 1)")
    parser.add_argument("--poll-interval", type=int, default=60, dest="poll_interval",
                        help="supervised-loop poll cadence in seconds (start only; default 60)")
    if needs_now:
        parser.add_argument("--now", default=None,
                            help="injected ISO-8601 instant (default: the wall clock at start)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cosmosiq_service",
        description="CosmosIQ supervised operator service: a local, operator-started service that "
                    "calls the accepted 015B one-tick orchestrator. Default OFF; continuous "
                    "PRODUCTION_24X7 requires the Phase-020F gate.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="run the supervised loop (MANUAL only; SHADOW/PROD gated)")
    _add_common(start)
    start.set_defaults(func=_cmd_start)

    stop = sub.add_parser("stop", help="release the single-instance lockfile")
    _add_common(stop)
    stop.set_defaults(func=_cmd_stop)

    status = sub.add_parser("status", help="print the sanitized health snapshot")
    _add_common(status)
    status.set_defaults(func=_cmd_status)

    pause_p = sub.add_parser("pause", help="journal paused_all (ticks then run nothing)")
    _add_common(pause_p, needs_now=True)
    pause_p.set_defaults(func=_cmd_pause)

    resume_p = sub.add_parser("resume", help="lift the pause (backoff still holds)")
    _add_common(resume_p, needs_now=True)
    resume_p.set_defaults(func=_cmd_resume)

    once = sub.add_parser("run-once", help="run exactly ONE supervised tick, then exit")
    _add_common(once, needs_now=True)
    once.set_defaults(func=_cmd_run_once)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
