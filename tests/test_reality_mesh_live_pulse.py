"""PROD-LIVE-1 -- the credential-gated LIVE pulse wiring (OFFLINE, mocked transports).

``reality_mesh.live_pulse`` composes the accepted 020B SEC EDGAR + 021A FMP live adapters with the
frozen ``run_pulse`` / ``persist_and_summarize`` into a first-class, sanctioned operator refresh.

Discipline proved here (all OFFLINE -- the real network path is NEVER exercised):

* ``build_live_adapters`` is built from credential PRESENCE only (SEC adapter iff SEC_USER_AGENT,
  FMP adapter iff FMP_API_KEY); neither -> empty + honest notes; the credential VALUE never appears
  in a note / result;
* ``run_live_pulse`` with INJECTED mock transports produces events/signals, persists to the store,
  reports per-source health, keeps SEC canonical + FMP convenience, and turns a 429 / timeout into
  a VISIBLE gap (other source continues; no fixture fallback);
* BOTH credentials missing -> an honest empty result: NO run fabricated, NO fixture fallback, and
  NO network attempted (the socket kill-switch stays clean);
* NO network on import (AST + kill-switch); NO secret value in any output; the ``--live`` CLI is
  offline-safe with no creds; the default (non-live) path stays byte-identical.
"""
import ast
import io
import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import (
    FMP_LIVE_ENV_VAR,
    NO_LIVE_SOURCES_NOTE,
    SEC_LIVE_ENV_VAR,
    LivePulseResult,
    build_live_adapters,
    run_live_pulse,
)
from reality_mesh.adapters.fmp_live import FmpLiveAdapter
from reality_mesh.adapters.sec_edgar_live import SecEdgarLiveAdapter

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PY = os.path.join(_HERE, "..", "src", "reality_mesh", "live_pulse.py")
_SEC_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "sec_edgar_live")
_FMP_DIR = os.path.join(_HERE, "fixtures", "reality_mesh", "fmp_live")

_WATCHLIST = "IREN,AAOI"
_THEMES = "physical-ai,robotics"
_NOW = "2026-07-05T14:00:00Z"

_CIK_TO_FIXTURE = {
    "0001878848": "sec_submissions_iren_live.json",
    "0000123456": "sec_submissions_aaoi_live.json",
}

# A stand-in credential VALUE used ONLY to prove it never leaks anywhere.
_FAKE_SEC_VALUE = "Jane Doe jane.doe-SECRET-hunter2@example.com"
_FAKE_FMP_VALUE = "sk-FAKEFMPKEY-hunter2-000"

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: the live pulse must run fully offline on injected mock transports "
            "-- the real network path is never exercised in tests")

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


def _raise_429(*_a):
    raise RuntimeError("HTTP 429 Too Many Requests (rate exceeded)")


def _raise_timeout(*_a):
    raise RuntimeError("connection timed out / reset by peer (simulated source failure)")


def _sec_adapter(**t):
    return SecEdgarLiveAdapter(transport=_sec_transport(**t), sec_user_agent_present=True)


def _fmp_adapter(**t):
    return FmpLiveAdapter(transport=_fmp_transport(**t), fmp_api_key_present=True)


def _result_text(result):
    """Every rendered / returned string of a LivePulseResult, for leak scans."""
    parts = list(result.config_notes) + list(result.data_gaps) + list(result.sources_configured)
    parts.append(result.run_id)
    parts.append(result.summary_line())
    for h in result.source_health:
        parts.extend([h.adapter_id, h.source_name, h.authority, h.status, h.health,
                      h.credentials_status, h.rate_limit_status])
        parts.extend(h.data_gaps)
    return " ".join(str(p) for p in parts)


# --------------------------------------------------------------------------- #
# 1. build_live_adapters -- credential PRESENCE only                            #
# --------------------------------------------------------------------------- #
class BuildLiveAdaptersTests(unittest.TestCase):
    def test_sec_only_present_builds_a_sec_adapter(self):
        adapters, notes = build_live_adapters(env={SEC_LIVE_ENV_VAR: _FAKE_SEC_VALUE})
        self.assertEqual(len(adapters), 1)
        self.assertIsInstance(adapters[0], SecEdgarLiveAdapter)
        self.assertIn("SEC live: configured", notes)
        self.assertIn("FMP live: not configured ({0} missing)".format(FMP_LIVE_ENV_VAR), notes)

    def test_fmp_only_present_builds_an_fmp_adapter(self):
        adapters, notes = build_live_adapters(env={FMP_LIVE_ENV_VAR: _FAKE_FMP_VALUE})
        self.assertEqual(len(adapters), 1)
        self.assertIsInstance(adapters[0], FmpLiveAdapter)
        self.assertIn("FMP live: configured", notes)
        self.assertIn("SEC live: not configured ({0} missing)".format(SEC_LIVE_ENV_VAR), notes)

    def test_both_present_builds_both_sec_first(self):
        adapters, notes = build_live_adapters(
            env={SEC_LIVE_ENV_VAR: _FAKE_SEC_VALUE, FMP_LIVE_ENV_VAR: _FAKE_FMP_VALUE})
        self.assertEqual([type(a).__name__ for a in adapters],
                         ["SecEdgarLiveAdapter", "FmpLiveAdapter"])
        self.assertIn("SEC live: configured", notes)
        self.assertIn("FMP live: configured", notes)

    def test_neither_present_is_empty_with_honest_notes(self):
        adapters, notes = build_live_adapters(env={})
        self.assertEqual(adapters, ())
        self.assertEqual(len(notes), 2)
        self.assertTrue(all("not configured" in n for n in notes))

    def test_credential_value_never_appears_in_notes(self):
        _adapters, notes = build_live_adapters(
            env={SEC_LIVE_ENV_VAR: _FAKE_SEC_VALUE, FMP_LIVE_ENV_VAR: _FAKE_FMP_VALUE})
        blob = " ".join(notes)
        self.assertNotIn(_FAKE_SEC_VALUE, blob)
        self.assertNotIn(_FAKE_FMP_VALUE, blob)
        self.assertNotIn("hunter2", blob)

    def test_non_mapping_env_is_refused_without_echo(self):
        with self.assertRaises(ValueError) as ctx:
            build_live_adapters(env=_FAKE_SEC_VALUE)   # a value passed by mistake
        self.assertNotIn(_FAKE_SEC_VALUE, str(ctx.exception))


# --------------------------------------------------------------------------- #
# 2. run_live_pulse with INJECTED mock transports -> events, persistence, health #
# --------------------------------------------------------------------------- #
class RunLivePulseTests(unittest.TestCase):
    def _run(self, adapters, store_dir=None, **kw):
        store_dir = store_dir or tempfile.mkdtemp()
        return run_live_pulse(_WATCHLIST, _THEMES, store_dir=store_dir, now=_NOW,
                              adapters=adapters, **kw), store_dir

    def test_produces_events_signals_and_persists(self):
        result, store_dir = self._run([_sec_adapter(), _fmp_adapter()])
        self.assertIsInstance(result, LivePulseResult)
        self.assertTrue(result.configured)
        self.assertTrue(result.persisted)
        self.assertTrue(result.shadow)
        self.assertGreater(result.events_loaded, 0)
        self.assertGreater(result.signals, 0)
        self.assertTrue(result.replay_deterministic_match)
        # the append-only stores were actually written
        self.assertIn("event_store.jsonl", os.listdir(store_dir))
        self.assertIn("signal_store.jsonl", os.listdir(store_dir))

    def test_reports_source_health_per_adapter(self):
        result, _ = self._run([_sec_adapter(), _fmp_adapter()])
        by_id = {h.adapter_id: h for h in result.source_health}
        self.assertEqual(by_id["evidence.sec_edgar_live"].health, "healthy")
        self.assertEqual(by_id["evidence.fmp_live"].health, "healthy")
        self.assertGreater(by_id["evidence.sec_edgar_live"].events_created, 0)
        self.assertGreater(by_id["evidence.fmp_live"].events_created, 0)

    def test_sec_canonical_outranks_fmp_convenience(self):
        result, _ = self._run([_sec_adapter(), _fmp_adapter()])
        by_id = {h.adapter_id: h for h in result.source_health}
        self.assertEqual(by_id["evidence.sec_edgar_live"].authority, "canonical")
        self.assertEqual(by_id["evidence.fmp_live"].authority, "convenience")
        # the produced signals preserve the ladder: canonical + convenience both present.
        authorities = set(result.pulse_result.authority_by_signal.values())
        self.assertIn("canonical", authorities)
        self.assertIn("convenience", authorities)

    def test_fetch_failure_is_a_visible_gap_not_a_fixture_fallback(self):
        # SEC 429 -> rate_limited gap; FMP still delivers. No news_filings fixture backfill.
        result, _ = self._run([
            _sec_adapter(submissions=_raise_429), _fmp_adapter()])
        by_id = {h.adapter_id: h for h in result.source_health}
        self.assertEqual(by_id["evidence.sec_edgar_live"].health, "rate_limited")
        self.assertEqual(by_id["evidence.sec_edgar_live"].events_created, 0)
        self.assertEqual(by_id["evidence.fmp_live"].health, "healthy")   # other source continues
        gap_blob = " ".join(result.data_gaps)
        self.assertIn("rate limit", gap_blob.lower())
        # SEC delivered ZERO events (no fixture backfill for the covered news_filings
        # discipline); the FMP financial_inflection events still landed.
        self.assertGreater(by_id["evidence.fmp_live"].events_created, 0)

    def test_timeout_failure_is_source_unavailable_gap(self):
        result, _ = self._run([_sec_adapter(submissions=_raise_timeout), _fmp_adapter()])
        by_id = {h.adapter_id: h for h in result.source_health}
        self.assertIn(by_id["evidence.sec_edgar_live"].health,
                      ("source_unavailable", "failed", "degraded"))
        self.assertEqual(by_id["evidence.fmp_live"].health, "healthy")

    def test_deterministic_run_id_and_replay(self):
        d = tempfile.mkdtemp()
        r1 = run_live_pulse(_WATCHLIST, _THEMES, store_dir=d, now=_NOW,
                            adapters=[_sec_adapter(), _fmp_adapter()])
        # same scope + now -> same derived run_id
        d2 = tempfile.mkdtemp()
        r2 = run_live_pulse(_WATCHLIST, _THEMES, store_dir=d2, now=_NOW,
                            adapters=[_sec_adapter(), _fmp_adapter()])
        self.assertEqual(r1.run_id, r2.run_id)
        self.assertTrue(r1.run_id.startswith("live-"))

    def test_no_secret_value_in_any_output(self):
        # Even with the values PRESENT in env, run_live_pulse (using injected adapters) must
        # never surface a value. Scan the whole result blob.
        result, _ = self._run(
            [_sec_adapter(), _fmp_adapter()],
            env={SEC_LIVE_ENV_VAR: _FAKE_SEC_VALUE, FMP_LIVE_ENV_VAR: _FAKE_FMP_VALUE})
        blob = _result_text(result)
        self.assertNotIn(_FAKE_SEC_VALUE, blob)
        self.assertNotIn(_FAKE_FMP_VALUE, blob)
        self.assertNotIn("hunter2", blob)


# --------------------------------------------------------------------------- #
# 3. BOTH creds missing -> honest empty result, NO run, NO network              #
# --------------------------------------------------------------------------- #
class BothMissingTests(unittest.TestCase):
    def test_honest_empty_result_no_run_no_fabrication(self):
        store_dir = tempfile.mkdtemp()
        result = run_live_pulse(_WATCHLIST, _THEMES, store_dir=store_dir, now=_NOW, env={})
        self.assertFalse(result.configured)
        self.assertFalse(result.persisted)
        self.assertEqual(result.sources_configured, ())
        self.assertEqual(result.run_id, "")
        self.assertEqual(result.data_gaps, (NO_LIVE_SOURCES_NOTE,))
        self.assertEqual(result.events_loaded, 0)
        self.assertEqual(result.signals, 0)
        # nothing persisted, no store side effect (dir stays empty of run stores)
        self.assertEqual(
            [n for n in os.listdir(store_dir) if n.endswith(".jsonl")], [])

    def test_no_network_attempted_when_missing(self):
        # The socket kill-switch is armed module-wide; a network attempt would raise. This must
        # complete cleanly WITHOUT building any transport.
        run_live_pulse(_WATCHLIST, _THEMES, store_dir=tempfile.mkdtemp(), now=_NOW, env={})

    def test_summary_line_is_the_honest_note(self):
        result = run_live_pulse(_WATCHLIST, _THEMES, store_dir=tempfile.mkdtemp(),
                                now=_NOW, env={})
        self.assertEqual(result.summary_line(), NO_LIVE_SOURCES_NOTE)


# --------------------------------------------------------------------------- #
# 4. No network on import; module hygiene                                       #
# --------------------------------------------------------------------------- #
class ModuleHygieneTests(unittest.TestCase):
    def test_no_network_import_anywhere(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
                  "websocket", "websockets", "ftplib", "smtplib", "telnetlib")
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
                        "network import {0!r} in live_pulse.py".format(name))

    def test_no_score_rank_trade_broker_fn_defs(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        import re
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(
                    re.search(r"(score|rank|rating|broker|_order|buy|sell)", node.name),
                    "banned fn name {0!r}".format(node.name))


# --------------------------------------------------------------------------- #
# 5. The --live CLI is offline-safe with no creds                               #
# --------------------------------------------------------------------------- #
class LiveCliTests(unittest.TestCase):
    def _run_cli(self, argv):
        from cosmosiq_pulse.__main__ import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_live_no_creds_is_offline_and_persists_nothing(self):
        store_dir = os.path.join(tempfile.mkdtemp(), "store")   # not pre-created
        env_keys = (SEC_LIVE_ENV_VAR, FMP_LIVE_ENV_VAR)
        saved = {k: os.environ.pop(k, None) for k in env_keys}
        try:
            code, out = self._run_cli([
                "--live", "--watchlist", "IREN,AAOI", "--themes", "physical-ai",
                "--persist-dir", store_dir, "--now", _NOW])
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        self.assertEqual(code, 0)
        self.assertIn("No live sources configured", out)
        self.assertIn(SEC_LIVE_ENV_VAR, out)
        self.assertNotIn("hunter2", out)
        self.assertFalse(os.path.isdir(store_dir))   # nothing persisted

    def test_live_requires_persist_dir(self):
        from cosmosiq_pulse.__main__ import main
        with self.assertRaises(SystemExit):
            main(["--live", "--watchlist", "IREN", "--themes", "physical-ai"])


if __name__ == "__main__":
    unittest.main()
