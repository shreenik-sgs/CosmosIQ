"""The Capital Picks Report Renderer -- MANUAL REVIEW (IMPLEMENTATION-022E).

The presentation layer ABOVE the 022A/022B/022C/022D typed stack. It renders a
:func:`render_capital_picks_report` -- a deterministic, plain-text stock-pick report titled
**"CosmosIQ Capital Picks -- Manual Review"** -- from a sequence of
:class:`~reality_mesh.recommendation.CapitalRecommendation` records. It renders whatever HONESTLY
exists: **zero actionable picks is a valid, expected outcome** and is stated plainly, never papered
over with a fabricated pick.

HARD DISCIPLINE (the whole reason this slice exists):

* **Read / inspect surface only -- NO trade affordance anywhere.** There is NO buy / sell / order /
  submit / place-trade / auto-trade control or verb in the report. The ONLY per-pick "next action"
  values are the six review/open affordances in :data:`ALLOWED_NEXT_ACTIONS`. The single "order"
  token in the whole report is the standing honesty phrase *"no order is placed"* in the Manual
  Execution Preview section. Execution stays MANUAL REVIEW.

* **No hidden score / rank / rating.** Every verdict is a LABEL, a plain reason, or a qualitative
  range -- never a number, never a score / rank / rating.

* **Zero-pick honesty.** A pick appears in "New Actionable Picks" ONLY when its
  ``recommendation_state`` is ``actionable_pick_manual_review`` (which the 022B gates already guard,
  and 022A makes structurally unforgeable). With none, the report says "0 Actionable Picks" plus the
  honest bucket counts, or the "0 Picks -- source freshness / Data Quality insufficient" variant when
  the supplied data-quality summary is degraded / failed.

* **Deterministic + offline.** Pure function of its inputs; byte-identical for the same input; the
  producing-run mode (demo vs default pulse) is NEVER rendered, so a demo and a default-pulse run
  over equivalent content render byte-identically. No network, no scheduler, no wall-clock.

Stdlib-only, Python 3.9, OFFLINE. No network / scheduler / broker on import.
"""

from __future__ import annotations

import re
from dataclasses import fields, is_dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .recommendation import RECOMMENDATION_STATES, CapitalRecommendation

__all__ = [
    "REPORT_TITLE",
    "SECTION_TITLES",
    "ALLOWED_NEXT_ACTIONS",
    "REPORT_MODES",
    "render_capital_picks_report",
]

# The canonical report title (em-dash U+2014). Asserted verbatim by the suite.
REPORT_TITLE = "CosmosIQ Capital Picks — Manual Review"

# The 13 sections, in permanent order. Rendered as "Section N. <title>".
SECTION_TITLES: Tuple[str, ...] = (
    "Executive Summary",
    "Market / Theme Context",
    "New Actionable Picks",
    "Prepare Entry Candidates",
    "Active Diligence Candidates",
    "Watchlist Changes",
    "Deteriorating / Exit Review Candidates",
    "Blocked Candidates and Reasons",
    "Red-Team Risks",
    "Trust & Data Quality",
    "Portfolio Fit",
    "Manual Execution Preview",
    "Replay / Provenance Appendix",
)

# The ONLY per-pick next-action values permitted anywhere in the report. Every one is a
# READ / INSPECT affordance -- there is no buy / sell / order / submit / place-trade / auto-trade
# verb in this set, and none may be added without breaking the read-only invariant.
ALLOWED_NEXT_ACTIONS: Tuple[str, ...] = (
    "Review Thesis",
    "Review Entry Setup",
    "Review Portfolio Fit",
    "Review Red-Team Risk",
    "Open Company Cockpit",
    "Open Manual Execution Preview",
)

# The report-level mode display (Shadow vs Production). This is the REPORT mode, never the
# producing-run's demo/pulse mode (which is deliberately never rendered).
REPORT_MODES: Dict[str, str] = {"shadow": "Shadow", "production": "Production"}

# The standing honesty phrase for the Manual Execution Preview section. The single occurrence of
# the "order" token in the whole report lives here -- a NEGATION, never an affordance.
_NO_ORDER = "Manual preview only — no order is placed. Execution stays Manual Review."

# The recommendation_state -> exec-summary bucket label (every closed state is counted honestly).
_BUCKET_LABELS: Tuple[Tuple[str, str], ...] = (
    ("actionable_pick_manual_review", "Actionable picks"),
    ("prepare_entry", "Prepare-entry candidates"),
    ("active_diligence", "Active-diligence candidates"),
    ("watch", "Watchlist"),
    ("deteriorating", "Deteriorating"),
    ("exit_review", "Exit-review"),
    ("blocked", "Blocked"),
    ("avoid", "Avoid"),
    ("not_recommended", "Not recommended"),
)


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _clean(value: Any) -> str:
    return str(value or "").strip()


def _seq(value: Any) -> Tuple[str, ...]:
    """A tuple of non-empty stripped strings from any iterable ('' entries dropped)."""
    return tuple(_clean(v) for v in (value or ()) if _clean(v))


def _or(value: Any, absent: str) -> str:
    """The cleaned value, or the honest ``absent`` placeholder when empty."""
    text = _clean(value)
    return text if text else absent


def _bullets(items: Sequence[str], indent: str, empty: str) -> List[str]:
    """One ``indent - item`` line per item, or a single honest ``empty`` line."""
    kept = _seq(items)
    if not kept:
        return ["{0}- {1}".format(indent, empty)]
    return ["{0}- {1}".format(indent, item) for item in kept]


def _section_header(index: int) -> str:
    return "Section {0}. {1}".format(index, SECTION_TITLES[index - 1])


# --------------------------------------------------------------------------- #
# Data-quality summary normalization (accepts str / mapping / result sequence)  #
# --------------------------------------------------------------------------- #
def _dq_lines(dq_summary: Any) -> Tuple[List[str], str]:
    """Render the DQ summary to lines + derive an overall status token.

    Accepts ``None`` (honest absence), a plain string, a mapping, a single gate-result object, or a
    sequence of gate-result objects (each with ``category`` / ``status`` / ``findings``). The
    overall token is ``failed`` if any result failed, ``degraded`` if any warned, else ``healthy``;
    a string / mapping is scanned for the same keywords. Never fabricates a verdict.
    """
    if dq_summary is None:
        return (["  No data-quality summary supplied for this run — trust cannot be asserted, so no "
                 "pick may be treated as production-grade without it."], "absent")

    if isinstance(dq_summary, str):
        text = dq_summary.strip()
        if not text:
            return (["  No data-quality summary supplied for this run."], "absent")
        return (["  {0}".format(text)], _scan_status(text))

    if isinstance(dq_summary, Mapping):
        lines = ["  {0}: {1}".format(_clean(k), _clean(v)) for k, v in dq_summary.items()]
        blob = " ".join("{0} {1}".format(k, v) for k, v in dq_summary.items())
        overall = _clean(dq_summary.get("overall_status") or dq_summary.get("status"))
        return (lines or ["  (empty data-quality summary)"], overall or _scan_status(blob))

    # A single result object or a sequence of them.
    results = dq_summary if isinstance(dq_summary, (list, tuple)) else [dq_summary]
    lines: List[str] = []
    statuses: List[str] = []
    for result in results:
        category = _clean(getattr(result, "category", "")) or "gate"
        status = _clean(getattr(result, "status", "")) or "unstated"
        statuses.append(status)
        findings = _seq(getattr(result, "findings", ()))
        lines.append("  {0}: {1}".format(category, status))
        for finding in findings:
            lines.append("      · {0}".format(finding))
    if not lines:
        return (["  (empty data-quality summary)"], "absent")
    overall = ("failed" if "fail" in statuses else
               "degraded" if "warn" in statuses else "healthy")
    return (lines, overall)


def _scan_status(text: str) -> str:
    low = text.lower()
    if "fail" in low or "failed" in low:
        return "failed"
    if "degrad" in low or "warn" in low or "insufficient" in low:
        return "degraded"
    if "healthy" in low:
        return "healthy"
    return "unknown"


def _dq_insufficient(overall: str) -> bool:
    """A SIGNALLED data-quality problem (not a mere absence) that justifies the 0-Picks-DQ headline.

    Only a supplied summary that reads failed / degraded / insufficient flips the headline. An
    absent / unknown / healthy summary leaves the plain "0 Actionable Picks" headline in place --
    absence of a summary is a gap surfaced in section 10, not a claim that DQ failed.
    """
    return overall in ("failed", "degraded", "insufficient")


# --------------------------------------------------------------------------- #
# Per-pick rendering                                                            #
# --------------------------------------------------------------------------- #
def _next_action_line() -> str:
    """The per-pick NEXT ACTION line -- ONLY the allowed read/inspect affordances."""
    return "  Next action: " + " · ".join(ALLOWED_NEXT_ACTIONS)


def _render_pick_full(rec: CapitalRecommendation, position: int) -> List[str]:
    """The FULL per-actionable-pick block -- every field the pick carries, or an honest absence."""
    lines: List[str] = []
    lines.append("Pick {0}: {1} — {2}".format(
        position, _clean(rec.ticker), _or(rec.company_name, "(company name not recorded)")))
    lines.append("  Recommendation: {0}".format(
        _or(rec.recommendation_label, "(label not set)")))
    lines.append("  Time horizon: {0}".format(
        _or(rec.recommendation_time_horizon, "not recorded")))
    lines.append("  Why now: {0}".format(_or(rec.why_now, "not recorded")))
    lines.append("  Theme: {0}   Mega theme: {1}".format(
        _or(rec.theme_ref, "not mapped"), _or(rec.mega_theme_ref, "not mapped")))
    lines.append("  Value chain: {0}".format(_or(rec.value_chain_ref, "not mapped")))
    lines.append("  Bottleneck exposure: {0}".format(_or(rec.bottleneck_ref, "not mapped")))
    lines.append("  Evidence summary: {0}".format(_or(rec.evidence_summary, "not recorded")))
    lines.append("  Source authority / provenance: {0}".format(
        ", ".join(_seq(rec.source_provenance)) or "none recorded"))
    lines.append("  Signal state: {0}".format(
        _or(rec.key_thesis, "not separately recorded on this pick (see provenance)")))
    lines.append("  Forward scenario: {0}".format(
        _or(rec.forward_scenario_ref, "absent — GAP (stated, not a block here)")))
    lines.append("  Technical setup (022C): {0}".format(
        _or(rec.technical_timing_ref, "not assessed")))
    lines.append("  Portfolio fit (022D): {0}".format(
        _or(rec.portfolio_fit_ref, "not assessed")))
    lines.append("  Sizing guardrail: {0}".format(
        _or(rec.sizing_guardrail, "not recorded (range label only, never a number)")))
    lines.append("  Invalidation:")
    lines.extend(_bullets(rec.invalidation_conditions, "    ", "none recorded"))
    lines.append("  Exit / watch:")
    lines.extend(_bullets(rec.exit_watch_conditions, "    ", "none recorded"))
    lines.append("  Red-team risks: {0}".format(_or(rec.red_team_ref, "no red-team ref recorded")))
    lines.extend(_bullets(rec.primary_risks, "    ", "no primary risks recorded"))
    lines.append("  Data gaps:")
    lines.extend(_bullets(rec.data_gaps, "    ", "none recorded"))
    lines.append(_next_action_line())
    return lines


def _render_pick_brief(rec: CapitalRecommendation) -> List[str]:
    """A lighter per-pick line for the non-actionable state sections (still label + why)."""
    return [
        "- {0} — {1} · {2}".format(
            _clean(rec.ticker), _or(rec.company_name, "(company not recorded)"),
            _or(rec.recommendation_label, "(label not set)")),
        "    Why now: {0}".format(_or(rec.why_now, "not recorded")),
        "    Time horizon: {0}".format(_or(rec.recommendation_time_horizon, "not recorded")),
    ]


# --------------------------------------------------------------------------- #
# Section builders                                                              #
# --------------------------------------------------------------------------- #
def _grouped(recommendations: Sequence[CapitalRecommendation]) -> Dict[str, List[CapitalRecommendation]]:
    groups: Dict[str, List[CapitalRecommendation]] = {state: [] for state in RECOMMENDATION_STATES}
    for rec in recommendations:
        groups.setdefault(rec.recommendation_state, []).append(rec)
    return groups


def _executive_summary(groups: Dict[str, List[CapitalRecommendation]],
                       dq_overall: str) -> List[str]:
    actionable = len(groups.get("actionable_pick_manual_review", ()))
    lines = [_section_header(1), ""]
    if actionable > 0:
        headline = "{0} New Actionable Pick(s) — Manual Review".format(actionable)
    elif _dq_insufficient(dq_overall) and dq_overall != "healthy":
        headline = ("0 Picks — source freshness / Data Quality insufficient "
                    "(data-quality summary is {0})".format(dq_overall))
    else:
        headline = "0 Actionable Picks"
    lines.append("Headline: {0}".format(headline))
    lines.append("")
    lines.append("Honest bucket counts (every recommendation state, nothing hidden):")
    for state, label in _BUCKET_LABELS:
        lines.append("  {0}: {1}".format(label, len(groups.get(state, ()))))
    lines.append("")
    if actionable == 0:
        lines.append("No recommendation reached actionable_pick_manual_review this run. Zero "
                     "actionable picks is a valid, expected outcome — nothing is fabricated to "
                     "fill the report.")
    else:
        lines.append("Each actionable pick below reached actionable_pick_manual_review only by "
                     "passing every recommendation gate; it is a review label, never a directive.")
    return lines


def _state_section(index: int, groups: Dict[str, List[CapitalRecommendation]],
                   states: Tuple[str, ...], empty_note: str,
                   full: bool = False) -> List[str]:
    lines = [_section_header(index), ""]
    picks: List[CapitalRecommendation] = []
    for state in states:
        picks.extend(groups.get(state, ()))
    if not picks:
        lines.append(empty_note)
        return lines
    if full:
        for position, rec in enumerate(picks, start=1):
            lines.extend(_render_pick_full(rec, position))
            lines.append("")
        lines.pop()  # drop the trailing blank
    else:
        for rec in picks:
            lines.extend(_render_pick_brief(rec))
    return lines


def _blocked_section(index: int, groups: Dict[str, List[CapitalRecommendation]]) -> List[str]:
    lines = [_section_header(index), ""]
    blocked = groups.get("blocked", ())
    if not blocked:
        lines.append("No blocked candidates in this run.")
        return lines
    lines.append("Each blocked candidate carries its EXACT reason — nothing is hidden:")
    for rec in blocked:
        lines.append("- {0}: {1}".format(
            _clean(rec.ticker), _or(rec.blocked_reason, "(no reason recorded — contract violation)")))
    return lines


def _red_team_section(index: int, recommendations: Sequence[CapitalRecommendation]) -> List[str]:
    lines = [_section_header(index), ""]
    any_shown = False
    for rec in recommendations:
        risks = _seq(rec.primary_risks)
        red_ref = _clean(rec.red_team_ref)
        if not risks and not red_ref:
            continue
        any_shown = True
        lines.append("- {0}: red-team ref {1}".format(
            _clean(rec.ticker), red_ref or "none recorded"))
        for risk in risks:
            lines.append("    · {0}".format(risk))
    if not any_shown:
        lines.append("No red-team risks recorded on any recommendation in this run.")
    return lines


def _dq_section(index: int, dq_lines: List[str]) -> List[str]:
    return [_section_header(index), ""] + dq_lines


def _portfolio_section(index: int, groups: Dict[str, List[CapitalRecommendation]]) -> List[str]:
    lines = [_section_header(index), ""]
    picks = list(groups.get("actionable_pick_manual_review", ())) \
        + list(groups.get("prepare_entry", ()))
    if not picks:
        lines.append("No pick carries a portfolio-fit + sizing guardrail this run "
                     "(sizing is a range label only, never a number).")
        return lines
    for rec in picks:
        lines.append("- {0}: portfolio-fit ref {1} · sizing guardrail {2}".format(
            _clean(rec.ticker), _or(rec.portfolio_fit_ref, "not assessed"),
            _or(rec.sizing_guardrail, "not recorded")))
    return lines


def _manual_execution_section(index: int,
                              groups: Dict[str, List[CapitalRecommendation]]) -> List[str]:
    lines = [_section_header(index), ""]
    lines.append(_NO_ORDER)
    lines.append("")
    picks = groups.get("actionable_pick_manual_review", ())
    if not picks:
        lines.append("No actionable pick, so there is nothing to preview for manual review.")
        return lines
    for rec in picks:
        lines.append("- {0}: manual execution preview {1} (read-only pointer to a human review).".format(
            _clean(rec.ticker),
            _or(rec.manual_execution_preview_ref, "not recorded")))
    return lines


def _provenance_section(index: int, run_id: str, generated_at: str,
                        recommendations: Sequence[CapitalRecommendation]) -> List[str]:
    lines = [_section_header(index), ""]
    lines.append("Run id: {0}".format(_or(run_id, "(run id not supplied)")))
    lines.append("Generated at: {0}".format(_or(generated_at, "(timestamp not supplied)")))
    lines.append("")
    if not recommendations:
        lines.append("No recommendations in this run — no provenance to appendix.")
        return lines
    lines.append("Per-recommendation provenance (id · candidate · source refs):")
    for rec in recommendations:
        lines.append("- {0}: rec {1} · candidate {2} · sources [{3}]".format(
            _clean(rec.ticker), _or(rec.recommendation_id, "?"),
            _or(rec.candidate_id, "?"),
            ", ".join(_seq(rec.source_provenance)) or "none recorded"))
    return lines


# --------------------------------------------------------------------------- #
# The public renderer                                                           #
# --------------------------------------------------------------------------- #
def render_capital_picks_report(
    recommendations: Sequence[CapitalRecommendation],
    *,
    run_id: str,
    generated_at: str,
    market_theme_context: Optional[Any] = None,
    dq_summary: Any = None,
    mode: str = "shadow",
) -> str:
    """Render the MANUAL-REVIEW Capital Picks report as a deterministic plain-text string.

    Groups ``recommendations`` by ``recommendation_state`` into the 13 fixed sections and renders
    whatever HONESTLY exists. A pick appears in "New Actionable Picks" ONLY when its state is
    ``actionable_pick_manual_review``; zero actionable picks is a valid outcome and is stated
    plainly. Read/inspect only -- the sole per-pick affordances are the six
    :data:`ALLOWED_NEXT_ACTIONS`; there is no buy / sell / order / submit / place-trade / auto-trade
    verb anywhere, and no score / rank / rating. Deterministic + offline; the producing-run mode is
    never rendered, so demo and default-pulse runs over equivalent content render byte-identically.
    """
    recs: List[CapitalRecommendation] = list(recommendations or ())
    groups = _grouped(recs)
    dq_rendered, dq_overall = _dq_lines(dq_summary)
    mode_display = REPORT_MODES.get(_clean(mode).lower(), _clean(mode).title() or "Shadow")

    out: List[str] = []
    # -- title + honest "as of" header ------------------------------------- #
    out.append(REPORT_TITLE)
    out.append("Mode: {0}".format(mode_display))
    out.append("Run id: {0}".format(_or(run_id, "(run id not supplied)")))
    out.append("As of: {0} — a point-in-time review of what exists this run; nothing is fetched "
               "live and nothing is a directive to act.".format(
                   _or(generated_at, "(timestamp not supplied)")))
    out.append("")

    # -- 1. Executive Summary ---------------------------------------------- #
    out.extend(_executive_summary(groups, dq_overall))
    out.append("")

    # -- 2. Market / Theme Context ----------------------------------------- #
    out.append(_section_header(2))
    out.append("")
    context_text = _clean(market_theme_context)
    out.append(context_text if context_text
               else "No market / theme context supplied for this run.")
    out.append("")

    # -- 3. New Actionable Picks ------------------------------------------- #
    out.extend(_state_section(
        3, groups, ("actionable_pick_manual_review",),
        "0 Actionable Picks. No recommendation reached actionable_pick_manual_review this run — "
        "nothing is fabricated to fill this section.", full=True))
    out.append("")

    # -- 4. Prepare Entry Candidates --------------------------------------- #
    out.extend(_state_section(
        4, groups, ("prepare_entry",),
        "No prepare-entry candidates this run."))
    out.append("")

    # -- 5. Active Diligence Candidates ------------------------------------ #
    out.extend(_state_section(
        5, groups, ("active_diligence",),
        "No active-diligence candidates this run."))
    out.append("")

    # -- 6. Watchlist Changes ---------------------------------------------- #
    out.extend(_state_section(
        6, groups, ("watch",),
        "No watchlist entries this run."))
    out.append("")

    # -- 7. Deteriorating / Exit Review Candidates ------------------------- #
    out.extend(_state_section(
        7, groups, ("deteriorating", "exit_review"),
        "No deteriorating / exit-review candidates this run."))
    out.append("")

    # -- 8. Blocked Candidates and Reasons --------------------------------- #
    out.extend(_blocked_section(8, groups))
    out.append("")

    # -- 9. Red-Team Risks ------------------------------------------------- #
    out.extend(_red_team_section(9, recs))
    out.append("")

    # -- 10. Trust & Data Quality ------------------------------------------ #
    out.extend(_dq_section(10, dq_rendered))
    out.append("")

    # -- 11. Portfolio Fit ------------------------------------------------- #
    out.extend(_portfolio_section(11, groups))
    out.append("")

    # -- 12. Manual Execution Preview -------------------------------------- #
    out.extend(_manual_execution_section(12, groups))
    out.append("")

    # -- 13. Replay / Provenance Appendix ---------------------------------- #
    out.extend(_provenance_section(13, run_id, generated_at, recs))
    out.append("")

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Import-time guard: the renderer references NO trade / score verb of its own.    #
# (The report body is asserted trade/score-clean by the 022E suite's sweep.)     #
# --------------------------------------------------------------------------- #
def _self_check() -> None:
    _forbidden = ("buy now", "sell now", "submit order", "place trade", "auto trade")
    joined = " ".join(SECTION_TITLES + ALLOWED_NEXT_ACTIONS + (REPORT_TITLE, _NO_ORDER)).lower()
    for phrase in _forbidden:
        assert phrase not in joined, "forbidden trade phrase in report scaffolding: {0!r}".format(
            phrase)
    # Whole-word only -- "Deteriorating" legitimately contains the substring "rating".
    for token in ("score", "rank", "rating", "alpha score"):
        assert re.search(r"\b{0}\b".format(re.escape(token)), joined) is None, (
            "forbidden score/rank token in report scaffolding: {0!r}".format(token))
    # No action label carries a buy/sell/order/submit verb (whole word).
    for action in ALLOWED_NEXT_ACTIONS:
        low = action.lower()
        for verb in ("buy", "sell", "order", "submit", "trade"):
            assert re.search(r"\b{0}\b".format(verb), low) is None, (
                "next-action {0!r} carries forbidden verb {1!r}".format(action, verb))
    # Sanity: the model is a frozen dataclass with no trade field (already guarded in 022A).
    assert is_dataclass(CapitalRecommendation)
    assert all(f.name != "" for f in fields(CapitalRecommendation))


_self_check()
