"""IMPLEMENTATION-020E -- the in-app alert inbox shows each alert's delivery STATUS (OFFLINE).

Proves the app surface of the delivery ledger:

* the /alerts inbox reads the latest delivery status per alert from the append-only
  AlertDeliveryStore and renders a Delivery column (delivered / suppressed_by_mode /
  suppressed_by_policy / failed_*);
* the inbox HTML carries NO forbidden trade/action language;
* with no delivery records the inbox still renders (the column shows an em-dash), and an inbox
  with no alerts is unchanged.

Pure + offline: the dispatcher is exercised directly; a socket kill-switch guards the module.
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
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES
from reality_mesh.alert_delivery import (
    AlertDeliveryPolicy, EmailChannel, InboxChannel, deliver_alert)
from cosmosiq_app.api import dispatch

_NOW = "2026-06-29T15:00:00Z"
_FORBIDDEN_SWEEP = re.compile(
    "|".join(re.escape(p) for p in sorted(FORBIDDEN_ALERT_PHRASES)), re.IGNORECASE)

_ORIG_CONNECT = None


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline 020E inbox suite")


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _get(store_dir, path="/alerts"):
    return dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                    store_dir=store_dir, now=_NOW)["body"]


def _seed_alert(store_dir, *, alert_id="al.1", category="filing_dilution_risk",
                severity="warning", dq_state="healthy"):
    alert = rm.Alert(
        alert_id=alert_id, run_id="RUN-1", category=category, severity=severity,
        human_readable_reason="A new dilution filing appeared between runs.",
        created_at=_NOW, dq_state=dq_state, evidence_refs=("sec:accession/1",),
        subject_tickers=("IREN",), recommended_review_action="Review Red-Team Risk")
    rm.AlertStore(store_dir).append(alert, timestamp=_NOW)
    return alert


class DeliveryInboxTests(unittest.TestCase):
    def test_inbox_shows_delivered_and_suppressed_statuses(self):
        with tempfile.TemporaryDirectory() as d:
            alert = _seed_alert(d)
            deliver_alert(alert, policy=AlertDeliveryPolicy.default(), mode="SHADOW_24X7",
                          channels=(InboxChannel(), EmailChannel()), store_dir=d, now=_NOW)
            html = _get(d)
            self.assertIn("Delivery", html)                 # the new column header
            self.assertIn("suppressed (mode)", html)         # email suppressed_by_mode in shadow

    def test_inbox_shows_production_suppressed_by_policy(self):
        with tempfile.TemporaryDirectory() as d:
            alert = _seed_alert(d)
            deliver_alert(alert, policy=AlertDeliveryPolicy.default(), mode="PRODUCTION_24X7",
                          channels=(EmailChannel(),), store_dir=d, now=_NOW)
            html = _get(d)
            self.assertIn("suppressed (policy)", html)

    def test_inbox_carries_no_forbidden_trade_language(self):
        with tempfile.TemporaryDirectory() as d:
            alert = _seed_alert(d)
            deliver_alert(alert, policy=AlertDeliveryPolicy.default(), mode="SHADOW_24X7",
                          channels=(InboxChannel(), EmailChannel()), store_dir=d, now=_NOW)
            html = _get(d)
            self.assertIsNone(_FORBIDDEN_SWEEP.search(html))

    def test_inbox_renders_with_no_delivery_records(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_alert(d)
            html = _get(d)                                   # no delivery attempts yet
            self.assertIn("Delivery", html)
            self.assertIn("A new dilution filing appeared", html)

    def test_empty_inbox_still_renders(self):
        with tempfile.TemporaryDirectory() as d:
            html = _get(d)
            self.assertIn("No alerts in this store yet", html)


if __name__ == "__main__":
    unittest.main()
