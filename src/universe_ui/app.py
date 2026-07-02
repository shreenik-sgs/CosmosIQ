"""Static-site builder for the Economic Universe UI (IMPLEMENTATION-010A).

``build_universe_app(output_dir)`` writes the seven static pages (plus local CSS/JS
assets) to ``output_dir`` and returns a dict of their paths. It is a pure,
deterministic projection -> render -> write: it loads the real IREN evidence-alpha
slice from local fixtures, projects the read-only Economic Universe view, renders the
seven pages, and writes them. No network, no live data, no scheduler, no broker, no
order affordance -- and generated HTML is a build ARTIFACT (do not commit it).
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from .assets import COSMIC_CSS, NAV_JS
from .iren_slice import load_iren_slice
from .render import render_all_pages
from .sky_asset import deep_space_background_svg
from .view_models import build_economic_universe_view

# Three top-level sections + the cockpit (opened FROM a planet). Galaxy / value-chain
# / bottleneck are zoom LEVELS inside universe.html, not separate pages.
PAGE_ORDER = (
    "universe.html", "dashboard.html", "data_quality.html", "cockpit.html",
)


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def build_universe_app(output_dir: str, mode: str = "demo",
                       iren_slice: Optional[object] = None,
                       fixture_dir: Optional[str] = None) -> Dict[str, str]:
    """Build all pages + local assets into ``output_dir``; return their paths.

    ``mode="demo"`` (default) renders the accepted hand-authored demo universe -- the
    behaviour every existing test relies on. ``mode="evidence_ingested_fixture"`` runs the
    IREN evidence-alpha vertical slice, builds a REAL sparse terrain from that ingested
    output (``terrain_from_slice``) and renders every page from THAT terrain -- sparse,
    honestly incomplete, and never labelled ``live``.

    Deterministic: two builds into two fresh directories produce byte-identical files.
    """
    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    slice_result = iren_slice if iren_slice is not None else load_iren_slice(fixture_dir)
    if mode == "evidence_ingested_fixture":
        from .terrain_adapters import terrain_from_slice
        terrain = terrain_from_slice(slice_result)
        view = build_economic_universe_view(slice_result, terrain=terrain)
    elif mode == "demo":
        view = build_economic_universe_view(slice_result)
    else:
        raise ValueError("unknown mode: {0!r}".format(mode))
    pages = render_all_pages(view, slice_result)

    paths: Dict[str, str] = {}
    for filename, html in pages:
        path = os.path.join(output_dir, filename)
        _write(path, html)
        paths[filename] = path

    # Local assets (also inlined in every page -- these are the standalone copies).
    css_path = os.path.join(assets_dir, "universe.css")
    js_path = os.path.join(assets_dir, "universe.js")
    svg_path = os.path.join(assets_dir, "deep_space_background.svg")
    _write(css_path, COSMIC_CSS)
    _write(js_path, NAV_JS)
    _write(svg_path, deep_space_background_svg())  # local deep-space asset (no network)
    paths["assets/universe.css"] = css_path
    paths["assets/universe.js"] = js_path
    paths["assets/deep_space_background.svg"] = svg_path
    return paths
