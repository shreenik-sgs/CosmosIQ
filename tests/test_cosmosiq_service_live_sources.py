"""GO-LIVE PL-4 -- the SHADOW_24X7 supervised service runs REAL live pulses (OFFLINE, mocked).

The 020C/020D supervised service's fixture tick (``run_once`` -> ``run_due_pulses`` ->
fixture-based ``run_pulse``) can never build an honest paper window: a SHADOW tick persists
fixture / fixture-tainted evidence, so PL-2 ``verify_live_source_health`` can never clear. GO-LIVE
PL-4 makes the shadow tick run the credential-gated LIVE pulse (``run_live_pulse``,
``suppress_fixture_evidence``, real SEC/FMP evidence, honest gaps, NO fixture fallback) -- opt-in
via ``ServiceConfig.live_sources`` with the DEFAULT (fixture) path byte-identical.

Proved here, all OFFLINE (a socket kill-switch guards the whole module; mock adapters carry the
real adapter shapes, the real network path is NEVER exercised):

* the DEFAULT tick (live_sources=False) is byte-identical to today (fixture ``sched.`` run); the
  live seams (live_adapters / live_env) are ignored when live_sources is False;
* a LIVE shadow tick persists a REAL run (sec:/fmp: refs), ZERO fixture events; repeated across two
  injected days -> two real runs;
* live_sources=True + NO credentials -> an HONEST gap (nothing persisted / fabricated, no fixture
  fallback, NOT a failure -> no backoff);
* the produced REAL run PASSES PL-2 ``verify_live_source_health``;
* OFF still does nothing (even with live_sources=True); the PRODUCTION gate / state machine are
  untouched; no trade / score / secret; no network on import.
"""

from __future__ import annotations

import ast
import json
import os
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from cosmosiq_service import ServiceConfig, ServiceMode, load_health, run_once
from cosmosiq_service.service import _live_mode_allowed
from cosmosiq_ops import (
    record_live_source_health_attestation,
    verify_live_source_health,
)
from cosmosiq_service.activation import ChecklistStatus
from reality_mesh.adapters.fmp_live import FMP_LIVE_ADAPTER_ID, FmpLiveAdapter
from reality_mesh.adapters.sec_edgar_live import SEC_EDGAR_LIVE_ADAPTER_ID, SecEdgarLiveAdapter
from reality_mesh import (
    FMP_LIVE_ENV_VAR,
    SEC_LIVE_ENV_VAR,
    NO_LIVE_SOURCES_NOTE,
)
from reality_mesh import stores as S

_HERE = os.path.dirname(os.path.abspath(__file__))
_SEC_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")
_FMP_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "fmp_live")
_SERVICE_PY = os.path.join(_SRC, "cosmosiq_service", "service.py")

_WATCHLIST = ("IREN", "AAOI")
_THEMES = ("physical-ai", "robotics")
_NOW = "2026-06-29T15:00:00Z"
_NOW_DAY2 = "2026-06-30T15:00:00Z"

# Stand-in credential VALUES used ONLY to prove they never leak to a log / health file.
_FAKE_SEC_VALUE = "Jane Doe jane.doe-SECRET-hunter2@example.com"
_FAKE_FMP_VALUE = "sk-FAKEFMPKEY-hunter2-000"

_CIK_TO_FIXTURE = {
    "0001878848": "sec_submissions_iren_live.json",
    "0000123456": "sec_submissions_aaoi_live.json",
}

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: the live shadow tick must run fully offline on injected mock "
            "adapters -- the real network path is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _load(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as fh:
        return json.load(fh)


def _sec_transport(**overrides):
    bundle = {
        "company_tickers": lambda: _load(_SEC_DIR, "company_tickers.json"),
        "submissions": lambda cik: _load(_SEC_DIR, _CIK_TO_FIXTURE[str(cik).zfill(10)]),
    }
    bundle.update(overrides)
    return bundle


def _fmp_fetch(prefix):
    def _fetch(symbol):
        return _load(_FMP_DIR, "{0}_{1}.json".format(prefix, str(symbol).strip().upper()))
    return _fetch


def _fmp_transport(**overrides):
    bundle = {
        "profile": _fmp_fetch("profile"),
        "income_statement": _fmp_fetch("income"),
        "balance_sheet": _fmp_fetch("balance"),
        "cash_flow": _fmp_fetch("cashflow"),
        "ratios": _fmp_fetch("ratios"),
        "quote": _fmp_fetch("quote"),
    }
    bundle.update(overrides)
    return bundle


def _sec_adapter():
    return SecEdgarLiveAdapter(transport=_sec_transport(), sec_user_agent_present=True)


def _fmp_adapter():
    return FmpLiveAdapter(transport=_fmp_transport(), fmp_api_key_present=True)


def _live_adapters():
    return [_sec_adapter(), _fmp_adapter()]


def _live_config(store_dir, *, mode=ServiceMode.SHADOW_24X7, **kw):
    return ServiceConfig(
        mode=mode, store_dir=store_dir, subscriptions=(),
        live_sources=True, live_watchlist=_WATCHLIST, live_themes=_THEMES, **kw)


def _read_log(config):
    with open(config.log_path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# =========================================================================== #
# 1. The DEFAULT (live_sources=False) path is untouched                        #
# =========================================================================== #
class DefaultPathByteIdenticalTests(unittest.TestCase):
    def _fixture_config(self, store_dir):
        from reality_mesh.orchestrator import Subscription
        sub = Subscription(
            subscription_id="sub.core", watchlist=("IREN", "NVDA"),
            themes=("physical_ai", "robotics"), policy_ids=("cadence.news_filings",))
        return ServiceConfig(mode=ServiceMode.MANUAL, store_dir=store_dir, subscriptions=(sub,))

    def test_live_seams_are_ignored_when_live_sources_false(self):
        # Two fixture MANUAL ticks: one plain, one passing live_adapters/live_env. They must
        # produce byte-identical health files and event stores (the live seams are inert).
        d1, d2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        h1 = run_once(self._fixture_config(d1), now=_NOW, pid=7)
        h2 = run_once(self._fixture_config(d2), now=_NOW, pid=7,
                      live_adapters=_live_adapters(),
                      live_env={SEC_LIVE_ENV_VAR: _FAKE_SEC_VALUE})
        # a fixture scheduled run (never a live- run)
        self.assertTrue(h1.last_successful_run_id.startswith("sched.cadence.news_filings."))
        self.assertEqual(h1.last_successful_run_id, h2.last_successful_run_id)
        with open(os.path.join(d1, "event_store.jsonl"), "rb") as fh:
            b1 = fh.read()
        with open(os.path.join(d2, "event_store.jsonl"), "rb") as fh:
            b2 = fh.read()
        self.assertEqual(b1, b2)
        self.assertGreater(len(b1), 0)
        # the default config's live flag is OFF
        self.assertFalse(self._fixture_config(d1).live_sources)

    def test_config_defaults_leave_live_off(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = ServiceConfig(store_dir=d)
            self.assertFalse(cfg.live_sources)
            self.assertEqual(cfg.live_watchlist, ())
            self.assertEqual(cfg.live_themes, ())
            self.assertFalse(cfg.live_use_accepted_watchlist)


# =========================================================================== #
# 2. A LIVE shadow tick persists REAL evidence, ZERO fixture                    #
# =========================================================================== #
class LiveShadowTickTests(unittest.TestCase):
    def test_live_tick_persists_real_events_zero_fixture(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d)
        health = run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters())
        run_id = health.last_successful_run_id
        self.assertTrue(run_id.startswith("live-"))
        self.assertEqual(health.consecutive_failures, 0)
        self.assertEqual(health.last_error_class, "")
        self.assertEqual(health.last_tick_completed_at, _NOW)

        events = list(S.EventStore(d).query(run_id=run_id))
        self.assertTrue(events, "a live tick must persist its real adapter events")
        # ZERO fixture events; every event carries a real live source id.
        self.assertTrue(all(not str(e.source_id).startswith("fixture") for e in events))
        self.assertTrue(all(str(e.source_id) in ("sec.edgar", "fmp.live") for e in events))
        refs = " ".join(r for e in events for r in e.source_refs)
        self.assertIn("sec:", refs)
        self.assertIn("fmp:", refs)
        self.assertNotIn("fixture", refs)

    def test_two_injected_days_make_two_real_runs(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d)
        h1 = run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters())
        h2 = run_once(cfg, now=_NOW_DAY2, pid=11, live_adapters=_live_adapters())
        self.assertNotEqual(h1.last_successful_run_id, h2.last_successful_run_id)
        runs = {r.run_id for r in S.RunStore(d).read_all()}
        self.assertIn(h1.last_successful_run_id, runs)
        self.assertIn(h2.last_successful_run_id, runs)
        # both are real live runs; both persisted only real evidence
        all_events = list(S.EventStore(d).read_all())
        self.assertTrue(all(str(e.source_id) in ("sec.edgar", "fmp.live") for e in all_events))

    def test_live_success_log_is_structured_and_sanitized(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d)
        run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters(),
                 live_env={SEC_LIVE_ENV_VAR: _FAKE_SEC_VALUE, FMP_LIVE_ENV_VAR: _FAKE_FMP_VALUE})
        lines = _read_log(cfg)
        success = [ln for ln in lines if ln.get("event") == "tick.live_success"]
        self.assertEqual(len(success), 1)
        self.assertTrue(success[0]["live_sources"])
        self.assertFalse(success[0]["external_delivery"])       # shadow: inbox only
        self.assertFalse(success[0]["production_escalation"])
        # no credential value anywhere in the log or the health file
        blob = json.dumps(lines) + json.dumps(load_health(cfg).to_dict())
        self.assertNotIn("hunter2", blob)
        self.assertNotIn(_FAKE_SEC_VALUE, blob)
        self.assertNotIn(_FAKE_FMP_VALUE, blob)


# =========================================================================== #
# 3. live_sources=True + NO credentials -> honest gap (no fixture, no fake)     #
# =========================================================================== #
class HonestCredentialGapTests(unittest.TestCase):
    def test_no_creds_is_an_honest_gap_not_a_fixture_fallback(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d)
        # adapters=None + an EMPTY env -> no live source configured
        health = run_once(cfg, now=_NOW, pid=11, live_env={})
        # nothing succeeded, nothing failed, nothing backed off (an honest gap, not a failure)
        self.assertEqual(health.last_successful_run_id, "")
        self.assertEqual(health.consecutive_failures, 0)
        self.assertEqual(health.next_retry_at, "")
        self.assertEqual(health.last_error_class, "")
        # NOTHING persisted -- no run store, no event store, no fixture backfill
        self.assertFalse(os.path.isfile(os.path.join(d, "run_store.jsonl")))
        self.assertFalse(os.path.isfile(os.path.join(d, "event_store.jsonl")))
        lines = _read_log(cfg)
        gap = [ln for ln in lines if ln.get("event") == "tick.live_gap"]
        self.assertEqual(len(gap), 1)
        self.assertIn("No live sources configured", gap[0]["message"])

    def test_no_scope_configured_is_an_honest_no_op(self):
        d = tempfile.mkdtemp()
        cfg = ServiceConfig(mode=ServiceMode.SHADOW_24X7, store_dir=d, live_sources=True)
        health = run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters())
        self.assertEqual(health.last_successful_run_id, "")
        self.assertEqual(health.consecutive_failures, 0)
        self.assertFalse(os.path.isfile(os.path.join(d, "event_store.jsonl")))
        lines = _read_log(cfg)
        self.assertTrue(any(ln.get("event") == "tick.live_no_scope" for ln in lines))


# =========================================================================== #
# 4. The produced REAL run PASSES PL-2 verify_live_source_health                #
# =========================================================================== #
class VerifyLiveSourceHealthTests(unittest.TestCase):
    def test_live_run_satisfies_pl2_verifier(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d)
        health = run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters())
        run_id = health.last_successful_run_id
        self.assertTrue(run_id.startswith("live-"))

        # An operator records a live-source-health attestation naming the REAL run.
        record_live_source_health_attestation(
            d, run_id=run_id,
            sources_reviewed=(SEC_EDGAR_LIVE_ADAPTER_ID, FMP_LIVE_ADAPTER_ID),
            reviewed_by="operator.jane", reviewed_at=_NOW)

        # The verifier re-reads the persisted evidence and PASSES (real sec.edgar + fmp.live).
        result = verify_live_source_health(d, now=_NOW)
        self.assertEqual(result.status, ChecklistStatus.PASS,
                         "verify_live_source_health should PASS on the live tick's real evidence; "
                         "got {0}: {1}".format(result.status, result.details))


# =========================================================================== #
# 5. Modes / gates / hygiene                                                    #
# =========================================================================== #
class ModeGateAndHygieneTests(unittest.TestCase):
    def test_off_runs_nothing_even_with_live_sources(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d, mode=ServiceMode.OFF)
        health = run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters())
        self.assertEqual(health.service_mode, "off")
        self.assertEqual(health.last_successful_run_id, "")
        self.assertFalse(os.path.isfile(os.path.join(d, "event_store.jsonl")))

    def test_production_never_takes_the_live_path(self):
        # PRODUCTION is deliberately excluded from live sourcing (unchanged / still gated).
        self.assertFalse(_live_mode_allowed(ServiceMode.PRODUCTION_24X7))
        self.assertFalse(_live_mode_allowed(ServiceMode.OFF))
        self.assertTrue(_live_mode_allowed(ServiceMode.SHADOW_24X7))
        self.assertTrue(_live_mode_allowed(ServiceMode.MANUAL))

    def test_manual_mode_supports_live_on_demand(self):
        d = tempfile.mkdtemp()
        cfg = _live_config(d, mode=ServiceMode.MANUAL)
        health = run_once(cfg, now=_NOW, pid=11, live_adapters=_live_adapters())
        self.assertTrue(health.last_successful_run_id.startswith("live-"))
        # a MANUAL live tick does NOT emit shadow alerts (that hook is SHADOW_24X7 only)
        lines = _read_log(cfg)
        success = [ln for ln in lines if ln.get("event") == "tick.live_success"]
        self.assertNotIn("external_delivery", success[0])

    def test_no_network_import_in_service_module(self):
        with open(_SERVICE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib")
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            for name in names:
                for root in banned:
                    self.assertFalse(
                        name == root or name.startswith(root + "."),
                        "network import {0!r} in service.py".format(name))

    def test_no_trade_or_score_affordance_in_live_helpers(self):
        import re
        with open(_SERVICE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(
                    re.search(r"(score|rank|rating|broker|_order|buy|sell)", node.name),
                    "banned fn name {0!r}".format(node.name))


if __name__ == "__main__":
    unittest.main()
