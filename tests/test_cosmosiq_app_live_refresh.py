"""PROD-LIVE-1 -- the cockpit "Refresh from live sources" operator form (OFFLINE).

The sanctioned, credential-gated live-refresh action on the Dashboard: presence indicators
(labels only, never a value), a POST to /api/pulse/live that calls ``run_live_pulse`` against the
cockpit store, and an honest result render. Record/refresh-only -- no broker / order / trade
affordance (a trade route is refused 403). All OFFLINE: the no-credentials path attempts no
network, and the configured render is exercised via injected mock adapters.
"""
import json
import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cosmosiq_app.api import dispatch
from cosmosiq_app import pages as _pages
from reality_mesh import SEC_LIVE_ENV_VAR, FMP_LIVE_ENV_VAR, run_live_pulse
from reality_mesh.adapters.fmp_live import FmpLiveAdapter
from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter

_HERE = os.path.dirname(os.path.abspath(__file__))
_SEC_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")
_FMP_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "fmp_live")
_NOW = "2026-07-05T14:00:00Z"
_FAKE_SEC_VALUE = "Jane Doe jane.doe-SECRET-hunter2@example.com"
_CIK_TO_FIXTURE = {
    "0001878848": "sec_submissions_iren_live.json",
    "0000123456": "sec_submissions_aaoi_live.json",
}
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: live refresh must be fully offline in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return json.load(fh)


def _sec_adapter():
    transport = {
        "company_tickers": lambda: _load(_SEC_DIR, "company_tickers.json"),
        "submissions": lambda cik: _load(_SEC_DIR, _CIK_TO_FIXTURE[str(cik).zfill(10)]),
    }
    return SecEdgarLiveAdapter(transport=transport, sec_user_agent_present=True)


def _fmp_adapter():
    def fetch(prefix):
        return lambda s: _load(_FMP_DIR, "{0}_{1}.json".format(prefix, str(s).strip().upper()))
    transport = {"profile": fetch("profile"), "income_statement": fetch("income"),
                 "balance_sheet": fetch("balance"), "cash_flow": fetch("cashflow"),
                 "ratios": fetch("ratios"), "quote": fetch("quote")}
    return FmpLiveAdapter(transport=transport, fmp_api_key_present=True)


class LiveRefreshFormTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp()
        self._saved = {k: os.environ.pop(k, None)
                       for k in (SEC_LIVE_ENV_VAR, FMP_LIVE_ENV_VAR)}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v

    def _get_evidence(self):
        return dispatch({"method": "GET", "path": "/evidence"}, store_dir=self.store, now=_NOW)

    def test_evidence_shows_form_and_presence_indicators(self):
        resp = self._get_evidence()
        body = resp["body"]
        self.assertEqual(resp["status"], 200)
        self.assertIn("Refresh from external sources", body)
        self.assertIn('action="/api/pulse/refresh"', body)
        self.assertIn("SEC EDGAR: not configured", body)
        self.assertIn("FMP: not configured", body)

    def test_post_no_creds_renders_honest_note(self):
        resp = dispatch(
            {"method": "POST", "path": "/api/pulse/live",
             "body": {"watchlist": ["IREN"], "themes": ["physical-ai"], "now": _NOW}},
            store_dir=self.store, now=_NOW)
        self.assertEqual(resp["status"], 200)
        self.assertIn("No external sources configured", resp["body"])
        self.assertIn(SEC_LIVE_ENV_VAR, resp["body"])
        # nothing persisted on the honest no-run path
        self.assertEqual([n for n in os.listdir(self.store) if n.endswith(".jsonl")], [])

    def test_form_carries_no_guarded_overclaim_or_trade_or_token_words(self):
        # the Evidence tab is scanned by the coherence guards -- the sanctioned form must be free
        # of the word "live", any trade verb, and any credential key token.
        import re
        body = self._get_evidence()["body"]
        self.assertIsNone(re.search(r"\blive\b", body, re.IGNORECASE))
        self.assertEqual(
            re.findall(r"\b(buy|sell|order|submit|execute|trade|broker)\b", body, re.IGNORECASE),
            [])
        for token in ("api_key", "apikey", "secret", "password", "bearer", "credential"):
            self.assertNotIn(token, body.lower())

    def test_no_trade_affordance_and_order_route_403(self):
        refusal = dispatch({"method": "POST", "path": "/api/orders", "body": {}},
                           store_dir=self.store, now=_NOW)
        self.assertEqual(refusal["status"], 403)

    def test_get_requires_no_secret_value(self):
        # even with a value present in env, the rendered presence label carries no value
        os.environ[SEC_LIVE_ENV_VAR] = _FAKE_SEC_VALUE
        try:
            body = self._get_evidence()["body"]
        finally:
            os.environ.pop(SEC_LIVE_ENV_VAR, None)
        self.assertIn("SEC EDGAR: configured", body)
        self.assertNotIn(_FAKE_SEC_VALUE, body)
        self.assertNotIn("hunter2", body)

    def test_configured_refresh_persists_and_appears_on_evidence(self):
        # exercise the CONFIGURED path offline via injected mock adapters, then confirm the run
        # is persisted and visible on the Evidence page.
        result = run_live_pulse("IREN,AAOI", ["physical-ai", "robotics"],
                                store_dir=self.store, now=_NOW,
                                adapters=[_sec_adapter(), _fmp_adapter()])
        self.assertTrue(result.persisted)
        html = _pages.render_evidence_page(
            self.store, refresh_note="Refreshed from external sources (shadow, record-only).")
        self.assertIn(result.run_id, html)
        self.assertIn("Refreshed from external sources", html)


if __name__ == "__main__":
    unittest.main()
