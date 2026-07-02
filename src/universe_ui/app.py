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
                       fixture_dir: Optional[str] = None,
                       ticker: Optional[str] = None,
                       tickers: Optional[object] = None,
                       transports: Optional[object] = None,
                       transports_by_ticker: Optional[object] = None,
                       sec_user_agent: Optional[str] = None,
                       fmp_api_key: Optional[str] = None,
                       enable_yfinance: bool = False,
                       diligence_inputs: Optional[object] = None,
                       profile: Optional[object] = None,
                       portfolio: Optional[object] = None,
                       user_selected_size: Optional[float] = None,
                       enrichment: Optional[object] = None,
                       now: Optional[float] = None) -> Dict[str, str]:
    """Build all pages + local assets into ``output_dir``; return their paths.

    ``mode="demo"`` (default) renders the accepted hand-authored demo universe -- the
    behaviour every existing test relies on. ``mode="evidence_ingested_fixture"`` runs the
    IREN evidence-alpha vertical slice, builds a REAL sparse terrain from that ingested
    output (``terrain_from_slice``) and renders every page from THAT terrain -- sparse,
    honestly incomplete, and never labelled ``live``.

    ``mode="real_evidence_on_demand"`` (IMPLEMENTATION-010D) lazily imports the on-demand
    builder, fetches REAL current source data for ``ticker`` (SEC/FMP/yfinance via the
    injected/real transports), builds a sparse ``real_evidence_on_demand`` terrain, and
    renders every page from it. It REQUIRES an explicit ``ticker``. Credentials are passed
    explicitly (resolved from env by the CLI); network happens ONLY here and ONLY on this
    explicit path.

    Deterministic: demo / fixture builds into two fresh directories are byte-identical.
    Real mode is deterministic only when ``transports`` + ``now`` are injected (tests).
    """
    os.makedirs(output_dir, exist_ok=True)
    assets_dir = os.path.join(output_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    if mode == "real_evidence_on_demand":
        # A watchlist (``tickers`` / ``transports_by_ticker``) takes precedence over the
        # single-ticker 010D path, which stays byte-for-byte unchanged when only
        # ``ticker`` is supplied.
        if tickers is not None or transports_by_ticker is not None:
            return _build_watchlist(
                output_dir, assets_dir, tickers=tickers, transports=transports,
                transports_by_ticker=transports_by_ticker, sec_user_agent=sec_user_agent,
                fmp_api_key=fmp_api_key, enable_yfinance=enable_yfinance, now=now)
        if not ticker:
            raise ValueError(
                "mode 'real_evidence_on_demand' requires an explicit ticker or tickers "
                "(pass ticker= / --ticker, or tickers= / --tickers); real mode never runs "
                "without one")
        from .real_terrain import build_real_evidence_terrain_for_ticker
        terrain, source_status = build_real_evidence_terrain_for_ticker(
            ticker, transports=transports, sec_user_agent=sec_user_agent,
            fmp_api_key=fmp_api_key, enable_yfinance=enable_yfinance,
            diligence_inputs=diligence_inputs, profile=profile, portfolio=portfolio,
            user_selected_size=user_selected_size, enrichment=enrichment, now=now)
        slice_result = source_status.pop("slice_result")
        view = build_economic_universe_view(
            slice_result, terrain=terrain, source_status=source_status,
            enrichment_bundles=([enrichment] if enrichment is not None else None))
        pages = render_all_pages(view, slice_result)
        return _write_pages(output_dir, assets_dir, pages)

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
    return _write_pages(output_dir, assets_dir, pages)


def _build_watchlist(output_dir, assets_dir, *, tickers, transports,
                     transports_by_ticker, sec_user_agent, fmp_api_key,
                     enable_yfinance, now) -> Dict[str, str]:
    """IMPLEMENTATION-010E: build ONE merged real-evidence terrain for a small watchlist.

    Renders the four base pages from the merged terrain (``cockpit.html`` = the
    representative company that produced a decision cockpit), plus a per-ticker
    ``cockpit_<ticker>.html`` for every built company that has its own cockpit. Real
    network happens only inside the lazily-imported builder and only on this explicit
    path; tests drive it entirely offline with ``transports_by_ticker``."""
    from .watchlist_terrain import build_real_evidence_watchlist_terrain, normalize_tickers
    from .render import _strip_for_mode, render_cockpit
    from .view_models import slugify

    norm = normalize_tickers(tickers if tickers is not None else
                             tuple((transports_by_ticker or {}).keys()))
    if not norm:
        raise ValueError(
            "mode 'real_evidence_on_demand' watchlist requires >=1 ticker "
            "(empty / whitespace --tickers rejected; nothing fetched)")
    terrain, summary = build_real_evidence_watchlist_terrain(
        norm, transports_by_ticker=transports_by_ticker, transports=transports,
        sec_user_agent=sec_user_agent, fmp_api_key=fmp_api_key,
        enable_yfinance=enable_yfinance, now=now)
    rep = summary.representative_slice
    view = build_economic_universe_view(
        rep, terrain=terrain, slice_by_subject=summary.slice_by_subject,
        watchlist_summary=summary)
    pages = render_all_pages(view, rep)
    paths = _write_pages(output_dir, assets_dir, pages)

    # Per-ticker cockpit pages (only where a cockpit exists), so each real company's
    # planet links to ITS OWN cockpit rather than a shared / mislabelled one.
    strip = _strip_for_mode("real_evidence_on_demand") + view.run_summary_line
    for tk, sl in summary.slice_by_subject.items():
        if getattr(sl, "cockpit_view", None) is not None:
            fname = "cockpit_{0}.html".format(slugify(tk))
            html = render_cockpit(sl, strip_text=strip)
            path = os.path.join(output_dir, fname)
            _write(path, html)
            paths[fname] = path
    return paths


def _write_pages(output_dir, assets_dir, pages) -> Dict[str, str]:

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
