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
    parser.add_argument(
        "--persist-dir", default=None,
        help="OPT-IN (IMPLEMENTATION-013F, default OFF): also persist this run into append-only "
             "JSONL stores under this local directory, verify it replays deterministically, and "
             "render the run-observability panel into the Data-Quality page. Local files only -- "
             "no network, no scheduler, no broker.")
    parser.add_argument(
        "--run-id", default=None,
        help="optional stable run id for --persist-dir (default: derived deterministically from "
             "the watchlist + themes). Re-persisting the same run id into the same store dir "
             "appends new history (stores are append-only) -- use a fresh id per persisted run.")
    parser.add_argument(
        "--scheduled-tick", action="store_true", default=False,
        help="OPT-IN (IMPLEMENTATION-015B, default OFF): run exactly ONE synchronous scheduled "
             "tick and exit -- ask the 015A cadence core what is due at --tick-now, run each due "
             "policy's subscribed pulse through the full 013 chain, journal the schedule state, "
             "print what ran/was skipped and why, and STOP. Explicitly started, never a daemon: "
             "no loop, no waiting, no background anything. Requires --persist-dir, --tick-now "
             "and --subscriptions. Offline; still no live data, no broker, no orders.")
    parser.add_argument(
        "--subscriptions", default=None,
        help="for --scheduled-tick: a local JSON file of watchlist/theme subscriptions "
             "(subscription_id / watchlist / themes / policy_ids [/ data_dir]; optional "
             "'calendar' and 'max_runs_per_hour' keys). Labels and local paths only -- "
             "no secrets, no endpoints.")
    parser.add_argument(
        "--tick-now", default=None,
        help="for --scheduled-tick: the injected ISO-8601 instant the tick decides at "
             "(e.g. 2026-06-29T15:00:00Z). REQUIRED -- the wall clock is never read.")
    parser.add_argument(
        "--max-pulses", type=int, default=1,
        help="for --scheduled-tick: at most this many pulse attempts in the one tick "
             "(default 1). Remaining due policies wait for the next explicit tick.")
    parser.add_argument(
        "--pause-policy", default=None, metavar="POLICY_ID|all",
        help="OPT-IN operator control (IMPLEMENTATION-015C): pause one cadence policy (or "
             "'all') and journal the new schedule state, then exit. One-shot, offline. "
             "Requires --persist-dir and --tick-now (the injected instant journaled; the "
             "wall clock is never read). Nothing runs while paused.")
    parser.add_argument(
        "--resume-policy", default=None, metavar="POLICY_ID|all",
        help="OPT-IN operator control (015C): resume one cadence policy (or 'all') and "
             "journal the new schedule state, then exit. One-shot, offline. Requires "
             "--persist-dir and --tick-now. Resume lifts the pause only -- an unexpired "
             "failure backoff still applies.")
    parser.add_argument(
        "--ack-alert", default=None, metavar="ALERT_ID",
        help="OPT-IN operator control (015C): acknowledge one alert by APPENDING a new "
             "acknowledgment record referencing it (the alert line itself is never "
             "edited), then exit. One-shot, offline. Requires --persist-dir and "
             "--tick-now.")
    parser.add_argument(
        "--list-alerts", action="store_true", default=False,
        help="OPT-IN operator control (015C): print the persisted alert inbox (severity "
             "label, category, plain-English reason, acknowledged/open), then exit. "
             "One-shot, offline, read-only. Requires --persist-dir.")
    args = parser.parse_args(argv)

    # 015C OPT-IN operator controls: each is ONE offline action, then exit. They branch
    # BEFORE the manual-pulse argument checks so the default CLI path stays byte-identical
    # when no control flag is passed. Exactly one control per invocation -- honest and
    # unambiguous.
    controls = [name for name, value in (
        ("--pause-policy", args.pause_policy),
        ("--resume-policy", args.resume_policy),
        ("--ack-alert", args.ack_alert),
        ("--list-alerts", args.list_alerts),
    ) if value]
    if controls:
        if len(controls) > 1 or args.scheduled_tick:
            parser.error("operator controls are one-shot: pass exactly ONE of "
                         "--pause-policy / --resume-policy / --ack-alert / --list-alerts "
                         "(and not together with --scheduled-tick)")
        return _run_operator_control(args, parser)

    # 015B OPT-IN: one scheduled tick, then exit. Branches BEFORE the manual-pulse argument
    # checks so the default CLI path below stays byte-identical when the flag is absent.
    if args.scheduled_tick:
        return _run_scheduled_tick(args, parser)

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

    # 013F OPT-IN persistence: only when --persist-dir is explicitly passed (default OFF -- the
    # CLI output and pages stay byte-identical without it). Persists the run into append-only
    # local stores, verifies a deterministic replay, and renders the observability panel.
    pulse_run = replay_result = None
    run_observability_html = ""
    if args.persist_dir:
        import hashlib

        from reality_mesh.pulse_persistence import persist_and_summarize

        run_id = args.run_id or "pulse-{0}".format(hashlib.md5(
            ("|".join(result.watchlist) + "||" + "|".join(result.themes)).encode(
                "utf-8")).hexdigest()[:12])
        pulse_run, replay_result, run_observability_html = persist_and_summarize(
            result, store_dir=args.persist_dir, run_id=run_id)

    # Render the produced signals / clusters / theme pulses into the Economic Universe Data-Quality
    # page as EVIDENCE (012J panel). Demo mode + the opt-in pulse args only -- the demo default
    # stays byte-identical when no pulse args are passed. No network, no scheduler, no broker.
    paths = build_universe_app(
        args.out, mode="demo",
        pulse_signals=result.signals,
        signal_clusters=result.clusters,
        theme_pulses=result.theme_pulses,
        pulse_authority_by_signal=result.authority_by_signal,
        run_observability_html=run_observability_html)

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
    if pulse_run is not None and replay_result is not None:
        print("  run persisted · replayable (deterministic_match: {0})".format(
            replay_result.deterministic_match))
        print("    run_id: {0} · stores (append-only JSONL): {1}".format(
            pulse_run.run_id, args.persist_dir))
    print("Outputs written under {0}:".format(args.out))
    for name in PAGE_ORDER:
        print("  {0}".format(paths[name]))
    print("  {0}".format(paths["pulse_summary.json"]))
    print("Open {0} -> Data Quality for the reality-signal evidence panel.".format(
        paths["universe.html"]))
    print("Live data / scheduler / broker / orders: NOT enabled.")
    return 0


def _run_scheduled_tick(args, parser) -> int:
    """Run exactly ONE scheduled tick (IMPLEMENTATION-015B) and exit. Never a daemon.

    Loads the subscriptions JSON, resumes the journaled schedule state from --persist-dir (or
    starts from the accepted default cadence policies), runs ONE synchronous
    :func:`reality_mesh.orchestrator.run_due_pulses` pass at the injected --tick-now, prints
    what ran / failed / was skipped and WHY (throttled / backoff / market closed / paused /
    interval / no subscription -- all named), and returns 0. The next tick happens only when
    the operator runs this command again.
    """
    from reality_mesh.orchestrator import (
        load_schedule_state,
        run_due_pulses,
        subscription_from_dict,
    )
    from reality_mesh.scheduler import (
        DEFAULT_MARKET_HOURS,
        build_default_schedule,
        calendar_from_dict,
    )

    if not args.persist_dir:
        parser.error("--scheduled-tick requires --persist-dir (the append-only local store "
                     "directory the tick persists into)")
    if not args.tick_now:
        parser.error("--scheduled-tick requires --tick-now (an injected ISO-8601 instant; "
                     "the wall clock is never read)")
    if not args.subscriptions:
        parser.error("--scheduled-tick requires --subscriptions (a local JSON file of "
                     "watchlist/theme subscriptions; nothing runs without an explicit scope)")

    with open(args.subscriptions, encoding="utf-8") as fh:
        config = json.load(fh)
    subscriptions = tuple(subscription_from_dict(entry)
                          for entry in config.get("subscriptions", ()) or ())
    calendar = (calendar_from_dict(config["calendar"])
                if config.get("calendar") else DEFAULT_MARKET_HOURS)

    schedule = load_schedule_state(args.persist_dir)
    resumed = schedule is not None
    if schedule is None:
        schedule = build_default_schedule(
            max_runs_per_hour=int(config.get("max_runs_per_hour", 60)))

    print("ONE scheduled tick (015B) · explicitly started by the operator · not a daemon · "
          "no loop · offline · fixture/local-file backed · no live data, no broker, no orders.")
    print("  tick instant (injected): {0}".format(args.tick_now))
    print("  schedule state: {0}".format(
        "resumed from journal" if resumed else "fresh default cadence policies"))
    print("  subscriptions: {0}".format(
        ", ".join(s.subscription_id for s in subscriptions) or "none"))

    result = run_due_pulses(
        schedule, now=args.tick_now, store_dir=args.persist_dir,
        subscriptions=subscriptions, calendar=calendar, max_pulses=args.max_pulses,
        fixture_dir=args.fixture_dir)

    print("  ran ({0}):".format(len(result.ran)))
    for line in result.ran:
        print("    - {0}".format(line))
    if result.failed:
        print("  failed ({0}) -- recorded honestly (backoff + health), tick not aborted:"
              .format(len(result.failed)))
        for line in result.failed:
            print("    - {0}".format(line))
    print("  skipped ({0}) -- with reasons:".format(len(result.skipped)))
    for line in result.skipped:
        print("    - {0}".format(line))
    for line in result.notes:
        print("  note: {0}".format(line))
    if result.alerts:
        print("  alerts ({0}) -- observations only, nothing acts on them; read with "
              "--list-alerts, acknowledge with --ack-alert:".format(len(result.alerts)))
        for alert in result.alerts:
            print("    - [{0}] {1}: {2}".format(
                alert.severity, alert.category, alert.human_readable_reason))
    print("  schedule state appended (append-only journal): {0}".format(
        os.path.join(args.persist_dir, "schedule_state_store.jsonl")))
    print("One tick only -- exiting. Run this command again for the next tick. "
          "Streaming / auto-trading: NOT enabled.")
    return 0


def _run_operator_control(args, parser) -> int:
    """Run exactly ONE offline operator control (IMPLEMENTATION-015C) and exit.

    ``--pause-policy`` / ``--resume-policy`` journal the NEW schedule state (append-style:
    a new JSONL line, prior lines byte-unchanged). ``--ack-alert`` APPENDS an acknowledgment
    record referencing the alert (the alert line itself is never edited). ``--list-alerts``
    is read-only. Every action prints honestly what it did and nothing keeps running.
    """
    from reality_mesh.alerts import acknowledge_alert, alerts_with_status
    from reality_mesh.orchestrator import append_schedule_state, load_schedule_state
    from reality_mesh.scheduler import build_default_schedule
    from reality_mesh.scheduler import pause as pause_schedule
    from reality_mesh.scheduler import resume as resume_schedule

    if not args.persist_dir:
        parser.error("operator controls require --persist-dir (the local append-only "
                     "store directory they read from / journal into)")

    # ---- --list-alerts: read-only inbox print ------------------------------------------- #
    if args.list_alerts:
        entries = alerts_with_status(args.persist_dir)
        print("Alert inbox (015C) · append-only · offline · alerts OBSERVE, nothing acts "
              "on them.")
        if not entries:
            print("  no alerts recorded in {0} -- an unchanged reality stays quiet.".format(
                args.persist_dir))
        else:
            open_count = sum(1 for a in entries if not a.acknowledged)
            print("  {0} alert(s): {1} open · {2} acknowledged".format(
                len(entries), open_count, len(entries) - open_count))
            for alert in entries:
                print("  - [{0}] {1} · run {2} · {3}".format(
                    alert.severity, alert.category, alert.run_id,
                    "acknowledged" if alert.acknowledged else "open"))
                print("      id: {0}".format(alert.alert_id))
                print("      reason: {0}".format(alert.human_readable_reason))
        print("One-shot action -- exiting. Acknowledge with --ack-alert <id>; nothing "
              "runs by itself.")
        return 0

    # The mutating controls journal an injected instant -- the wall clock is never read.
    if not args.tick_now:
        parser.error("--pause-policy / --resume-policy / --ack-alert require --tick-now "
                     "(an injected ISO-8601 instant; the wall clock is never read)")

    # ---- --ack-alert: a NEW acknowledgment record, never a mutation ---------------------- #
    if args.ack_alert:
        try:
            ack_id = acknowledge_alert(args.persist_dir, args.ack_alert, at=args.tick_now)
        except ValueError as exc:
            parser.error(str(exc))
        print("Alert acknowledged (015C) · append-only · offline.")
        print("  alert: {0}".format(args.ack_alert))
        print("  acknowledgment record APPENDED: {0} (a NEW record referencing the alert; "
              "the original alert line is byte-unchanged)".format(ack_id))
        print("  store: {0}".format(os.path.join(args.persist_dir,
                                                 "alert_ack_store.jsonl")))
        print("One-shot action -- exiting. Nothing runs by itself.")
        return 0

    # ---- --pause-policy / --resume-policy: journal the NEW schedule state ---------------- #
    pausing = args.pause_policy is not None
    target = args.pause_policy if pausing else args.resume_policy
    schedule = load_schedule_state(args.persist_dir)
    resumed_from_journal = schedule is not None
    if schedule is None:
        schedule = build_default_schedule()
    try:
        new_schedule = (pause_schedule if pausing else resume_schedule)(
            schedule, target, args.tick_now)
    except ValueError as exc:
        parser.error(str(exc))
    verb = "paused" if pausing else "resumed"
    append_schedule_state(
        args.persist_dir, new_schedule, now=args.tick_now,
        note="operator {0} policy {1} (015C operator control)".format(verb, target))
    print("Schedule {0} (015C operator control) · one-shot · offline · journaled.".format(
        verb))
    print("  schedule state: {0}".format(
        "resumed from journal" if resumed_from_journal
        else "fresh default cadence policies (nothing journaled before this)"))
    print("  target: {0}".format("ALL policies" if target == "all" else target))
    if pausing:
        print("  effect: {0} will not run until resumed (--resume-policy).".format(
            "no policy" if target == "all" else "policy {0}".format(target)))
    else:
        print("  effect: {0} may run again when due. Resume lifts the pause only -- an "
              "unexpired failure backoff still applies.".format(
                  "every policy" if target == "all" else "policy {0}".format(target)))
    print("  new state APPENDED to the journal (prior lines byte-unchanged): {0}".format(
        os.path.join(args.persist_dir, "schedule_state_store.jsonl")))
    print("One-shot action -- exiting. Nothing runs by itself; the next tick happens only "
          "when an operator runs --scheduled-tick.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
