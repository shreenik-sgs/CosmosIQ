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
"""

from typing import Any, Dict, Iterable, Optional, Tuple

__all__ = ["build_pulse_data_quality_panel"]

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
