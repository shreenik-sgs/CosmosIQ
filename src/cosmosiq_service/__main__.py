"""``python3 -m cosmosiq_service <start|stop|status|pause|resume|run-once>`` (IMPLEMENTATION-020C).

The OPERATOR-STARTED process. This module is the ONLY place in the service with a ``while`` +
``time.sleep`` supervised loop, and it runs ONLY because an operator explicitly started it -- it is
never imported by the tests, never auto-started on import, and never imported by
:mod:`reality_mesh`. The pure state logic lives in :mod:`cosmosiq_service.service`; this file is the
thin shell around it: argparse, the wall-clock boundary, the supervised loop, and the honest banner.

Commands:

* ``start``    -- acquire the single-instance lock and run the supervised loop. MANUAL is the
                  attended loop; continuous SHADOW_24X7 runs ONLY on the explicit operator opt-in
                  (``--confirm-continuous-shadow``) -- inbox-only alerts, NO external delivery, NO
                  broker, NO orders. Without the opt-in ``start --mode shadow_24x7`` is REFUSED (safe
                  default). Continuous PRODUCTION_24X7 stays gated to Phase-020F and is ALWAYS REFUSED
                  here (never a launchd job). ``OFF`` runs nothing.
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
import signal
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
    continuous_shadow_allowed,
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


def _split_csv(value: Optional[str]):
    """Split a comma-separated CLI scope into a tuple of non-blank tokens ("" -> ())."""
    if not value:
        return ()
    return tuple(tok.strip() for tok in str(value).split(",") if tok.strip())


def _build_config(args: argparse.Namespace) -> ServiceConfig:
    subscriptions, calendar, max_runs = _load_subscriptions(getattr(args, "subscriptions", None))
    return ServiceConfig(
        mode=ServiceMode.parse(args.mode),
        store_dir=args.store_dir,
        subscriptions=subscriptions,
        calendar=calendar,
        max_runs_per_hour=max_runs,
        max_pulses=args.max_pulses,
        poll_interval_seconds=args.poll_interval,
        live_sources=bool(getattr(args, "live_sources", False)),
        live_watchlist=_split_csv(getattr(args, "live_watchlist", None)),
        live_themes=_split_csv(getattr(args, "live_themes", None)),
        live_use_accepted_watchlist=bool(getattr(args, "live_accepted_watchlist", False)),
        live_include_price_fallback=bool(getattr(args, "live_price_fallback", False)))


def _now_for(args: argparse.Namespace) -> str:
    """The injected ``--now`` if given, else the wall clock (read at this boundary only)."""
    return getattr(args, "now", None) or wall_clock_now()


# --------------------------------------------------------------------------- #
# start -- the supervised loop (the ONLY while + time.sleep in the service)      #
# --------------------------------------------------------------------------- #
def _pre_loop_decision(config: ServiceConfig, *,
                       operator_opt_in_continuous_shadow: bool):
    """The loop-free ``start`` policy gate. ``None`` => enter the supervised loop; ``(code, message)``
    => print ``message`` and return ``code`` (never entering the loop).

    Pure and while-loop-free so it is unit-testable WITHOUT the supervised loop. The policy:

    * ``OFF`` -> ``(0, no-op message)`` -- nothing runs continuously (safe default, unchanged).
    * continuous ``PRODUCTION_24X7`` -> ALWAYS ``(2, gate refusal)`` regardless of any opt-in flag;
      continuous production is never launched here -- it is the explicit ``cosmosiq_ops activate`` +
      operator sign-off path (Phase-020F). :func:`requires_activation_gate` semantics are unchanged.
    * continuous ``SHADOW_24X7`` -> permitted (``None``) ONLY on the EXPLICIT operator opt-in
      (``--confirm-continuous-shadow``); without it ``(2, opt-in-required refusal)`` -- the safe
      default still refuses. Shadow stays inbox-only: no external delivery, no broker, no orders.
    * ``MANUAL`` -> ``None`` (the attended supervised loop, unchanged).
    """
    if config.mode is ServiceMode.OFF:
        return 0, ("Service mode is OFF -- nothing to run continuously. Set --mode manual for the "
                   "attended supervised loop, or use `run-once` for a single tick.")
    # Continuous PRODUCTION stays gated + refused -- NO flag can start it here.
    if requires_activation_gate(config.mode):
        gate = continuous_activation_gate(config.mode)
        return 2, ("REFUSED: continuous {0} operation requires the {1} activation gate and is never "
                   "launched here -- continuous production is the explicit `cosmosiq_ops activate` + "
                   "operator sign-off path, never a launchd job. Use `run-once` to exercise a "
                   "single tick.".format(config.mode.value, gate))
    # Continuous SHADOW is safe (inbox-only) but requires the EXPLICIT operator opt-in.
    if config.mode is ServiceMode.SHADOW_24X7 and not continuous_shadow_allowed(
            config.mode, operator_opt_in=operator_opt_in_continuous_shadow):
        return 2, ("REFUSED: continuous shadow_24x7 operation requires the EXPLICIT operator opt-in "
                   "--confirm-continuous-shadow (the safe default refuses). Continuous SHADOW is "
                   "inbox-only -- NO external delivery, NO broker, NO orders; production is never "
                   "launched here. Pass --confirm-continuous-shadow to start the paper/observation "
                   "window, or use `run-once` for a single tick.")
    return None


def _raise_keyboard_interrupt(signum, frame):
    """SIGTERM -> KeyboardInterrupt, so a supervisor stop unwinds through the loop's `finally`."""
    raise KeyboardInterrupt


def _supervise(config: ServiceConfig, *,
               operator_opt_in_continuous_shadow: bool = False) -> int:
    """Run the supervised loop. MANUAL is the attended loop; continuous SHADOW_24X7 runs ONLY on the
    explicit operator opt-in (inbox-only, no external delivery/broker/orders); continuous
    PRODUCTION_24X7 is always refused (the promotion-gated path, never launched here)."""
    decision = _pre_loop_decision(
        config, operator_opt_in_continuous_shadow=operator_opt_in_continuous_shadow)
    if decision is not None:
        code, message = decision
        print(message)
        return code

    pid = os.getpid()
    try:
        handle = acquire_lock(config.lock_path, pid=pid, now=wall_clock_now(),
                              stale_after_seconds=config.lock_stale_seconds)
    except LockError as exc:
        print("REFUSED: {0}".format(exc))
        return 2

    print(BANNER)
    if config.mode is ServiceMode.SHADOW_24X7:
        print("  supervised loop: SHADOW_24X7 (operator opt-in --confirm-continuous-shadow) -- "
              "inbox-only alerts, NO external delivery, NO broker, NO orders; production is never "
              "launched here.")
        print("  · poll every {0}s · Ctrl-C to stop · lock {1}"
              .format(config.poll_interval_seconds, config.lock_path))
    else:
        print("  supervised loop: MANUAL (attended) · poll every {0}s · Ctrl-C to stop · lock {1}"
              .format(config.poll_interval_seconds, config.lock_path))
    # A supervisor (launchd/systemd) STOPS this process with SIGTERM, which by default kills the
    # interpreter WITHOUT unwinding -- the `finally` below would never run and the lockfile would
    # be orphaned holding a dead pid. A restart inside `lock_stale_seconds` would then be REFUSED
    # against that orphan and crash-loop under KeepAlive. Route SIGTERM into the same
    # KeyboardInterrupt path Ctrl-C already uses so the lock is always released on the way out.
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    try:
        while True:                     # the ONE supervised loop -- __main__ only, never the CORE
            now = wall_clock_now()
            health = run_once(config, now=now, is_running=True, pid=pid,
                              lock_handle=handle)
            print("  tick {0}: mode={1} failures={2} last_ok={3}".format(
                now, health.service_mode, health.consecutive_failures,
                health.last_successful_run_id or "-"))
            time.sleep(config.poll_interval_seconds)    # the ONE sleep -- __main__ only
    except KeyboardInterrupt:
        print("\nstop signal received (Ctrl-C / SIGTERM) -- supervised service stopped, lock released.")
    finally:
        release_lock(handle)
    return 0


# --------------------------------------------------------------------------- #
# command handlers                                                              #
# --------------------------------------------------------------------------- #
def _cmd_start(args: argparse.Namespace) -> int:
    return _supervise(
        _build_config(args),
        operator_opt_in_continuous_shadow=bool(
            getattr(args, "confirm_continuous_shadow", False)))


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
    # -- GO-LIVE PL-4: opt-in LIVE sourcing (default OFF -> the fixture path is byte-identical). --
    # Shadow-with-live-sources is what accumulates the HONEST paper window: a SHADOW_24X7 tick runs
    # the credential-gated LIVE pulse (real SEC/FMP evidence from SEC_USER_AGENT / FMP_API_KEY
    # PRESENCE, no fixture fallback, honest gap when creds are absent) instead of the fixture pulse.
    parser.add_argument("--live-sources", action="store_true", dest="live_sources",
                        help="opt in to REAL live sourcing (SHADOW_24X7 / MANUAL only): each tick "
                             "runs the credential-gated LIVE pulse (real SEC/FMP evidence, no "
                             "fixture fallback; honest gap if no credentials). Default OFF.")
    parser.add_argument("--live-watchlist", default=None, dest="live_watchlist",
                        help="comma-separated tickers for the live pulse scope (with --live-sources)")
    parser.add_argument("--live-themes", default=None, dest="live_themes",
                        help="comma-separated themes for the live pulse scope (with --live-sources)")
    parser.add_argument("--live-accepted-watchlist", action="store_true",
                        dest="live_accepted_watchlist",
                        help="use the accepted-universe watchlist from the store as the live scope")
    parser.add_argument("--live-price-fallback", action="store_true", dest="live_price_fallback",
                        help="also append the credential-free Yahoo price-history fallback adapter")
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

    start = sub.add_parser(
        "start",
        help="run the supervised loop (MANUAL; continuous SHADOW_24X7 with the explicit opt-in; "
             "PRODUCTION_24X7 always refused)")
    _add_common(start)
    # GO-LIVE PL-5: the EXPLICIT operator opt-in for CONTINUOUS SHADOW_24X7. Default False -> the
    # safe default still REFUSES `start --mode shadow_24x7`. It is inbox-only (no external delivery,
    # no broker, no orders); no flag can start continuous production.
    start.add_argument("--confirm-continuous-shadow", action="store_true",
                       dest="confirm_continuous_shadow",
                       help="explicit operator opt-in to run CONTINUOUS SHADOW_24X7 (paper/"
                            "observation window): inbox-only alerts, no external delivery, no "
                            "broker, no orders. Without this flag `start --mode shadow_24x7` is "
                            "refused (safe default). Never starts production.")
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
