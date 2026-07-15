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
    if args and args[0] == "accept-diligence":
        return _accept_diligence(args[1:])
    if args and args[0] == "accept-universe":
        return _accept_universe(args[1:])
    if args and args[0] == "attest-live-source":
        return _attest_live_source(args[1:])
    if args and args[0] == "attest-shadow-validation":
        return _attest_shadow_validation(args[1:])
    if "--live" in args:
        return _run_live(args)
    from tattva_pulse.__main__ import main as _main
    return _main(args)


def _accept_diligence(argv) -> int:
    """RECORD one OPERATOR-accepted diligence thesis into a store (headless). Never auto-accepts.

    The command-line twin of the Opportunities 'Record your diligence review' form: it calls
    :func:`reality_mesh.accept_diligence_thesis` -- the ONLY path that creates an eligibility-valid
    diligence ref -- with the OPERATOR's own verdict / written thesis / key risks / reviewed
    evidence ids / name. It NEVER auto-generates or auto-fills a field, makes NO network / broker
    call, and submits no orders. On a validation failure it prints the honest reason and exits
    non-zero, writing nothing.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="cosmosiq_pulse accept-diligence",
        description=("RECORD one OPERATOR-accepted investment-diligence thesis (the human review "
                     "conclusion) into a local store. The engine never generates or accepts a "
                     "thesis on its own; only a thesis_supported verdict can advance a candidate "
                     "toward eligible. Append-only, offline, no broker, no orders."))
    parser.add_argument("--store-dir", required=True,
                        help="the local append-only store the run + evidence live in (the cockpit "
                             "store, e.g. reports/cockpit_live_store).")
    parser.add_argument("--ticker", required=True, help="the candidate ticker being reviewed.")
    parser.add_argument("--run-id", required=True,
                        help="the run whose evidence you reviewed (its hypothesis must resolve).")
    parser.add_argument("--hypothesis-ref", required=True,
                        help="the REAL opportunity-hypothesis packet id this thesis addresses; a "
                             "free string that does not resolve is refused.")
    parser.add_argument("--verdict", required=True,
                        choices=("thesis_supported", "thesis_rejected", "insufficient"),
                        help="your closed conclusion; only thesis_supported advances eligibility.")
    parser.add_argument("--thesis", required=True,
                        help="your written conclusion (the operator authors it).")
    parser.add_argument("--evidence-refs", required=True,
                        help="comma-separated REAL signal/event/finding ids you reviewed; must be "
                             "non-empty and resolve in the run's stores.")
    parser.add_argument("--accepted-by", required=True,
                        help="who is accepting this (your operator label).")
    parser.add_argument("--key-risks", default="",
                        help="comma-separated risks you see (optional).")
    parser.add_argument("--correction-of", default="",
                        help="id of a prior thesis this record supersedes (a correction, never a "
                             "mutation; optional).")
    parser.add_argument("--now", default=None,
                        help="injected ISO-8601 instant (default: the wall clock, read ONCE here "
                             "at the shell boundary).")
    args = parser.parse_args(argv)

    now = args.now
    if not now:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    from reality_mesh import accept_diligence_thesis

    def _split(text):
        return tuple(s.strip() for s in str(text or "").split(",") if s.strip())

    print("RECORD one operator-accepted diligence thesis · manual review only · CosmosIQ records "
          "it, never generates it · no broker, no orders.")
    try:
        diligence = accept_diligence_thesis(
            args.store_dir,
            ticker=args.ticker, run_id=args.run_id,
            opportunity_hypothesis_ref=args.hypothesis_ref,
            verdict=args.verdict, thesis=args.thesis,
            key_risks=_split(args.key_risks),
            evidence_refs=_split(args.evidence_refs),
            accepted_by=args.accepted_by, now=now,
            correction_of=args.correction_of)
    except (ValueError, TypeError) as exc:
        print("  REFUSED (nothing written): {0}".format(exc))
        return 1

    print("  recorded diligence_id={0} · ticker={1} · verdict={2} · accepted_by={3}".format(
        diligence.diligence_id, diligence.ticker, diligence.verdict, diligence.accepted_by))
    if diligence.is_eligibility_valid:
        print("  verdict is thesis_supported -- with healthy DQ the candidate now reads eligible "
              "in the lineage (a real, evidence-grounded, operator-accepted ref).")
    else:
        print("  verdict is not thesis_supported -- recorded honestly; the candidate stays "
              "ineligible_missing_diligence (never eligible).")
    return 0


def _accept_universe(argv) -> int:
    """ACCEPT one ticker into the operator's universe (headless, UD-3). Never auto-accepts.

    The command-line twin of the Universe 'Accept into universe' form: it calls
    :func:`reality_mesh.accept_universe_entry` -- the ONLY producer of an accepted entry -- with the
    OPERATOR's own theme / name / grounding reference(s) / note. Acceptance is REFUSED (non-zero
    exit, nothing written) unless the entry is GROUNDED: real UD-1 provenance
    (``sec:fts/`` / ``sec:cik/`` / ``fmp:screener/``) in ``--grounding-refs``, OR
    ``--origin operator_manual`` with an explicit operator evidence ref, OR (when no refs are given)
    a live UD-1 grounding call. The derived authority is HONEST (SEC -> canonical, screener ->
    convenience, operator -> manual) -- never ai_suggestion, never canonical unless SEC-grounded.
    Append-only, no broker, no orders; the theme graph / pulse / lineage are not touched.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="cosmosiq_pulse accept-universe",
        description=("ACCEPT one ticker into the operator's investment universe. Only a GROUNDED "
                     "entry can be accepted; an unverified AI suggestion is refused. The engine "
                     "never accepts on its own. Append-only, offline, no broker, no orders."))
    parser.add_argument("--store-dir", required=True,
                        help="the local append-only store the universe log lives in.")
    parser.add_argument("--ticker", required=True, help="the ticker to accept into the universe.")
    parser.add_argument("--theme-id", required=True,
                        help="the theme id you are filing the ticker under.")
    parser.add_argument("--theme-label", required=True, help="the human-facing theme name.")
    parser.add_argument("--accepted-by", required=True,
                        help="who is accepting this (your operator label).")
    parser.add_argument("--grounding-refs", default="",
                        help="comma-separated REAL grounding reference(s): sec:fts/... / sec:cik/... "
                             "/ fmp:screener/... (or, with --origin operator_manual, your own "
                             "evidence ref). Empty triggers a live UD-1 grounding call.")
    parser.add_argument("--origin", default="evidence_discovery",
                        choices=("evidence_discovery", "ai_suggestion_grounded", "operator_manual"),
                        help="how the lead reached you; ai_suggestion_grounded records that an AI "
                             "lead was GROUNDED, not taken on faith.")
    parser.add_argument("--verdict", default="accepted", choices=("accepted", "rejected"),
                        help="your closed decision; only 'accepted' enters the working universe.")
    parser.add_argument("--note", default="", help="an optional operator note.")
    parser.add_argument("--correction-of", default="",
                        help="id of a prior entry this record supersedes (a correction, never a "
                             "mutation; optional).")
    parser.add_argument("--now", default=None,
                        help="injected ISO-8601 instant (default: the wall clock, read ONCE here "
                             "at the shell boundary).")
    args = parser.parse_args(argv)

    now = args.now
    if not now:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    from reality_mesh import accept_universe_entry

    def _split(text):
        return tuple(s.strip() for s in str(text or "").split(",") if s.strip())

    print("ACCEPT one ticker into your universe · manual review only · CosmosIQ records it, never "
          "accepts it for you · grounded against SEC / FMP first · no broker, no orders.")
    try:
        entry = accept_universe_entry(
            args.store_dir,
            ticker=args.ticker, theme_id=args.theme_id, theme_label=args.theme_label,
            accepted_by=args.accepted_by, now=now,
            grounding_refs=_split(args.grounding_refs),
            origin=args.origin, verdict=args.verdict, note=args.note,
            correction_of=args.correction_of)
    except (ValueError, TypeError) as exc:
        print("  REFUSED (nothing written): {0}".format(exc))
        return 1

    print("  accepted entry_id={0} · ticker={1} · theme={2} · authority={3} · origin={4} · "
          "accepted_by={5}".format(entry.entry_id, entry.ticker, entry.theme_id,
                                    entry.source_authority, entry.origin, entry.accepted_by))
    print("  grounded by: {0} · provenance: {1}".format(
        entry.grounded_by, ", ".join(entry.source_refs)))
    if entry.verdict == "accepted":
        print("  the ticker is now in your working universe (a grounded, operator-accepted entry).")
    else:
        print("  recorded honestly as rejected -- the ticker is NOT in your working universe.")
    return 0


def _attest_live_source(argv) -> int:
    """RECORD one OPERATOR live-source-health attestation (GO-LIVE PL-2). Never auto-attests.

    The headless twin of the operator reviewing a REAL live run's source health and attesting it.
    It calls :func:`cosmosiq_ops.operator_attestation.record_live_source_health_attestation`, which
    REFUSES (non-zero exit, nothing written) unless the named ``--run-id`` is a REAL persisted run.
    Recording an attestation does NOT clear the 020F item on its own: an independent verifier
    re-reads the persisted run/events and confirms the sources actually reported healthy + fresh;
    a false / unbacked / stale attestation leaves live_source_health BLOCKING. No broker / orders.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="cosmosiq_pulse attest-live-source",
        description=("RECORD one operator attestation that a REAL live run's sources are healthy. "
                     "The engine never attests on its own; an attestation clears the 020F "
                     "live_source_health item only if an independent verifier confirms the real "
                     "persisted evidence backs it. Append-only, offline, no broker, no orders."))
    parser.add_argument("--store-dir", required=True,
                        help="the local append-only store the live run + attestation live in.")
    parser.add_argument("--run-id", required=True,
                        help="the REAL persisted live run you reviewed (must exist in the store).")
    parser.add_argument("--sources", required=True,
                        help="comma-separated live adapter ids you confirm healthy, e.g. "
                             "evidence.sec_edgar_live,evidence.fmp_live.")
    parser.add_argument("--reviewed-by", required=True,
                        help="who reviewed this (your operator label).")
    parser.add_argument("--statement", default="", help="an optional operator note.")
    parser.add_argument("--correction-of", default="",
                        help="id of a prior attestation this record supersedes (a correction, "
                             "never a mutation; optional).")
    parser.add_argument("--now", default=None,
                        help="injected ISO-8601 instant (default: the wall clock, read ONCE here "
                             "at the shell boundary).")
    args = parser.parse_args(argv)

    now = args.now
    if not now:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    from cosmosiq_ops.operator_attestation import record_live_source_health_attestation

    def _split(text):
        return tuple(s.strip() for s in str(text or "").split(",") if s.strip())

    print("RECORD one operator live-source-health attestation · manual review only · CosmosIQ "
          "records it, never attests for you · an independent verifier confirms it · no broker, "
          "no orders.")
    try:
        attestation = record_live_source_health_attestation(
            args.store_dir, run_id=args.run_id, sources_reviewed=_split(args.sources),
            reviewed_by=args.reviewed_by, reviewed_at=now, statement=args.statement,
            correction_of=args.correction_of)
    except (ValueError, TypeError) as exc:
        print("  REFUSED (nothing written): {0}".format(exc))
        return 1

    print("  recorded attestation_id={0} · run_id={1} · sources={2} · reviewed_by={3}".format(
        attestation.attestation_id, attestation.run_id,
        ", ".join(attestation.sources_reviewed), attestation.reviewed_by))
    print("  the attestation is RECORDED; live_source_health clears ONLY if an independent verifier "
          "confirms the real persisted run/events back it (healthy + fresh).")
    return 0


def _attest_shadow_validation(argv) -> int:
    """RECORD one OPERATOR shadow-validation attestation (GO-LIVE PL-2). Never auto-attests.

    The headless twin of the operator reviewing a REAL shadow / paper observation window (several
    persisted runs over real calendar days) and attesting it. It calls
    :func:`cosmosiq_ops.operator_attestation.record_shadow_validation_attestation`, which REFUSES
    (non-zero exit, nothing written) unless every named ``--run-ids`` is a REAL persisted run (or a
    non-empty window is given). Recording does NOT clear the 020F item on its own: an independent
    verifier confirms the runs form a genuine window (enough distinct runs over enough distinct
    days); too few / too short leaves operator_shadow_validation BLOCKING. No broker / orders.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="cosmosiq_pulse attest-shadow-validation",
        description=("RECORD one operator attestation that a REAL shadow / paper observation "
                     "window was reviewed. The engine never attests on its own; it clears the "
                     "020F operator_shadow_validation item only if an independent verifier confirms "
                     "a genuine window of real persisted runs. Append-only, offline, no orders."))
    parser.add_argument("--store-dir", required=True,
                        help="the local append-only store the runs + attestation live in.")
    parser.add_argument("--run-ids", default="",
                        help="comma-separated REAL persisted run ids forming the reviewed window "
                             "(each must exist). Omit to use --window-start/--window-end instead.")
    parser.add_argument("--window-start", default="",
                        help="window start instant (used when --run-ids is omitted).")
    parser.add_argument("--window-end", default="",
                        help="window end instant (used when --run-ids is omitted).")
    parser.add_argument("--reviewed-by", required=True,
                        help="who reviewed this (your operator label).")
    parser.add_argument("--statement", default="", help="an optional operator note.")
    parser.add_argument("--correction-of", default="",
                        help="id of a prior attestation this record supersedes (a correction, "
                             "never a mutation; optional).")
    parser.add_argument("--now", default=None,
                        help="injected ISO-8601 instant (default: the wall clock, read ONCE here "
                             "at the shell boundary).")
    args = parser.parse_args(argv)

    now = args.now
    if not now:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    from cosmosiq_ops.operator_attestation import record_shadow_validation_attestation

    def _split(text):
        return tuple(s.strip() for s in str(text or "").split(",") if s.strip())

    print("RECORD one operator shadow-validation attestation · manual review only · CosmosIQ "
          "records it, never attests for you · an independent verifier confirms the window · no "
          "broker, no orders.")
    try:
        attestation = record_shadow_validation_attestation(
            args.store_dir, window_run_ids=_split(args.run_ids),
            window_start=args.window_start, window_end=args.window_end,
            reviewed_by=args.reviewed_by, reviewed_at=now, statement=args.statement,
            correction_of=args.correction_of)
    except (ValueError, TypeError) as exc:
        print("  REFUSED (nothing written): {0}".format(exc))
        return 1

    window = (", ".join(attestation.window_run_ids)
              or "{0}..{1}".format(attestation.window_start, attestation.window_end))
    print("  recorded attestation_id={0} · window={1} · reviewed_by={2}".format(
        attestation.attestation_id, window, attestation.reviewed_by))
    print("  the attestation is RECORDED; operator_shadow_validation clears ONLY if an independent "
          "verifier confirms the runs form a genuine window (enough distinct runs over enough "
          "distinct days).")
    return 0


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
