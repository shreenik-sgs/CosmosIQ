"""GO-LIVE PL-3 -- the operator production-activation FLOW (promotion / rollback + readiness view).

OFFLINE, deterministic (a socket kill-switch is armed). Proves the honesty core:

* promotion is REFUSED unless run_prod_check (RE-RUN at request time) says
  production_mode_allowed=True -- with no attestations / no sign-off the exact blocking items are
  returned and NOTHING changes (mode stays OFF/SHADOW);
* promotion IS reachable in a fully-constructed scenario (both PL-2 attestations backed by real
  persisted live runs + a valid operator sign-off + current mode SHADOW_24X7 + an explicit operator
  + the confirm token) -> the mode becomes PRODUCTION_24X7 and a promotion event is journaled;
* only SHADOW_24X7 -> PRODUCTION_24X7 (an OFF/MANUAL jump is refused even when the gate allows);
* rollback to shadow from PRODUCTION_24X7 always works; the append-only event journal records both;
* PRODUCTION_24X7 is never the default (the service still starts OFF); execution stays MANUAL --
  the product UI + api carry no trade affordance and /api/production/{order,buy,sell,trade} -> 403;
  no score / rank / secret; the readiness page renders honest per-item status and the promote form
  is absent unless the gate allows it.

The gate CORE (activation.py), read_operator_signoff, and the PL-2 verifiers are NEVER modified --
this slice only composes them.
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import run_live_pulse
from reality_mesh.adapters.fmp_live import FmpLiveAdapter
from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter

from cosmosiq_app.api import dispatch
from cosmosiq_ops.activate import _write_mode_marker, read_current_mode
from cosmosiq_ops.ci_gate import TRADE_WORD_RE
from cosmosiq_ops.operator_attestation import (
    record_live_source_health_attestation,
    record_shadow_validation_attestation,
)
from cosmosiq_service.promotion_flow import (
    CONFIRM_TOKEN,
    request_production_promotion,
    read_promotion_events,
    rollback_to_shadow,
)
from cosmosiq_service.service import ServiceMode

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_SEC_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")
_FMP_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "fmp_live")
_NOW = "2026-06-29T15:00:00Z"
_THREE_DAYS = ("2026-06-27T14:00:00Z", "2026-06-28T14:00:00Z", "2026-06-29T14:00:00Z")
_CIK_TO_FIXTURE = {
    "0001878848": "sec_submissions_iren_live.json",
    "0000123456": "sec_submissions_aaoi_live.json",
}
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: PL-3 promotion tests run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return json.load(fh)


def _sec_adapter():
    return SecEdgarLiveAdapter(
        transport={
            "company_tickers": lambda: _load(_SEC_DIR, "company_tickers.json"),
            "submissions": lambda cik: _load(_SEC_DIR, _CIK_TO_FIXTURE[str(cik).zfill(10)])},
        sec_user_agent_present=True)


def _fmp_fetch(prefix):
    return lambda symbol: _load(_FMP_DIR, "{0}_{1}.json".format(prefix, str(symbol).strip().upper()))


def _fmp_adapter():
    return FmpLiveAdapter(
        transport={
            "profile": _fmp_fetch("profile"), "income_statement": _fmp_fetch("income"),
            "balance_sheet": _fmp_fetch("balance"), "cash_flow": _fmp_fetch("cashflow"),
            "ratios": _fmp_fetch("ratios"), "quote": _fmp_fetch("quote")},
        fmp_api_key_present=True)


def _seed_window(store_dir):
    """Seed three real live runs (SEC + FMP) over three calendar days; return the ordered ids."""
    rids = []
    for i, day in enumerate(_THREE_DAYS):
        result = run_live_pulse(
            "IREN,AAOI", "physical-ai,robotics", store_dir=store_dir, now=day,
            run_id="live-{0}".format(i), adapters=[_sec_adapter(), _fmp_adapter()])
        assert result.persisted, "seed run must persist"
        rids.append(result.run_id)
    return rids


def _write_signoff(dir_path, *, mode="PRODUCTION_24X7_APPROVED", name="Jane Operator",
                   timestamp="2026-06-29T00:00:00Z", acks=(True, True, True, True)):
    ack_lines = "\n".join(
        "- [{0}] **Acknowledgement {1}** accepted".format("x" if ok else " ", i + 1)
        for i, ok in enumerate(acks))
    text = (
        "# Operator Signoff\n\n## Signoff record\n\n| Field | Value |\n|-------|-------|\n"
        "| Operator name | {name} |\n| Timestamp (RFC3339) | {ts} |\n"
        "| Approved mode | `{mode}` |\n\n## Acknowledgements\n\n{acks}\n").format(
            name=name, ts=timestamp, mode=mode, acks=ack_lines)
    path = os.path.join(dir_path, "signoff.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _full_gate(store_dir, signoff_dir):
    """Construct a fully-satisfiable gate in ``store_dir`` (real runs + both attestations), current
    mode SHADOW_24X7, and return the path to a valid PRODUCTION sign-off."""
    rids = _seed_window(store_dir)
    record_live_source_health_attestation(
        store_dir, run_id=rids[-1],
        sources_reviewed=["evidence.sec_edgar_live", "evidence.fmp_live"],
        reviewed_by="op", reviewed_at=_NOW)
    record_shadow_validation_attestation(
        store_dir, window_run_ids=rids, reviewed_by="op", reviewed_at=_NOW)
    _write_mode_marker(store_dir, ServiceMode.SHADOW_24X7, now=_NOW)
    return _write_signoff(signoff_dir)


# --------------------------------------------------------------------------- #
# 1. Refusal without the full gate -- exact blocking items, nothing changes     #
# --------------------------------------------------------------------------- #
class RefusalTests(unittest.TestCase):
    def test_promote_refused_no_attestations_no_signoff(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work:
            result = request_production_promotion(
                store, work, _REPO_ROOT, now=_NOW, confirmed_by="op", confirm=CONFIRM_TOKEN,
                quick=True)
        self.assertFalse(result.promoted)
        self.assertFalse(result.production_mode_allowed)
        self.assertEqual(result.from_mode, "off")
        self.assertEqual(result.to_mode, "off")           # nothing changed
        for item in ("live_source_health", "operator_shadow_validation", "operator_signoff"):
            self.assertIn(item, result.blocking_items)

    def test_promote_refused_leaves_mode_unchanged_from_shadow(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work:
            _write_mode_marker(store, ServiceMode.SHADOW_24X7, now=_NOW)
            result = request_production_promotion(
                store, work, _REPO_ROOT, now=_NOW, confirmed_by="op", confirm=CONFIRM_TOKEN,
                quick=True)
            self.assertFalse(result.promoted)
            self.assertEqual(read_current_mode(store).value, "shadow_24x7")   # unchanged
            self.assertEqual(read_promotion_events(store), ())                # nothing journaled

    def test_promote_refused_when_confirm_token_missing_even_if_allowed(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work, \
                tempfile.TemporaryDirectory() as sd:
            signoff = _full_gate(store, sd)
            result = request_production_promotion(
                store, work, _REPO_ROOT, now=_NOW, confirmed_by="Jane Operator",
                confirm="not-the-token", signoff_path=signoff, quick=True)
            self.assertTrue(result.production_mode_allowed)   # the gate DID allow it ...
            self.assertFalse(result.promoted)                 # ... but the token was wrong -> refuse
            self.assertEqual(read_current_mode(store).value, "shadow_24x7")

    def test_promote_refused_when_confirmed_by_empty_even_if_allowed(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work, \
                tempfile.TemporaryDirectory() as sd:
            signoff = _full_gate(store, sd)
            result = request_production_promotion(
                store, work, _REPO_ROOT, now=_NOW, confirmed_by="  ", confirm=CONFIRM_TOKEN,
                signoff_path=signoff, quick=True)
            self.assertTrue(result.production_mode_allowed)
            self.assertFalse(result.promoted)
            self.assertEqual(read_current_mode(store).value, "shadow_24x7")


# --------------------------------------------------------------------------- #
# 2. The full-gate scenario reaches PRODUCTION_24X7 (prove it CAN happen)       #
# --------------------------------------------------------------------------- #
class FullGateTests(unittest.TestCase):
    def test_full_gate_shadow_to_production_promotes_and_records_event(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work, \
                tempfile.TemporaryDirectory() as sd:
            signoff = _full_gate(store, sd)
            result = request_production_promotion(
                store, work, _REPO_ROOT, now=_NOW, confirmed_by="Jane Operator",
                confirm=CONFIRM_TOKEN, signoff_path=signoff, quick=True)
            self.assertTrue(result.promoted, result.refusal_reasons)
            self.assertEqual(result.from_mode, "shadow_24x7")
            self.assertEqual(result.to_mode, "production_24x7")
            self.assertEqual(read_current_mode(store).value, "production_24x7")
            events = read_promotion_events(store)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "production_promotion")
            self.assertEqual(events[0]["confirmed_by"], "Jane Operator")
            # execution stays manual even in production -- no trade token in the banner/event
            self.assertIn("Manual Review Only", result.banner)
            self.assertIsNone(TRADE_WORD_RE.search(result.banner))

    def test_production_is_never_the_default_service_starts_off(self):
        # A freshly-configured service is OFF; PRODUCTION_24X7 is only ever reached through the flow.
        with tempfile.TemporaryDirectory() as store:
            self.assertEqual(read_current_mode(store).value, "off")


# --------------------------------------------------------------------------- #
# 3. Only SHADOW_24X7 -> PRODUCTION_24X7 (no OFF/MANUAL jump)                    #
# --------------------------------------------------------------------------- #
class LadderTests(unittest.TestCase):
    def test_off_and_manual_jump_refused_even_when_gate_allows(self):
        for mode in (ServiceMode.OFF, ServiceMode.MANUAL):
            with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work, \
                    tempfile.TemporaryDirectory() as sd:
                signoff = _full_gate(store, sd)          # gate satisfiable + attestations present
                _write_mode_marker(store, mode, now=_NOW)   # but current mode is OFF/MANUAL
                result = request_production_promotion(
                    store, work, _REPO_ROOT, now=_NOW, confirmed_by="Jane Operator",
                    confirm=CONFIRM_TOKEN, signoff_path=signoff, quick=True)
                self.assertTrue(result.production_mode_allowed)
                self.assertFalse(result.promoted, "no OFF/MANUAL -> PRODUCTION jump")
                self.assertEqual(read_current_mode(store).value, mode.value)
                self.assertTrue(any("ONLY from SHADOW_24X7" in r for r in result.refusal_reasons))


# --------------------------------------------------------------------------- #
# 4. Rollback is always available                                               #
# --------------------------------------------------------------------------- #
class RollbackTests(unittest.TestCase):
    def test_rollback_from_production_to_shadow_always_works(self):
        with tempfile.TemporaryDirectory() as store:
            _write_mode_marker(store, ServiceMode.PRODUCTION_24X7, now=_NOW)
            result = rollback_to_shadow(store, now=_NOW, actor="op", reason="drill")
        self.assertTrue(result.applied)
        self.assertEqual(result.from_mode, "production_24x7")
        self.assertEqual(result.to_mode, "shadow_24x7")

    def test_rollback_after_a_real_promotion_steps_back_down(self):
        with tempfile.TemporaryDirectory() as store, tempfile.TemporaryDirectory() as work, \
                tempfile.TemporaryDirectory() as sd:
            signoff = _full_gate(store, sd)
            request_production_promotion(
                store, work, _REPO_ROOT, now=_NOW, confirmed_by="Jane Operator",
                confirm=CONFIRM_TOKEN, signoff_path=signoff, quick=True)
            self.assertEqual(read_current_mode(store).value, "production_24x7")
            rb = rollback_to_shadow(store, now=_NOW, actor="Jane Operator")
            self.assertTrue(rb.applied)
            self.assertEqual(read_current_mode(store).value, "shadow_24x7")
            kinds = [e["event"] for e in read_promotion_events(store)]
            self.assertEqual(kinds, ["production_promotion", "production_rollback"])


# --------------------------------------------------------------------------- #
# 5. The product surface: readiness page + gated endpoints + no trade affordance #
# --------------------------------------------------------------------------- #
class ProductSurfaceTests(unittest.TestCase):
    def _get(self, store, path):
        return dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                        store_dir=store, now=_NOW)

    def _post(self, store, path, body):
        return dispatch({"method": "POST", "path": path, "query": {}, "body": body},
                        store_dir=store, now=_NOW)

    def test_readiness_page_renders_honest_status_and_no_promote_form_when_blocked(self):
        with tempfile.TemporaryDirectory() as store:
            response = self._get(store, "/production")
        self.assertEqual(response["status"], 200)
        body = response["body"]
        self.assertTrue(body.startswith("<!doctype html>"))
        self.assertIn("Production means 24x7", body)
        self.assertIn("Execution stays MANUAL", body)
        self.assertIn("shadow only", body)                      # honest overall verdict
        self.assertNotIn('action="/api/production/promote"', body)   # promote form ABSENT
        self.assertIn('action="/api/production/rollback"', body)     # rollback ALWAYS present

    def test_readiness_page_carries_no_trade_affordance_or_score(self):
        with tempfile.TemporaryDirectory() as store:
            body = self._get(store, "/production")["body"]
        self.assertIsNone(TRADE_WORD_RE.search(body))
        for word in ("buy", "sell", "broker", "order", "score", "rank", "rating"):
            self.assertIsNone(re.search(r"\b" + word + r"\b", body, re.I),
                              "readiness copy must carry no {0!r} word".format(word))

    def test_trade_like_production_routes_are_refused_403(self):
        with tempfile.TemporaryDirectory() as store:
            for tail in ("order", "buy", "sell", "trade"):
                response = self._post(store, "/api/production/" + tail, {})
                self.assertEqual(response["status"], 403, tail)

    def test_api_promote_refuses_premature_input_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as store:
            response = self._post(store, "/api/production/promote",
                                  {"confirmed_by": "op", "confirm": CONFIRM_TOKEN, "now": _NOW})
            self.assertEqual(response["status"], 400)       # refused, page re-rendered
            self.assertEqual(read_current_mode(store).value, "off")   # nothing changed

    def test_api_rollback_always_redirects(self):
        with tempfile.TemporaryDirectory() as store:
            response = self._post(store, "/api/production/rollback", {"actor": "op", "now": _NOW})
            self.assertEqual(response["status"], 303)
            self.assertEqual(response["headers"].get("Location"), "/production")

    def test_readiness_page_is_deterministic(self):
        with tempfile.TemporaryDirectory() as store:
            first = self._get(store, "/production")["body"]
            second = self._get(store, "/production")["body"]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
