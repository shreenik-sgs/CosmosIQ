"""PROD-LIVE-3 -- the AI Research Assistant PANEL on Company Research (OFFLINE, mocked provider).

Exercises the cockpit panel end-to-end through the pure ``dispatch`` surface:

* the idle GET /research panel with NO key shows the honest "not configured" state and carries the
  mandatory AI-generated label, and it passes the repo trade-affordance sweep (TRADE_WORD_RE);
* a POST /api/assistant/summarize | /api/assistant/thesis with an injected fake provider renders the
  labelled, POST-FILTERED result -- the "[action directive removed ...]" marker replaces a
  buy/sell/order directive and NONE of the 020D forbidden phrases survive;
* a planted key VALUE never appears in the rendered panel;
* there is no trade affordance (the trade-path guard also refuses any /api/.../order route with 403).

Fully offline: a module-wide socket kill-switch + injected fake clients; the real provider network
is never exercised.
"""

import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cosmosiq_app.api import dispatch
from cosmosiq_assistant.router import clear_test_clients, install_test_clients
from cosmosiq_ops.ci_gate import TRADE_WORD_RE
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES

_NOW = "2026-07-05T00:00:00Z"
_PLANTED_KEY = "sk-PLANTED-hunter2-VALUE-should-never-appear-000"
_ALL_KEYS = ("NVIDIA_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_FALLBACK")

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: the assistant panel must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


class FakeClient:
    def __init__(self, provider, *, out="ok"):
        self.provider = provider
        self.configured = True
        self._out = out

    def complete(self, prompt, *, system=""):
        return self._out


def _clear_env():
    for key in _ALL_KEYS:
        os.environ.pop(key, None)


def _get(store_dir, path):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                    store_dir=store_dir, now=_NOW)


def _post(store_dir, path, body):
    return dispatch({"method": "POST", "path": path, "query": {}, "body": body},
                    store_dir=store_dir, now=_NOW)


class AssistantPanelTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp()
        _clear_env()
        clear_test_clients()

    def tearDown(self):
        _clear_env()
        clear_test_clients()

    # -- idle / not-configured ------------------------------------------------ #
    def test_idle_research_page_shows_not_configured_and_the_label(self):
        resp = _get(self.store, "/research")
        self.assertEqual(resp["status"], 200)
        html = resp["body"]
        self.assertIn("AI Research Assistant", html)
        self.assertIn("AI-generated", html)          # the mandatory label
        self.assertIn("AI assistant not configured", html)
        self.assertIn("NVIDIA_API_KEY", html)        # honest env-var guidance

    def test_idle_panel_passes_the_trade_affordance_sweep(self):
        resp = _get(self.store, "/research")
        match = TRADE_WORD_RE.search(resp["body"])
        self.assertIsNone(match, "idle assistant panel tripped the trade sweep: {0}".format(
            match.group(0) if match else ""))

    # -- configured: buttons render ------------------------------------------- #
    def test_configured_panel_renders_the_two_ai_actions(self):
        os.environ["NVIDIA_API_KEY"] = _PLANTED_KEY
        html = _get(self.store, "/research")["body"]
        self.assertIn("Summarise this filing (AI)", html)
        self.assertIn("Draft a thesis note (AI)", html)
        self.assertIn("/api/assistant/summarize", html)
        self.assertIn("/api/assistant/thesis", html)
        self.assertIn("Use full API (Claude)", html)
        self.assertNotIn(_PLANTED_KEY, html)         # presence only -- the value never renders

    # -- POST summarize: labelled, post-filtered, no key leak ----------------- #
    def test_post_summarize_renders_labelled_post_filtered_output(self):
        os.environ["NVIDIA_API_KEY"] = _PLANTED_KEY
        install_test_clients({"nvidia": FakeClient(
            "nvidia", out="Strong buy now, submit order. Revenue up 40%.")})
        resp = _post(self.store, "/api/assistant/summarize",
                     {"filing_text": "IREN 8-K material agreement", "ticker": "iren",
                      "now": _NOW})
        self.assertEqual(resp["status"], 200)
        html = resp["body"]
        self.assertIn("AI-generated", html)
        self.assertIn("action directive removed", html)
        self.assertIn("nvidia", html)                # provider used shown
        self.assertIn("Revenue up 40%", html)
        low = html.lower()
        for phrase in FORBIDDEN_ALERT_PHRASES:
            self.assertNotIn(phrase, low,
                             "forbidden phrase {0!r} rendered in the panel".format(phrase))
        self.assertNotIn(_PLANTED_KEY, html)
        self.assertNotIn("hunter2", html)

    def test_post_thesis_uses_full_api_when_opted_in(self):
        os.environ["ANTHROPIC_API_KEY"] = _PLANTED_KEY
        install_test_clients({"anthropic": FakeClient("anthropic", out="A neutral review note.")})
        resp = _post(self.store, "/api/assistant/thesis",
                     {"ticker": "IREN", "evidence_context": "strong margins; dilution risk",
                      "mode": "full_api", "now": _NOW})
        self.assertEqual(resp["status"], 200)
        html = resp["body"]
        self.assertIn("A neutral review note.", html)
        self.assertIn("anthropic", html)
        self.assertIn("AI thesis note", html)

    def test_post_with_no_key_is_the_honest_not_configured_state(self):
        _clear_env()
        resp = _post(self.store, "/api/assistant/summarize",
                     {"filing_text": "x", "now": _NOW})
        self.assertEqual(resp["status"], 200)
        self.assertIn("AI assistant not configured", resp["body"])

    # -- no trade affordance -------------------------------------------------- #
    def test_no_order_route_is_refused_403(self):
        resp = _post(self.store, "/api/assistant/order", {"now": _NOW})
        self.assertEqual(resp["status"], 403)         # trade-path guard refuses it outright


if __name__ == "__main__":
    unittest.main()
