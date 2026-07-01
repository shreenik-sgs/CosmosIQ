"""Deterministic static-HTML renderer for the Economic Universe UI (010A).

PRESENTATION ONLY. Renders the read-only :mod:`universe_ui.view_models` projections
into seven self-contained static HTML pages with a cosmic command-center theme. It
copies and formats already-projected fields -- it scores nothing, reasons over
nothing, ingests nothing, and originates no order.

Guarantees for every page it emits:

* A persistent status strip: ``Mode: fixture/demo · Live data: not enabled ·
  Scheduler: not enabled · Broker automation: disabled · Manual review required``.
* NO ``<form>``, NO ``<button>``, no ``onclick``, no ``type="submit"``, no
  ``fetch``/``XHR``, and no buy/sell/place-order affordance. Navigation is
  ``<a href>`` links plus navigation-only JS (tab/collapse toggles).
* Data gaps, conflicts, and source-authority badges are always rendered -- never
  hidden inside a collapsible region.
* Deterministic: a pure function of the view -- the same view renders byte-identically.

The IREN cockpit page is the ACCEPTED ``render_cockpit_html`` output, wrapped with a
status strip + nav (not reimplemented).
"""

from __future__ import annotations

import html
from typing import Any, Iterable, Tuple

from infinite_canvas.render_html import render_cockpit_html

from .assets import COSMIC_CSS, NAV_JS
from .view_models import (
    BucketView,
    CandidateCardView,
    CIODashboardView,
    DataQualityView,
    EconomicUniverseView,
    GalaxyClusterView,
    GalaxyThemeView,
    PlanetCandidateView,
    SolarSystemValueChainView,
    StarBottleneckView,
)

STATUS_STRIP_TEXT = (
    "Mode: fixture/demo · Live data: not enabled · Scheduler: not enabled "
    "· Broker automation: disabled · Manual review required"
)

# (label, filename) for the persistent nav.
_NAV = (
    ("Economic Universe", "universe.html"),
    ("Galaxies", "galaxy.html"),
    ("Value Chains", "solar_system.html"),
    ("Bottleneck Stars", "star.html"),
    ("IREN Cockpit", "cockpit.html"),
    ("CIO Dashboard", "dashboard.html"),
    ("Data Quality", "data_quality.html"),
)

_HEAT_CLASS = {"hot": "heat-hot", "warm": "heat-warm", "cool": "heat-cool", "dim": "heat-dim"}


# --------------------------------------------------------------------------- #
# Primitives                                                                  #
# --------------------------------------------------------------------------- #
def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _badge(text: str, cls: str = "") -> str:
    return '<span class="badge {0}">{1}</span>'.format(_esc(cls), _esc(text))


def _quality_badge(quality: str) -> str:
    q = (quality or "").lower()
    cls = "q-{0}".format(q) if q in ("high", "medium", "low", "sparse") else ""
    return _badge("data quality: {0}".format(quality or "unknown"), cls)


def _list(items: Iterable[Any], empty: str = "(none)") -> str:
    items = tuple(items or ())
    if not items:
        return '<p class="note">{0}</p>'.format(_esc(empty))
    return "<ul>{0}</ul>".format("".join("<li>{0}</li>".format(_esc(x)) for x in items))


def _gap_box(title: str, items: Iterable[Any]) -> str:
    items = tuple(items or ())
    if not items:
        return '<div class="gap-box"><h4>{0}</h4><p class="note">none flagged</p></div>'.format(
            _esc(title))
    return '<div class="gap-box"><h4>{0}</h4>{1}</div>'.format(_esc(title), _list(items))


def _status_strip() -> str:
    return '<div class="status-strip">{0}</div>'.format(_esc(STATUS_STRIP_TEXT))


def _command_bar(current_file: str) -> str:
    links = []
    for label, fname in _NAV:
        cls = "navlink here" if fname == current_file else "navlink"
        links.append('<a class="{0}" href="{1}">{2}</a>'.format(cls, _esc(fname), _esc(label)))
    brand = ('<div class="brand">SUDARSHAN<small>ECONOMIC UNIVERSE · '
             'READ-ONLY PROJECTION</small></div>')
    return '<div class="command-bar">{0}{1}</div>'.format(brand, "".join(links))


def _page(title: str, current_file: str, body: str) -> str:
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>{0}</title>".format(_esc(title)),
        "<style>{0}</style>".format(COSMIC_CSS),
        "</head>",
        "<body>",
        _status_strip(),
        _command_bar(current_file),
        '<div class="wrap">',
        body,
        _footer(),
        "</div>",
        "<script>{0}</script>".format(NAV_JS),
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)


def _footer() -> str:
    return (
        "<footer>"
        "SUDARSHAN Economic Universe — IMPLEMENTATION-010A. Read-only projection of "
        "existing pipeline statuses and hand-authored DEMO terrain. No live data, no "
        "ranking, no scheduler, no broker, no order affordance. "
        "Every candidate requires manual review."
        "</footer>"
    )


def _money(value: Any) -> str:
    """Format a raw magnitude for the tooltip/card details (pure, deterministic)."""
    if value is None:
        return "unknown (data gap)"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _esc(value)
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(v) >= scale:
            return "${0:.2f}{1}".format(v / scale, unit)
    return "${0:.0f}".format(v)


def _orb(size_px: int, glow: int, dashed: bool, raw_label: str, raw_value: Any) -> str:
    """A visual-size orb. SIZE encodes economic magnitude (bounded log scale);
    GLOW encodes status; a dashed outline flags missing magnitude. The RAW value is
    always shown in the details -- size is never the only signal, and never a ranking."""
    cls = "orb glow-{0}".format(int(glow) if glow in (1, 2, 3) else 1)
    if dashed:
        cls += " dashed"
    style = "width:{0}px;height:{0}px".format(int(size_px))
    gap = (' <span class="badge gap">magnitude missing — neutral size, data gap</span>'
           if dashed else "")
    return (
        '<div class="orb-wrap"><div class="{cls}" style="{style}"></div>'
        '<div class="orb-meta">visual size ∝ {label} (bounded log scale; not a ranking)<br>'
        '<b>{label}: {raw}</b>{gap}</div></div>'
    ).format(cls=cls, style=style, label=_esc(raw_label), raw=_esc(_money(raw_value)), gap=gap)


# --------------------------------------------------------------------------- #
# A. Universe / Reality Map                                                   #
# --------------------------------------------------------------------------- #
def _cluster_card(c: GalaxyClusterView) -> str:
    classes = ["card", "galaxy-node", _HEAT_CLASS.get((c.heat_label or "").lower(), "heat-dim")]
    if c.data_poor:
        classes += ["heat-dim", "data-poor"]
    if c.red_team_risk:
        classes.append("blackhole")
    if c.crowded_euphoric:
        classes.append("euphoric")
    markers = []
    if c.red_team_risk:
        markers.append(_badge("black-hole: red-team risk", "hazard"))
    if c.crowded_euphoric:
        markers.append(_badge("warning halo: crowded / euphoric", "gap"))
    if c.data_poor:
        markers.append(_badge("dim: data-poor", "q-low"))
    rows = "".join([
        "<tr><th>Megatrend</th><td>{0}</td></tr>".format(_esc(c.megatrend)),
        "<tr><th>Capital cycle</th><td>{0}</td></tr>".format(_esc(c.capital_cycle)),
        "<tr><th>Heat / priority</th><td>{0} · {1}</td></tr>".format(
            _esc(c.heat_label), _esc(c.priority_label)),
        "<tr><th>Signal convergence</th><td>{0}</td></tr>".format(_esc(c.signal_convergence)),
        "<tr><th>Bottleneck severity</th><td>{0}</td></tr>".format(_esc(c.bottleneck_severity)),
        "<tr><th>Candidates</th><td>{0}</td></tr>".format(_esc(c.candidate_count)),
        "<tr><th>Evidence count</th><td>{0}</td></tr>".format(_esc(c.evidence_count)),
        "<tr><th>Maturity / timing</th><td>{0}</td></tr>".format(_esc(c.maturity_timing)),
    ])
    if c.magnitude_missing:
        classes.append("dashed-outline")
    orb = _orb(c.visual_size_px, 2, c.magnitude_missing, "theme TAM (DEMO)", c.theme_tam)
    return (
        '<div class="{cls}">'
        '<p class="title">{name}</p>'
        '<p class="sub">{badges}</p>'
        "{orb}"
        '<p>{markers}</p>'
        '<table class="kv">{rows}</table>'
        '<p>{q} {demo}</p>'
        '<p><a href="galaxy.html#g-{slug}">Zoom into galaxy →</a></p>'
        "</div>"
    ).format(
        cls=" ".join(classes), name=_esc(c.theme_name),
        badges=_quality_badge(c.data_quality), orb=orb,
        markers=" ".join(markers) or _badge("nominal", "q-high"),
        rows=rows, q=_badge("terrain: semi-static", ""),
        demo=_badge("DEMO", "demo"), slug=_esc(c.slug))


def render_universe(view: EconomicUniverseView) -> str:
    intro = (
        "<h1>Economic Universe — Reality Map</h1>"
        '<p class="lead">Every glowing cluster is a galaxy (an investment theme / '
        "capital cycle). Heat shows priority; dim clusters are data-poor; a black-hole "
        "marker flags red-team risk; a warning halo flags a crowded / euphoric trade. "
        "This is a read-only projection — no ranking, no live data. Navigate inward: "
        "galaxy → value chain → bottleneck star → candidate cockpit.</p>"
    )
    cards = "".join(_cluster_card(c) for c in view.clusters)
    body = intro + '<div class="grid-cards">{0}</div>'.format(cards)
    return _page("Economic Universe — Reality Map", "universe.html", body)


# --------------------------------------------------------------------------- #
# B. Galaxy (theme zoom) — tabbed by galaxy                                   #
# --------------------------------------------------------------------------- #
def _planet_mini(p: PlanetCandidateView) -> str:
    origin = _badge("REAL evidence slice", "real") if p.is_real else _badge("DEMO", "demo")
    cockpit = ('<a href="{0}">open cockpit →</a>'.format(_esc(p.cockpit_link))
               if p.cockpit_link else '<span class="note">cockpit for real candidates only</span>')
    rt = _badge("red-team: {0}".format(p.red_team_label), "hazard") if (
        (p.red_team_label or "").lower() in ("concern", "fail")) else _badge(
        "red-team: {0}".format(p.red_team_label or "n/a"))
    orb = _orb(p.visual_size_px, p.glow_level, p.magnitude_missing,
               "market cap (DEMO)", p.market_cap)
    cls = "card dashed-outline" if p.magnitude_missing else "card"
    return (
        '<div class="{cls}">'
        '<p class="title">{company} {origin}</p>'
        '<p class="sub">{role} · proximity: {prox}</p>'
        "{orb}"
        "<p>{inv} {timing} {rt} {rec}</p>"
        '<p class="qualifier">{qual}: <b>{ticker}</b></p>'
        "<p>{q} · evidence {ev} · {cockpit} · "
        '<a href="{locate}">locate in universe →</a></p>'
        "</div>"
    ).format(
        cls=cls, company=_esc(p.company), origin=origin, role=_esc(p.value_chain_role),
        prox=_esc(p.proximity_to_bottleneck), orb=orb,
        inv=_badge("investability: {0}".format(p.investability_label)),
        timing=_badge(p.timing_label), rt=rt,
        rec=_badge("recommendation: {0}".format(p.recommendation_label)),
        qual=_esc(p.security_mapping_qualifier), ticker=_esc(p.ticker),
        q=_quality_badge(p.data_quality), ev=_esc(p.evidence_count),
        cockpit=cockpit, locate=_esc(p.locate_link))


def _galaxy_section(t: GalaxyThemeView) -> str:
    c = t.cluster
    header = (
        '<h2 id="g-{slug}">{name}</h2>'
        "<p>{heat} {prio} {q} {demo}</p>"
        '<table class="kv">'
        "<tr><th>Megatrend</th><td>{mega}</td></tr>"
        "<tr><th>Capital cycle</th><td>{cyc}</td></tr>"
        "<tr><th>Why now</th><td>{now}</td></tr>"
        "<tr><th>Why before obvious</th><td>{before}</td></tr>"
        "<tr><th>Signal convergence</th><td>{conv}</td></tr>"
        "<tr><th>Maturity / timing</th><td>{mat}</td></tr>"
        "</table>"
    ).format(
        slug=_esc(c.slug), name=_esc(c.theme_name),
        heat=_badge("heat: {0}".format(c.heat_label)),
        prio=_badge(c.priority_label), q=_quality_badge(c.data_quality),
        demo=_badge("DEMO terrain", "demo"), mega=_esc(c.megatrend), cyc=_esc(c.capital_cycle),
        now=_esc(t.why_now), before=_esc(t.why_before_obvious), conv=_esc(c.signal_convergence),
        mat=_esc(c.maturity_timing))

    signals = (
        "<h3>Signals — confirmed vs speculative</h3>"
        "<h4>Confirmed</h4>{conf}<h4>Speculative / unconfirmed</h4>{spec}"
    ).format(conf=_list(t.confirmed_signals), spec=_list(t.speculative_signals))

    catalysts = (
        "<h3>Catalysts</h3><h4>Positive</h4>{pos}<h4>Negative</h4>{neg}"
    ).format(pos=_list(t.positive_catalysts), neg=_list(t.negative_catalysts))

    redteam = '<div class="hazard-box"><h4>Red-team notes</h4>{0}</div>'.format(
        _list(t.red_team_notes))
    gaps = _gap_box("Data gaps", t.data_gaps)

    links = ["<h3>Explore inward</h3><p>"]
    for ss in t.solar_systems:
        links.append('<a href="solar_system.html#ss-{0}">value chain: {1} →</a> '.format(
            _esc(ss.slug), _esc(ss.name)))
    for s in t.stars:
        links.append('<a href="star.html#star-{0}">bottleneck star: {1} →</a> '.format(
            _esc(s.slug), _esc(s.constrained_node)))
    links.append("</p>")

    planets = "<h3>Top candidate planets</h3>" + '<div class="grid-cards">{0}</div>'.format(
        "".join(_planet_mini(p) for p in t.planets))

    return header + signals + catalysts + redteam + gaps + "".join(links) + planets


def render_galaxy(view: EconomicUniverseView) -> str:
    tabs = []
    panels = []
    for i, t in enumerate(view.themes):
        c = t.cluster
        active = " active" if i == 0 else ""
        shown = " shown" if i == 0 else ""
        tabs.append(
            '<span class="tab{active}" data-tab-group="galaxies" '
            'data-tab-target="panel-{slug}">{name}</span>'.format(
                active=active, slug=_esc(c.slug), name=_esc(c.theme_name)))
        panels.append(
            '<div id="panel-{slug}" data-tab-panel data-tab-group="galaxies"'
            ' class="galaxy-panel{shown}">{body}</div>'.format(
                slug=_esc(c.slug), shown=shown, body=_galaxy_section(t)))
    intro = (
        "<h1>Galaxies — Theme Zoom</h1>"
        '<p class="lead">Each galaxy: megatrend, why-now, why-before-obvious, confirmed '
        "vs speculative signals, positive and negative catalysts, red-team notes and data "
        "gaps — with links inward to its value chains, bottleneck stars and candidate "
        "planets. Use the galaxy filter tabs.</p>"
    )
    body = intro + '<div class="tabbar">{0}</div>'.format("".join(tabs)) + "".join(panels)
    return _page("Galaxies — Theme Zoom", "galaxy.html", body)


# --------------------------------------------------------------------------- #
# C. Solar System (value chain)                                              #
# --------------------------------------------------------------------------- #
def _node_row(n) -> str:
    missing = _badge("missing: {0}".format("; ".join(n.missing_data)), "gap") if n.missing_data else ""
    dyn = _badge("dynamic-evidence: {0}".format(
        "attached" if n.has_dynamic_evidence else "empty (static terrain)"), "")
    return (
        "<tr><td><span class='tier-tag'>{tier}</span><br>{nid}</td>"
        "<td>{role}</td><td>{econ}</td><td>{exp}</td>"
        "<td>{eq} {missing}</td><td>{dyn}</td></tr>"
    ).format(
        tier=_esc(n.tier), nid=_esc(n.node_id), role=_esc(n.role),
        econ=_esc(n.economics_capture), exp=_esc(n.bottleneck_exposure),
        eq=_esc(n.evidence_quality), missing=missing, dyn=dyn)


def _solar_section(ss: SolarSystemValueChainView) -> str:
    rows = "".join(_node_row(n) for n in ss.nodes)
    table = (
        '<table class="chain"><tr><th>node (tier)</th><th>role</th>'
        "<th>economics capture</th><th>bottleneck exposure</th>"
        "<th>evidence quality / missing</th><th>static/dynamic</th></tr>{0}</table>"
    ).format(rows)
    # Missing supplier / TAM / moat visibility.
    all_missing = []
    for n in ss.nodes:
        for m in n.missing_data:
            all_missing.append("{0}: {1}".format(n.node_id, m))
    gaps = _gap_box("Missing data (supplier / TAM / moat visibility)", all_missing)
    # Security / ticker mapping AFTER the value-chain / winner mapping.
    mapping_rows = []
    for role, tickers in ss.node_ticker_map:
        mapping_rows.append("<tr><td>{0}</td><td>{1}</td></tr>".format(
            _esc(role), _esc(", ".join(tickers))))
    mapping_tbl = (
        '<div class="warn-box"><h4>{qual}</h4>'
        '<table class="chain"><tr><th>value-chain node (winner context)</th>'
        "<th>candidate tickers</th></tr>{rows}</table></div>"
    ).format(qual=_esc(ss.security_mapping_qualifier),
             rows="".join(mapping_rows) or "<tr><td colspan='2'>(none mapped)</td></tr>")
    header = (
        '<h2 id="ss-{slug}">{name} {demo}</h2>'
        "<p>Galaxy: <a href='galaxy.html#g-{gslug}'>{galaxy}</a> · {desc}</p>"
    ).format(slug=_esc(ss.slug), name=_esc(ss.name), demo=_badge("DEMO", "demo"),
             gslug=_esc(ss.galaxy_slug), galaxy=_esc(ss.galaxy_name), desc=_esc(ss.description))
    return header + table + gaps + mapping_tbl


def render_solar_system(view: EconomicUniverseView) -> str:
    intro = (
        "<h1>Value Chains — Solar Systems</h1>"
        '<p class="lead">Each solar system is a value chain: layered nodes from upstream '
        "through infrastructure, enabling-tech, suppliers, supplier-of-supplier "
        "placeholders, integrators, customers and downstream. Security / ticker mapping "
        "is shown only AFTER the value-chain / winner context — never as the entry point. "
        "Missing supplier / TAM / moat data stays visible.</p>"
    )
    sections = []
    for t in view.themes:
        for ss in t.solar_systems:
            sections.append(_solar_section(ss))
    body = intro + "".join(sections)
    return _page("Value Chains — Solar Systems", "solar_system.html", body)


# --------------------------------------------------------------------------- #
# D. Star (bottleneck) — the 10x discovery layer                            #
# --------------------------------------------------------------------------- #
def _star_section(s: StarBottleneckView) -> str:
    rows = "".join([
        "<tr><th>Type</th><td>{0}</td></tr>".format(_esc(s.star_type)),
        "<tr><th>Constrained node</th><td>{0}</td></tr>".format(_esc(s.constrained_node)),
        "<tr><th>Severity</th><td>{0}</td></tr>".format(_esc(s.severity)),
        "<tr><th>Expected duration</th><td>{0}</td></tr>".format(_esc(s.duration)),
        "<tr><th>Resolution risk</th><td>{0}</td></tr>".format(_esc(s.resolution_risk)),
    ])
    return (
        '<h2 id="star-{slug}">Bottleneck: {node} {demo}</h2>'
        "<p>Galaxy: <a href='galaxy.html#g-{gslug}'>{galaxy}</a> · "
        "the 10x discovery layer — where a constrained node concentrates economics.</p>"
        '<table class="kv">{rows}</table>'
        "<h4>Beneficiaries</h4>{ben}"
        "<h4>Losers (constrained / disadvantaged)</h4>{los}"
        "<h4>Evidence</h4>{ev}"
        "{gaps}"
    ).format(
        slug=_esc(s.slug), node=_esc(s.constrained_node), demo=_badge("DEMO", "demo"),
        gslug=_esc(s.galaxy_slug), galaxy=_esc(s.galaxy_name), rows=rows,
        ben=_list(s.beneficiaries), los=_list(s.losers), ev=_list(s.evidence),
        gaps=_gap_box("Data gaps at this bottleneck", s.data_gaps))


def render_star(view: EconomicUniverseView) -> str:
    intro = (
        "<h1>Bottleneck Stars — The 10x Discovery Layer</h1>"
        '<p class="lead">Each star is a bottleneck: the constrained node whose scarcity '
        "concentrates economics. Type, constrained node, severity, duration, beneficiaries, "
        "losers, resolution risk, evidence and data gaps — the layer where asymmetric "
        "opportunities are discovered before they are obvious.</p>"
    )
    sections = []
    for t in view.themes:
        for s in t.stars:
            sections.append(_star_section(s))
    body = intro + "".join(sections)
    return _page("Bottleneck Stars", "star.html", body)


# --------------------------------------------------------------------------- #
# E. Cockpit (IREN) — the ACCEPTED renderer, wrapped                         #
# --------------------------------------------------------------------------- #
def _cockpit_wrapper() -> str:
    strip = (
        '<div style="position:sticky;top:0;z-index:50;background:#0a0f24;color:#c7d0f5;'
        'padding:.5rem 1rem;font:600 13px sans-serif;border-bottom:1px solid #26315f">'
        '{0}</div>'.format(_esc(STATUS_STRIP_TEXT)))
    links = []
    for label, fname in _NAV:
        links.append(
            '<a href="{0}" style="color:#7c8cff;text-decoration:none;'
            'margin-right:.9rem;font:600 13px sans-serif">{1}</a>'.format(
                _esc(fname), _esc(label)))
    nav = (
        '<div style="background:#0e1330;padding:.55rem 1rem;border-bottom:1px solid #26315f">'
        '{0}</div>'.format("".join(links)))
    note = (
        '<div style="background:#1a1030;color:#e3d9ff;padding:.6rem 1rem;'
        'font:600 13px sans-serif;border-bottom:1px solid #5a3fb0">'
        'IREN planet — REAL evidence-alpha slice. Rendered by the ACCEPTED cockpit '
        'renderer (render_cockpit_html). Ticker/security mapping is derived after '
        'value-chain / winner mapping inside the cockpit. Manual review required.</div>')
    return strip + nav + note


def render_cockpit(iren_slice) -> str:
    doc = render_cockpit_html(iren_slice.cockpit_view)
    return doc.replace("<body>", "<body>\n" + _cockpit_wrapper(), 1)


# --------------------------------------------------------------------------- #
# F. CIO Dashboard                                                            #
# --------------------------------------------------------------------------- #
def _card(c: CandidateCardView) -> str:
    origin = _badge("REAL slice", "real") if c.is_real else _badge("DEMO", "demo")
    cockpit = ('<a href="{0}">open cockpit →</a>'.format(_esc(c.cockpit_link))
               if c.cockpit_link else '<span class="note">cockpit for real candidates only</span>')
    cross = " ".join(_badge(b, "hazard" if "Red-Team" in b else "gap") for b in c.cross_cut_buckets)
    rt_cls = "hazard" if (c.red_team_label or "").lower() in ("concern", "fail") else ""
    capstruct = _badge("capital-structure risk", "hazard") if c.capital_structure_risk else ""
    auth = " ".join(_badge(b, "") for b in c.source_authority_badges)
    orb = _orb(c.visual_size_px, c.glow_level, c.magnitude_missing,
               "market cap (DEMO)", c.market_cap)
    cls = "card dashed-outline" if c.magnitude_missing else "card"
    return (
        '<div class="{cls}">'
        '<p class="title">{label}: {company} {origin}</p>'
        '<p class="sub">{galaxy} · {role} · proximity: {prox}</p>'
        "{orb}"
        "<p>{inv} {timing} {rt} {rec} {caps}</p>"
        "<p>{cross}</p>"
        '<p class="qualifier">{qual}: <b>{ticker}</b></p>'
        "<p>{auth}</p>"
        '<p>{q} · evidence {ev} · {cockpit} · '
        '<a href="{locate}">locate in universe →</a></p>'
        "</div>"
    ).format(
        cls=cls, label=_esc(c.card_label), company=_esc(c.company), origin=origin,
        galaxy=_esc(c.galaxy_name), role=_esc(c.value_chain_role),
        prox=_esc(c.proximity_to_bottleneck), orb=orb,
        inv=_badge("investability: {0}".format(c.investability_label)),
        timing=_badge(c.timing_label),
        rt=_badge("red-team: {0}".format(c.red_team_label or "n/a"), rt_cls),
        rec=_badge("recommendation: {0}".format(c.recommendation_label)), caps=capstruct,
        cross=cross or _badge("no cross-cut alerts", "q-high"),
        qual=_esc(c.security_mapping_qualifier), ticker=_esc(c.ticker), auth=auth,
        q=_quality_badge(c.data_quality), ev=_esc(c.evidence_count),
        cockpit=cockpit, locate=_esc(c.locate_link))


def _bucket(b: BucketView) -> str:
    if not b.cards:
        cards = '<p class="note">(no candidates in this bucket)</p>'
    else:
        cards = '<div class="grid-cards">{0}</div>'.format("".join(_card(c) for c in b.cards))
    return (
        '<div class="bucket"><h3>{name} <span class="count">'
        "({count}) — {desc}</span></h3>{cards}</div>"
    ).format(name=_esc(b.name), count=len(b.cards), desc=_esc(b.description), cards=cards)


def render_dashboard(dash: CIODashboardView) -> str:
    banner = '<div class="banner">{0}</div>'.format(_esc(dash.banner))
    intro = (
        "<h1>CIO Dashboard — Candidate Buckets</h1>"
        '<p class="lead">Candidates are grouped by their EXISTING pipeline statuses '
        "(investability_assessment / timing_confirmation / red-team verdict / "
        "recommendation_status). There is no composite ranking metric, no live "
        "ranking, and no trade-execution affordance — every card is a manual review "
        "candidate. Cards link to the cockpit and to their location in the universe.</p>"
    )
    note = (
        '<p class="note">Buckets are read-only groupings of existing statuses. '
        "Within-bucket ordering reuses an existing field (thesis_confidence for the real "
        "candidate; evidence_count for demo terrain) — it is not a new composite figure. "
        "live ranking not enabled.</p>"
    )
    buckets = "".join(_bucket(b) for b in dash.buckets)
    body = intro + banner + note + buckets
    return _page("CIO Dashboard", "dashboard.html", body)


# --------------------------------------------------------------------------- #
# G. Data Quality / Provenance                                               #
# --------------------------------------------------------------------------- #
def render_data_quality(dq: DataQualityView) -> str:
    rows = "".join([
        "<tr><th>Run mode</th><td>{0}</td></tr>".format(_esc(dq.run_mode)),
        "<tr><th>Fixture / demo status</th><td>{0}</td></tr>".format(_esc(dq.fixture_demo_status)),
        "<tr><th>Live data</th><td>not enabled</td></tr>",
        "<tr><th>Scheduler status</th><td>{0}</td></tr>".format(_esc(dq.scheduler_status)),
        "<tr><th>Broker automation status</th><td>{0}</td></tr>".format(
            _esc(dq.broker_automation_status)),
        "<tr><th>Manual review required</th><td>{0}</td></tr>".format(
            "yes" if dq.manual_review_required else "no"),
        "<tr><th>Source hierarchy</th><td>{0}</td></tr>".format(_esc(dq.source_hierarchy)),
    ])
    counts = "".join([
        "<tr><th>SEC canonical observations</th><td>{0}</td></tr>".format(_esc(dq.canonical_count)),
        "<tr><th>FMP convenience observations</th><td>{0}</td></tr>".format(
            _esc(dq.convenience_count)),
        "<tr><th>yfinance fallback observations</th><td>{0}</td></tr>".format(
            _esc(dq.fallback_count)),
        "<tr><th>Signal observations (inferred)</th><td>{0}</td></tr>".format(
            _esc(dq.signal_observation_count)),
        "<tr><th>Factual observations (OHLCV/profile/ownership/quote)</th><td>{0}</td></tr>".format(
            _esc(dq.factual_observation_count)),
    ])
    body = (
        "<h1>Data Quality &amp; Provenance</h1>"
        '<p class="lead">Run mode, source hierarchy, conflict resolution, overridden facts, '
        "data gaps and the provenance chain for the one real candidate (IREN). Live data, "
        "scheduler and broker automation are all off.</p>"
        + _badge("REAL subject: {0}".format(dq.real_subject), "real") + " "
        + _badge("DEMO terrain for all other planets", "demo")
        + '<h2>Run &amp; boundary status</h2><table class="kv">{run}</table>'.format(run=rows)
        + '<h2>Source hierarchy — authority counts</h2>'
        + '<p class="note">SEC canonical &gt; FMP convenience &gt; yfinance fallback. '
        "Signal observations drive reasoning; factual observations stay partitioned.</p>"
        + '<table class="kv">{counts}</table>'.format(counts=counts)
        + "<h2>Conflict warnings (arbitration)</h2>" + _list(dq.conflict_warnings, "no conflicts")
        + "<h2>Overridden facts (lost arbitration)</h2>" + _list(dq.overridden_facts, "none overridden")
        + _gap_box("Data gaps", dq.data_gaps)
        + "<h2>Provenance chain (Observation → … → Ticket preview)</h2>"
        + _list(dq.provenance_chain, "no chain")
        + '<div class="hazard-box"><h4>Automation boundary</h4>'
        + "<p>Scheduler: not enabled. Broker automation: disabled. No order is placed, "
        "routed, or recorded anywhere in this UI. Manual review required.</p></div>"
    )
    return _page("Data Quality & Provenance", "data_quality.html", body)


# --------------------------------------------------------------------------- #
# Convenience: render every page from one view                               #
# --------------------------------------------------------------------------- #
def render_all_pages(view: EconomicUniverseView, iren_slice) -> Tuple[Tuple[str, str], ...]:
    """Return an ordered ((filename, html), ...) for all seven pages."""
    return (
        ("universe.html", render_universe(view)),
        ("galaxy.html", render_galaxy(view)),
        ("solar_system.html", render_solar_system(view)),
        ("star.html", render_star(view)),
        ("cockpit.html", render_cockpit(iren_slice)),
        ("dashboard.html", render_dashboard(view.dashboard)),
        ("data_quality.html", render_data_quality(view.data_quality)),
    )
