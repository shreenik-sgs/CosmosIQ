"""Infinite Canvas -- thin, deterministic STATIC-HTML renderer (IMPLEMENTATION-008B).

PRESENTATION ONLY. This module renders an already-assembled, READ-ONLY
:class:`~infinite_canvas.cockpit.AlphaDecisionCockpitView` (008A) into a single,
self-contained static HTML document. It is the *thinnest possible* view layer:

* **Reads only the view.** It imports nothing but ``.view_models`` / ``.cockpit``
  and the stdlib ``html`` module. It never touches a reasoning layer
  (reality_intelligence / genesis / prometheus / personal_cio / execution_manual),
  never reads a raw pipeline object, and never reasons over one.
* **Originates no reasoning.** It copies and formats the view's already-computed
  fields. It scores nothing, derives no number, and invents no value. A rumor's
  presence changes no displayed confidence -- confidence is printed verbatim.
* **No action affordance can exist.** The output carries NO ``<script>``, NO
  ``<form>``, NO ``<button>``, no ``onclick``/action ``href``, no submit/endpoint.
  It is pure display: nothing here can place, route, or record an order.
* **Deterministic & stdlib-only.** A pure function of the view -- no clock, no
  randomness. The same view always renders byte-identically. Python 3.9.
* **Missing data is visible.** Every ``missing_fields`` entry is rendered with a
  clear marker; gaps are never blank-hidden.

All dynamic text is escaped through :func:`html.escape`.
"""

from __future__ import annotations

import html
from typing import Any, Iterable, Optional, Tuple

from .cockpit import AlphaDecisionCockpitView, from_slice


# --------------------------------------------------------------------------- #
# Small, pure formatting primitives                                           #
# --------------------------------------------------------------------------- #
_MISSING_MARKER = '<span class="missing">&mdash; missing (requires 009 ingestion / manual entry)</span>'


def _esc(value: Any) -> str:
    """HTML-escape any value's string form (``None`` -> empty string)."""
    return html.escape("" if value is None else str(value))


def _val(value: Any) -> str:
    """Render a scalar field value for display (read-only, never recomputed)."""
    if value is None:
        return '<span class="none">(not provided)</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        # Deterministic, lossless-enough display; no rounding that invents precision.
        return _esc(("%g" % value))
    return _esc(value)


def _row(label: str, value: Any) -> str:
    return "<tr><th>{0}</th><td>{1}</td></tr>".format(_esc(label), _val(value))


def _list_block(label: str, items: Optional[Iterable[Any]]) -> str:
    items = tuple(items or ())
    if not items:
        return "<tr><th>{0}</th><td><span class=\"none\">(none)</span></td></tr>".format(_esc(label))
    lis = "".join("<li>{0}</li>".format(_val(x)) for x in items)
    return "<tr><th>{0}</th><td><ul>{1}</ul></td></tr>".format(_esc(label), lis)


def _section(anchor: str, title: str, body: str) -> str:
    """Wrap a section in stable BEGIN/END markers so it can be sliced precisely."""
    return (
        "<!-- BEGIN-SECTION:{a} -->\n"
        "<section id=\"panel-{a}\" class=\"panel\">\n"
        "<h2>{t}</h2>\n{b}\n</section>\n"
        "<!-- END-SECTION:{a} -->\n"
    ).format(a=_esc(anchor), t=_esc(title), b=body)


def _meta_rows(panel: Any) -> str:
    """The cross-cutting provenance/meta every panel carries."""
    rows = [
        _row("panel_id", getattr(panel, "panel_id", "")),
        _row("source_layer", getattr(panel, "source_layer", "")),
        _row("source_class", getattr(panel, "source_class", "")),
    ]
    ids = tuple(getattr(panel, "source_object_ids", ()) or ())
    vers = tuple(getattr(panel, "source_object_versions", ()) or ())
    paired = ["{0} (v{1})".format(i, vers[k] if k < len(vers) else "?")
              for k, i in enumerate(ids)]
    rows.append(_list_block("source objects", paired))
    conf = getattr(panel, "confidence", None)
    if conf is not None:
        rows.append(_row("confidence", conf))
    eq = getattr(panel, "evidence_quality", None)
    if eq is not None:
        rows.append(_row("evidence_quality", eq))
    return "".join(rows)


def _missing_block(panel: Any) -> str:
    """Render the panel's honest missing-data flags -- never blank-hidden."""
    missing = tuple(getattr(panel, "missing_fields", ()) or ())
    if not missing:
        return "<p class=\"missing-none\">No missing fields flagged for this panel.</p>"
    lis = "".join("<li>{0} {1}</li>".format(_esc(m), _MISSING_MARKER) for m in missing)
    return "<div class=\"missing-fields\"><h4>Missing fields</h4><ul>{0}</ul></div>".format(lis)


def _table(rows: str) -> str:
    return "<table class=\"kv\">{0}</table>".format(rows)


# --------------------------------------------------------------------------- #
# 0. Header / case summary                                                    #
# --------------------------------------------------------------------------- #
def _header(cockpit: AlphaDecisionCockpitView) -> str:
    om = cockpit.opportunity_map
    rt = cockpit.red_team
    tech = cockpit.technical_confirmation
    pa = cockpit.personalized_action
    me = cockpit.manual_execution

    investability = rt.red_team_verdict or "(not provided)"
    if rt.false_positive_label:
        investability = "{0} / {1}".format(investability, rt.false_positive_label)

    if tech.technical_timing_confirmation is None:
        timing = "unknown"
    else:
        timing = "timing confirmed" if tech.technical_timing_confirmation else "timing not confirmed"

    pa_status = pa.recommendation_status if pa is not None else "(panel not present)"
    if me is None:
        me_preview = "(panel not present)"
    else:
        me_preview = me.ticket_state or (
            "preview required" if me.preview_required else "no ticket preview")

    rows = "".join([
        _row("Subject / security", cockpit.subject),
        _row("Theme", om.theme),
        _row("Investability (red-team verdict)", investability),
        _row("Timing-confirmation status", timing),
        _row("Personalized-action status", pa_status),
        _row("Manual-execution preview status", me_preview),
        _row("Data gaps", len(cockpit.data_gaps)),
        _row("Provenance-chain length", len(cockpit.provenance_chain)),
    ])
    body = (
        "<p class=\"lead\">Alpha Decision Cockpit &mdash; read-only presentation of "
        "the assembled view. No reasoning, scoring, ingestion, or order affordance "
        "is originated here.</p>\n" + _table(rows)
    )
    return (
        "<header id=\"case-summary\">\n<h1>Alpha Decision Cockpit</h1>\n" + body + "\n</header>\n"
    )


# --------------------------------------------------------------------------- #
# 1. Opportunity Map                                                          #
# --------------------------------------------------------------------------- #
def _opportunity_map(p: Any) -> str:
    rows = _meta_rows(p) + "".join([
        _row("Theme", p.theme),
        _list_block("Megatrend context", p.megatrend_context),
        _list_block("Cross-domain convergence", p.cross_domain_convergence),
        _row("Why now", p.why_now),
        _row("Why before obvious", p.why_before_obvious),
        _row("Opportunity timing", p.opportunity_timing),
        _row("Opportunity maturity", p.opportunity_maturity),
        _row("Theme maturity", p.theme_maturity),
        _row("Opportunity magnitude", p.opportunity_magnitude),
        _row("Bottleneck-driven", p.bottleneck_driven),
        _row("Driving constraint", p.driving_constraint),
        _row("Value-chain position", p.value_chain_position),
        _row("False-positive risk", p.false_positive_risk),
        _row("Bubble / hype risk", p.bubble_hype_risk),
        _list_block("Monitoring signals", p.monitoring_signals),
    ])
    return _section("opportunity_map", "1. Opportunity Map", _table(rows) + _missing_block(p))


# --------------------------------------------------------------------------- #
# 2. Value Chain / Bottleneck                                                 #
# --------------------------------------------------------------------------- #
def _value_chain_bottleneck(p: Any) -> str:
    # Value chain nodes
    node_rows = ""
    for n in p.value_chain_nodes:
        node_rows += (
            "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td>"
            "<td>{4}</td><td>{5}</td><td>{6}</td></tr>"
        ).format(
            _esc(n.node_id), _esc(n.tier), _esc(n.role), _val(n.choke_point),
            _val(n.pricing_power), _val(n.margin_capture_potential),
            _val(n.economic_leverage_score),
        )
    nodes_tbl = (
        "<h4>Value-chain nodes</h4>"
        "<table class=\"grid\"><tr><th>node</th><th>tier</th><th>role</th>"
        "<th>choke</th><th>pricing power</th><th>margin capture</th>"
        "<th>econ leverage</th></tr>{0}</table>"
    ).format(node_rows or "<tr><td colspan=\"7\">(none)</td></tr>")

    # Winners FIRST, then the derived security mapping AFTER.
    win_rows = ""
    for w in p.players:
        win_rows += (
            "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td>"
            "<td>{4}</td><td>{5}</td></tr>"
        ).format(
            _esc(w.name), _esc(w.ticker), _esc(w.value_chain_role),
            _val(w.winner_score), _val(w.exposure_directness),
            _val(w.margin_capture_ability),
        )
    winners_tbl = (
        "<h4>Winner mapping (scored players)</h4>"
        "<table class=\"grid\"><tr><th>name</th><th>ticker</th><th>role</th>"
        "<th>winner score</th><th>exposure directness</th>"
        "<th>margin capture</th></tr>{0}</table>"
    ).format(win_rows or "<tr><td colspan=\"6\">(none)</td></tr>")

    mapping_tbl = _table("".join([
        _row("Security / instrument mapping", p.security_or_instrument_mapping),
        _row("Mapping follows winners", p.security_mapping_follows_winners),
    ]))
    mapping_block = (
        "<h4>Security / instrument mapping "
        "<em>(derived after winner mapping)</em></h4>" + mapping_tbl
    )

    bottleneck_tbl = _table("".join([
        _row("Bottleneck type", p.bottleneck_type),
        _row("Constrained node", p.constrained_node),
        _row("Severity", p.severity),
        _row("Expected duration", p.duration),
        _row("Resolution risk", p.resolution_risk),
        _row("Bottleneck leverage", p.bottleneck_leverage),
        _row("Timing window", p.timing_window),
        _list_block("Direct beneficiaries", p.direct_beneficiaries),
        _list_block("Indirect beneficiaries", p.indirect_beneficiaries),
        _list_block("Constrained losers", p.constrained_losers),
    ]))
    bottleneck_block = "<h4>Bottleneck</h4>" + bottleneck_tbl

    body = (
        _table(_meta_rows(p)) + nodes_tbl + winners_tbl + mapping_block
        + bottleneck_block + _missing_block(p)
    )
    return _section("value_chain_bottleneck", "2. Value Chain / Bottleneck", body)


# --------------------------------------------------------------------------- #
# 3. Catalyst (positive / possible / RUMOR / negative kept SEPARATE)          #
# --------------------------------------------------------------------------- #
def _catalyst_item(c: Any) -> str:
    rows = "".join([
        _row("Type", c.catalyst_type),
        _row("Status", c.catalyst_status),
        _row("Expected direction", c.expected_direction),
        _row("Timing window", c.expected_timing_window),
        _row("Business impact", c.expected_business_impact),
        _row("Affected value-chain node", c.affected_value_chain_node),
        _row("Novelty", c.novelty),
        _row("Evidence quality", c.evidence_quality),
        _row("Monitoring only", c.monitoring_only),
        _row("Dilution flag", c.dilution_flag),
    ])
    return "<div class=\"catalyst-item\">" + _table(rows) + "</div>"


def _catalyst(p: Any) -> str:
    confirmed_probable = tuple(
        c for c in p.positive_catalysts
        if (c.catalyst_status or "") in ("confirmed", "probable")
    )
    possible = tuple(
        c for c in p.positive_catalysts
        if (c.catalyst_status or "") not in ("confirmed", "probable")
    )

    def block(title, items, css="", note=""):
        head = "<h4 class=\"{0}\">{1}</h4>".format(_esc(css), _esc(title))
        if note:
            head += "<p class=\"flag\">{0}</p>".format(_esc(note))
        if not items:
            return head + "<p class=\"none\">(none)</p>"
        return head + "".join(_catalyst_item(c) for c in items)

    body = _table(_meta_rows(p))
    body += "<div class=\"subsection positive\">"
    body += block("Positive catalysts — confirmed / probable", confirmed_probable, "positive")
    body += "</div>"
    body += "<div class=\"subsection possible\">"
    body += block("Positive catalysts — possible", possible, "possible")
    body += "</div>"
    body += "<div class=\"subsection rumors\">"
    body += block(
        "Speculative rumors", p.speculative_rumors, "rumor",
        note="RUMOR — not confirmed evidence. Shown separately; raises no confidence value.",
    )
    body += "</div>"
    body += "<div class=\"subsection negative\">"
    body += block("Negative catalysts", p.negative_catalysts, "negative")
    body += "</div>"
    body += _table(_list_block("Repricing key trigger events", p.repricing_key_trigger_events))
    if p.red_team_catalyst_check is not None:
        rt = p.red_team_catalyst_check
        body += _table("".join([
            _row("Red-team catalyst check", rt.check),
            _row("Verdict", rt.verdict),
            _row("Rationale", rt.rationale),
        ]))
    body += _missing_block(p)
    return _section("catalyst", "3. Catalyst", body)


# --------------------------------------------------------------------------- #
# 4. Financial Inflection                                                     #
# --------------------------------------------------------------------------- #
def _financial_inflection(p: Any) -> str:
    rows = _meta_rows(p) + "".join([
        _row("Revenue inflection (acceleration)", p.revenue_inflection),
        _row("Margin expansion (inflection)", p.margin_expansion),
        _row("Guidance adjustment", p.guidance_adjustment),
        _row("Backlog", p.backlog),
        _row("Guidance", p.guidance),
        _row("Cash runway", p.cash_runway),
        _row("EBITDA", p.ebitda),
        _row("FCF", p.fcf),
        _row("Capex", p.capex),
        _row("Operating leverage", p.operating_leverage),
        _row("Unit economics", p.unit_economics),
        _row("Dilution penalty (dilution risk)", p.dilution_penalty),
        _row("Financing penalty", p.financing_penalty),
        _row("Customer concentration", p.customer_concentration),
        _row("Inflection timing", p.inflection_timing),
        _row("Financial-inflection probability", p.financial_inflection_probability),
        _row("Financial-inflection score", p.financial_inflection_score),
        _list_block("Notes", p.notes),
    ])
    return _section("financial_inflection", "4. Financial Inflection",
                    _table(rows) + _missing_block(p))


# --------------------------------------------------------------------------- #
# 5. Scenario / Asymmetry                                                     #
# --------------------------------------------------------------------------- #
def _scenario_asymmetry(p: Any) -> str:
    rows = _meta_rows(p) + "".join([
        _row("Asymmetry label (classification)", p.asymmetry_label),
        _row("Asymmetry score", p.asymmetry_score),
        _row("Upside potential", p.upside_potential),
        _row("Downside risk", p.downside_risk),
        _row("Upside/downside ratio", p.upside_downside_ratio),
        _row("Probability-weighted EV", p.prob_weighted_ev),
        _row("Effective bear price", p.effective_bear_price),
        _row("Bear price", p.bear_price),
        _row("Base price", p.base_price),
        _row("Bull price", p.bull_price),
        _row("Extreme-bull price", p.extreme_bull_price),
        _row("Valuation method (valuation risk)", p.valuation_method),
        _row("Current TAM", p.current_tam),
        _row("Implied market share", p.implied_market_share),
        _list_block("Sensitivity drivers", p.sensitivity_drivers),
        _list_block("Invalidation triggers", p.invalidation_triggers),
        _list_block("Notes", p.notes),
    ])
    note = (
        "<p class=\"flag\">Good company ≠ good thesis ≠ good stock ≠ "
        "asymmetric stock. Scenario anchors are shown only where already present; "
        "absent numbers are flagged, never invented.</p>"
    )
    return _section("scenario_asymmetry", "5. Scenario / Asymmetry",
                    note + _table(rows) + _missing_block(p))


# --------------------------------------------------------------------------- #
# 6. Technical Confirmation  (timing-confirmation language ONLY)              #
# --------------------------------------------------------------------------- #
def _technical(p: Any) -> str:
    if p.technical_timing_confirmation is None:
        timing = "unknown"
    else:
        timing = "timing confirmed" if p.technical_timing_confirmation else "timing not confirmed"
    rows = _meta_rows(p) + "".join([
        _row("EMA stack status (9/20/50/200)", p.ema_stack_status),
        _row("Trend alignment (slope status)", p.trend_alignment),
        _row("Compression / breakout status", p.compression_breakout_status),
        _row("Breakout", p.breakout),
        _row("Volume confirmation", p.volume_confirmation),
        _row("Relative-strength confirmation", p.relative_strength_confirmation),
        _row("VWAP", p.vwap),
        _row("Anchored VWAP", p.anchored_vwap),
        _row("Overhead supply", p.overhead_supply),
        _row("Failed-breakout risk", p.failed_breakout_risk),
        _row("Dilution / ATM overhang penalty", p.dilution_overhang_penalty),
        _row("Invalidation level", p.invalidation_level),
        _row("Technical setup score", p.technical_setup_score),
        _row("Timing quality", p.timing_quality),
        _row("Technical timing-confirmation", timing),
        _list_block("Notes", p.notes),
    ])
    note = (
        "<p class=\"flag\">Timing-confirmation read only — this confirms timing, "
        "it is not an action or order signal.</p>"
    )
    return _section("technical_confirmation", "6. Technical Confirmation",
                    note + _table(rows) + _missing_block(p))


# --------------------------------------------------------------------------- #
# 7. Red Team                                                                 #
# --------------------------------------------------------------------------- #
def _red_team(p: Any) -> str:
    check_rows = ""
    for ch in p.checks:
        check_rows += "<tr><td>{0}</td><td>{1}</td><td>{2}</td></tr>".format(
            _esc(ch.check), _esc(ch.verdict), _esc(ch.rationale))
    checks_tbl = (
        "<h4>Checks (kill risks / thesis breakers)</h4>"
        "<table class=\"grid\"><tr><th>check</th><th>verdict</th>"
        "<th>rationale</th></tr>{0}</table>"
    ).format(check_rows or "<tr><td colspan=\"3\">(none)</td></tr>")
    rows = _meta_rows(p) + "".join([
        _row("Red-team verdict", p.red_team_verdict),
        _row("Confidence haircut", p.confidence_haircut),
        _row("False-positive label", p.false_positive_label),
        _list_block("Kill risks", p.kill_risks),
    ])
    return _section("red_team", "7. Red Team",
                    _table(rows) + checks_tbl + _missing_block(p))


# --------------------------------------------------------------------------- #
# 8. Personalized Action  (RANGE / max-exposure % only -- no exact size)      #
# --------------------------------------------------------------------------- #
def _personalized_action(p: Any) -> str:
    if p is None:
        body = "<p class=\"none\">(personalized-action panel not present)</p>"
        return _section("personalized_action", "8. Personalized Action", body)
    sizing = p.suggested_sizing_range_pct or (None, None)
    lo = sizing[0] if len(sizing) > 0 else None
    hi = sizing[1] if len(sizing) > 1 else None
    rows = _meta_rows(p) + "".join([
        _row("Recommendation status", p.recommendation_status),
        _row("Suitability score", p.suitability_score),
        _row("Concentration score", p.concentration_score),
        _row("Liquidity score", p.liquidity_score),
        _row("Risk-fit score", p.risk_fit_score),
        _row("Portfolio-fit score", p.portfolio_fit_score),
        _row("Recommended max exposure %", p.recommended_max_exposure_pct),
        _row("Suggested sizing range % (low)", lo),
        _row("Suggested sizing range % (high)", hi),
        _list_block("Blocking conditions", p.blocking_conditions),
        _list_block("Risk warnings", p.risk_warnings),
        _list_block("Monitoring signals", p.monitoring_signals),
        _list_block("Required user confirmations", p.required_user_confirmations),
        _list_block("Review triggers", p.review_triggers),
    ])
    note = (
        "<p class=\"flag\">Sizing RANGE / max-exposure % only — no exact size, "
        "no execution decision is expressed in this section (cognition / actuation "
        "boundary).</p>"
    )
    return _section("personalized_action", "8. Personalized Action",
                    note + _table(rows) + _missing_block(p))


# --------------------------------------------------------------------------- #
# 9. Manual Execution  (manual-only; no automated order, no broker routing)   #
# --------------------------------------------------------------------------- #
def _manual_execution(p: Any) -> str:
    if p is None:
        body = "<p class=\"none\">(manual-execution panel not present)</p>"
        return _section("manual_execution", "9. Manual Execution", body)

    banner = (
        "<div class=\"banner\">MANUAL EXECUTION — performed by hand outside the "
        "system; no automated order, no broker routing, no automated trade "
        "placement. This is a read-only preview only.</div>"
    )

    intent_rows = _meta_rows(p) + "".join([
        _row("Execution intent id", p.execution_intent_id),
        _row("Selected instrument", p.selected_instrument),
        _row("User-selected allocation amount", p.user_selected_allocation_amount),
        _row("User-selected allocation %", p.user_selected_allocation_pct),
        _row("Execution side", p.execution_side),
        _row("Account", p.account),
        _row("User confirmation required", p.user_confirmation_required),
        _row("Stale check required", p.stale_check_required),
        _row("Preview required", p.preview_required),
        _row("Manual execution only", p.manual_execution_only),
    ])

    preview_rows = "".join([
        _row("Ticket id", p.ticket_id),
        _row("Ticket preview state", p.ticket_state),
        _row("Ticket quantity", p.ticket_quantity),
        _row("Order type", p.order_type),
        _row("Limit price", p.limit_price),
        _row("Estimated cost", p.estimated_cost),
        _row("Preview hash", p.preview_hash),
    ])
    preview_block = (
        "<h4>Ticket preview (operational; manual placement only)</h4>"
        + _table(preview_rows)
    )

    record_rows = "".join([
        _row("Broker order id (manual recording, after hand-placed trade)", p.broker_order_id),
        _row("Reconciliation all-reconciled", p.reconciliation_all_reconciled),
        _row("Audit entry count", p.audit_entry_count),
    ])
    record_block = (
        "<h4>Manual recording (filled in by the user after a hand-placed trade)</h4>"
        + _table(record_rows)
    )

    body = banner + _table(intent_rows) + preview_block + record_block + _missing_block(p)
    return _section("manual_execution", "9. Manual Execution", body)


# --------------------------------------------------------------------------- #
# 10. Provenance / Evidence drawer                                            #
# --------------------------------------------------------------------------- #
def _provenance(cockpit: AlphaDecisionCockpitView) -> str:
    chain_rows = ""
    for i, ref in enumerate(cockpit.provenance_chain, start=1):
        chain_rows += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>v{3}</td></tr>".format(
            _esc(i), _esc(ref.kind), _esc(ref.object_id), _esc(ref.version))
    chain_tbl = (
        "<h4>Provenance chain (Observation &rarr; &hellip; &rarr; Ticket)</h4>"
        "<table class=\"grid\"><tr><th>#</th><th>kind</th><th>object id</th>"
        "<th>version</th></tr>{0}</table>"
    ).format(chain_rows or "<tr><td colspan=\"4\">(none)</td></tr>")

    panel_rows = ""
    for panel in cockpit.panels:
        ids = tuple(getattr(panel, "source_object_ids", ()) or ())
        vers = tuple(getattr(panel, "source_object_versions", ()) or ())
        paired = ", ".join("{0} (v{1})".format(i, vers[k] if k < len(vers) else "?")
                           for k, i in enumerate(ids)) or "(none)"
        prov = getattr(panel, "provenance", None)
        upstream = ", ".join(getattr(prov, "upstream_observation_ids", ()) or ()) or "(none)"
        panel_rows += "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td></tr>".format(
            _esc(getattr(panel, "panel_id", "")),
            _esc(getattr(panel, "source_layer", "")),
            _esc(paired), _esc(upstream))
    panel_tbl = (
        "<h4>Per-panel source objects + upstream observations</h4>"
        "<table class=\"grid\"><tr><th>panel</th><th>source layer</th>"
        "<th>source objects</th><th>upstream observations</th></tr>{0}</table>"
    ).format(panel_rows or "<tr><td colspan=\"4\">(none)</td></tr>")

    return _section("provenance", "10. Provenance / Evidence", chain_tbl + panel_tbl)


# --------------------------------------------------------------------------- #
# 11. Data Gaps                                                               #
# --------------------------------------------------------------------------- #
def _data_gaps(cockpit: AlphaDecisionCockpitView) -> str:
    gaps = tuple(cockpit.data_gaps)
    if not gaps:
        body = "<p class=\"missing-none\">No data gaps flagged.</p>"
        return _section("data_gaps", "11. Data Gaps", body)
    lis = "".join("<li>{0} {1}</li>".format(_esc(g), _MISSING_MARKER) for g in gaps)
    body = (
        "<p class=\"flag\">Every gap below is a panel-scoped missing field, surfaced "
        "honestly rather than blank-hidden.</p>"
        "<ul class=\"data-gaps\">{0}</ul>".format(lis)
    )
    return _section("data_gaps", "11. Data Gaps", body)


# --------------------------------------------------------------------------- #
# Document shell                                                              #
# --------------------------------------------------------------------------- #
_STYLE = (
    "body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
    "margin:0;padding:1.5rem;color:#1b1f24;background:#f6f7f9;line-height:1.45}"
    "h1{font-size:1.6rem;margin:0 0 .5rem}"
    "h2{font-size:1.2rem;border-bottom:2px solid #d0d7de;padding-bottom:.25rem}"
    "h4{font-size:1rem;margin:1rem 0 .35rem}"
    "header,section{background:#fff;border:1px solid #d0d7de;border-radius:8px;"
    "padding:1rem 1.25rem;margin:0 0 1.25rem}"
    "table{border-collapse:collapse;width:100%;margin:.25rem 0}"
    "table.kv th{text-align:left;width:30%;vertical-align:top;color:#57606a;"
    "font-weight:600;padding:.2rem .5rem}"
    "table.kv td{padding:.2rem .5rem;vertical-align:top}"
    "table.grid th,table.grid td{border:1px solid #d8dee4;padding:.3rem .5rem;"
    "text-align:left;font-size:.9rem}"
    "table.grid th{background:#f0f3f6}"
    "ul{margin:.2rem 0;padding-left:1.2rem}"
    ".none,.missing{color:#9a6700}.missing{font-weight:600}"
    ".flag{background:#fff8c5;border-left:4px solid #d4a72c;padding:.4rem .6rem;"
    "margin:.4rem 0;font-size:.9rem}"
    ".banner{background:#ffebe9;border:1px solid #ff8182;border-radius:6px;"
    "padding:.6rem .8rem;font-weight:700;margin:.2rem 0 .6rem}"
    ".subsection.rumors h4{color:#9a6700}"
    ".subsection.negative h4{color:#cf222e}"
    ".missing-fields{background:#fbf1d6;border-radius:6px;padding:.4rem .7rem}"
    ".lead{color:#57606a}"
)


def render_cockpit_html(cockpit: AlphaDecisionCockpitView) -> str:
    """Render the cockpit view into a complete, deterministic, static HTML document.

    Pure function of ``cockpit``: no clock, no randomness, no mutation. The document
    is fully self-contained (inline ``<style>`` only) and carries NO JavaScript, NO
    form, NO button, and no submit/order affordance -- it is display only.
    """
    title = "Alpha Decision Cockpit — {0}".format(cockpit.subject or "(no subject)")
    parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        "<title>{0}</title>".format(_esc(title)),
        "<style>{0}</style>".format(_STYLE),
        "</head>",
        "<body>",
        _header(cockpit),
        _opportunity_map(cockpit.opportunity_map),
        _value_chain_bottleneck(cockpit.value_chain_bottleneck),
        _catalyst(cockpit.catalyst),
        _financial_inflection(cockpit.financial_inflection),
        _scenario_asymmetry(cockpit.scenario_asymmetry),
        _technical(cockpit.technical_confirmation),
        _red_team(cockpit.red_team),
        _personalized_action(cockpit.personalized_action),
        _manual_execution(cockpit.manual_execution),
        _provenance(cockpit),
        _data_gaps(cockpit),
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def render_slice_to_html(slice_result) -> str:
    """Convenience: project a runtime ``SliceResult`` to the cockpit, then render it."""
    return render_cockpit_html(from_slice(slice_result))


def write_cockpit_html(cockpit: AlphaDecisionCockpitView, path) -> None:
    """Write the rendered HTML to ``path`` (deterministic; UTF-8, no clock)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_cockpit_html(cockpit))
