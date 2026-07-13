"""UX-6 -- the Dashboard "Recent evidence" panel: newest real evidence on the homepage.

The homepage (``/``) previously looked empty because real filings render only on the company
pages. UX-6 adds a "Recent evidence" panel to the Dashboard that surfaces the most RECENT
persisted evidence (SEC filings + FMP financial events) from the latest run(s), newest first,
each linking to its company page. These tests exercise the DISPATCHER ONLY -- fully offline
under a socket kill-switch; every event below is a persisted store record, never fetched.

Proven here:

* the panel lists REAL events newest-first, each with a VISIBLE source-authority chip
  (canonical / convenience / fallback -- the real label, never hidden or laundered);
* an honest EMPTY STATE (no runs/events) that links to Evidence & Trust and fabricates no row;
* NO trade affordance anywhere on ``/`` (no buy/sell/order/submit/execute/trade/broker word,
  no order/execute control) and NO score/rank/rating surface;
* a ``fixture:``-sourced event is labelled "demo" and NEVER presented as real canonical data
  (this slice exists BECAUSE of a fixture-leak bug -- it must not reappear);
* NO secret / no full URL bearing a key in the output (bare host tokens only).
"""

from __future__ import annotations

import os
import re
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from cosmosiq_app.api import dispatch

_NOW = "2026-06-29T00:00:00Z"

# Word-boundary trade verbs -- ZERO may appear on the Dashboard (word-boundary so CSS "border"
# and prose "recorded" never false-positive).
_TRADE_WORD = re.compile(r"\b(buy|sell|order|submit|execute|trade|broker)\b", re.IGNORECASE)
# Score-like tokens -- ZERO may appear (the panel carries labels + dates only).
_SCORE_TOKENS = ("score", "rank", "rating", "investab")
# A full URL / credential-like value -- ZERO may appear (bare host tokens only).
_URL_TOKENS = ("http://", "https://")
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"apikey=", re.IGNORECASE),
    re.compile(r"api_key=", re.IGNORECASE),
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline recent-evidence tests")


def _run_record(run_id):
    return rm.PulseRun(run_id=run_id, started_at=_NOW, completed_at=_NOW, mode="pulse",
                       trigger_type="manual", watchlist=("ZALPHA", "ZBETA", "ZGAMMA"),
                       themes=("robotics",), events_created=3)


def _sec_event():
    """A REAL SEC 10-K -- canonical, newest by filing date."""
    return rm.RealityEvent(
        event_id="seclive.zalpha.10k.aaaaaaaaaaaa", timestamp="2026-06-20T00:00:00Z",
        source_id="sec.edgar", source_type="sec_10-k", source_authority="canonical",
        claim_status="verified_fact", raw_payload_ref="raw:sec/zalpha#sha256=deadbeef",
        discipline="news_filings", event_type="sec_10-k_annual_report",
        affected_companies=("ZALPHA",), observed_fact="ZALPHA filed its annual report.",
        evidence_refs=("sec:edgar/ZALPHA/10-K/0001",),
        source_refs=("sec:accession/0001", "sec:cik/0000123"),
        confidence_label="high", freshness_label="recent", half_life="quarters")


def _fmp_event():
    """A REAL FMP financials event -- convenience, middle by as-of date."""
    return rm.RealityEvent(
        event_id="fmplive.zbeta.income.bbbbbbbbbbbb", timestamp="2026-06-10T00:00:00Z",
        source_id="fmp.live", source_type="fmp_income_statement_snapshot",
        source_authority="convenience", claim_status="reported_claim",
        raw_payload_ref="raw:fmp_income/zbeta#sha256=cafef00d",
        discipline="financial_inflection", event_type="fmp_income_statement_snapshot",
        affected_companies=("ZBETA",), observed_fact="ZBETA revenue reported.",
        evidence_refs=("fmp:income/ZBETA",),
        source_refs=("fmp:endpoint/income", "fmp:symbol/ZBETA"),
        confidence_label="low", freshness_label="recent", half_life="quarters")


def _fixture_event():
    """A bundled fixture/demo event that CLAIMS canonical -- must render as "demo", not real."""
    return rm.RealityEvent(
        event_id="fixture.zgamma.breadth.cccccccccccc", timestamp="2026-06-01T00:00:00Z",
        source_id="fixture.market_regime", source_type="market_breadth",
        source_authority="canonical", claim_status="verified_fact",
        raw_payload_ref="fixture:breadth/pct_above_200dma", discipline="market_regime",
        event_type="market_breadth_reading", affected_companies=("ZGAMMA",),
        observed_fact="Index breadth reading.",
        source_refs=("fixture:breadth/pct_above_200dma",),
        confidence_label="moderate", freshness_label="recent", half_life="days")


def _seed(store_dir, run_id, *events):
    rm.RunStore(store_dir).append(_run_record(run_id))
    store = rm.EventStore(store_dir)
    for event in events:
        store.append(event, run_id=run_id)


def _home(store_dir):
    response = dispatch({"method": "GET", "path": "/", "query": {}, "body": None},
                        store_dir=store_dir)
    assert response["status"] == 200, response
    return response["body"]


def _panel(html):
    """Just the Recent-evidence panel body (the <div class=panel> after its <h2>)."""
    marker = "<h2>Recent evidence</h2>"
    start = html.index(marker)
    return html[start:html.index("</div>", start) + len("</div>")]


class RecentEvidenceTests(unittest.TestCase):
    _orig = None

    @classmethod
    def setUpClass(cls):
        cls._orig = socket.socket.connect
        socket.socket.connect = _boom_socket

    @classmethod
    def tearDownClass(cls):
        socket.socket.connect = cls._orig

    def _store(self, *events):
        store_dir = tempfile.mkdtemp(prefix="cosmosiq_recent_ev_")
        _seed(store_dir, "R-EV-1", *events)
        return store_dir

    # -- the panel lists real events newest-first with the authority chip ---------- #
    def test_panel_present_on_the_dashboard(self):
        html = _home(self._store(_sec_event()))
        self.assertIn("<h2>Recent evidence</h2>", html)

    def test_real_events_listed_newest_first_by_filing_date(self):
        html = _home(self._store(_sec_event(), _fmp_event()))
        panel = _panel(html)
        # SEC (2026-06-20) is newer than FMP (2026-06-10) -> SEC row appears FIRST.
        self.assertLess(panel.index("ZALPHA"), panel.index("ZBETA"))
        self.assertIn('href="/companies/ZALPHA"', panel)
        self.assertIn('href="/companies/ZBETA"', panel)

    def test_plain_english_labels_and_dates(self):
        panel = _panel(_home(self._store(_sec_event(), _fmp_event())))
        self.assertIn("SEC 10-K", panel)
        self.assertIn("FMP financials", panel)
        self.assertIn("2026-06-20T00:00:00Z", panel)   # filing/as-of date (freshness)

    def test_visible_honest_authority_chip(self):
        panel = _panel(_home(self._store(_sec_event(), _fmp_event())))
        # canonical for the SEC filing, convenience for FMP -- the REAL label, never hidden.
        self.assertIn("canonical", panel)
        self.assertIn("convenience", panel)

    def test_source_host_shown_without_a_url_or_key(self):
        panel = _panel(_home(self._store(_sec_event(), _fmp_event())))
        self.assertIn("sec.gov", panel)
        self.assertIn("financialmodelingprep", panel)
        for token in _URL_TOKENS:
            self.assertNotIn(token, panel)

    # -- honest empty state -------------------------------------------------------- #
    def test_honest_empty_state_when_no_runs_or_events(self):
        store_dir = tempfile.mkdtemp(prefix="cosmosiq_recent_ev_empty_")
        panel = _panel(_home(store_dir))
        self.assertIn("No pulses yet", panel)
        self.assertIn('href="/evidence"', panel)
        # nothing fabricated: no evidence table rows
        self.assertNotIn("/companies/", panel)

    def test_empty_state_when_a_run_persisted_no_events(self):
        store_dir = tempfile.mkdtemp(prefix="cosmosiq_recent_ev_norows_")
        rm.RunStore(store_dir).append(_run_record("R-EV-EMPTY"))
        panel = _panel(_home(store_dir))
        self.assertIn("No pulses yet", panel)

    # -- fixture handling: demo, NEVER real canonical ------------------------------ #
    def test_fixture_event_marked_demo_never_canonical(self):
        panel = _panel(_home(self._store(_fixture_event())))
        # the fixture datum is marked demo ...
        self.assertIn("demo", panel)
        self.assertIn("ZGAMMA", panel)   # still visible, just honestly labelled
        # ... and its ZGAMMA row is NOT presented with a canonical chip, even though the stored
        # event CLAIMS source_authority="canonical".
        zrow = panel[panel.index("ZGAMMA"):]
        zrow = zrow[:zrow.index("</tr>")]
        self.assertNotIn("canonical", zrow)
        self.assertIn("demo", zrow)

    def test_fixture_ref_never_leaks_as_a_real_ref(self):
        panel = _panel(_home(self._store(_fixture_event())))
        self.assertNotIn("fixture:breadth", panel)   # the raw fixture ref is never rendered

    def test_real_canonical_still_shown_beside_a_fixture(self):
        panel = _panel(_home(self._store(_sec_event(), _fixture_event())))
        # the SEC row keeps its real canonical chip; the fixture row is demo -- no laundering.
        srow = panel[panel.index("ZALPHA"):]
        srow = srow[:srow.index("</tr>")]
        self.assertIn("canonical", srow)
        self.assertNotIn("demo", srow)

    # -- guardrails: no trade affordance / no score-rank / no secret --------------- #
    def test_no_trade_affordance_on_the_dashboard(self):
        html = _home(self._store(_sec_event(), _fmp_event(), _fixture_event()))
        # no trade verb anywhere on the whole Dashboard, and none in the new panel specifically.
        self.assertIsNone(_TRADE_WORD.search(html))
        self.assertIsNone(_TRADE_WORD.search(_panel(html)))

    def test_no_score_rank_rating_surface(self):
        panel = _panel(_home(self._store(_sec_event(), _fmp_event(), _fixture_event())))
        lowered = panel.lower()
        for token in _SCORE_TOKENS:
            self.assertNotIn(token, lowered, token)

    def test_no_secret_in_output(self):
        html = _home(self._store(_sec_event(), _fmp_event(), _fixture_event()))
        for pattern in _SECRET_PATTERNS:
            self.assertIsNone(pattern.search(html), pattern.pattern)


if __name__ == "__main__":
    unittest.main()
