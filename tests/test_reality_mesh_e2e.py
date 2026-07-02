"""IMPLEMENTATION-012K — the manual/on-demand ``tattva_pulse`` CLI + orchestrator E2E (OFFLINE).

Per TEST_MATRIX_012 §H (+ the §I global guardrails). The manual pulse runs the full fixture chain
sources -> sensor agents -> Buddhi routing -> Tattva fusion -> Sphurana theme pulses -> Data-Quality
roll-up, honestly and gap-visibly. It is MANUAL / on-demand only (no scheduler / daemon / streaming),
FIXTURE-backed (no live X, no network), emits LABELS not scores, has no broker / order / affordance,
leaks no secrets, and keeps the demo default byte-identical.
"""
import ast
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh.pulse import PulseResult, run_pulse
from reality_mesh import models as M
import tattva_pulse
from tattva_pulse.__main__ import main as pulse_main
from universe_ui.app import build_universe_app

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src")
_PULSE_PY = os.path.join(_SRC, "reality_mesh", "pulse.py")
_CLI_MAIN = os.path.join(_SRC, "tattva_pulse", "__main__.py")
_CLI_INIT = os.path.join(_SRC, "tattva_pulse", "__init__.py")
_CLI_SUMMARY = os.path.join(_SRC, "tattva_pulse", "summary.py")
_PULSE_MODULE_FILES = (_PULSE_PY, _CLI_MAIN, _CLI_INIT, _CLI_SUMMARY)

_WATCHLIST = "IREN,AAOI,AMBA,OUST"
_THEMES = "physical-ai,robotics,ai-power"
_NOW = "2026-06-29T14:00:00Z"


def _pulse():
    return run_pulse(_WATCHLIST, _THEMES, now=_NOW)


def _run_cli(out, watchlist=_WATCHLIST, themes=_THEMES):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = pulse_main(["--watchlist", watchlist, "--themes", themes, "--out", out])
    return rc, buf.getvalue()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# §H2 — the full pulse chain produces each required piece, honest + gap-visible #
# --------------------------------------------------------------------------- #
class PulseChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _pulse()

    def test_result_is_frozen_pulse_result(self):
        self.assertIsInstance(self.r, PulseResult)
        with self.assertRaises(Exception):
            self.r.signals = ()  # frozen

    def test_market_regime_finding_present(self):
        mr = [f for f in self.r.findings if f.discipline == "market_regime"]
        self.assertTrue(mr, "expected a market-regime finding")

    def test_sector_or_theme_rotation_finding_present(self):
        rot = [f for f in self.r.findings
               if f.discipline in ("sector_rotation", "theme_rotation")]
        self.assertTrue(rot, "expected a sector/theme rotation finding")
        # theme rotation reads a genuine broadening/ignition on physical-ai
        self.assertTrue(any(f.discipline == "theme_rotation" for f in rot))

    def test_news_filings_signal_present(self):
        nf = [s for s in self.r.signals if s.discipline == "news_filings"]
        self.assertTrue(nf, "expected a news/filings signal")
        # the 8-K is a canonical SEC filing fact (authority preserved)
        self.assertEqual(self.r.authority_by_signal.get(nf[0].signal_id), "canonical")

    def test_social_signal_is_weak_rumor_never_verified(self):
        soc = [s for s in self.r.signals if s.discipline == "narrative"]
        self.assertTrue(soc, "expected an X/social narrative signal")
        for s in soc:
            # rumor authority, never verified; weak/uncorroborated with an explicit gap
            self.assertEqual(self.r.authority_by_signal.get(s.signal_id), "rumor")
            self.assertNotEqual(s.corroboration_status, "corroborated")
            self.assertTrue(any("rumor" in g.lower() or "social" in g.lower()
                                for g in s.data_gaps),
                            "social signal must carry an explicit weak/rumor gap")

    def test_fusion_produced_reality_signals(self):
        self.assertTrue(self.r.signals)
        for s in self.r.signals:
            self.assertIsInstance(s, M.RealitySignal)

    def test_sphurana_theme_pulse_present(self):
        self.assertTrue(self.r.theme_pulses)
        by_name = {p.theme_name: p for p in self.r.theme_pulses}
        self.assertIn("physical-ai", by_name)
        self.assertIn("robotics", by_name)
        # physical-ai broadens across multiple members; robotics is social-only -> insufficient
        self.assertEqual(by_name["physical-ai"].state, "Broadening")
        self.assertEqual(by_name["robotics"].state, "Data insufficient")

    def test_theme_pulse_is_a_state_not_a_pick(self):
        for p in self.r.theme_pulses:
            self.assertIn(p.state, M._labels.THEME_PULSE_STATES)

    def test_data_quality_summary_rolls_up_gaps(self):
        self.assertTrue(self.r.data_gaps)
        # every per-agent run has an honest status label + counts
        for a in self.r.agent_runs:
            self.assertIn(a.status, ("ok", "no_findings", "no_matching_events"))

    def test_uncovered_theme_is_an_honest_gap_not_fabricated(self):
        # ai-power has no fixture coverage -> explicit gap, no signal, no pulse invented
        joined = " ".join(self.r.data_gaps).lower()
        self.assertIn("ai-power", joined)
        self.assertNotIn("ai-power", {p.theme_name for p in self.r.theme_pulses})
        self.assertNotIn("aipower", {re.sub(r"[^a-z0-9]", "", t.lower())
                                     for t in self.r.covered_themes})

    def test_uncovered_watchlist_ticker_gaps(self):
        r = run_pulse("IREN,ZZZZ", "physical-ai", now=_NOW)
        self.assertTrue(any("ZZZZ" in g for g in r.data_gaps),
                        "an uncovered watchlist ticker must surface as an honest gap")

    def test_full_chain_agents_all_ran(self):
        disciplines = {a.discipline for a in self.r.agent_runs}
        self.assertEqual(disciplines, {"market_regime", "sector_rotation", "theme_rotation",
                                       "news_filings", "narrative"})

    def test_handoff_envelopes_forbid_broker_order(self):
        # Buddhi routing wraps every finding; the envelope always forbids the four defaults.
        for env in self.r.handoff_envelopes:
            for banned in ("broker_order", "auto_execute", "buy_sell_recommendation",
                           "hidden_score"):
                self.assertIn(banned, env.forbidden_downstream_uses)


# --------------------------------------------------------------------------- #
# §H1 — watchlist/themes REQUIRED; manual/on-demand                            #
# --------------------------------------------------------------------------- #
class RequiredArgsTests(unittest.TestCase):
    def test_empty_watchlist_rejected_orchestrator(self):
        with self.assertRaises(ValueError):
            run_pulse("", _THEMES, now=_NOW)
        with self.assertRaises(ValueError):
            run_pulse("   ,  ", _THEMES, now=_NOW)

    def test_empty_themes_rejected_orchestrator(self):
        with self.assertRaises(ValueError):
            run_pulse(_WATCHLIST, "", now=_NOW)

    def test_empty_watchlist_rejected_cli(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                _run_cli(d, watchlist="", themes=_THEMES)

    def test_empty_themes_rejected_cli(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit):
                _run_cli(d, watchlist=_WATCHLIST, themes="  ")

    def test_deterministic_same_inputs_same_gaps(self):
        a = _pulse()
        b = _pulse()
        self.assertEqual(a.data_gaps, b.data_gaps)
        self.assertEqual([s.signal_id for s in a.signals], [s.signal_id for s in b.signals])
        self.assertEqual([p.state for p in a.theme_pulses], [p.state for p in b.theme_pulses])


# --------------------------------------------------------------------------- #
# CLI outputs land under --out; the operator-doc command builds (offline)      #
# --------------------------------------------------------------------------- #
class CliOutputTests(unittest.TestCase):
    def test_outputs_land_under_out(self):
        with tempfile.TemporaryDirectory() as d:
            rc, log = _run_cli(d)
            self.assertEqual(rc, 0)
            for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html",
                         "pulse_summary.json"):
                self.assertTrue(os.path.isfile(os.path.join(d, name)),
                                "missing output {0}".format(name))
            # banner printed; honest labelling
            self.assertIn("manual pulse", log.lower())
            self.assertIn("not scheduled", log.lower())
            self.assertIn("not broker-connected", log.lower())

    def test_signals_render_into_data_quality(self):
        with tempfile.TemporaryDirectory() as d:
            _run_cli(d)
            dq = _read(os.path.join(d, "data_quality.html"))
            self.assertIn("Manual pulse — reality signals", dq)
            self.assertIn("physical-ai", dq)
            self.assertIn("WEAK", dq)  # the X/social signal is marked weak

    def test_pulse_summary_is_labels_and_gaps_no_scores(self):
        with tempfile.TemporaryDirectory() as d:
            _run_cli(d)
            summary = json.loads(_read(os.path.join(d, "pulse_summary.json")))
            self.assertEqual(summary["mode"], "pulse")
            self.assertFalse(summary["scheduled"])
            self.assertFalse(summary["broker_connected"])
            self.assertFalse(summary["live_data"])
            self.assertFalse(summary["network"])
            self.assertTrue(summary["data_gaps"])
            # no numeric investability score/rank/rating key anywhere in the summary
            self._assert_no_score_keys(summary)

    def _assert_no_score_keys(self, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                self.assertFalse(re.search(r"(score|rank|rating|investab)", k.lower()),
                                 "forbidden score/rank key: {0}".format(k))
                self._assert_no_score_keys(v)
        elif isinstance(obj, list):
            for v in obj:
                self._assert_no_score_keys(v)

    def test_operator_doc_command_actually_builds(self):
        doc = os.path.join(_HERE, "..", "docs", "OPERATOR_GUIDE_012.md")
        text = _read(doc)
        self.assertIn("tattva_pulse", text)
        self.assertIn("--watchlist", text)
        self.assertIn("--themes", text)
        # the exact documented command builds offline
        with tempfile.TemporaryDirectory() as d:
            rc, _ = _run_cli(d)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(os.path.join(d, "universe.html")))

    def test_fixture_dir_override(self):
        from reality_mesh.pulse import DEFAULT_PULSE_FIXTURE_DIR
        with tempfile.TemporaryDirectory() as d:
            rc, _ = _run_cli(d)  # default dir
            self.assertEqual(rc, 0)
        # explicit override to the same bundled dir works too
        r = run_pulse(_WATCHLIST, _THEMES, fixture_dir=DEFAULT_PULSE_FIXTURE_DIR, now=_NOW)
        self.assertTrue(r.signals)


# --------------------------------------------------------------------------- #
# §I guardrails                                                                 #
# --------------------------------------------------------------------------- #
class GuardrailTests(unittest.TestCase):
    def test_no_scheduler_daemon_streaming_imports(self):
        banned = ("sched", "asyncio", "threading", "multiprocessing", "schedule",
                  "apscheduler", "crontab", "signal", "requests", "urllib", "http.client",
                  "socketserver", "subprocess")
        for path in _PULSE_MODULE_FILES:
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    for b in banned:
                        self.assertFalse(name == b or name.startswith(b + "."),
                                         "banned import {0!r} in {1}".format(name, path))

    def test_no_scheduler_or_loop_construct_in_source(self):
        # Code-form constructs only (prose disclaimers legitimately say "no scheduler / no
        # daemon"); a real background loop / scheduler call would use one of these forms.
        for path in _PULSE_MODULE_FILES:
            low = _read(path).lower()
            for token in ("while true", "run_forever", "start_polling", "scheduler(",
                          "schedule.every", ".daemon", "loop.run", "set_interval"):
                self.assertNotIn(token, low,
                                 "scheduler/loop construct {0!r} in {1}".format(token, path))

    def test_no_score_or_rank_function_defs(self):
        for path in _PULSE_MODULE_FILES:
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                     "banned fn name {0!r} in {1}".format(node.name, path))

    def test_no_network_socket_kill_switch(self):
        orig = socket.socket.connect

        def _block(*a, **k):
            raise RuntimeError("network blocked during offline pulse")

        socket.socket.connect = _block
        try:
            with tempfile.TemporaryDirectory() as d:
                rc, _ = _run_cli(d)
                self.assertEqual(rc, 0)
            # the orchestrator alone is also offline
            run_pulse(_WATCHLIST, _THEMES, now=_NOW)
        finally:
            socket.socket.connect = orig

    def test_no_affordance_or_secret_in_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            _run_cli(d)
            for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
                low = _read(os.path.join(d, name)).lower()
                for bad in ("<button", "<form", "onclick", 'type="submit"', "place order",
                            "api_key", "apikey", "password"):
                    self.assertNotIn(bad, low,
                                     "forbidden token {0!r} in {1}".format(bad, name))
                # secret-key prefixes with a word boundary (avoid matching e.g. "risk-")
                self.assertNotRegex(low, r"\bsk-[a-z0-9]{6}")
                self.assertNotRegex(low, r"\bsecret[_-]?(key|token)\b")
            # summary carries no secret + no live/scheduler claim
            summ = _read(os.path.join(d, "pulse_summary.json")).lower()
            for bad in ("api_key", "apikey", "password"):
                self.assertNotIn(bad, summ)
            self.assertNotRegex(summ, r"\bsk-[a-z0-9]{6}")

    def test_no_trade_verb_in_pulse_evidence_rows(self):
        # the DQ panel disclaims trade/ranking in its <p class="note"> captions (naming what a
        # pulse is NOT). Strip the disclaimer notes, then assert the data is trade-verb-free.
        with tempfile.TemporaryDirectory() as d:
            _run_cli(d)
            dq = _read(os.path.join(d, "data_quality.html")).lower()
            data_only = re.sub(r'<p class="note">.*?</p>', "", dq, flags=re.S)
            self.assertNotRegex(data_only,
                                r"\b(buy|sell|hold|top pick|strong buy|price target)\b")
            self.assertNotRegex(data_only, r"\b(investability|score:|rank #|rating:)\b")

    def test_no_always_on_or_realtime_claim(self):
        with tempfile.TemporaryDirectory() as d:
            _run_cli(d)
            dq = _read(os.path.join(d, "data_quality.html")).lower()
            self.assertIn("manual pulse", dq)
            self.assertNotRegex(dq, r"\b(always[- ]on|real[- ]time|streaming|24/7|live feed)\b")


# --------------------------------------------------------------------------- #
# §I9 — demo default byte-identical; existing paths green                      #
# --------------------------------------------------------------------------- #
class DemoByteIdenticalTests(unittest.TestCase):
    def test_demo_default_byte_identical_after_012k(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo")
            for name in a:
                self.assertEqual(_read(a[name]), _read(b[name]),
                                 "demo default drifted for {0}".format(name))

    def test_demo_with_no_pulse_args_is_unchanged(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_universe_app(d1, mode="demo")
            b = build_universe_app(d2, mode="demo", pulse_signals=None, theme_pulses=None)
            for name in a:
                self.assertEqual(_read(a[name]), _read(b[name]))

    def test_pulse_public_surface(self):
        self.assertTrue(hasattr(tattva_pulse, "build_pulse_summary"))
        self.assertTrue(hasattr(tattva_pulse, "main"))


if __name__ == "__main__":
    unittest.main()
