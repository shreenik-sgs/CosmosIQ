"""Load the ONE real evidence-alpha slice for the IREN planet (IMPLEMENTATION-010A).

Thin, deterministic wrapper around the ACCEPTED
``runtime.run_evidence_alpha_slice``. It locates the existing IREN evidence
fixtures (``tests/fixtures/slice``) and runs the slice at a fixed ``now`` so two
builds are byte-identical.

Discipline: NO network, NO live call, NO keys/secrets, NO scheduler, NO broker.
It reads local JSON fixtures with the stdlib only and calls the existing runner --
it adds no reasoning, no scoring, and no new status of its own. ``os`` is used only
for path resolution (never ``os.environ`` / ``os.getenv``).
"""

from __future__ import annotations

import json
import os
from typing import Optional

from runtime.evidence_alpha_slice_runner import run_evidence_alpha_slice

# Fixed clock so the whole build is deterministic / byte-stable.
IREN_NOW = 1750000000.0
_QUOTE_AS_OF = "2026-03-31"

_FIXTURES = (
    "sec_submissions_iren.json",
    "sec_companyfacts_iren.json",
    "fmp_income_statement_iren.json",
    "fmp_profile_iren.json",
    "fmp_ohlcv_iren.json",
    "fmp_news_iren.json",
    "fmp_ownership_iren.json",
    "yf_history_iren.json",
    "yf_quote_iren.json",
)


def _find_fixture_dir() -> str:
    """Walk up from this file to the repo's ``tests/fixtures/slice`` directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(8):
        candidate = os.path.join(root, "tests", "fixtures", "slice")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise FileNotFoundError(
        "Could not locate tests/fixtures/slice relative to {0}".format(here))


def _load(fixture_dir: str, name: str):
    with open(os.path.join(fixture_dir, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_iren_slice(fixture_dir: Optional[str] = None):
    """Run the real IREN evidence-alpha slice deterministically from fixtures.

    Returns the existing ``EvidenceAlphaSliceResult`` (with ``.cockpit_view``,
    ``.investment_thesis``, ``.personalized_action``, ``.ingestion_result``, ...).
    """
    fdir = fixture_dir or _find_fixture_dir()
    data = {name: _load(fdir, name) for name in _FIXTURES}
    return run_evidence_alpha_slice(
        subject="IREN",
        domain="ai-infrastructure",
        sec_submissions=data["sec_submissions_iren.json"],
        sec_companyfacts=data["sec_companyfacts_iren.json"],
        fmp_income_statement=data["fmp_income_statement_iren.json"],
        fmp_profile=data["fmp_profile_iren.json"],
        fmp_ohlcv=data["fmp_ohlcv_iren.json"],
        fmp_news=data["fmp_news_iren.json"],
        fmp_ownership=data["fmp_ownership_iren.json"],
        yf_history=data["yf_history_iren.json"],
        yf_quote=data["yf_quote_iren.json"],
        yf_quote_as_of=_QUOTE_AS_OF,
        now=IREN_NOW,
        render_html=False,
    )
