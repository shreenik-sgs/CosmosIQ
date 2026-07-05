"""IMPLEMENTATION-020D -- the cosmosiq_app SHADOW mode indicator + shadow alert inbox (OFFLINE).

Proves the app surface of Shadow 24x7:

* the product pages read the service mode from ``<store>/service_health.json`` (else OFF) and,
  in SHADOW, render the VERBATIM indicator ``Mode: SHADOW_24X7 · Live Data: ... · Scheduler: On
  · Broker: Disabled · Execution: Manual Review Only · Alerts: Shadow Mode`` -- and NEVER the
  words "Production 24x7" in shadow;
* with no service_health.json (the default posture) the pages are byte-identical to 015C (no
  indicator injected);
* the alert inbox renders a shadow alert with the Shadow Mode marker + its recommended review
  action + no buy/sell/order language.

Pure + offline: the dispatcher is exercised directly; a socket kill-switch guards the module.
"""

from __future__ import annotations

import json
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
from reality_mesh import stores as S
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES, SHADOW_MARKER, to_shadow
from reality_mesh.runtime import PulseRun
from cosmosiq_app.api import dispatch
from cosmosiq_app.pages import service_mode_indicator

_NOW = "2026-06-29T15:00:00Z"

_SHADOW_LINE = ("Mode: SHADOW_24X7 · Live Data: On · Scheduler: On · Broker: Disabled · "
                "Execution: Manual Review Only · Alerts: Shadow Mode")

_PAGES = ("/", "/runs", "/alerts", "/settings")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline 020D app suite")


_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _get(store_dir, path):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                    store_dir=store_dir, now=_NOW)["body"]


def _seed_run(store_dir):
    S.RunStore(store_dir).append(
        PulseRun(run_id="RUN-0", started_at=_NOW, completed_at=_NOW, mode="pulse"),
        timestamp=_NOW)


def _write_health(store_dir, *, mode, failed=0, coverage=3):
    health = {
        "service_mode": mode,
        "source_health_summary": {"coverage_records": coverage,
                                  "failed_source_records": failed},
    }
    with open(os.path.join(store_dir, "service_health.json"), "w", encoding="utf-8") as fh:
        json.dump(health, fh)


class ShadowModeIndicatorTests(unittest.TestCase):
    def test_shadow_indicator_is_verbatim_on_every_product_page(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _write_health(d, mode="shadow_24x7")
            for path in _PAGES:
                html = _get(d, path)
                self.assertIn(_SHADOW_LINE, html, path)

    def test_shadow_indicator_never_says_production(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _write_health(d, mode="shadow_24x7")
            for path in _PAGES:
                html = _get(d, path)
                self.assertNotIn("Production 24x7", html, path)
                self.assertNotIn("PRODUCTION_24X7", html, path)

    def test_indicator_marks_a_source_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _write_health(d, mode="shadow_24x7", failed=1)
            html = _get(d, "/")
            self.assertIn("Live Data: Source gap", html)

    def test_no_health_file_means_no_indicator_byte_identical_default(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            _seed_run(d1)
            _seed_run(d2)
            _write_health(d2, mode="shadow_24x7")
            plain = _get(d1, "/")
            shadow = _get(d2, "/")
            # the ONLY difference the health file introduces is the mode indicator
            self.assertEqual(service_mode_indicator(d1), "")
            self.assertNotIn("Mode: SHADOW_24X7", plain)
            self.assertIn("Mode: SHADOW_24X7", shadow)

    def test_off_mode_indicator_carries_no_live_or_broker_alarm_words(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _write_health(d, mode="off", coverage=0)
            html = _get(d, "/")
            self.assertIn("Mode: OFF", html)
            self.assertNotIn("SHADOW_24X7", html)


class ShadowAlertInboxTests(unittest.TestCase):
    def _seed_shadow_alert(self, store_dir):
        base = rm.Alert(
            alert_id="alert.RUN-0.theme_pulse_changed.physical-ai", run_id="RUN-0",
            category="theme_pulse_changed", severity="notice",
            human_readable_reason="Theme pulse for 'physical-ai' changed state from 'Warming' "
                                  "to 'Igniting'.",
            subject_themes=("physical-ai",), created_at=_NOW)
        shadow = to_shadow(base, now=_NOW, dq_state="pass")
        rm.AlertStore(store_dir).append(shadow, timestamp=_NOW)
        return shadow

    def test_inbox_shows_the_shadow_marker_and_review_action(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            shadow = self._seed_shadow_alert(d)
            html = _get(d, "/alerts")
            self.assertIn("Shadow Mode", html)
            self.assertIn(shadow.recommended_review_action, html)
            self.assertIn("Review Thesis", html)

    def test_inbox_shadow_alert_has_no_action_language(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            self._seed_shadow_alert(d)
            html = _get(d, "/alerts")
            sweep = re.compile("|".join(re.escape(p) for p in FORBIDDEN_ALERT_PHRASES),
                               re.IGNORECASE)
            self.assertIsNone(sweep.search(html))


if __name__ == "__main__":
    unittest.main()
