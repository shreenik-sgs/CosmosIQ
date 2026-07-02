"""Deterministic static-HTML renderer for the Economic Universe UI (010A-R).

PRESENTATION ONLY. Renders the read-only :mod:`universe_ui.view_models` projections
into four self-contained static pages with a cosmic command-center theme:

* ``universe.html`` — ONE interactive, zoomable Economic Universe page using a
  TWO-PANE model: a dominant TOP canvas (the Infinite Canvas: Universe → galaxy →
  theme → value-chain → bottleneck star → planet → moon, as zoom LEVELS inside one
  page) and a BOTTOM Intelligence Pane that re-renders for the currently selected
  object. Galaxy / Value-Chain / Star are zoom levels here, NOT separate pages.
* ``dashboard.html`` — the CIO candidate buckets (each card has "Locate in Universe"
  + "Open Cockpit").
* ``data_quality.html`` — provenance / source authority / gaps.
* ``cockpit.html`` — the ACCEPTED ``render_cockpit_html`` output for the one real
  planet (IREN), opened FROM a planet (not a top-level tab).

Guarantees for every page:

* Persistent status strip (fixture/demo · live not enabled · scheduler off · broker
  disabled · manual review).
* NO ``<form>``, NO ``<button>``, no ``onclick``, no ``type="submit"``, no
  ``fetch``/``XHR``, no buy/sell/place-order affordance. Navigation is ``<a href>``
  links plus navigation-only JS (zoom show/hide, breadcrumb, back, deep-link focus,
  bottom-pane swap, collapse) — it copies pre-rendered DOM and can never hide a gap.
* Visual object SIZE encodes economic magnitude (bounded log) and stays DECOUPLED
  from ranking / heat / buckets.
* Data gaps, conflicts and source-authority badges are always rendered.
* Deterministic: a pure function of the view — byte-identical across builds.
"""

from __future__ import annotations

import html
import math
from typing import Any, Iterable, Optional, Tuple

from infinite_canvas.render_html import render_cockpit_html

from .assets import COSMIC_CSS, NAV_JS
from .demo_universe import slugify
from .view_models import (
    BucketView,
    CandidateCardView,
    CIODashboardView,
    DataQualityView,
    EconomicUniverseView,
    GalaxyThemeView,
    NodeView,
    PlanetCandidateView,
    SolarSystemValueChainView,
    StarBottleneckView,
    assign_buckets,
    card_label_for,
)

STATUS_STRIP_TEXT = (
    "Mode: fixture/demo · Live data: not enabled · Scheduler: not enabled "
    "· Broker automation: disabled · Manual review required"
)

EVIDENCE_STRIP_TEXT = (
    "Mode: evidence_ingested_fixture · Live data: not enabled · Scheduler: not enabled "
    "· Broker automation: disabled · Manual review required"
)

# IMPLEMENTATION-010D. Real, on-demand, MANUAL-only. Every claim is a negation or a
# hedge -- no "fully live", "automated", "scheduled", "trade-ready" or "real-time" claim.
REAL_STRIP_TEXT = (
    "Mode: real evidence on demand · Manual refresh only · Not scheduled "
    "· Not broker-connected · Data may be incomplete"
)


def _origin_tokens(data_origin: str) -> Tuple[str, str]:
    """(badge text, css class) for an object's data origin. Demo/live-fixture keep the
    ``DEMO`` wording (so demo output is byte-identical); evidence-ingested objects are
    honestly labelled ``evidence-ingested``; real on-demand objects are labelled
    ``real-source`` -- never ``live``."""
    up = (data_origin or "").upper()
    if up.startswith("REAL"):
        return ("real-source (manual)", "evidence")
    if up.startswith("EVIDENCE"):
        return ("evidence-ingested", "evidence")
    return ("DEMO", "demo")


def _origin_suffix(data_origin: str) -> str:
    return _origin_tokens(data_origin)[0]


def _strip_for_mode(mode: str) -> str:
    if mode == "real_evidence_on_demand":
        return REAL_STRIP_TEXT
    if mode == "evidence_ingested_fixture":
        return EVIDENCE_STRIP_TEXT
    return STATUS_STRIP_TEXT


def _terrain_notice(view) -> str:
    """The visible 'terrain incomplete' notice for an evidence / real view (else '')."""
    if getattr(view, "mode", "") not in ("evidence_ingested_fixture",
                                         "real_evidence_on_demand"):
        return ""
    terrain = getattr(view, "terrain", None)
    for gap in getattr(terrain, "data_gaps", ()) or ():
        if str(gap).lower().startswith("terrain incomplete"):
            return str(gap)
    return ("terrain incomplete — evidence-ingested single candidate; missing-data "
            "placeholders shown, nothing fabricated")

# Only THREE top-level product sections. The cockpit opens FROM a planet.
_NAV = (
    ("Economic Universe", "universe.html"),
    ("CIO Dashboard", "dashboard.html"),
    ("Data Quality", "data_quality.html"),
)

_HEAT_GLOW = {"hot": 3, "warm": 2, "cool": 2, "dim": 1}


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


def _ev_class(quality: str) -> str:
    q = (quality or "").lower()
    if q == "sparse":
        return "ev-sparse"
    if q == "low":
        return "ev-low"
    return ""


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


def _status_strip(strip_text: Optional[str] = None) -> str:
    return '<div class="status-strip">{0}</div>'.format(
        _esc(strip_text if strip_text is not None else STATUS_STRIP_TEXT))


def _command_bar(current_file: str) -> str:
    links = []
    for label, fname in _NAV:
        cls = "navlink here" if fname == current_file else "navlink"
        links.append('<a class="{0}" href="{1}">{2}</a>'.format(cls, _esc(fname), _esc(label)))
    brand = ('<div class="brand">SUDARSHAN<small>ECONOMIC UNIVERSE · '
             'READ-ONLY PROJECTION</small></div>')
    return '<div class="command-bar">{0}{1}</div>'.format(brand, "".join(links))


def _footer() -> str:
    return (
        "<footer>"
        "SUDARSHAN Economic Universe — IMPLEMENTATION-010A-R. Read-only projection of "
        "existing pipeline statuses and hand-authored DEMO terrain. No live data, no "
        "ranking, no scheduler, no broker, no order affordance. "
        "Every candidate requires manual review."
        "</footer>"
    )


def _page(title: str, current_file: str, body: str, full_screen: bool = False,
          strip_text: Optional[str] = None) -> str:
    """Render a full page. ``full_screen`` gives the Economic Universe page the
    immersive SKY shell: a sticky status strip + command bar, then a full-viewport
    telescope universe HERO, with the intelligence pane BELOW the fold (the page
    scrolls naturally). Other pages keep the document ``.wrap`` layout."""
    head = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>{0}</title>".format(_esc(title)),
        "<style>{0}</style>".format(COSMIC_CSS),
        "</head>",
    ]
    if full_screen:
        middle = [
            '<body class="sky">',
            _status_strip(strip_text),
            _command_bar(current_file),
            body,  # body is the .universe-app (hero + below-fold intel section)
        ]
    else:
        middle = [
            "<body>",
            _status_strip(strip_text),
            _command_bar(current_file),
            '<div class="wrap">',
            body,
            _footer(),
            "</div>",
        ]
    tail = [
        "<script>{0}</script>".format(NAV_JS),
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(head + middle + tail)


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
    """A visual-size orb. SIZE = economic magnitude (bounded log scale); GLOW = status;
    a dashed outline flags missing magnitude. The RAW value is always shown — size is
    never the only signal and never a ranking."""
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
# Zoom-path helpers (must match view_models.planet_universe_path)             #
# --------------------------------------------------------------------------- #
def _path_galaxy(gslug: str) -> str:
    return "universe/g:{0}".format(gslug)


def _path_theme(gslug: str) -> str:
    return "universe/g:{0}/t:{0}".format(gslug)


def _path_vc(gslug: str, vcslug: str) -> str:
    return _path_theme(gslug) + "/vc:{0}".format(vcslug)


def _path_star(gslug: str, vcslug: str, stslug: str) -> str:
    return _path_vc(gslug, vcslug) + "/st:{0}".format(stslug)


# Stable ids into the hidden intel store (one blob per unique object).
def _intel_id_galaxy(slug: str) -> str:
    return "intel-g-" + slug


def _intel_id_theme(slug: str) -> str:
    return "intel-t-" + slug


def _intel_id_vc(vcslug: str) -> str:
    return "intel-vc-" + vcslug


def _intel_id_star(stslug: str) -> str:
    return "intel-st-" + stslug


def _intel_id_planet(p: PlanetCandidateView) -> str:
    return "intel-pl-{0}-{1}".format(p.galaxy_slug, slugify(p.ticker))


def _intel_id_moon(node_id: str) -> str:
    return "intel-mo-" + slugify(node_id)


# --------------------------------------------------------------------------- #
# Deep-space scene: deterministic starfield + object positioning              #
# --------------------------------------------------------------------------- #
def _space_background() -> str:
    """A telescopic deep-field backdrop built entirely from CSS layers (no per-star
    DOM, no randomness, no remote image): a galactic-core bloom, THREE tiled star
    layers (far/mid/near for depth), soft nebula clouds, a dust-lane silhouette, and a
    vignette -- wrapped in ``.sky-bg`` so JS can PARALLAX it a fraction of the pan/zoom.
    Byte-stable; the background recedes so the economic objects lead."""
    return (
        '<div class="sky-bg" aria-hidden="true">'
        # the LOCAL telescope deep-field asset (dense stars / nebulae / dust / glow)
        '<div class="deep-space-bg"></div>'
        '<div class="space-glow"></div>'
        '<div class="star-far"></div>'
        '<div class="star-mid"></div>'
        '<div class="star-near"></div>'
        '<div class="nebula neb-1"></div>'
        '<div class="nebula neb-2"></div>'
        '<div class="nebula neb-3"></div>'
        '<div class="dust-lane"></div>'
        "</div>"
        '<div class="vignette" aria-hidden="true"></div>'
    )


def _scene_position(index: int, total: int) -> Tuple[float, float]:
    """A deterministic (left%, top%) for a body: a spaced golden-angle spiral.

    Single-object levels are centred; multi-object levels spiral out from the centre
    so bodies don't overlap into unreadability. Pure math -> byte-stable."""
    if total <= 1:
        return (50.0, 47.0)
    golden = 2.399963229728653  # golden angle (radians)
    ang = index * golden
    r = 15.0 + 27.0 * math.sqrt((index + 1) / float(total))
    left = 50.0 + r * math.cos(ang) * 1.18
    top = 47.0 + r * math.sin(ang)
    left = max(9.0, min(91.0, left))
    top = max(12.0, min(85.0, top))
    return (left, top)


def _orbit_svg(positions, focal: Tuple[float, float] = (50.0, 47.0)) -> str:
    """Faint relationship/orbit lines from a level's focal point (the parent) to each
    child body -- so economic relationships (parent->children, star<-planets,
    planet<-moons) are visible. Deterministic; purely contextual."""
    fx, fy = focal
    segs = []
    for (x, y) in positions:
        if abs(x - fx) < 0.05 and abs(y - fy) < 0.05:
            continue
        segs.append(
            '<line x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{3:.2f}"></line>'.format(
                fx, fy, x, y))
    if not segs:
        return ""
    return (
        '<svg class="orbit-lines" viewBox="0 0 100 100" preserveAspectRatio="none" '
        'aria-hidden="true">{0}</svg>'
    ).format("".join(segs))


def _universe_scatter(index: int, total: int) -> Tuple[float, float]:
    """Deterministic WIDE scatter for the L0 galaxies across an open field.

    NO centre anchor and NO spiral-from-centre: galaxies float as a field of regions
    across a canvas wider than the viewport, so the Universe level has no 'centre of
    the universe'. Pure integer math (a jittered grid; no random, no clock) -> byte
    stable."""
    if total <= 1:
        return (50.0, 47.0)
    cols = int(math.ceil(math.sqrt(total)))
    rows = int(math.ceil(total / float(cols)))
    col = index % cols
    row = index // cols
    x = 8.0 + (col + 0.5) * (84.0 / cols)
    y = 16.0 + (row + 0.5) * (68.0 / rows)
    # deterministic per-index jitter (fixed integer hash; no random/clock)
    jx = (((index * 2654435761) % 1000) / 1000.0) - 0.5
    jy = (((index * 40503 + 7) % 1000) / 1000.0) - 0.5
    x += jx * (52.0 / cols)
    y += jy * (44.0 / rows)
    return (max(5.0, min(95.0, x)), max(12.0, min(88.0, y)))


def _edge_svg(edges, pos_by_slug) -> str:
    """Semantic economic-relationship lines between related galaxies at the UNIVERSE
    level. Draws ONE line per explicit edge whose BOTH endpoints exist -- never a line
    to a centre, never hub-and-spoke, never a line for an unrelated pair. If an edge
    references a missing galaxy it is skipped. Deterministic."""
    segs = []
    for e in edges:
        a = pos_by_slug.get(e.source_slug)
        b = pos_by_slug.get(e.target_slug)
        if not a or not b:
            continue
        strength = (e.strength or "").lower()
        cls = "rel-" + (strength if strength in ("strong", "medium", "weak") else "weak")
        title = "{0} ↔ {1} — {2}: {3} (DEMO · strength {4} · evidence {5})".format(
            e.source_name, e.target_name, e.type, e.reason, e.strength, e.evidence_quality)
        segs.append(
            '<line class="{cls}" x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{3:.2f}">'
            "<title>{title}</title></line>".format(
                a[0], a[1], b[0], b[1], cls=cls, title=_esc(title)))
    # Even with no semantic edges (e.g. a single-theme evidence terrain) keep the
    # semantic rel-lines scaffold -- NEVER a centre / hub-and-spoke fallback.
    return (
        '<svg class="rel-lines" viewBox="0 0 100 100" preserveAspectRatio="none" '
        'aria-hidden="true">{0}</svg>'
    ).format("".join(segs))


# Directional economic-FLOW layout (value-chain level): upstream -> ... -> customers.
_TIER_RANK = {"upstream": 0, "supplier-of-supplier": 1, "suppliers": 2,
              "enabling-tech": 3, "infrastructure": 4, "integrators": 5,
              "customers": 6, "downstream": 7}


def _flow_position(index: int, total: int, row: float = 66.0) -> Tuple[float, float]:
    """A left->right flow slot across the canvas (upstream at left, demand at right)."""
    if total <= 1:
        return (50.0, row)
    x = 12.0 + 76.0 * (index / float(total - 1))
    # a gentle zig-zag so labels don't collide
    y = row + (-3.5 if index % 2 else 3.5)
    return (x, y)


def _flow_svg(positions) -> str:
    """Faint directional connectors + arrowheads along a left->right economic flow.
    Extends the orbit-line SVG; deterministic."""
    if len(positions) < 2:
        return ""
    parts = []
    for (x1, y1), (x2, y2) in zip(positions, positions[1:]):
        parts.append('<line x1="{0:.2f}" y1="{1:.2f}" x2="{2:.2f}" y2="{3:.2f}"></line>'.format(
            x1, y1, x2, y2))
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        parts.append(
            '<polygon points="{0:.2f},{1:.2f} {2:.2f},{3:.2f} {2:.2f},{4:.2f}"></polygon>'.format(
                mx + 1.1, my, mx - 0.7, my - 1.0, my + 1.0))
    return (
        '<svg class="orbit-lines flow-lines" viewBox="0 0 100 100" '
        'preserveAspectRatio="none" aria-hidden="true">{0}</svg>'
    ).format("".join(parts))


def _legend() -> str:
    """A compact, collapsible legend card explaining ALL EIGHT visual channels."""
    rows = (
        ("size", "economic magnitude"),
        ("brightness", "heat / signal convergence"),
        ("color", "status / risk"),
        ("link line", "economic relationship (hover)"),
        ("orbit distance", "directness of exposure"),
        ("halo", "catalyst / crowding"),
        ("red shadow", "red-team / dilution / insolvency"),
        ("opacity", "evidence quality"),
        ("dashed outline", "missing data"),
    )
    items = "".join(
        '<div class="lg-row"><span class="lg-key">{0}</span>'
        '<span class="lg-val">{1}</span></div>'.format(_esc(k), _esc(v)) for k, v in rows)
    return (
        '<div class="legend">'
        '<div class="legend-head" data-collapse-target="legend-body">'
        '<span class="micro">Legend</span><span class="lg-toggle">▾</span></div>'
        '<div class="legend-body" id="legend-body">{0}</div></div>'
    ).format(items)


# --------------------------------------------------------------------------- #
# Cosmic body (a luminous, absolutely-positioned object in the scene)          #
# --------------------------------------------------------------------------- #
_BODY_KIND = {"galaxy": "galaxy", "theme": "milkyway", "value_chain": "nebula",
              "star": "star", "planet": "planet", "moon": "moon"}

# Each zoom level gets a distinct CSS class so a glance tells you where you are.
_LEVEL_CLASS = {0: "level-universe", 1: "level-galaxy", 2: "level-theme",
                3: "level-valuechain", 4: "level-star", 5: "level-planet"}


def _cosmic_object(*, kind: str, path: str, target_path: str, target_level,
                   title: str, sub: str, size_px: int, glow: int, dashed: bool,
                   redshadow: bool, halo: bool, ev_class: str, size_label: str,
                   size_raw: str, badges: str, intel_id: str,
                   pos: Tuple[float, float], variant: str = "",
                   extra_class: str = "", marker: str = "", preview_html: str = "",
                   cockpit: str = "") -> str:
    """A luminous body positioned in the scene. It carries ONLY its glowing shape +
    a small NAME label + a hover preview chip; its full intelligence lives (once) in
    the hidden intel store and is referenced by ``data-intel`` for the bottom pane."""
    left, top = pos
    classes = ["cosmic-object", "k-{0}".format(kind),
               "body-{0}".format(_BODY_KIND.get(kind, "planet")),
               "glow-{0}".format(int(glow) if glow in (1, 2, 3) else 1)]
    if variant:
        classes.append("variant-{0}".format(variant))
    if dashed:
        classes.append("dashed-outline")
    if redshadow:
        classes.append("redshadow")
    if halo:
        classes.append("halo")
    if ev_class:
        classes.append(ev_class)
    if extra_class:
        classes.append(extra_class)
    attrs = 'data-kind="{0}" data-path="{1}" data-intel="{2}" data-title="{3}"'.format(
        _esc(kind), _esc(path), _esc(intel_id), _esc(title))
    if target_path:
        attrs += ' data-target-path="{0}" data-target-level="{1}"'.format(
            _esc(target_path), _esc(target_level))
    if cockpit:
        attrs += ' data-cockpit="{0}"'.format(_esc(cockpit))
    gapbadge = (' <span class="badge gap">magnitude missing — neutral size</span>'
                if dashed else "")
    body = '<div class="body" style="width:{s}px;height:{s}px"></div>'.format(s=int(size_px))
    marker_html = '<div class="body-marker micro">{0}</div>'.format(_esc(marker)) if marker else ""
    if preview_html:
        tip = '<span class="body-tip">{0}</span>'.format(preview_html)
    else:
        tip = (
            '<span class="body-tip">{sub}<br>size ∝ {label}: <b>{raw}</b> '
            "(bounded log; not a ranking)<br>{badges}{gap}</span>"
        ).format(sub=_esc(sub), label=_esc(size_label), raw=_esc(size_raw),
                 badges=badges, gap=gapbadge)
    style = "left:{0:.2f}%;top:{1:.2f}%".format(left, top)
    return (
        '<div class="{cls}" style="{style}" {attrs}>'
        "{marker}{body}"
        '<div class="body-label">{title}{tip}</div>'
        "</div>"
    ).format(cls=" ".join(classes), style=style, attrs=attrs, marker=marker_html,
             body=body, title=_esc(title), tip=tip)


def _level_panel(*, level: int, path: str, parent: str, crumb: str, kind: str,
                 title: str, objects_html: str, intel_id: str, active: bool) -> str:
    """A zoom level: ONLY its luminous bodies inside a pan/zoom ``.scene-transform``.

    No caption, table, or intel renders here -- the level's intelligence lives in the
    hidden store and is referenced by ``data-intel`` for the bottom pane."""
    parent_attr = ' data-parent="{0}"'.format(_esc(parent)) if parent else ""
    level_cls = _LEVEL_CLASS.get(level, "level-universe")
    bodies = (
        '<div class="scene-bodies"><div class="scene-transform">{0}</div></div>'
    ).format(objects_html or "")
    return (
        '<section class="level-panel scene-layer {lvlcls}{act}" data-level="{lvl}"'
        ' data-path="{path}"{par} data-crumb="{crumb}" data-intel="{intel}">'
        "{bodies}"
        "</section>"
    ).format(lvlcls=level_cls, act=" active" if active else "", lvl=level, path=_esc(path),
             par=parent_attr, crumb=_esc(crumb), intel=_esc(intel_id), bodies=bodies)


# --------------------------------------------------------------------------- #
# Bottom-pane Intelligence templates (organise existing data; compute nothing) #
# --------------------------------------------------------------------------- #
def _authority_badges(p: PlanetCandidateView) -> str:
    return " ".join(_badge(b, "") for b in p.source_authority_badges)


# --- executive-briefing primitives ---------------------------------------- #
def _brief_header(eyebrow: str, title: str, badges: str = "") -> str:
    return (
        '<div class="brief-header"><div class="brief-heading">'
        '<div class="micro brief-eyebrow">{0}</div>'
        '<h3 class="brief-title">{1}</h3></div>'
        '<div class="brief-badges">{2}</div></div>'
    ).format(_esc(eyebrow), _esc(title), badges)


def _brief_card(label: str, body: str, extra: str = "") -> str:
    cls = "brief-card {0}".format(extra) if extra else "brief-card"
    return (
        '<section class="{0}"><div class="micro brief-label">{1}</div>'
        '<div class="brief-body">{2}</div></section>'
    ).format(cls, _esc(label), body)


# The five fixed CIO framings. These ONLY reorganise existing view-model fields --
# they invent no new conclusion, score, or reasoning.
_EXEC_FRAMES = ("What this is", "Why it matters", "Where the alpha could be",
                "What could go wrong", "What to inspect next")


def _exec_header(texts) -> str:
    """A five-line executive header (What this is / Why it matters / Where the alpha
    could be / What could go wrong / What to inspect next). Pure reorganisation."""
    texts = list(texts)
    rows = "".join(
        '<div class="exec-line"><span class="micro exec-frame">{0}</span>'
        '<span class="exec-text">{1}</span></div>'.format(
            _esc(_EXEC_FRAMES[i]), _esc(texts[i] if i < len(texts) else "—"))
        for i in range(5))
    return '<div class="exec-header">{0}</div>'.format(rows)


def _timeline(items) -> str:
    items = tuple(items or ())
    if not items:
        return '<p class="note">(none tracked)</p>'
    chips = "".join('<span class="tl-chip">{0}</span>'.format(_esc(x)) for x in items)
    return '<div class="timeline">{0}</div>'.format(chips)


def _intel_universe(view: EconomicUniverseView) -> str:
    dq = view.data_quality
    rows = ""
    for c in view.clusters:
        glow = _HEAT_GLOW.get((c.heat_label or "").lower(), 1)
        bar = '<span class="heatbar g{0}"></span>'.format(glow)
        marks = ""
        if c.red_team_risk:
            marks += _badge("red-team", "hazard")
        if c.crowded_euphoric:
            marks += _badge("crowded", "gap")
        if c.data_poor:
            marks += _badge("data-poor", "q-low")
        rows += (
            "<tr><td>{bar} {name}</td><td>{heat}</td><td>{prio}</td>"
            '<td class="num">{cand}</td><td>{marks}</td></tr>'
        ).format(bar=bar, name=_esc(c.theme_name), heat=_esc(c.heat_label),
                 prio=_esc(c.priority_label), cand=_esc(c.candidate_count),
                 marks=marks or "—")
    heatmap = (
        '<table class="chain"><tr><th>galaxy / theme</th><th>heat</th><th>priority</th>'
        '<th class="num">candidates</th><th>flags</th></tr>{0}</table>'
        '<p class="note">Heat = existing signal heat, NOT a candidate ranking.</p>'
    ).format(rows)
    cycles = _list(("{0} — {1}".format(c.theme_name, c.capital_cycle) for c in view.clusters))
    coverage = "<p>{sec} {fmp} {yf}</p>".format(
        sec=_badge("SEC canonical ×{0}".format(dq.canonical_count), "auth-canonical"),
        fmp=_badge("FMP convenience ×{0}".format(dq.convenience_count), "auth-convenience"),
        yf=_badge("yfinance fallback ×{0}".format(dq.fallback_count), "auth-fallback"))
    big_gaps = ["{0}: data-poor / magnitude gaps".format(c.theme_name)
                for c in view.clusters if c.data_poor or c.magnitude_missing]
    redteam = [c.theme_name for c in view.clusters if c.red_team_risk]
    hot = [c.theme_name for c in view.clusters if (c.heat_label or "").lower() == "hot"]
    exec_h = _exec_header([
        "Economic Universe — {0} galaxies by megatrend & capital cycle.".format(len(view.clusters)),
        "Scarce bottlenecks concentrate economics; heat marks priority, not a ranking.",
        "Hottest themes: {0}.".format(", ".join(hot[:3]) or "none"),
        "Red-team regions: {0}.".format(", ".join(redteam) or "none flagged"),
        "Zoom a galaxy → theme → value chain → bottleneck → planet.",
    ])
    return (
        exec_h
        + _brief_header("Universe — Intelligence Pane", "Economic Universe",
                      _badge(view.mode, "demo" if view.mode == "fixture/demo" else "evidence")
                      + _badge("live ranking not enabled", "gap"))
        + _brief_card("Executive summary",
                      "<p>{0} galaxies mapped by megatrend and capital cycle. Size = economic "
                      "magnitude (not a ranking); glow = heat; dim nebulae are data-poor; red "
                      "rings flag red-team regions. Select a body to brief it.</p>".format(
                          len(view.clusters)))
        + _brief_card("Theme heat map", heatmap)
        + _brief_card("Capital-cycle summary", cycles)
        + _brief_card("Source authority", coverage)
        + _brief_card("Data gaps", _gap_box("Major data gaps", big_gaps), extra="risk")
        + _brief_card("Red-team warnings",
                      _list(("{0}: red-team risk flagged (demo)".format(n) for n in redteam),
                            "none flagged"), extra="risk")
    )


def _intel_galaxy(t: GalaxyThemeView) -> str:
    c = t.cluster
    _ot = _origin_tokens(c.data_origin)
    badges = (_badge("heat: {0}".format(c.heat_label)) + _badge(c.priority_label)
              + _quality_badge(c.data_quality) + _badge(_ot[0] + " terrain", _ot[1]))
    cat = (
        '<div class="cols"><div><div class="micro">positive</div>{pos}</div>'
        '<div><div class="micro">negative</div>{neg}</div></div>'
    ).format(pos=_timeline(t.positive_catalysts), neg=_timeline(t.negative_catalysts))
    exec_h = _exec_header([
        "{0} galaxy — {1}.".format(c.theme_name, c.capital_cycle),
        c.megatrend,
        t.why_before_obvious,
        (t.red_team_notes[0] if t.red_team_notes else
         (t.negative_catalysts[0] if t.negative_catalysts else "see data gaps below")),
        "Zoom into the theme's value chains.",
    ])
    return (
        exec_h
        + _brief_header("Galaxy / Megatrend", c.theme_name, badges)
        + _brief_card("Executive summary", "<p>{0}</p>".format(_esc(c.megatrend)))
        + _brief_card("Why now", "<p>{0}</p>".format(_esc(t.why_now)))
        + _brief_card("Why before obvious", "<p>{0}</p>".format(_esc(t.why_before_obvious)))
        + _brief_card("Signal convergence", "<p>{0}</p>".format(_esc(c.signal_convergence)))
        + _brief_card("Catalyst timeline", cat)
        + _brief_card("Red-team risks", _list(t.red_team_notes), extra="risk")
        + _brief_card("Data gaps", _gap_box("Data gaps", t.data_gaps), extra="risk")
    )


def _intel_theme(t: GalaxyThemeView) -> str:
    c = t.cluster
    timeline = tuple(list(t.positive_catalysts)
                     + ["(negative) " + n for n in t.negative_catalysts])
    planets = _list(("{0} ({1}) — {2}".format(p.company, p.ticker, p.investability_label)
                     for p in t.planets))
    exec_h = _exec_header([
        "{0} theme — value chains within the megatrend.".format(c.theme_name),
        t.why_now,
        (t.confirmed_signals[0] if t.confirmed_signals else t.why_before_obvious),
        (t.negative_catalysts[0] if t.negative_catalysts else
         (t.red_team_notes[0] if t.red_team_notes else "see data gaps below")),
        "Zoom a value chain to see the flow and its bottleneck.",
    ])
    return (
        exec_h
        + _brief_header("Milky Way / Theme", c.theme_name,
                      _badge("heat: {0}".format(c.heat_label)) + _quality_badge(c.data_quality))
        + _brief_card("Executive summary", "<p>{0}</p>".format(_esc(c.megatrend)))
        + _brief_card("Value-chain overview",
                      _list(("{0} — {1}".format(ss.name, ss.description)
                             for ss in t.solar_systems)))
        + _brief_card("Why now", "<p>{0}</p>".format(_esc(t.why_now)))
        + _brief_card("Why before obvious", "<p>{0}</p>".format(_esc(t.why_before_obvious)))
        + _brief_card("Confirmed vs speculative",
                      '<div class="cols"><div><div class="micro">confirmed</div>{0}</div>'
                      '<div><div class="micro">speculative</div>{1}</div></div>'.format(
                          _list(t.confirmed_signals), _list(t.speculative_signals)))
        + _brief_card("Catalyst timeline", _timeline(timeline))
        + _brief_card("Candidate planets", planets)
        + _brief_card("Data gaps", _gap_box("Data gaps", t.data_gaps), extra="risk")
    )


def _intel_value_chain(ss: SolarSystemValueChainView) -> str:
    chips = []
    for n in ss.nodes:
        missing = (_badge("missing: {0}".format("; ".join(n.missing_data)), "gap")
                   if n.missing_data else "")
        companies = (", ".join(n.candidate_companies) if n.candidate_companies
                     else "(no named company)")
        chips.append(
            '<div class="flow-node"><span class="tier-tag">{tier}</span><b>{role}</b>'
            '<div class="fn-line">capture: {econ}</div>'
            '<div class="fn-line">exposure: {exp}</div>'
            '<div class="fn-line">companies: {co}</div>{missing}</div>'.format(
                tier=_esc(n.tier), role=_esc(n.role), econ=_esc(n.economics_capture),
                exp=_esc(n.bottleneck_exposure), co=_esc(companies), missing=missing))
    flow = '<div class="flow-diagram">{0}</div>'.format(
        '<span class="flow-arrow">→</span>'.join(chips))
    trows = "".join(
        "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td></tr>".format(
            _esc(n.tier), _esc(n.role), _esc(n.economics_capture), _esc(n.bottleneck_exposure))
        for n in ss.nodes)
    table = (
        '<table class="chain"><tr><th>tier</th><th>role</th>'
        "<th>economics capture</th><th>bottleneck exposure</th></tr>{0}</table>".format(trows))
    all_missing = ["{0}: {1}".format(n.node_id, m) for n in ss.nodes for m in n.missing_data]
    mapping_rows = "".join(
        "<tr><td>{0}</td><td>{1}</td></tr>".format(_esc(role), _esc(", ".join(tk)))
        for role, tk in ss.node_ticker_map) or "<tr><td colspan='2'>(none mapped)</td></tr>"
    mapping = (
        '<table class="chain"><tr><th>value-chain node (winner context)</th>'
        "<th>candidate tickers</th></tr>{rows}</table>"
        '<p class="qualifier">{qual}</p>'
    ).format(rows=mapping_rows, qual=_esc(ss.security_mapping_qualifier))
    exec_h = _exec_header([
        "{0} — {1}".format(ss.name, ss.description),
        "Value flows upstream → bottleneck → customers; the bottleneck concentrates margin.",
        ss.security_mapping_qualifier,
        "Missing supplier / TAM / moat data (see below).",
        "Zoom the bottleneck star at the centre of the flow.",
    ])
    return (
        exec_h
        + _brief_header("Solar System / Value Chain", ss.name,
                        _badge(*_origin_tokens(ss.data_origin)))
        + _brief_card("Executive summary", "<p>{0}</p>".format(_esc(ss.description)))
        + _brief_card("Value-chain flow diagram", flow)
        + _brief_card("Economics capture & bottleneck exposure", table)
        + _brief_card("Missing supplier / TAM / moat data",
                      _gap_box("Missing data", all_missing), extra="risk")
        + _brief_card("Security mapping (after winners)", mapping)
    )


def _intel_star(s: StarBottleneckView) -> str:
    diagram = (
        '<div class="bottleneck-diagram">'
        '<div class="bd-side beneficiaries"><div class="micro">beneficiaries</div>{ben}</div>'
        '<div class="bd-core"><div class="micro">constrained core</div><b>{node}</b>'
        '<div class="fn-line">severity: {sev}</div></div>'
        '<div class="bd-side losers"><div class="micro">losers / at risk</div>{los}</div>'
        "</div>"
    ).format(ben=_list(s.beneficiaries), node=_esc(s.constrained_node),
             sev=_esc(s.severity), los=_list(s.losers))
    rows = "".join([
        "<tr><th>Type</th><td>{0}</td></tr>".format(_esc(s.star_type)),
        "<tr><th>Severity</th><td>{0}</td></tr>".format(_esc(s.severity)),
        "<tr><th>Expected duration</th><td>{0}</td></tr>".format(_esc(s.duration)),
        "<tr><th>Resolution risk</th><td>{0}</td></tr>".format(_esc(s.resolution_risk)),
    ])
    exec_h = _exec_header([
        "{0} — {1}.".format(s.constrained_node, s.star_type),
        "Scarce node ({0}); beneficiaries capture it, losers are squeezed.".format(s.severity),
        "Beneficiaries: {0}.".format(s.beneficiaries[0] if s.beneficiaries else "—"),
        "Resolution risk: {0}.".format(s.resolution_risk or "—"),
        "Zoom to candidate planets orbiting the bottleneck.",
    ])
    return (
        exec_h
        + _brief_header("Bottleneck Star", s.constrained_node,
                      _badge("severity: {0}".format(s.severity),
                             "hazard" if (s.severity or "").lower() == "high" else ""))
        + _brief_card("Executive summary",
                      "<p>The 10x discovery layer — a constrained node concentrates economics "
                      "here. Beneficiaries capture it; losers are squeezed.</p>")
        + _brief_card("Bottleneck analysis", diagram)
        + _brief_card("Details", '<table class="kv">{0}</table>'.format(rows))
        + _brief_card("Evidence", _list(s.evidence))
        + _brief_card("Data gaps", _gap_box("Data gaps at this bottleneck", s.data_gaps),
                      extra="risk")
    )


def _planet_reasons(p: PlanetCandidateView) -> Tuple[str, ...]:
    out = [
        "value-chain role: {0}".format(p.value_chain_role),
        "proximity to bottleneck: {0}".format(p.proximity_to_bottleneck),
        "investability: {0}".format(p.investability_label),
    ]
    if (p.catalyst_label or "").strip():
        out.append("catalyst: {0}".format(p.catalyst_label))
    return tuple(x for x in out if x)[:3]


def _planet_risks(p: PlanetCandidateView) -> Tuple[str, ...]:
    out = []
    if (p.red_team_label or "").lower() in ("concern", "fail"):
        out.append("red-team verdict: {0}".format(p.red_team_label))
    if p.capital_structure_risk:
        out.append("capital-structure / dilution risk flagged")
    if (p.data_quality or "").lower() in ("low", "sparse"):
        out.append("evidence-limited (data quality: {0})".format(p.data_quality))
    out.append("manual review required before any action")
    return tuple(out)[:3]


def _intel_planet(p: PlanetCandidateView) -> str:
    origin = _badge("REAL evidence slice", "real") if p.is_real else _badge("DEMO", "demo")
    rt_hazard = (p.red_team_label or "").lower() in ("concern", "fail")
    badges = (
        origin
        + _badge("investability: {0}".format(p.investability_label))
        + _badge(p.timing_label)
        + _badge("red-team: {0}".format(p.red_team_label or "n/a"),
                 "hazard" if rt_hazard else "")
        + _quality_badge(p.data_quality))
    if p.capital_structure_risk:
        badges += _badge("capital-structure / dilution risk", "hazard")
    cockpit = (
        '<a class="cockpit-cta" href="{0}">Open Cockpit — full evidence-alpha slice →</a>'.format(
            _esc(p.cockpit_link))
        if p.cockpit_link
        else '<span class="note">Open Cockpit available for real candidates only (demo planet)</span>')
    snapshot = (
        '<table class="kv">'
        + "<tr><th>Theme / galaxy</th><td>{0}</td></tr>".format(_esc(p.galaxy_name))
        + "<tr><th>Value-chain role</th><td>{0}</td></tr>".format(_esc(p.value_chain_role))
        + "<tr><th>Directness to bottleneck</th><td>{0}</td></tr>".format(
            _esc(p.proximity_to_bottleneck))
        + "<tr><th>Thesis status (investability)</th><td>{0}</td></tr>".format(
            _esc(p.investability_label))
        + "<tr><th>Timing-confirmation</th><td>{0}</td></tr>".format(_esc(p.timing_label))
        + "<tr><th>Personalized / manual-review</th><td>{0}</td></tr>".format(
            _esc(p.recommendation_label))
        + "<tr><th>Catalyst status</th><td>{0}</td></tr>".format(
            _esc(p.catalyst_label or "(none tracked)"))
        + "</table>")
    provenance = (
        "<p>{0}</p>".format(_authority_badges(p))
        + '<p class="note">Provenance: Observation → IntelligenceAssessment → '
        "OpportunityHypothesis → InvestmentThesis → InvestmentAction → PersonalizedAction "
        "→ ticket preview{0}.</p>".format(
            " (real, content-addressed)" if p.is_real else " (demo terrain)"))
    _rs = _planet_reasons(p); _rk = _planet_risks(p)
    exec_h = _exec_header([
        "{0} ({1}) — {2}.".format(p.company, p.ticker, p.value_chain_role),
        "Investability {0}; {1}.".format(p.investability_label, p.timing_label),
        (_rs[0] if _rs else "—"),
        (_rk[0] if _rk else "—"),
        "Open the cockpit for the full evidence-alpha slice.",
    ])
    return (
        exec_h
        + _brief_header("Planet / Company", "{0} ({1})".format(p.company, p.ticker), badges)
        + '<div class="cockpit-cta-wrap">{0}</div>'.format(cockpit)
        + _brief_card("Executive summary",
                      "<p>{company} sits at the {role}, {prox}. Thesis status: "
                      "<b>{inv}</b>; {timing}. Manual review required.</p>".format(
                          company=_esc(p.company), role=_esc(p.value_chain_role),
                          prox=_esc(p.proximity_to_bottleneck),
                          inv=_esc(p.investability_label), timing=_esc(p.timing_label)))
        + _brief_card("Snapshot", snapshot)
        + _brief_card("Top reasons", _list(_planet_reasons(p)))
        + _brief_card("Top risks", _list(_planet_risks(p)), extra="risk")
        + _brief_card("Source authority", provenance)
        + _brief_card("Security mapping",
                      '<p class="qualifier">{0}: <b>{1}</b></p>'.format(
                          _esc(p.security_mapping_qualifier), _esc(p.ticker)))
    )


def _intel_moon(n: NodeView) -> str:
    dashed = _badge("dashed placeholder — missing data", "gap") if n.magnitude_missing else ""
    snapshot = (
        '<table class="kv">'
        + "<tr><th>Node</th><td>{0}</td></tr>".format(_esc(n.node_id))
        + "<tr><th>Tier / relationship</th><td>{0}</td></tr>".format(_esc(n.tier))
        + "<tr><th>Exposure type</th><td>{0}</td></tr>".format(_esc(n.bottleneck_exposure))
        + "<tr><th>Economics capture</th><td>{0}</td></tr>".format(_esc(n.economics_capture))
        + "<tr><th>Evidence quality</th><td>{0}</td></tr>".format(_esc(n.evidence_quality))
        + "</table>{0}".format(dashed))
    exec_h = _exec_header([
        "{0} — supplier / dependency ({1}).".format(n.role, n.tier),
        "Exposure: {0}.".format(n.bottleneck_exposure),
        "Economics capture: {0}.".format(n.economics_capture),
        ("Missing data: {0}.".format("; ".join(n.missing_data)) if n.missing_data
         else "No missing-data flags."),
        "Return to the parent planet.",
    ])
    return (
        exec_h
        + _brief_header("Moon / Supplier", n.role, _badge("tier: {0}".format(n.tier)))
        + _brief_card("Executive summary",
                      "<p>A dependency of the parent planet. A constrained or data-dark "
                      "moon here can gate the planet's economics (organised from existing "
                      "terrain; not a new conclusion).</p>")
        + _brief_card("Snapshot", snapshot)
        + _brief_card("Missing data", _gap_box("Missing data", n.missing_data), extra="risk")
    )


# --------------------------------------------------------------------------- #
# Object builders (compact clickable nodes carrying their intel template)      #
# --------------------------------------------------------------------------- #
def _galaxy_object(t: GalaxyThemeView, target_path: str, pos: Tuple[float, float]) -> str:
    c = t.cluster
    badges = " ".join([
        _badge("heat: {0}".format(c.heat_label)), _badge(c.priority_label),
        _quality_badge(c.data_quality), _badge("candidates: {0}".format(c.candidate_count)),
        _badge(*_origin_tokens(c.data_origin))])
    if c.red_team_risk:
        badges += _badge("black-hole: red-team", "hazard")
    if c.crowded_euphoric:
        badges += _badge("halo: crowded/euphoric", "gap")
    return _cosmic_object(
        kind="galaxy", path=_path_galaxy(c.slug), target_path=target_path, target_level=1,
        title=c.theme_name, sub=c.megatrend,
        size_px=c.visual_size_px, glow=_HEAT_GLOW.get((c.heat_label or "").lower(), 1),
        dashed=c.magnitude_missing, redshadow=c.red_team_risk, halo=c.crowded_euphoric,
        ev_class=_ev_class(c.data_quality),
        size_label="theme TAM ({0})".format(_origin_suffix(c.data_origin)),
        size_raw=_money(c.theme_tam), badges=badges, intel_id=_intel_id_galaxy(c.slug),
        pos=pos, variant="nebula" if c.data_poor else "")


def _theme_object(t: GalaxyThemeView, target_path: str, pos: Tuple[float, float]) -> str:
    c = t.cluster
    badges = " ".join([_badge("theme"), _badge("heat: {0}".format(c.heat_label)),
                       _quality_badge(c.data_quality), _badge(*_origin_tokens(c.data_origin))])
    return _cosmic_object(
        kind="theme", path=_path_theme(c.slug), target_path=target_path, target_level=2,
        title="{0} — theme".format(c.theme_name), sub=c.signal_convergence,
        size_px=c.visual_size_px, glow=_HEAT_GLOW.get((c.heat_label or "").lower(), 1),
        dashed=c.magnitude_missing, redshadow=c.red_team_risk, halo=c.crowded_euphoric,
        ev_class=_ev_class(c.data_quality),
        size_label="theme TAM ({0})".format(_origin_suffix(c.data_origin)),
        size_raw=_money(c.theme_tam), badges=badges, intel_id=_intel_id_theme(c.slug),
        pos=pos, variant="nebula" if c.data_poor else "")


def _value_chain_object(ss: SolarSystemValueChainView, target_path: str,
                        pos: Tuple[float, float]) -> str:
    badges = " ".join([_badge("value chain"),
                       _badge("nodes: {0}".format(len(ss.nodes))),
                       _badge(*_origin_tokens(ss.data_origin))])
    return _cosmic_object(
        kind="value_chain", path=target_path, target_path=target_path, target_level=3,
        title=ss.name, sub=ss.description, size_px=ss.visual_size_px, glow=2,
        dashed=ss.magnitude_missing, redshadow=False, halo=False, ev_class="",
        size_label="value-chain revenue pool ({0})".format(_origin_suffix(ss.data_origin)),
        size_raw=_money(ss.value_chain_revenue_pool),
        badges=badges, intel_id=_intel_id_vc(ss.slug), pos=pos)


def _star_object(s: StarBottleneckView, target_path: str, pos: Tuple[float, float],
                 central: bool = False) -> str:
    high = (s.severity or "").lower() == "high"
    badges = " ".join([_badge("bottleneck"), _badge("type: {0}".format(s.star_type)),
                       _badge("severity: {0}".format(s.severity),
                              "hazard" if high else ""),
                       _badge(*_origin_tokens(s.data_origin))])
    return _cosmic_object(
        kind="star", path=target_path, target_path=target_path, target_level=4,
        title=s.constrained_node, sub="{0} · {1}".format(s.star_type, s.severity),
        size_px=s.visual_size_px, glow=3 if high else 2, dashed=s.magnitude_missing,
        redshadow=high, halo=False, ev_class="",
        size_label="bottleneck economic importance ({0})".format(_origin_suffix(s.data_origin)),
        size_raw=("{0:.0f} / 100".format(s.bottleneck_economic_importance)
                  if s.bottleneck_economic_importance is not None else "unknown (data gap)"),
        badges=badges, intel_id=_intel_id_star(s.slug), pos=pos,
        extra_class="bottleneck-central" if central else "",
        marker="scarce node" if central else "")


def _planet_bucket(p: PlanetCandidateView) -> str:
    """The candidate's EXISTING status bucket (label) -- reused, not recomputed."""
    primary, _cross = assign_buckets(
        investability_label=p.investability_label, timing_label=p.timing_label,
        red_team_label=p.red_team_label, recommendation_label=p.recommendation_label,
        catalyst_label=p.catalyst_label, capital_structure_risk=p.capital_structure_risk,
        data_quality=p.data_quality, evidence_count=p.evidence_count)
    return "{0} ({1})".format(primary, card_label_for(primary, p.investability_label))


def _planet_preview(p: PlanetCandidateView) -> str:
    """The candidate hover summary -- all from EXISTING view-model fields."""
    reasons = _planet_reasons(p)
    risks = _planet_risks(p)
    origin = "REAL slice" if p.is_real else "DEMO"
    return (
        '<div class="pv-name">{company} <b>({ticker})</b></div>'
        '<div class="pv-row"><span>theme/galaxy</span><b>{galaxy}</b></div>'
        '<div class="pv-row"><span>value-chain role</span><b>{role}</b></div>'
        '<div class="pv-row"><span>candidate bucket</span><b>{bucket}</b></div>'
        '<div class="pv-row"><span>top reason</span><b>{reason}</b></div>'
        '<div class="pv-row"><span>top risk</span><b>{risk}</b></div>'
        '<div class="pv-row"><span>market cap</span><b>{cap}</b></div>'
        '<div class="pv-foot">{origin} · manual review required</div>'
    ).format(
        company=_esc(p.company), ticker=_esc(p.ticker), galaxy=_esc(p.galaxy_name),
        role=_esc(p.value_chain_role), bucket=_esc(_planet_bucket(p)),
        reason=_esc(reasons[0] if reasons else "—"),
        risk=_esc(risks[0] if risks else "—"), cap=_esc(_money(p.market_cap)),
        origin=_esc(origin))


def _planet_object(p: PlanetCandidateView, pos: Tuple[float, float]) -> str:
    origin = _badge("REAL slice", "real") if p.is_real else _badge("DEMO", "demo")
    rt_hazard = (p.red_team_label or "").lower() in ("concern", "fail")
    severe = rt_hazard or p.capital_structure_risk
    has_catalyst = bool((p.catalyst_label or "").strip())
    badges = " ".join([
        _badge("investability: {0}".format(p.investability_label)),
        _badge(p.timing_label),
        _badge("red-team: {0}".format(p.red_team_label or "n/a"), "hazard" if rt_hazard else ""),
        _quality_badge(p.data_quality), origin])
    if p.is_real:
        badges += " " + _authority_badges(p)
    variant = "blackhole" if severe else ("comet" if has_catalyst else "")
    return _cosmic_object(
        kind="planet", path=p.universe_path, target_path=p.universe_path, target_level=5,
        title="{0} ({1})".format(p.company, p.ticker), sub=p.value_chain_role,
        size_px=p.visual_size_px, glow=p.glow_level, dashed=p.magnitude_missing,
        redshadow=severe, halo=has_catalyst,
        ev_class=_ev_class(p.data_quality),
        size_label="market cap ({0})".format(_origin_suffix(p.data_origin)),
        size_raw=_money(p.market_cap), badges=badges, intel_id=_intel_id_planet(p),
        pos=pos, variant=variant, preview_html=_planet_preview(p),
        cockpit=(p.cockpit_link or ""))


def _moon_object(n: NodeView, pos: Tuple[float, float]) -> str:
    missing = _badge("missing: {0}".format("; ".join(n.missing_data)), "gap") if n.missing_data else ""
    badges = " ".join([_badge("moon / supplier"), _badge("tier: {0}".format(n.tier)),
                       _badge("evidence: {0}".format(n.evidence_quality)), missing])
    return _cosmic_object(
        kind="moon", path="mo:{0}".format(n.node_id), target_path="", target_level=6,
        title=n.role, sub="{0} · {1}".format(n.tier, n.node_id), size_px=n.visual_size_px,
        glow=1, dashed=n.magnitude_missing, redshadow=False, halo=False,
        ev_class=_ev_class(n.evidence_quality),
        size_label="dependency exposure ({0})".format(_origin_suffix(n.data_origin)),
        size_raw=_money(n.dependency_exposure), badges=badges, intel_id=_intel_id_moon(n.node_id),
        pos=pos)


def _severe(p: PlanetCandidateView) -> bool:
    return (p.red_team_label or "").lower() in ("concern", "fail") or p.capital_structure_risk


def _bottleneck_positions(planets) -> list:
    """Beneficiary planets cluster in a ring around the central bottleneck core;
    loser / at-risk planets are separated to the right edge (and red-shadowed)."""
    pos = [None] * len(planets)
    safe = [i for i, p in enumerate(planets) if not _severe(p)]
    risk = [i for i, p in enumerate(planets) if _severe(p)]
    for k, i in enumerate(safe):
        ang = (k / float(max(1, len(safe)))) * 2.0 * math.pi
        pos[i] = (42.0 + 22.0 * math.cos(ang), 46.0 + 22.0 * math.sin(ang))
    for k, i in enumerate(risk):
        pos[i] = (85.0, 24.0 + (k + 1) * (48.0 / (len(risk) + 1)))
    return pos


# --------------------------------------------------------------------------- #
# The single zoomable universe page                                          #
# --------------------------------------------------------------------------- #
def render_universe(view: EconomicUniverseView, strip_text: Optional[str] = None,
                    notice: str = "") -> str:
    panels = []
    # The hidden intelligence store: ONE blob per unique object, referenced by
    # data-intel. Nothing structural (tables, diagrams, headings) renders in the
    # canvas -- these blobs feed the bottom pane only.
    store = []
    seen = set()

    def add_intel(intel_id, html_blob):
        if intel_id not in seen:
            seen.add(intel_id)
            store.append('<div class="intel-template" id="{0}">{1}</div>'.format(
                _esc(intel_id), html_blob))

    # L0 Universe — galaxies float in an OPEN field (NO centre, NO hub-and-spoke).
    # Only explicit SEMANTIC relationship edges are drawn, between related galaxies.
    ntheme = len(view.themes)
    gpos = [_universe_scatter(i, ntheme) for i in range(ntheme)]
    pos_by_slug = {t.cluster.slug: gpos[i] for i, t in enumerate(view.themes)}
    galaxy_objs = _edge_svg(view.edges, pos_by_slug) + "".join(
        _galaxy_object(t, _path_galaxy(t.cluster.slug), gpos[i])
        for i, t in enumerate(view.themes))
    universe_intel = _intel_universe(view)
    add_intel("intel-universe", universe_intel)
    panels.append(_level_panel(
        level=0, path="universe", parent="", crumb="Universe", kind="Universe",
        title="Economic Universe — galaxy clusters", objects_html=galaxy_objs,
        intel_id="intel-universe", active=True))

    for t in view.themes:
        c = t.cluster
        gslug = c.slug
        gp = _path_galaxy(gslug)
        tp = _path_theme(gslug)
        vc0 = t.solar_systems[0].slug if t.solar_systems else "vc0"
        star0 = t.stars[0].slug if t.stars else "star0"
        add_intel(_intel_id_galaxy(gslug), _intel_galaxy(t))
        add_intel(_intel_id_theme(gslug), _intel_theme(t))

        # L1 Galaxy -> the theme (a single central body).
        panels.append(_level_panel(
            level=1, path=gp, parent="universe", crumb="{0} Galaxy".format(c.theme_name),
            kind="Galaxy / megatrend", title="{0} — galaxy".format(c.theme_name),
            objects_html=_theme_object(t, tp, _scene_position(0, 1)),
            intel_id=_intel_id_galaxy(gslug), active=False))

        # L2 Theme -> value-chain bodies.
        nvc = len(t.solar_systems)
        vpos = [_scene_position(i, nvc) for i in range(nvc)]
        vc_objs = _orbit_svg(vpos) + "".join(
            _value_chain_object(ss, _path_vc(gslug, ss.slug), vpos[i])
            for i, ss in enumerate(t.solar_systems))
        panels.append(_level_panel(
            level=2, path=tp, parent=gp, crumb="{0} Theme".format(c.theme_name),
            kind="Milky Way / theme", title="{0} — theme".format(c.theme_name),
            objects_html=vc_objs, intel_id=_intel_id_theme(gslug), active=False))
        for ss in t.solar_systems:
            add_intel(_intel_id_vc(ss.slug), _intel_value_chain(ss))
        for s in t.stars:
            add_intel(_intel_id_star(s.slug), _intel_star(s))
        for p in t.planets:
            add_intel(_intel_id_planet(p), _intel_planet(p))
        for ss in t.solar_systems:
            for n in ss.nodes:
                add_intel(_intel_id_moon(n.node_id), _intel_moon(n))

        # L3 Value chain = a legible left->right economic FLOW: upstream inputs ->
        # ... -> customers, with the bottleneck STAR centred and dominant among them.
        for ss in t.solar_systems:
            ordered = sorted(ss.nodes, key=lambda n: _TIER_RANK.get(n.tier, 9))
            nnode = len(ordered)
            fpos = [_flow_position(i, nnode, row=66.0) for i in range(nnode)]
            flow = _flow_svg(fpos) + "".join(
                _moon_object(n, fpos[i]) for i, n in enumerate(ordered))
            star_objs = "".join(
                _star_object(s, _path_star(gslug, ss.slug, s.slug), (50.0, 34.0), central=True)
                for s in t.stars)
            panels.append(_level_panel(
                level=3, path=_path_vc(gslug, ss.slug), parent=tp, crumb=ss.name,
                kind="Solar system / value chain", title=ss.name,
                objects_html=flow + star_objs, intel_id=_intel_id_vc(ss.slug), active=False))

        # L4 Bottleneck = the scarce star centred & dominant; beneficiary planets
        # cluster around it, loser / at-risk planets are separated + red-shadowed.
        for ss in t.solar_systems:
            for s in t.stars:
                ppos = _bottleneck_positions(t.planets)
                core = _star_object(s, "", (50.0, 46.0), central=True)
                planet_objs = _orbit_svg(ppos) + core + "".join(
                    _planet_object(p, ppos[i]) for i, p in enumerate(t.planets))
                panels.append(_level_panel(
                    level=4, path=_path_star(gslug, ss.slug, s.slug),
                    parent=_path_vc(gslug, ss.slug), crumb=s.constrained_node,
                    kind="Star / bottleneck", title="Bottleneck: {0}".format(s.constrained_node),
                    objects_html=planet_objs, intel_id=_intel_id_star(s.slug), active=False))

        # L5 Planet(s) -> moon bodies. Parent = the first star (matches planet path).
        star0_path = _path_star(gslug, vc0, star0)
        moon_src = t.solar_systems[0].nodes if t.solar_systems else ()
        nmoon = len(moon_src)
        mpos = [_scene_position(i, nmoon) for i in range(nmoon)]
        moon_objs = _orbit_svg(mpos) + "".join(
            _moon_object(n, mpos[i]) for i, n in enumerate(moon_src))
        for p in t.planets:
            panels.append(_level_panel(
                level=5, path=p.universe_path, parent=star0_path, crumb=p.company,
                kind="Planet / company", title="{0} ({1})".format(p.company, p.ticker),
                objects_html=moon_objs, intel_id=_intel_id_planet(p), active=False))

    # Floating preview card INSIDE the universe hero. HIDDEN by default (starts
    # ``dismissed``); it only appears once the user clicks an object, and a click
    # updates this compact card here AND the full pane below.
    floating = (
        '<div id="floating-preview" class="floating-preview dismissed" aria-live="polite">'
        '<div class="fp-head"><span id="fp-type" class="fp-type micro">object</span>'
        '<a id="fp-close" class="fp-close" href="#" aria-label="dismiss">×</a></div>'
        '<h3 id="fp-title" class="fp-title"></h3>'
        '<div id="fp-body" class="fp-body"></div>'
        '<div class="fp-actions">'
        '<a id="fp-details" class="fp-btn" href="#intel-pane">View details below ↓</a>'
        '<a id="fp-zoom" class="fp-btn" href="#" style="display:none">Zoom in ⤢</a>'
        '<a id="fp-cockpit" class="fp-btn" href="#" style="display:none">Open cockpit ↗</a>'
        "</div></div>")
    viewport = '<div id="viewport" class="viewport">{0}{1}{2}{3}</div>'.format(
        _space_background(), "".join(panels), floating, _legend())
    intel_store = '<div class="intel-store" aria-hidden="true">{0}</div>'.format("".join(store))
    canvas = (
        '<section id="top-canvas" class="top-canvas" aria-label="Universe (telescope view)">'
        '<div class="canvas-bar">'
        '<nav id="breadcrumb" class="breadcrumb">'
        '<a class="crumb" data-goto="universe" href="#path=universe">Universe</a></nav>'
        '<div class="zoom-controls">'
        '<a id="zoom-back" class="zoom-ctrl" href="#" style="display:none">↑ Back</a>'
        '<a id="zoom-in" class="zoom-ctrl" href="#" aria-label="zoom in">+</a>'
        '<a id="zoom-out" class="zoom-ctrl" href="#" aria-label="zoom out">−</a>'
        '<a id="zoom-fit" class="zoom-ctrl" href="#">Fit all</a>'
        '<a id="zoom-locate" class="zoom-ctrl" href="#">Locate</a>'
        '<a id="zoom-reset" class="zoom-ctrl" href="#">Reset</a>'
        '<span class="hint">scroll = zoom · drag = pan · click = descend</span>'
        "</div></div>"
        + viewport + "</section>")
    # HERO = the full-viewport telescope universe (first screen); the intelligence
    # pane sits BELOW the fold, full width, revealed by scrolling.
    hero = '<section class="universe-hero">{0}</section>'.format(canvas)
    intel = (
        '<section id="intel-pane" class="intel-pane intel-section" '
        'aria-label="Intelligence Pane (below the fold)">'
        '<div id="intel-body" class="detail-body">{0}</div></section>'.format(universe_intel))
    notice_html = ('<div class="terrain-notice">⚠ {0}</div>'.format(_esc(notice))
                   if notice else "")
    body = (
        '<div class="universe-app">' + notice_html + hero + intel + "</div>" + intel_store)
    return _page("Economic Universe", "universe.html", body, full_screen=True,
                 strip_text=strip_text)


# --------------------------------------------------------------------------- #
# Cockpit (IREN) — the ACCEPTED renderer, wrapped; opened FROM a planet       #
# --------------------------------------------------------------------------- #
def _cockpit_enrichment_note(coverage, subject: str) -> str:
    """A READ-ONLY diligence-enrichment status note for the cockpit PAGE wrapper.

    Built from the enrichment-coverage diagnostic for ``subject`` (or the first ticker).
    Coverage + gaps ONLY — there is NO trade / order affordance, and the broker order stays
    None. Returns "" when no coverage exists, so the pre-011C wrapper is unchanged."""
    if coverage is None or not getattr(coverage, "per_ticker", ()):
        return ""
    subj = (subject or "").strip().upper()
    tc = None
    for t in coverage.per_ticker:
        if t.ticker == subj:
            tc = t
            break
    tc = tc or coverage.per_ticker[0]
    avail = sum(1 for a in tc.areas if a.available)
    gaps = "; ".join(tc.gaps[:4]) if tc.gaps else "none"
    return (
        '<div style="background:#101a2e;color:#cfe0ff;padding:.55rem 1rem;'
        'font:600 12px sans-serif;border-bottom:1px solid #26315f">'
        "Diligence enrichment (read-only evidence): {tk} — status {st}, {av}/{n} diligence "
        "areas source-backed. Gaps (data-sourcing only): {gaps}. This is evidence + coverage "
        "only — no recommendation, no order; broker order: none; manual review required."
        "</div>").format(
            tk=_esc(tc.ticker), st=_esc(tc.enrichment_status), av=avail,
            n=len(tc.areas), gaps=_esc(gaps))


def _cockpit_wrapper(strip_text: Optional[str] = None,
                     enrichment_note: str = "") -> str:
    strip = (
        '<div style="position:sticky;top:0;z-index:50;background:#0a0f24;color:#c7d0f5;'
        'padding:.5rem 1rem;font:600 13px sans-serif;border-bottom:1px solid #26315f">'
        '{0}</div>'.format(_esc(strip_text if strip_text is not None else STATUS_STRIP_TEXT)))
    links = [
        '<a href="universe.html#focus=universe/g:ai-infrastructure/t:ai-infrastructure/'
        'vc:ai-infrastructure--ai-compute-hosting-value-chain/st:ai-infrastructure--star-0/pl:iren"'
        ' style="color:#7c8cff;text-decoration:none;margin-right:.9rem;font:600 13px sans-serif">'
        '← Back to IREN planet in the Universe</a>']
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
        'IREN planet — REAL evidence-alpha slice, opened FROM the planet as a deeper view. '
        'Rendered by the ACCEPTED cockpit renderer (render_cockpit_html). Ticker/security '
        'mapping is derived after value-chain / winner mapping inside the cockpit. '
        'Manual review required.</div>')
    return strip + nav + note + (enrichment_note or "")


def render_cockpit(iren_slice, strip_text: Optional[str] = None,
                   enrichment_note: str = "") -> str:
    cockpit_view = getattr(iren_slice, "cockpit_view", None)
    if cockpit_view is None:
        # Real / early-stop runs may lack a full decision cockpit (insufficient inputs).
        # Render an honest placeholder page instead of fabricating a cockpit.
        body = (
            '<div class="glass-panel"><h1>Alpha Decision Cockpit</h1>'
            '<p class="lead">No decision cockpit for this run — the evidence chain '
            "stopped before an investment thesis (insufficient inputs). This is a data "
            "gap, not a recommendation. Manual review required; no order is placed.</p>"
            "</div>" + (enrichment_note or ""))
        return _page("Alpha Decision Cockpit", "cockpit.html", body, strip_text=strip_text)
    doc = render_cockpit_html(cockpit_view)
    return doc.replace(
        "<body>", "<body>\n" + _cockpit_wrapper(strip_text, enrichment_note), 1)


# --------------------------------------------------------------------------- #
# CIO Dashboard                                                               #
# --------------------------------------------------------------------------- #
def _card(c: CandidateCardView) -> str:
    origin = _badge("REAL slice", "real") if c.is_real else _badge("DEMO", "demo")
    cockpit = ('<a href="{0}">Open Cockpit →</a>'.format(_esc(c.cockpit_link))
               if c.cockpit_link else '<span class="note">Open Cockpit for real candidates only</span>')
    cross = " ".join(_badge(b, "hazard" if "Red-Team" in b else "gap") for b in c.cross_cut_buckets)
    rt_cls = "hazard" if (c.red_team_label or "").lower() in ("concern", "fail") else ""
    capstruct = _badge("capital-structure risk", "hazard") if c.capital_structure_risk else ""
    auth = " ".join(_badge(b, "") for b in c.source_authority_badges)
    orb = _orb(c.visual_size_px, c.glow_level, c.magnitude_missing,
               "market cap ({0})".format(_origin_suffix(c.data_origin)), c.market_cap)
    cls = "card dashed-outline" if c.magnitude_missing else "card"
    # IMPLEMENTATION-011C: per-company diligence-enrichment context (evidence + coverage +
    # gaps; label-only, never a trade action). Rendered only when a source-backed bundle
    # supplied it, so demo / non-enriched cards are byte-identical.
    enrich_html = ""
    if c.enrichment_coverage_line or c.enrichment_context or c.enrichment_gaps:
        ctx = _list(c.enrichment_context, "no source-backed profile facts")
        egaps = _list(c.enrichment_gaps, "no enrichment gaps")
        enrich_html = (
            '<div class="brief-card"><div class="brief-label micro">Diligence enrichment '
            "(evidence + coverage only — no recommendation)</div>"
            '<p class="note">{cov}</p>'
            '<div class="brief-label micro">Source-backed facts</div>{ctx}'
            '<div class="brief-label micro">Enrichment gaps (data-sourcing)</div>{gaps}'
            "</div>").format(
                cov=_esc(c.enrichment_coverage_line or "enrichment: source-backed evidence"),
                ctx=ctx, gaps=egaps)
    top_reason = "{0}; {1}".format(c.value_chain_role, c.proximity_to_bottleneck)
    top_risk = ("capital-structure / dilution risk" if c.capital_structure_risk else
                ("red-team: {0}".format(c.red_team_label) if rt_cls else
                 "manual review required"))
    return (
        '<div class="{cls}">'
        '<p class="title">{label}: {company} {origin}</p>'
        '<p class="sub">{galaxy} · {role} · proximity: {prox}</p>'
        "{orb}"
        "<p>{inv} {timing} {rt} {rec} {caps}</p>"
        "<p>{cross}</p>"
        '<table class="kv">'
        "<tr><th>Timing-confirmation</th><td>{timing_txt}</td></tr>"
        "<tr><th>Thesis status</th><td>{inv_txt}</td></tr>"
        "<tr><th>Top reason</th><td>{reason}</td></tr>"
        "<tr><th>Top risk</th><td>{risk}</td></tr>"
        "<tr><th>Source coverage</th><td>{auth}</td></tr>"
        "</table>"
        "{enrich}"
        '<p class="qualifier">{qual}: <b>{ticker}</b></p>'
        '<p>{q} · evidence {ev} · '
        '<a href="{locate}">Locate in Universe →</a> · {cockpit}</p>'
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
        timing_txt=_esc(c.timing_label), inv_txt=_esc(c.investability_label),
        reason=_esc(top_reason), risk=_esc(top_risk), auth=auth, enrich=enrich_html,
        qual=_esc(c.security_mapping_qualifier), ticker=_esc(c.ticker),
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


def render_dashboard(dash: CIODashboardView, strip_text: Optional[str] = None) -> str:
    banner = '<div class="banner">{0}</div>'.format(_esc(dash.banner))
    intro = (
        "<h1>CIO Dashboard — Candidate Buckets</h1>"
        '<p class="lead">Candidates are grouped by their EXISTING pipeline statuses '
        "(investability_assessment / timing_confirmation / red-team verdict / "
        "recommendation_status). There is no composite ranking metric, no live "
        "ranking, and no trade-execution affordance — every card is a manual review "
        "candidate. Each card has Locate in Universe (zooms the canvas to the planet) "
        "and Open Cockpit (the accepted renderer).</p>"
    )
    note = (
        '<p class="note">Buckets are read-only groupings of existing statuses. '
        "Within-bucket ordering reuses an existing field (thesis_confidence for the real "
        "candidate; evidence_count for demo terrain) — it is not a new composite figure. "
        "live ranking not enabled.</p>"
    )
    buckets = "".join(_bucket(b) for b in dash.buckets)
    body = intro + banner + note + buckets
    return _page("CIO Dashboard", "dashboard.html", body, strip_text=strip_text)


# --------------------------------------------------------------------------- #
# Data Quality / Provenance                                                   #
# --------------------------------------------------------------------------- #
# EIOS platform layers (Sudarshan) — the CORRECTED namespace labels. Grouped like the
# architecture diagram: reasoning (1-2), opportunity & capital (3-5), operational (6-8).
_PLATFORM_LAYERS = (
    ("1", "Adhāra", "Foundation", "grp-reason"),
    ("2", "Buddhi", "Cognitive Architecture", "grp-reason"),
    ("3", "Tattva", "Reality Intelligence", "grp-cap"),
    ("4", "Sphurana", "Opportunity Generation / Genesis", "grp-cap"),
    ("5", "Nivesha", "Investment Diligence / Capital Candidate", "grp-cap"),
    ("6", "Saarathi", "Personal CIO / Portfolio Fit / Sizing Guardrails", "grp-op"),
    ("7", "Kriya", "Manual Execution Preview", "grp-op"),
    ("8", "Anubhava", "Feedback / Learning", "grp-op"),
)


def _platform_layer_map() -> str:
    """The EIOS layer map with the corrected labels (Nivesha = Investment Diligence /
    Capital Candidate; Saarathi = Personal CIO / Portfolio Fit / Sizing Guardrails;
    Kriya = Manual Execution Preview) — matches the architecture diagram."""
    rows = "".join(
        '<div class="layer-row {grp}"><span class="layer-num">{n}</span>'
        '<span class="layer-name">{name}</span>'
        '<span class="layer-label">{label}</span></div>'.format(
            grp=grp, n=n, name=_esc(name), label=_esc(label))
        for n, name, label, grp in _PLATFORM_LAYERS)
    return (
        '<div class="layer-map glass-panel">'
        '<div class="micro">EIOS Platform Layers · Sudarshan</div>'
        '<div class="layer-rows">{0}</div>'
        '<div class="layer-legend"><span class="lg-dot grp-reason"></span>Reasoning (1–2)'
        ' · <span class="lg-dot grp-cap"></span>Opportunity &amp; Capital (3–5)'
        ' · <span class="lg-dot grp-op"></span>Operational (6–8)</div></div>'
    ).format(rows)


def _coverage_bar(count: int, top: int) -> str:
    pct = 0 if top <= 0 else int(round(100.0 * float(count) / float(top)))
    return ('<div class="cov-bar"><span style="width:{0}%"></span></div>'
            '<span class="cov-n">{1}</span>').format(max(0, min(100, pct)), _esc(count))


def _dq_pipeline(dq: DataQualityView) -> str:
    """Source-hierarchy PIPELINE: SEC EDGAR -> FMP -> yfinance -> manual/other."""
    stages = (
        ("SEC EDGAR", "canonical", dq.canonical_count, "auth-canonical"),
        ("FMP", "convenience", dq.convenience_count, "auth-convenience"),
        ("yfinance", "fallback", dq.fallback_count, "auth-fallback"),
        ("manual / other", "unverified", "—", "gap"),
    )
    cells = []
    for i, (name, auth, cnt, cls) in enumerate(stages):
        if i:
            cells.append('<span class="pipe-arrow">→</span>')
        cells.append(
            '<div class="pipe-stage">{badge}<div class="pipe-name">{name}</div>'
            '<div class="pipe-count num">{cnt}</div>'
            '<div class="micro">records</div></div>'.format(
                badge=_badge(auth, cls), name=_esc(name), cnt=_esc(cnt)))
    return '<div class="dq-pipeline">{0}</div>'.format("".join(cells))


def _authority_matrix(dq: DataQualityView) -> str:
    """Authority MATRIX: source · authority · coverage · conflicts · overridden · gaps
    · red-team flags (aggregate demo view of the real IREN slice)."""
    nconf = len(dq.conflict_warnings)
    nover = len(dq.overridden_facts)
    ngap = len(dq.data_gaps)
    top = max(dq.canonical_count, dq.convenience_count, dq.fallback_count, 1)
    # (source, authority, count, conflicts, overridden, gaps, redteam)
    matrix = (
        ("SEC EDGAR", "canonical", dq.canonical_count, 0, 0, 0, 0),
        ("FMP", "convenience", dq.convenience_count, nconf, nover, 0, 0),
        ("yfinance", "fallback", dq.fallback_count, 0, 0, ngap, 0),
        ("manual / other", "unverified", 0, 0, 0, ngap, 0),
    )
    rows = ""
    for src, auth, cnt, cf, ov, gp, rt in matrix:
        acls = {"canonical": "auth-canonical", "convenience": "auth-convenience",
                "fallback": "auth-fallback"}.get(auth, "gap")
        flag = (lambda n, cls: '<span class="mx-flag {1}">{0}</span>'.format(n, cls)
                if n else '<span class="mx-ok">—</span>')
        rows += (
            "<tr><td>{src}</td><td>{auth}</td><td>{cov}</td>"
            "<td>{cf}</td><td>{ov}</td><td>{gp}</td><td>{rt}</td></tr>"
        ).format(src=_esc(src), auth=_badge(auth, acls), cov=_coverage_bar(cnt, top),
                 cf=flag(cf, "warn"), ov=flag(ov, "warn"), gp=flag(gp, "gap"),
                 rt=flag(rt, "hazard"))
    return (
        '<table class="chain matrix"><tr><th>source</th><th>authority</th>'
        "<th>coverage</th><th>conflicts</th><th>overridden</th><th>data gaps</th>"
        "<th>red-team</th></tr>{0}</table>".format(rows))


def _quality_cards(dq: DataQualityView) -> str:
    """Quality summary stat CARDS."""
    stale = 1  # manual / other evidence source not yet wired (demo)
    cards = (
        ("canonical records", dq.canonical_count, "auth-canonical"),
        ("convenience records", dq.convenience_count, "auth-convenience"),
        ("fallback records", dq.fallback_count, "auth-fallback"),
        ("factual observations", dq.factual_observation_count, ""),
        ("signal observations", dq.signal_observation_count, "real"),
        ("conflicts", len(dq.conflict_warnings), "warn"),
        ("data gaps", len(dq.data_gaps), "gap"),
        ("stale / missing sources", stale, "hazard"),
    )
    items = "".join(
        '<div class="stat-card {cls}"><div class="stat-n num">{n}</div>'
        '<div class="stat-l micro">{label}</div></div>'.format(
            cls=cls, n=_esc(n), label=_esc(label)) for label, n, cls in cards)
    return '<div class="stat-grid">{0}</div>'.format(items)


def _watchlist_dq_panel(dq: DataQualityView) -> str:
    """IMPLEMENTATION-010E watchlist Data-Quality panel: (A) OVERALL run summary,
    (B) PER-TICKER source-status table, (C) FAILURE / GAP cards. Reuses the accepted
    control-panel styling; every value is copied from the run summary — no key is leaked,
    nothing is ranked or recomputed."""
    if not getattr(dq, "is_watchlist", False):
        return ""
    # A. overall run summary
    overall = "".join([
        "<tr><th>Requested</th><td>{0}</td></tr>".format(_esc(dq.wl_requested)),
        "<tr><th>Built</th><td>{0}</td></tr>".format(_esc(dq.wl_succeeded)),
        "<tr><th>Failed</th><td>{0}</td></tr>".format(_esc(dq.wl_failed)),
        "<tr><th>Deferred</th><td>{0}</td></tr>".format(_esc(dq.wl_deferred)),
        "<tr><th>Tickers built</th><td>{0}</td></tr>".format(
            _esc(", ".join(dq.tickers) or "—")),
        "<tr><th>Run timestamp</th><td>{0}</td></tr>".format(_esc(dq.run_timestamp)),
        "<tr><th>SEC canonical (total)</th><td>{0}</td></tr>".format(_esc(dq.canonical_count)),
        "<tr><th>FMP convenience (total)</th><td>{0}</td></tr>".format(
            _esc(dq.convenience_count)),
        "<tr><th>yfinance fallback (total)</th><td>{0}</td></tr>".format(_esc(dq.fallback_count)),
        "<tr><th>Conflicts</th><td>{0}</td></tr>".format(_esc(len(dq.conflict_warnings))),
        "<tr><th>Overridden facts</th><td>{0}</td></tr>".format(_esc(len(dq.overridden_facts))),
        "<tr><th>Data gaps</th><td>{0}</td></tr>".format(_esc(len(dq.data_gaps))),
        "<tr><th>Deferred records</th><td>{0}</td></tr>".format(
            _esc(dq.deferred_records_count)),
    ])
    # B. per-ticker source-status table
    def _st_badge(st):
        st = str(st)
        cls = ("q-high" if st == "fetched" else
               ("hazard" if st in ("failed", "not run") else "gap"))
        return _badge(st, cls)
    trows = "".join(
        "<tr><td>{tk}</td><td>{sec}</td><td>{fmp}</td><td>{yf}</td>"
        '<td class="num">{can}</td><td class="num">{con}</td><td class="num">{fb}</td>'
        '<td class="num">{cf}</td><td class="num">{gp}</td><td class="num">{pr}</td>'
        "<td>{ts}</td></tr>".format(
            tk=_esc(r[0]), sec=_st_badge(r[1]), fmp=_st_badge(r[2]), yf=_st_badge(r[3]),
            can=_esc(r[4]), con=_esc(r[5]), fb=_esc(r[6]), cf=_esc(r[7]), gp=_esc(r[8]),
            pr=_esc(r[9]), ts=_badge(r[10], "q-high" if r[10] == "built" else "hazard"))
        for r in dq.per_ticker_rows)
    table = (
        '<table class="chain"><tr><th>ticker</th><th>SEC</th><th>FMP</th>'
        "<th>yfinance</th><th>canonical</th><th>convenience</th><th>fallback</th>"
        "<th>conflicts</th><th>data gaps</th><th>provenance</th><th>terrain</th></tr>"
        "{0}</table>".format(trows))
    # C. failure / gap cards
    if dq.failure_cards:
        cards = "".join(
            '<div class="brief-card risk"><div class="brief-label micro">{0}</div>'
            '<div class="brief-body">{1}</div></div>'.format(_esc(k), _esc(v))
            for k, v in dq.failure_cards)
        cards_html = '<div class="cols">{0}</div>'.format(cards)
    else:
        cards_html = '<p class="note">no per-ticker failures or credential gaps flagged</p>'
    return (
        '<h2>Watchlist run — overall</h2><div class="glass-panel">'
        '<p class="note">Real evidence on demand · manual refresh only · not scheduled · '
        "not broker-connected · data may be incomplete — completeness is NOT claimed. "
        "A ticker that failed is recorded here, never silently dropped.</p>"
        '<table class="kv">' + overall + "</table></div>"
        "<h2>Per-ticker source status</h2>"
        '<div class="glass-panel">' + table + "</div>"
        "<h2>Failures &amp; credential / data gaps</h2>"
        '<div class="glass-panel">' + cards_html + "</div>")


def _diag_label_badge(label: str) -> str:
    """Badge for a TRUST / COMPLETENESS / status LABEL (never a number)."""
    cls = {
        "sufficient": "q-high", "direct": "q-high", "built": "q-high",
        "partial": "q-medium", "weak": "gap", "fallback": "gap", "deferred": "gap",
        "stale": "warn", "conflicted": "warn",
        "missing": "hazard", "unclassified": "hazard", "failed": "hazard",
        "source_failed": "hazard", "credentials_missing": "hazard",
        "needs_human_review": "warn",
    }.get(str(label), "")
    return _badge(str(label), cls)


def _diagnostics_panel(dq: DataQualityView) -> str:
    """IMPLEMENTATION-010F TRUST / COMPLETENESS diagnostics panel (labels, not scores).

    (A) overall terrain health, (B) per-ticker diagnostic table, (C) diagnostic cards,
    (D) per-ticker DATA-SOURCING action list, (E) visual-encoding explanation. Every value
    is a label / string copied from the typed diagnostics — no ranking, no score, no key,
    no trade instruction. Empty (section omitted) in demo / evidence-fixture modes."""
    diag = getattr(dq, "terrain_diagnostics", None)
    if diag is None:
        return ""

    # A. overall terrain health -------------------------------------------- #
    overall = "".join([
        "<tr><th>Mode</th><td>{0}</td></tr>".format(_esc(diag.mode)),
        "<tr><th>Requested / built / failed-or-deferred</th><td>{0} / {1} / {2}</td></tr>"
        .format(_esc(len(diag.requested_tickers)), _esc(len(diag.built_tickers)),
                _esc(len(diag.failed_tickers))),
        "<tr><th>Source coverage</th><td>{0}</td></tr>".format(_esc(diag.coverage_summary)),
        "<tr><th>TRUST level</th><td>{0}</td></tr>".format(_diag_label_badge(diag.trust_level)),
        "<tr><th>COMPLETENESS level</th><td>{0}</td></tr>".format(
            _diag_label_badge(diag.completeness_level)),
        "<tr><th>Conflicts (resolved by authority)</th><td>{0}</td></tr>".format(
            _esc(len(diag.unresolved_conflicts))),
        "<tr><th>Stale / missing sources</th><td>{0}</td></tr>".format(
            _esc(len(diag.stale_or_missing_sources))),
    ])
    warn_html = _list(diag.warnings, "no warnings")
    actions_html = _list(diag.recommended_next_data_actions, "no data actions")
    overall_html = (
        '<h2>Terrain health &amp; trust</h2><div class="glass-panel">'
        '<p class="note">TRUST and COMPLETENESS are data-quality LABELS (not scores, not a '
        "ranking). TRUST reflects source authority + conflict resolution + theme "
        "classification; COMPLETENESS reflects value-chain / bottleneck / TAM coverage.</p>"
        '<table class="kv">' + overall + "</table>"
        '<div class="brief-label micro">Run notes</div>' + warn_html
        + '<div class="brief-label micro">Recommended next DATA actions (data-sourcing '
        "only — never a trade instruction)</div>" + actions_html + "</div>")

    # B. per-ticker diagnostic table --------------------------------------- #
    def _src(statuses, key):
        for s, st in statuses:
            if s == key:
                return _diag_label_badge(st)
        return _badge("—", "gap")

    trows = "".join(
        "<tr><td>{tk}</td><td>{status}</td><td>{sec}</td><td>{fmp}</td><td>{yf}</td>"
        '<td class="num">{can}</td><td class="num">{con}</td><td class="num">{cf}</td>'
        '<td class="num">{gp}</td><td>{theme}</td><td>{vc}</td><td>{bn}</td>'
        "<td>{ck}</td><td>{trust}</td></tr>".format(
            tk=_esc(d.ticker), status=_diag_label_badge(d.terrain_status),
            sec=_src(d.source_statuses, "sec"), fmp=_src(d.source_statuses, "fmp"),
            yf=_src(d.source_statuses, "yfinance"),
            can=_esc(d.canonical_coverage), con=_esc(d.convenience_coverage),
            cf=_esc(len(d.unresolved_conflicts)), gp=_esc(len(d.data_gaps)),
            theme=_diag_label_badge(d.theme_classification_status),
            vc=_diag_label_badge(d.value_chain_status),
            bn=_diag_label_badge(d.bottleneck_status),
            ck=_diag_label_badge(d.cockpit_status),
            trust=_diag_label_badge(d.trust_label))
        for d in diag.per_ticker)
    table_html = (
        "<h2>Per-ticker diagnostics</h2>"
        '<div class="glass-panel"><table class="chain"><tr><th>ticker</th><th>status</th>'
        "<th>SEC</th><th>FMP</th><th>yfinance</th><th>canonical</th><th>convenience</th>"
        "<th>conflicts</th><th>data gaps</th><th>theme</th><th>value chain</th>"
        "<th>bottleneck</th><th>cockpit</th><th>trust</th></tr>"
        + trows + "</table></div>")

    # C. diagnostic cards -------------------------------------------------- #
    if dq.diagnostic_cards:
        cards = "".join(
            '<div class="brief-card risk"><div class="brief-label micro">{0}</div>'
            '<div class="brief-body">{1}</div></div>'.format(_esc(k), _esc(v))
            for k, v in dq.diagnostic_cards)
        cards_html = '<div class="cols">{0}</div>'.format(cards)
    else:
        cards_html = '<p class="note">no diagnostic conditions flagged</p>'
    cards_html = ("<h2>Diagnostic cards</h2>"
                  '<div class="glass-panel">' + cards_html + "</div>")

    # D. per-ticker DATA-SOURCING action list ------------------------------ #
    if dq.data_action_rows:
        rows = "".join(
            '<div class="brief-card"><div class="brief-label micro">{0}</div>{1}</div>'
            .format(_esc(tk), _list(acts, "no actions"))
            for tk, acts in dq.data_action_rows)
        actions_block = '<div class="cols">{0}</div>'.format(rows)
    else:
        actions_block = '<p class="note">no data-sourcing actions outstanding</p>'
    actions_block = (
        "<h2>Data-sourcing actions per ticker</h2>"
        '<div class="glass-panel"><p class="note">These are DATA-SOURCING actions only '
        "(add a source, resolve a CIK, set a credential) — never a trade instruction.</p>"
        + actions_block + "</div>")

    # E. visual-encoding explanation --------------------------------------- #
    ve_rows = ""
    for label, channels in dq.visual_encoding_explanations:
        chans = "".join(
            "<li><b>{0}</b>: {1}</li>".format(_esc(ch), _esc(reason))
            for ch, reason in channels)
        ve_rows += (
            '<div class="brief-card"><div class="brief-label micro">{0}</div>'
            "<ul>{1}</ul></div>".format(_esc(label), chans))
    ve_html = (
        "<h2>Visual encoding — why each object is drawn this way</h2>"
        '<div class="glass-panel"><p class="note">Each channel is a projection of an '
        "EXISTING field (the encoding basis) — why a neutral size, a dashed outline, a red "
        "shadow, low opacity, a halo or a glow. No channel is a score or a ranking.</p>"
        '<div class="cols">' + (ve_rows or '<p class="note">no encoded objects</p>')
        + "</div></div>")

    return overall_html + table_html + cards_html + actions_block + ve_html


def _enrichment_coverage_panel(dq: DataQualityView) -> str:
    """IMPLEMENTATION-011A diligence-enrichment COVERAGE panel (labels, not scores).

    Per diligence area (market cap / TAM / value-chain / bottleneck / company IR /
    leadership): available-vs-missing + the source AUTHORITY backing it; per-ticker
    enrichment GAPS; and recommended DATA-SOURCING actions (add an investor presentation /
    transcript / IR source / TAM source / supplier-customer source / bottleneck source /
    leadership source) -- never a trade instruction. Empty (section omitted) unless a real /
    watchlist run supplied enrichment bundles."""
    cov = getattr(dq, "enrichment_coverage", None)
    if cov is None or not getattr(cov, "per_ticker", ()):
        return ""

    summary_rows = "".join(
        "<tr><th>{0}</th><td>{1}</td></tr>".format(_esc(area), _esc(val))
        for area, val in cov.areas_summary)
    summary_html = (
        "<h2>Diligence-enrichment coverage</h2>"
        '<div class="glass-panel"><p class="note">Enrichment collects the missing diligence '
        "INPUTS (market cap, TAM, value chain, bottleneck, company IR, leadership) with "
        "EXPLICIT source authority and claim status. Availability is a data-quality LABEL — "
        "not a score, not a ranking, not a recommendation. Manual / analyst estimates are "
        "never treated as canonical; company statements are marked as claims.</p>"
        '<table class="kv">' + summary_rows + "</table></div>")

    # per-ticker area table
    def _avail(a):
        return _badge("available", "q-high") if a.available else _badge("missing", "gap")

    ticker_blocks = []
    for tc in cov.per_ticker:
        arows = "".join(
            "<tr><td>{area}</td><td>{avail}</td><td>{auth}</td><td>{claim}</td>"
            "<td>{detail}</td></tr>".format(
                area=_esc(a.area_label), avail=_avail(a),
                auth=_esc(a.authority or "—"), claim=_esc(a.claim_status or "—"),
                detail=_esc(a.detail))
            for a in tc.areas)
        gaps_html = _list(tc.gaps, "no enrichment gaps")
        actions_html = _list(tc.data_actions, "no data actions outstanding")
        ticker_blocks.append(
            '<div class="glass-panel"><div class="brief-label micro">{tk} · enrichment '
            "status: {st}</div>"
            '<table class="chain"><tr><th>area</th><th>availability</th><th>authority</th>'
            "<th>claim status</th><th>detail</th></tr>{rows}</table>"
            '<div class="brief-label micro">Enrichment gaps</div>{gaps}'
            '<div class="brief-label micro">Recommended DATA actions (data-sourcing only — '
            "never a trade instruction)</div>{acts}</div>".format(
                tk=_esc(tc.ticker), st=_esc(tc.enrichment_status), rows=arows,
                gaps=gaps_html, acts=actions_html))

    actions_all = _list(cov.recommended_data_actions, "no data actions outstanding")
    actions_html = (
        "<h2>Enrichment data-sourcing actions</h2>"
        '<div class="glass-panel"><p class="note">DATA-SOURCING actions only (add a source) '
        "— never an execution instruction.</p>" + actions_all + "</div>")

    return summary_html + "".join(ticker_blocks) + actions_html


def render_data_quality(dq: DataQualityView, strip_text: Optional[str] = None,
                        notice: str = "", pulse_panel_html: str = "") -> str:
    is_ev = "evidence" in (dq.run_mode or "").lower()
    terrain_badge = (_badge("evidence-ingested terrain", "evidence") if is_ev
                     else _badge("DEMO terrain", "demo"))
    notice_html = ('<div class="terrain-notice">⚠ {0}</div>'.format(_esc(notice))
                   if notice else "")
    # Real on-demand mode: an explicit per-source STATUS panel + run metadata. Completeness
    # is NEVER claimed. Empty in demo/fixture modes (section omitted).
    source_status_html = ""
    if getattr(dq, "source_status", ()):
        rows = "".join(
            "<tr><th>{0}</th><td>{1}</td></tr>".format(_esc(src), _badge(_esc(st),
                "q-high" if st == "fetched" else
                ("hazard" if st in ("failed",) else "gap")))
            for src, st in dq.source_status)
        meta = "".join([
            "<tr><th>Mode</th><td>{0}</td></tr>".format(_esc(dq.mode_label)),
            "<tr><th>Ticker(s)</th><td>{0}</td></tr>".format(
                _esc(", ".join(dq.tickers) or dq.real_subject)),
            "<tr><th>Run timestamp</th><td>{0}</td></tr>".format(_esc(dq.run_timestamp)),
            "<tr><th>Deferred records</th><td>{0}</td></tr>".format(
                _esc(dq.deferred_records_count)),
        ])
        source_status_html = (
            '<h2>Real-source status (on demand)</h2><div class="glass-panel">'
            '<p class="note">Manual refresh only · not scheduled · not broker-connected · '
            "data may be incomplete — completeness is NOT claimed.</p>"
            '<table class="kv">' + rows + meta + "</table></div>")
    watchlist_html = _watchlist_dq_panel(dq)
    diagnostics_html = _diagnostics_panel(dq)
    enrichment_html = _enrichment_coverage_panel(dq)
    boundary = "".join([
        "<tr><th>Run mode</th><td>{0}</td></tr>".format(_esc(dq.run_mode)),
        "<tr><th>Fixture / demo</th><td>{0}</td></tr>".format(_esc(dq.fixture_demo_status)),
        "<tr><th>Live data</th><td>not enabled</td></tr>",
        "<tr><th>Scheduler</th><td>{0}</td></tr>".format(_esc(dq.scheduler_status)),
        "<tr><th>Broker automation</th><td>{0}</td></tr>".format(
            _esc(dq.broker_automation_status)),
        "<tr><th>Manual review required</th><td>{0}</td></tr>".format(
            "yes" if dq.manual_review_required else "no"),
    ])
    body = (
        notice_html
        + '<div class="dq-head"><div><h1>Data Quality &amp; Provenance</h1>'
        '<p class="lead">Evidence sources, authority, coverage, conflicts, overridden '
        "facts, data gaps and the provenance chain for the one real candidate (IREN). A "
        "control panel over existing pipeline state — no live data, scheduler or broker.</p>"
        "</div><div>" + _badge("REAL subject: {0}".format(dq.real_subject), "real")
        + " " + terrain_badge + "</div></div>"
        # A. real-source status + (watchlist) overall run + per-ticker table + gaps
        + source_status_html
        + watchlist_html
        # 010F: typed TRUST / COMPLETENESS diagnostics + theme classification + encoding
        + diagnostics_html
        # 011A: diligence-enrichment coverage (data-sourcing actions only; empty otherwise)
        + enrichment_html
        # 012J: manual-pulse reality-signal EVIDENCE panel (empty unless pulse signals supplied;
        # additive/opt-in so demo/real/enriched default output stays byte-identical)
        + pulse_panel_html
        + '<h2>Source hierarchy pipeline</h2>'
        + '<div class="glass-panel">' + _dq_pipeline(dq)
        + '<p class="note">Authority order: SEC canonical (EDGAR) &gt; FMP convenience &gt; '
        "yfinance fallback &gt; manual / other (unverified). Signal observations drive "
        "reasoning; factual observations stay partitioned.</p></div>"
        # C. quality summary cards
        + "<h2>Quality summary</h2>" + _quality_cards(dq)
        # B. source authority matrix
        + "<h2>Source authority matrix</h2>"
        + '<div class="glass-panel">' + _authority_matrix(dq) + "</div>"
        # warnings + provenance
        + "<h2>Conflicts, overrides &amp; gaps</h2>"
        + '<div class="cols">'
        + '<div class="brief-card"><div class="brief-label micro">Conflict warnings (arbitration)</div>'
        + _list(dq.conflict_warnings, "no conflicts") + "</div>"
        + '<div class="brief-card"><div class="brief-label micro">Overridden facts (lost arbitration)</div>'
        + _list(dq.overridden_facts, "none overridden") + "</div></div>"
        + _gap_box("Data gaps", dq.data_gaps)
        + '<h2>Provenance chain</h2><div class="glass-panel">'
        + _list(dq.provenance_chain, "no chain") + "</div>"
        # platform layer map (corrected labels) + automation boundary
        + "<h2>EIOS platform layers</h2>" + _platform_layer_map()
        + '<div class="hazard-box"><h4>Automation boundary</h4>'
        + "<p>Scheduler: not enabled. Broker automation: disabled. No order is placed, "
        "routed, or recorded anywhere in this UI. Manual review required.</p></div>"
    )
    return _page("Data Quality & Provenance", "data_quality.html", body,
                 strip_text=strip_text)


# --------------------------------------------------------------------------- #
# Convenience: render every page from one view                               #
# --------------------------------------------------------------------------- #
def render_all_pages(view: EconomicUniverseView, iren_slice,
                     pulse_panel_html: str = "") -> Tuple[Tuple[str, str], ...]:
    """Return an ordered ((filename, html), ...) for all four pages.

    Galaxy / value-chain / bottleneck are zoom LEVELS inside ``universe.html`` — not
    separate pages. The cockpit is opened FROM a planet, not a top-level tab.
    """
    strip_text = _strip_for_mode(getattr(view, "mode", "")) + getattr(
        view, "run_summary_line", "")
    notice = _terrain_notice(view)
    enrichment_note = _cockpit_enrichment_note(
        getattr(view.data_quality, "enrichment_coverage", None),
        getattr(iren_slice, "subject", "") or getattr(view, "real_subject", ""))
    return (
        ("universe.html", render_universe(view, strip_text=strip_text, notice=notice)),
        ("dashboard.html", render_dashboard(view.dashboard, strip_text=strip_text)),
        ("data_quality.html", render_data_quality(
            view.data_quality, strip_text=strip_text, notice=notice,
            pulse_panel_html=pulse_panel_html)),
        ("cockpit.html", render_cockpit(
            iren_slice, strip_text=strip_text, enrichment_note=enrichment_note)),
    )
