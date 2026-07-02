"""IMPLEMENTATION-012J — reality-mesh signals/pulses -> Data Quality + Economic Universe.

Offline. The manual-pulse signal surface is ADDITIVE and opt-in: demo/real default output stays
byte-identical unless pulse signals/pulses are explicitly supplied. Signals surface as EVIDENCE
(freshness + authority + weak-social + contradictions + gaps + ThemePulse state), never a ranking
or a trade action; the closed cross-link graph is preserved (no dead anchors, no unresolved intel).
"""
import ast
import os
import re
import socket
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))  # so sibling test modules import

from reality_mesh import models as M
from reality_mesh.render_adapters import build_pulse_data_quality_panel
from universe_ui.app import build_universe_app

# Reuse the 010G closed-graph checker.
from test_terrain_interaction import HtmlLinkGraph, _cockpit_files  # type: ignore

RA_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "reality_mesh", "render_adapters.py")


def _sig(sid, disc, direction, conf="moderate", fresh="fresh", contra="unopposed",
         corr="corroborated"):
    return M.RealitySignal(signal_id=sid, signal_type=disc + "_sig", discipline=disc,
                           direction_label=direction, confidence_label=conf, freshness_label=fresh,
                           contradiction_status=contra, corroboration_status=corr,
                           affected_themes=("physical-ai",))


def _demo(dirname, **kw):
    return build_universe_app(dirname, mode="demo", **kw)


def _read(paths, name):
    with open(paths[name], encoding="utf-8") as fh:
        return fh.read()


# Signals: one strong market-regime, one weak/social narrative, one contradicted.
STRONG = _sig("s1", "market_regime", "improving", conf="moderate", fresh="fresh")
SOCIAL = _sig("s2", "narrative", "improving", conf="low", fresh="fresh", corr="uncorroborated")
CONFLICTED = _sig("s3", "sector_rotation", "mixed", contra="contradicted", corr="uncorroborated")
AUTH = {"s1": "canonical", "s2": "rumor", "s3": "convenience"}
PULSE = M.ThemePulse(theme_pulse_id="p1", theme_id="physical-ai", theme_name="Physical AI",
                     state="Data insufficient", breadth_label="minor", freshness_label="fresh")


class PanelUnitTests(unittest.TestCase):
    def test_empty_panel_when_nothing_supplied(self):
        self.assertEqual(build_pulse_data_quality_panel(), "")

    def test_panel_shows_freshness_and_authority(self):
        html = build_pulse_data_quality_panel(signals=(STRONG,), authority_by_signal=AUTH)
        self.assertIn("Signal coverage", html)
        self.assertIn("fresh", html)
        self.assertIn("canonical", html)  # source authority visible

    def test_weak_social_marked_weak(self):
        html = build_pulse_data_quality_panel(signals=(STRONG, SOCIAL), authority_by_signal=AUTH)
        self.assertIn("Weak / social signals", html)
        self.assertIn("WEAK", html)
        self.assertIn("uncorroborated", html)

    def test_contradiction_visible_both_sides(self):
        html = build_pulse_data_quality_panel(signals=(CONFLICTED,), authority_by_signal=AUTH)
        self.assertIn("Conflicting signals", html)
        self.assertIn("contradicted", html)
        self.assertIn("both sides preserved", html)

    def test_theme_pulse_is_state_not_recommendation(self):
        html = build_pulse_data_quality_panel(theme_pulses=(PULSE,))
        self.assertIn("Data insufficient", html)
        self.assertIn("NOT a trade recommendation", html)
        # no trade verb / affordance anywhere in the panel
        self.assertNotRegex(html.lower(), r"\b(buy|sell|hold|place order|submit)\b")
        self.assertNotIn("<button", html.lower())

    def test_gaps_visible(self):
        s = M.RealitySignal(signal_id="g1", signal_type="x", discipline="market_regime",
                            data_gaps=("missing breadth input",))
        html = build_pulse_data_quality_panel(signals=(s,))
        self.assertIn("Pulse data gaps", html)
        self.assertIn("missing breadth input", html)

    def test_no_trade_or_pick_language(self):
        # the panel DISCLAIMS ranking/trade/price-target in its <p class="note"> captions (naming
        # what a pulse is NOT is correct). The DATA rows must contain no trade verb / pick / score:
        # strip the disclaimer notes, then assert the remainder is clean.
        html = build_pulse_data_quality_panel(signals=(STRONG, SOCIAL, CONFLICTED),
                                              theme_pulses=(PULSE,), authority_by_signal=AUTH)
        data_only = re.sub(r'<p class="note">.*?</p>', "", html.lower(), flags=re.S)
        self.assertNotRegex(data_only,
                            r"\b(buy|sell|hold|top pick|best stock|strong buy|price target)\b")
        self.assertNotRegex(data_only, r"\b(investability|score:|rank #|rating:)\b")
        # sanity: the disclaimers ARE present in the full panel
        self.assertIn("never a ranking", html.lower())
        self.assertIn("not a trade recommendation", html.lower())


class DemoByteIdenticalTests(unittest.TestCase):
    def test_no_pulse_data_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = _demo(d1)                                   # plain demo
            b = _demo(d2, pulse_signals=None, theme_pulses=None)   # opt-out path
            for name in a:
                self.assertEqual(_read(a, name), _read(b, name),
                                 "demo default drifted for {0}".format(name))

    def test_demo_build_twice_identical(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a, b = _demo(d1), _demo(d2)
            for name in a:
                self.assertEqual(_read(a, name), _read(b, name))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.mkdtemp(prefix="ix_012j_")
        cls.paths = _demo(cls._dir, pulse_signals=(STRONG, SOCIAL, CONFLICTED),
                          theme_pulses=(PULSE,), pulse_authority_by_signal=AUTH)
        cls.dq_html = _read(cls.paths, "data_quality.html")
        cls.dq = HtmlLinkGraph(cls.dq_html)

    def test_panel_rendered_into_data_quality(self):
        self.assertIn("Manual pulse — reality signals", self.dq_html)
        self.assertIn("Physical AI", self.dq_html)

    def test_no_dead_anchors_with_panel(self):
        self.dq.assert_no_dead_anchors(self, _cockpit_files(self.paths))

    def test_no_affordance_or_secret_in_dq(self):
        low = self.dq_html.lower()
        for bad in ("<button", "<form", "onclick", "type=\"submit\"", "place order", "api_key",
                    "apikey", "sk-", "secret"):
            self.assertNotIn(bad, low, "forbidden token in DQ page: {0}".format(bad))

    def test_no_always_on_claim(self):
        low = self.dq_html.lower()
        self.assertIn("manual pulse", low)
        self.assertNotRegex(low, r"\b(always[- ]on|real[- ]time|streaming|24/7|live feed)\b")


class GuardrailTests(unittest.TestCase):
    def test_offline_build_with_pulse(self):
        orig = socket.socket.connect

        def _block(*a, **k):
            raise RuntimeError("network blocked")

        socket.socket.connect = _block
        try:
            with tempfile.TemporaryDirectory() as d:
                _demo(d, pulse_signals=(STRONG,), theme_pulses=(PULSE,),
                      pulse_authority_by_signal=AUTH)
        finally:
            socket.socket.connect = orig

    def test_render_adapters_no_forbidden_imports_or_funcs(self):
        with open(RA_PATH, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("requests", "urllib", "socket", "http", "sched", "asyncio", "subprocess",
                  "threading", "broker")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = (getattr(node, "module", "") or "") + " ".join(
                    a.name for a in getattr(node, "names", []))
                for b in banned:
                    self.assertNotIn(b, mod, "banned import in render_adapters: {0}".format(b))
            if isinstance(node, ast.FunctionDef):
                self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                 "banned fn name: {0}".format(node.name))


if __name__ == "__main__":
    unittest.main()
