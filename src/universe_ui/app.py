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
from .view_models import build_economic_universe_view

PAGE_ORDER = (
    "universe.html", "galaxy.html", "solar_system.html", "star.html",
    "cockpit.html", "dashboard.html", "data_quality.html",
)


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def build_universe_app(output_dir: str, iren_slice: Optional[object] = None,
                       fixture_dir: Optional[str] = None) -> Dict[str, str]:
    """Build all seven pages + local assets into ``output_dir``; return their paths.

    Deterministic: two builds into two fresh directories produce byte-identical files.
    """
    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    slice_result = iren_slice if iren_slice is not None else load_iren_slice(fixture_dir)
    view = build_economic_universe_view(slice_result)
    pages = render_all_pages(view, slice_result)

    paths: Dict[str, str] = {}
    for filename, html in pages:
        path = os.path.join(output_dir, filename)
        _write(path, html)
        paths[filename] = path

    # Local assets (also inlined in every page -- these are the standalone copies).
    css_path = os.path.join(assets_dir, "universe.css")
    js_path = os.path.join(assets_dir, "universe.js")
    _write(css_path, COSMIC_CSS)
    _write(js_path, NAV_JS)
    paths["assets/universe.css"] = css_path
    paths["assets/universe.js"] = js_path
    return paths
