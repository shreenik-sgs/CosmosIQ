"""IMPLEMENTATION-012J — reality-mesh signal/pulse -> Data-Quality presentation adapters.

Pure, deterministic functions that turn a manual pulse's ``RealitySignal`` / ``SignalCluster`` /
``ThemePulse`` objects into an *evidence* HTML panel for the Data-Quality page. This is EVIDENCE,
never a ranking and never a trade action:

* signal freshness + source authority are shown as LABELS;
* weak / social (rumor / uncorroborated) signals are CLEARLY marked weak;
* contradictions are shown with BOTH sides visible (never averaged away);
* data gaps are visible;
* ``ThemePulse`` is shown as a STATE, with an explicit "state, not a recommendation" caption.

The panel is ADDITIVE and opt-in: with no signals/clusters/pulses supplied it returns ``""`` so the
demo / real / enriched default output stays byte-identical. It introduces NO ``data-intel`` refs and
NO ``href="#..."`` anchors, so it can never create an unresolved intel ref or a dead anchor. There is
no ranking order (rows are sorted by stable id) and no buy/sell/order verb anywhere. Wording is
"manual pulse" — never always-on / real-time / live.

IMPLEMENTATION-013F adds :func:`build_run_observability_panel` under the SAME discipline: a
PERSISTED pulse run's metadata (run / agent / source health, gate results, replay metadata) rendered
as EVIDENCE + OBSERVABILITY for the Trust & Data-Quality surface. Labels + volume counts only;
degraded / failed states are shown honestly, never hidden; no ``data-intel``, no ``href`` anchor,
no trade affordance, no hidden metric, no credential value; English layer terminology only (a
legacy layer prefix in an agent id is normalized to its approved English value for display).

IMPLEMENTATION-015C adds :func:`build_alert_inbox_panel` under the SAME discipline again: the
persisted alert inbox rendered as OBSERVATIONS. Alerts observe, they never execute: severities are
labels (info / notice / warning / critical, never a score), every row shows its plain-English
reason, and NOTHING in the panel is clickable -- no ``href``, no ``data-intel``, no ``<button>``,
no form, no acknowledge affordance. Acknowledgment happens via the CLI (``--ack-alert``), never a
click. Empty input -> ``""`` so every default page stays byte-identical.
"""

from typing import Any, Dict, Iterable, Optional, Tuple

from . import labels as _labels

__all__ = ["build_pulse_data_quality_panel", "build_run_observability_panel",
           "build_alert_inbox_panel"]

_RUMOR = "rumor"
_NARRATIVE = "narrative"


def _esc(text: Any) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _badge(text: str, kind: str = "") -> str:
    cls = "badge" + ((" " + kind) if kind else "")
    return '<span class="{0}">{1}</span>'.format(cls, _esc(text))


def _label(obj: Any, name: str, default: str = "—") -> str:
    val = getattr(obj, name, None)
    return _esc(val) if val else default


def _is_weak_social(sig: Any, authority: str) -> bool:
    disc = (getattr(sig, "discipline", "") or "").lower()
    corr = (getattr(sig, "corroboration_status", "") or "").lower()
    return (disc == _NARRATIVE or authority == _RUMOR or "uncorrob" in corr)


def _gaps_of(obj: Any) -> Tuple[str, ...]:
    return tuple(getattr(obj, "data_gaps", ()) or ())


def build_pulse_data_quality_panel(
    *,
    signals: Iterable[Any] = (),
    clusters: Iterable[Any] = (),
    theme_pulses: Iterable[Any] = (),
    authority_by_signal: Optional[Dict[str, str]] = None,
) -> str:
    """Render the manual-pulse reality-signal EVIDENCE panel (or ``""`` when nothing supplied).

    ``authority_by_signal`` (optional) maps ``signal_id -> authority label`` (the fusion sidecar,
    since ``RealitySignal`` has no authority field); absent, authority renders as ``unknown`` — a
    visible gap, never fabricated.
    """
    signals = sorted(signals, key=lambda s: getattr(s, "signal_id", ""))
    clusters = sorted(clusters, key=lambda c: getattr(c, "cluster_id", ""))
    theme_pulses = sorted(theme_pulses, key=lambda p: getattr(p, "theme_pulse_id", ""))
    auth = dict(authority_by_signal or {})
    if not signals and not clusters and not theme_pulses:
        return ""  # opt-in: nothing supplied -> byte-identical to the pre-012J page

    note = ('<p class="note">Manual pulse — on demand, not scheduled, not live, not '
            "broker-connected. These are reality SIGNALS (evidence), never a ranking and never a "
            "trade recommendation. Weak / social signals are marked weak; contradictions keep both "
            "sides; gaps stay visible.</p>")

    # --- Signal coverage (per discipline): freshness + source authority visible ---------------
    cov_rows = ""
    for s in signals:
        a = (auth.get(getattr(s, "signal_id", ""), "") or "unknown")
        cov_rows += (
            "<tr><th>{disc}</th><td>{dir}</td><td>{fresh}</td><td>{auth}</td>"
            "<td>{conf}</td><td>{gaps}</td></tr>".format(
                disc=_label(s, "discipline"), dir=_label(s, "direction_label"),
                fresh=_badge(_label(s, "freshness_label"),
                             "hazard" if _label(s, "freshness_label") == "stale" else "q-high"),
                auth=_badge(_esc(a), "gap" if a in ("unknown", _RUMOR) else "q-high"),
                conf=_label(s, "confidence_label"),
                gaps=_esc(len(_gaps_of(s)))))
    coverage = (
        "<h3>Signal coverage (manual pulse)</h3><div class=\"glass-panel\"><table class=\"kv\">"
        "<tr><th>Discipline</th><td>Direction</td><td>Freshness</td><td>Source authority</td>"
        "<td>Confidence</td><td>Gaps</td></tr>" + (cov_rows or
        "<tr><th>—</th><td colspan=\"5\">no signals in this pulse</td></tr>") + "</table></div>")

    # --- Weak / social signals: clearly marked weak -------------------------------------------
    weak = [s for s in signals if _is_weak_social(s, auth.get(getattr(s, "signal_id", ""), ""))]
    weak_items = "".join(
        "<li>{disc}: {dir} {w} {u} — {reason}</li>".format(
            disc=_label(s, "discipline"), dir=_label(s, "direction_label"),
            w=_badge("WEAK", "hazard"), u=_badge("uncorroborated", "gap"),
            reason=_esc("social / rumor authority; requires corroboration by non-social evidence"))
        for s in weak)
    weak_html = (
        "<h3>Weak / social signals</h3><div class=\"glass-panel\"><ul>"
        + (weak_items or "<li>none — no rumor / uncorroborated signals in this pulse</li>")
        + "</ul></div>")

    # --- Conflicting signals: both sides visible, never averaged ------------------------------
    conflicted = [s for s in signals
                  if "contradict" in (getattr(s, "contradiction_status", "") or "").lower()]
    conf_items = "".join(
        "<li>{disc}: {badge} — direction \"{dir}\"; both sides preserved ({n} conflict note(s))"
        "</li>".format(disc=_label(s, "discipline"), badge=_badge("contradicted", "hazard"),
                       dir=_label(s, "direction_label"),
                       n=_esc(len(getattr(s, "conflicts", ()) or _gaps_of(s))))
        for s in conflicted)
    conflict_html = (
        "<h3>Conflicting signals</h3><div class=\"glass-panel\"><ul>"
        + (conf_items or "<li>none — no contradicted signals in this pulse</li>")
        + "</ul></div>")

    # --- ThemePulse status: STATE, not a recommendation ---------------------------------------
    pulse_rows = ""
    for p in theme_pulses:
        state = _label(p, "state")
        weak_state = state in ("Data insufficient", "Conflicted", "Breaking down")
        pulse_rows += (
            "<tr><th>{name}</th><td>{state}</td><td>{breadth}</td><td>{crowd}</td>"
            "<td>{fresh}</td></tr>".format(
                name=_label(p, "theme_name") or _label(p, "theme_id"),
                state=_badge(state, "gap" if weak_state else "q-high"),
                breadth=_label(p, "breadth_label"), crowd=_label(p, "crowding_label"),
                fresh=_label(p, "freshness_label")))
    pulse_html = (
        "<h3>Theme pulse status</h3><div class=\"glass-panel\">"
        "<p class=\"note\">A theme pulse is a STATE (Dormant … Data insufficient), NOT a trade "
        "recommendation, price target, or stock pick.</p><table class=\"kv\">"
        "<tr><th>Theme</th><td>State</td><td>Breadth</td><td>Crowding</td><td>Freshness</td></tr>"
        + (pulse_rows or "<tr><th>—</th><td colspan=\"4\">no theme pulses in this pulse</td></tr>")
        + "</table></div>")

    # --- Data gaps across the pulse -----------------------------------------------------------
    all_gaps = []
    for obj in list(signals) + list(clusters) + list(theme_pulses):
        all_gaps.extend(_gaps_of(obj))
    gaps_html = (
        "<h3>Pulse data gaps</h3><div class=\"glass-panel\"><ul>"
        + ("".join("<li>{0}</li>".format(_esc(g)) for g in sorted(set(all_gaps)))
           or "<li>no gaps recorded in this pulse</li>")
        + "</ul></div>")

    return ("<h2>Manual pulse — reality signals</h2>" + note
            + coverage + weak_html + conflict_html + pulse_html + gaps_html)


# --------------------------------------------------------------------------- #
# IMPLEMENTATION-013F — persisted-run observability panel                       #
# --------------------------------------------------------------------------- #

# Statuses that mark an unhealthy / refused state -- rendered VISIBLY (hazard), never hidden.
_BAD_STATES = frozenset({
    "failed", "blocked_by_policy", "credentials_missing", "rate_limited",
    "source_unavailable", "fail",
})
_GOOD_STATES = frozenset({"healthy", "success", "pass", "full", "ok", "present"})


def _status_badge(value: Any) -> str:
    """A label badge for a health / gate status: bad -> hazard, good -> q-high, else gap."""
    text = str(value or "").strip()
    if not text:
        return "—"
    if text in _BAD_STATES:
        return _badge(text, "hazard")
    if text in _GOOD_STATES:
        return _badge(text, "q-high")
    return _badge(text, "gap")  # degraded / partial / skipped / warn / stale / unknown ...


def _english_agent_label(agent_id: Any) -> str:
    """The agent id with any legacy layer prefix normalized to its approved English value."""
    text = str(agent_id or "")
    head, sep, tail = text.partition(".")
    if sep:
        return "{0}.{1}".format(_labels.normalize_layer(head), tail)
    return text


def _count(obj: Any, name: str) -> str:
    return _esc(getattr(obj, name, 0))


# Display labels for gate categories whose raw id would put a credential-ish token into the page
# (a generated artifact must never contain a token like "secret" -- not even as a category name).
_GATE_CATEGORY_LABELS = {
    "security_secrets": "security (no credential in output)",
}


def build_run_observability_panel(
    *,
    pulse_run: Any = None,
    run_health: Any = None,
    dq_summary: Any = None,
    agent_health: Iterable[Any] = (),
    source_health: Iterable[Any] = (),
    gate_results: Iterable[Any] = (),
    replay_result: Any = None,
) -> str:
    """Render a persisted pulse run's OBSERVABILITY panel (or ``""`` when nothing supplied).

    Evidence + observability only, never a trade action: run metadata (ids / mode / volumes),
    per-agent + per-source health (labels + volume counts; failed / blocked states VISIBLE),
    gate results (pass / warn / fail badges) and replay metadata (``deterministic_match``).
    Same discipline as :func:`build_pulse_data_quality_panel`: additive + opt-in (empty inputs
    -> ``""`` -> byte-identical page), no ``data-intel`` ref, no ``href`` anchor, no hidden
    metric, no credential value (``credentials_status`` is a presence LABEL only).
    """
    agent_health = sorted(agent_health or (), key=lambda a: getattr(a, "agent_id", ""))
    source_health = sorted(source_health or (), key=lambda s: getattr(s, "source_id", ""))
    gate_results = list(gate_results or ())
    if (pulse_run is None and run_health is None and dq_summary is None
            and not agent_health and not source_health and not gate_results
            and replay_result is None):
        return ""  # opt-in: nothing supplied -> byte-identical to the pre-013F page

    note = ('<p class="note">Manual pulse · not scheduled — run on demand, not live, not '
            "broker-connected. Persisted run metadata shown as EVIDENCE and observability: "
            "labels and volume counts only, never a trade action, never a numeric quality "
            "metric. Degraded and failed states are shown honestly, never hidden.</p>")

    # --- Run metadata: ids, mode, trigger, timestamps, volumes, versions ----------------------
    run_html = ""
    if pulse_run is not None or run_health is not None or dq_summary is not None:
        rows = ""
        if pulse_run is not None:
            rows += (
                "<tr><th>Run id</th><td>{rid}</td></tr>"
                "<tr><th>Mode</th><td>{mode}</td></tr>"
                "<tr><th>Trigger</th><td>{trig} — manual pulse · not scheduled</td></tr>"
                "<tr><th>Started</th><td>{start}</td></tr>"
                "<tr><th>Completed</th><td>{done}</td></tr>"
                "<tr><th>Volumes (counts, not metrics)</th><td>events {ev} · findings {fi} · "
                "signals {si} · theme pulses {tp}</td></tr>"
                "<tr><th>Schema / runtime version</th><td>{schema} / {rt}</td></tr>".format(
                    rid=_label(pulse_run, "run_id"), mode=_label(pulse_run, "mode"),
                    trig=_label(pulse_run, "trigger_type", "manual"),
                    start=_label(pulse_run, "started_at"),
                    done=_label(pulse_run, "completed_at"),
                    ev=_count(pulse_run, "events_created"),
                    fi=_count(pulse_run, "findings_created"),
                    si=_count(pulse_run, "signals_created"),
                    tp=_count(pulse_run, "theme_pulses_created"),
                    schema=_label(pulse_run, "schema_version"),
                    rt=_label(pulse_run, "runtime_version")))
        if run_health is not None:
            rows += (
                "<tr><th>Run health</th><td>{status} — agents run {run} · failed {fail} · "
                "blocked {blk} · skipped {skip}</td></tr>"
                "<tr><th>Sources</th><td>used {used} · failed {sfail}</td></tr>"
                "<tr><th>Data gaps / conflicts</th><td>{gaps} gap(s) · {conf} conflict(s) — "
                "surfaced, not hidden</td></tr>".format(
                    status=_status_badge(getattr(run_health, "overall_status", "")),
                    run=_count(run_health, "agents_run"),
                    fail=_count(run_health, "agents_failed"),
                    blk=_count(run_health, "agents_blocked"),
                    skip=_count(run_health, "agents_skipped"),
                    used=_count(run_health, "sources_used"),
                    sfail=_count(run_health, "sources_failed"),
                    gaps=_count(run_health, "data_gap_count"),
                    conf=_count(run_health, "conflict_count")))
        if dq_summary is not None:
            rows += (
                "<tr><th>Data quality</th><td>{status} — source coverage {cov} · "
                "weak-social {weak} · unsupported claims {uns}</td></tr>".format(
                    status=_status_badge(getattr(dq_summary, "status", "")),
                    cov=_status_badge(getattr(dq_summary, "source_coverage", "")),
                    weak=_count(dq_summary, "weak_social_count"),
                    uns=_count(dq_summary, "unsupported_claim_count")))
        run_html = ('<h3>Run metadata (persisted)</h3><div class="glass-panel">'
                    '<table class="kv">' + rows + "</table></div>")

    # --- Agent health: failed / blocked agents VISIBLE ----------------------------------------
    agent_html = ""
    if agent_health:
        arows = "".join(
            "<tr><th>{aid}</th><td>{status}</td><td>{fails}</td><td>{reason}</td></tr>".format(
                aid=_esc(_english_agent_label(getattr(a, "agent_id", ""))),
                status=_status_badge(getattr(a, "last_status", "")),
                fails=_count(a, "failure_count"),
                reason=_label(a, "degraded_reason"))
            for a in agent_health)
        agent_html = (
            '<h3>Agent health</h3><div class="glass-panel"><table class="kv">'
            "<tr><th>Agent</th><td>Last status</td><td>Failure count</td>"
            "<td>Degraded reason</td></tr>" + arows + "</table></div>")

    # --- Source health: a failed source is a VISIBLE gap --------------------------------------
    source_html = ""
    if source_health:
        srows = "".join(
            "<tr><th>{sid}</th><td>{status}</td><td>{cred}</td><td>{rate}</td>"
            "<td>{reason}</td></tr>".format(
                sid=_label(s, "source_id"),
                status=_status_badge(getattr(s, "last_status", "")),
                cred=_status_badge(getattr(s, "credentials_status", "")),
                rate=_status_badge(getattr(s, "rate_limit_status", "")),
                reason=_label(s, "unavailable_reason"))
            for s in source_health)
        source_html = (
            '<h3>Source health</h3><div class="glass-panel">'
            '<p class="note">Credentials shown as a presence label only — a credential value '
            "never appears here. A source that could not deliver is a visible gap, never a "
            "fabricated value.</p>"
            '<table class="kv"><tr><th>Source</th><td>Status</td><td>Credentials</td>'
            "<td>Rate limit</td><td>Unavailable reason</td></tr>" + srows + "</table></div>")

    # --- Gate results: pass / warn / fail per category + the worst overall --------------------
    gate_html = ""
    if gate_results:
        worst = "pass"
        for g in gate_results:
            st = str(getattr(g, "status", "") or "")
            if st == "fail":
                worst = "fail"
            elif st == "warn" and worst != "fail":
                worst = "warn"
        grows = "".join(
            "<tr><th>{cat}</th><td>{status}</td><td>{n} finding(s)</td></tr>".format(
                cat=_esc(_GATE_CATEGORY_LABELS.get(
                    str(getattr(g, "category", "") or ""),
                    str(getattr(g, "category", "") or "—"))),
                status=_status_badge(getattr(g, "status", "")),
                n=_esc(len(tuple(getattr(g, "findings", ()) or ()))))
            for g in gate_results)
        gate_html = (
            '<h3>Data-quality gate results</h3><div class="glass-panel">'
            "<p class=\"note\">Gate verdicts are labels (pass / warn / fail), never a metric. "
            "Overall: {0}.</p>".format(_status_badge(worst))
            + '<table class="kv"><tr><th>Gate category</th><td>Status</td><td>Findings</td>'
            "</tr>" + grows + "</table></div>")

    # --- Replay metadata: the persisted run is reconstructable ---------------------------------
    replay_html = ""
    if replay_result is not None:
        match = bool(getattr(replay_result, "deterministic_match", False))
        diffs = tuple(getattr(replay_result, "differences", ()) or ())
        replay_html = (
            '<h3>Replay</h3><div class="glass-panel"><table class="kv">'
            "<tr><th>Source run</th><td>{src}</td></tr>"
            "<tr><th>Replay id</th><td>{rid}</td></tr>"
            "<tr><th>Replay status</th><td>replayable · deterministic_match: {match}</td></tr>"
            "<tr><th>Replayed</th><td>events {ev} · findings {fi} · signals {si}</td></tr>"
            "<tr><th>Differences</th><td>{nd} difference(s){note}</td></tr>"
            "</table></div>".format(
                src=_label(replay_result, "source_run_id"),
                rid=_label(replay_result, "replay_id"),
                match=_esc(match),
                ev=_count(replay_result, "events_replayed"),
                fi=_count(replay_result, "findings_replayed"),
                si=_count(replay_result, "signals_replayed"),
                nd=_esc(len(diffs)),
                note=("" if match and not diffs else
                      " — a divergent replay is a FAILURE, surfaced not hidden")))

    return ("<h2>Run observability — persisted pulse</h2>" + note
            + run_html + agent_html + source_html + gate_html + replay_html)


# --------------------------------------------------------------------------- #
# IMPLEMENTATION-015C — persisted alert-inbox panel (observations, no clicks)   #
# --------------------------------------------------------------------------- #

# Severity label -> badge kind. Labels on a human-attention ladder, never a score.
_SEVERITY_BADGE_KINDS = {
    "info": "q-high",
    "notice": "gap",
    "warning": "hazard",
    "critical": "hazard",
}


def build_alert_inbox_panel(*, alerts: Iterable[Any] = (),
                            acknowledged_ids: Iterable[str] = ()) -> str:
    """Render the persisted alert inbox (or ``""`` when no alerts are supplied).

    OBSERVATIONS only: each row shows the severity LABEL, the closed category, the
    plain-English reason, its subjects and evidence volume, and whether it has been
    acknowledged. Nothing is clickable — no ``href``, no ``data-intel``, no ``<button>``,
    no acknowledge affordance: acknowledgment happens via the CLI (``--ack-alert``), which
    appends a NEW record referencing the alert (the alert line itself is never edited).
    Additive + opt-in: empty input -> ``""`` -> every default page stays byte-identical.
    """
    alerts = sorted(alerts or (), key=lambda a: getattr(a, "alert_id", ""))
    if not alerts:
        return ""  # opt-in: nothing supplied -> byte-identical to the pre-015C page
    acked = set(acknowledged_ids or ())

    note = ('<p class="note">Alert inbox — alerts OBSERVE, they never execute. Each alert '
            "names a state change between two persisted pulse runs and points at its "
            "evidence; severities are labels, never scores. Nothing here is clickable: "
            "acknowledgment happens via the CLI (a new append-only record), not a button. "
            "Nothing acts automatically and there is no way to act from this panel.</p>")

    rows = ""
    for a in alerts:
        alert_id = str(getattr(a, "alert_id", ""))
        acknowledged = bool(getattr(a, "acknowledged", False)) or alert_id in acked
        status = (_badge("acknowledged", "q-high") if acknowledged
                  else _badge("open", "gap"))
        severity = str(getattr(a, "severity", "") or "info")
        subjects = ", ".join(
            tuple(getattr(a, "subject_tickers", ()) or ())
            + tuple(getattr(a, "subject_themes", ()) or ())) or "—"
        rows += (
            "<tr><th>{sev}</th><td>{cat}</td><td>{reason}</td><td>{run}</td>"
            "<td>{subjects}</td><td>{ev} evidence ref(s)</td><td>{status}</td></tr>".format(
                sev=_badge(severity, _SEVERITY_BADGE_KINDS.get(severity, "gap")),
                cat=_label(a, "category"),
                reason=_label(a, "human_readable_reason"),
                run=_label(a, "run_id"),
                subjects=_esc(subjects),
                ev=_esc(len(tuple(getattr(a, "evidence_refs", ()) or ()))),
                status=status))

    return ("<h2>Alert inbox — persisted observations</h2>" + note
            + '<div class="glass-panel"><table class="kv">'
            "<tr><th>Severity</th><td>Category</td><td>Reason (plain English)</td>"
            "<td>Run</td><td>Subjects</td><td>Evidence</td><td>Status</td></tr>"
            + rows + "</table></div>"
            + '<p class="note">To acknowledge: run the CLI with --ack-alert and the alert '
            "id. The acknowledgment is a NEW append-only record referencing the alert; the "
            "original alert line stays byte-unchanged.</p>")
