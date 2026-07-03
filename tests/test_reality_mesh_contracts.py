"""IMPLEMENTATION-012A -- Reality Mesh core typed contracts.

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against in-process constructions --
no fixture endpoint, no network, no scheduler, no broker. It proves the ARCHITECTURE_
CONTRACT_012 invariants the gate enforces for the handoff substrate (TEST_MATRIX_012 §A + the
global guardrails §I):

* A. construction -- each of the 8 objects builds with valid labels; is frozen; preserves
  evidence_refs / conflicts / data_gaps; the envelope preserves allowed/forbidden uses;
* B. label closure -- an invalid source_authority / claim_status / theme_pulse_state /
  confidence / freshness / discipline / routing target is rejected with ValueError;
* C. boundary -- NO object has a buy/sell/hold/order/trade/broker or score/rank/rating field;
  the envelope default forbidden set includes the four mandatory uses; an X/social event
  defaults to rumor and can never be verified_fact; manual/analyst can never be canonical;
* D. compatibility -- the package imports no network/scheduler/broker module and defines no
  ``*score`` / ``*rank`` function (AST guards); the whole thing builds under a socket
  kill-switch; the demo default stays byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, dataclass, field, fields, is_dataclass

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import labels as L
from reality_mesh import models as M
from reality_mesh import validation as V

_PKG_DIR = os.path.join(_SRC, "reality_mesh")

# The 8 core handoff objects this slice defines.
_THE_EIGHT = (
    M.RealityEvent,
    M.AgentFinding,
    M.HandoffEnvelope,
    M.RealitySignal,
    M.SignalCluster,
    M.ThemePulse,
    M.OpportunityHypothesisPacket,
    M.DiligenceInputBundle,
)

# Field-name tokens forbidden on ANY handoff object (labels, not trades / numbers).
_BANNED_FIELD_TOKENS = (
    "buy", "sell", "hold", "order", "trade", "broker", "score", "rank", "rating",
)


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _one_of_each():
    """A valid instance of every one of the 8 core objects (labels populated)."""
    return {
        "event": M.RealityEvent(
            event_id="E1", timestamp="2026-06-29T00:00:00Z", source_id="src.sec",
            source_type="sec_filing", source_authority="canonical",
            claim_status="verified_fact", discipline="news_filings",
            event_type="8-K", affected_companies=("IREN",),
            evidence_refs=("ex1",), source_refs=("sec:0001",),
            confidence_label="high", freshness_label="fresh", half_life="days",
            conflicts=("c1",), data_gaps=("g1",)),
        "finding": M.AgentFinding(
            finding_id="F1", agent_id="tattva.market_regime", agent_layer="reality_intelligence",
            agent_name="Market Regime", discipline="market_regime",
            input_events=("E1",), finding_type="MarketRegimeFinding",
            direction_label="deteriorating", magnitude_label="moderate",
            urgency_label="elevated", confidence_label="moderate",
            freshness_label="recent", half_life="days",
            source_authority_summary="convenience",
            corroboration_status="uncorroborated", contradiction_status="unopposed",
            evidence_refs=("ex1",), data_gaps=("g1",),
            routing_targets=("SignalFusion",)),
        "envelope": M.HandoffEnvelope(
            envelope_id="H1", created_at="2026-06-29T00:00:00Z", from_layer="reality_intelligence",
            to_layer="opportunity_discovery", from_agent="tattva.market_regime",
            to_synthesizer="SignalFusion", payload_type="AgentFinding",
            payload_ids=("F1",), routing_reason="fuse findings",
            authority_summary="convenience", freshness_summary="recent",
            allowed_downstream_uses=("fuse",)),
        "signal": M.RealitySignal(
            signal_id="S1", signal_type="regime_shift", source_findings=("F1",),
            discipline="cross_discipline", direction_label="deteriorating",
            magnitude_label="major", confidence_label="moderate",
            corroboration_status="corroborated", contradiction_status="disputed",
            evidence_refs=("ex1",), conflicts=("c1",), data_gaps=("g1",),
            routing_targets=("Sphurana",)),
        "cluster": M.SignalCluster(
            cluster_id="C1", cluster_type="theme", theme="Physical AI",
            signals=("S1",), breadth_label="moderate", crowding_label="minor",
            momentum_label="rising", conflict_label="minor",
            confidence_label="moderate", evidence_refs=("ex1",),
            conflicts=("c1",), data_gaps=("g1",)),
        "pulse": M.ThemePulse(
            theme_pulse_id="P1", theme_id="physical_ai", theme_name="Physical AI",
            state="Warming", source_signal_clusters=("C1",),
            supporting_signals=("S1",), contradicting_signals=("S2",),
            breadth_label="moderate", rotation_label="rising",
            crowding_label="minor", bottleneck_label="major",
            confidence_label="moderate", evidence_refs=("ex1",),
            conflicts=("c1",), data_gaps=("g1",)),
        "hypothesis": M.OpportunityHypothesisPacket(
            hypothesis_id="O1", theme_pulse="P1", opportunity_summary="power bottleneck",
            required_diligence_questions=("is it real?",),
            supporting_evidence_refs=("ex1",), contradicting_evidence_refs=("ex2",),
            evidence_refs=("ex1",), confidence_label="low",
            conflicts=("c1",), data_gaps=("g1",)),
        "bundle": M.DiligenceInputBundle(
            ticker="IREN", company="IREN Ltd", theme_pulse_refs=("P1",),
            evidence_refs=("ex1",), conflicts=("c1",), data_gaps=("g1",),
            confidence_label="low"),
    }


# =========================================================================== #
# A. Construction / frozen / evidence-preservation                            #
# =========================================================================== #
class ConstructionTests(unittest.TestCase):
    def test_each_object_builds_with_valid_labels(self):
        objs = _one_of_each()
        self.assertEqual(len(objs), 8)
        for name, obj in objs.items():
            self.assertTrue(is_dataclass(obj), name)

    def test_everything_missing_builds_and_yields_gaps(self):
        # Minimal construction (only required ids) must succeed and default to explicit gaps.
        e = M.RealityEvent(event_id="E")
        self.assertEqual(e.data_gaps, tuple())
        self.assertEqual(e.confidence_label, "missing")
        self.assertEqual(e.source_authority, "")   # explicit gap, not a fabricated value
        M.AgentFinding(finding_id="F", agent_id="a")
        M.SignalCluster(cluster_id="C")
        M.OpportunityHypothesisPacket(hypothesis_id="O")
        M.DiligenceInputBundle(ticker="T")

    def test_objects_are_frozen(self):
        for obj in _one_of_each().values():
            first = fields(obj)[0].name
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, first, "mutated")

    def test_evidence_conflicts_gaps_preserved(self):
        objs = _one_of_each()
        for name in ("event", "signal", "cluster", "pulse", "hypothesis", "bundle"):
            obj = objs[name]
            self.assertEqual(obj.conflicts, ("c1",), name)
            self.assertEqual(obj.data_gaps, ("g1",), name)
            self.assertEqual(obj.evidence_refs, ("ex1",), name)
        # structural guarantee for every evidence-bearing object
        for name in ("event", "finding", "signal", "pulse"):
            V.assert_evidence_preserved(objs[name])

    def test_envelope_preserves_allowed_and_forbidden_uses(self):
        env = _one_of_each()["envelope"]
        self.assertIn("fuse", env.allowed_downstream_uses)
        for use in ("broker_order", "auto_execute", "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)
        self.assertTrue(env.permits("fuse"))
        self.assertFalse(env.permits("broker_order"))

    def test_numeric_values_carry_units_but_no_metric(self):
        # numeric_values are raw (name, value, unit) data -- never a derived score.
        e = M.RealityEvent(event_id="E", numeric_values=(("market_cap", 5.0e10, "USD"),))
        self.assertEqual(e.numeric_values[0][2], "USD")


# =========================================================================== #
# B. Label closure                                                            #
# =========================================================================== #
class LabelClosureTests(unittest.TestCase):
    def test_invalid_source_authority_rejected(self):
        with self.assertRaises(ValueError):
            M.RealityEvent(event_id="E", source_authority="supreme")

    def test_invalid_claim_status_rejected(self):
        with self.assertRaises(ValueError):
            M.RealityEvent(event_id="E", claim_status="gospel")

    def test_invalid_theme_pulse_state_rejected(self):
        with self.assertRaises(ValueError):
            M.ThemePulse(theme_pulse_id="P", state="Boiling")

    def test_invalid_confidence_label_rejected(self):
        with self.assertRaises(ValueError):
            M.RealitySignal(signal_id="S", confidence_label="0.87")

    def test_invalid_freshness_label_rejected(self):
        with self.assertRaises(ValueError):
            M.RealitySignal(signal_id="S", freshness_label="yesterday")

    def test_invalid_discipline_rejected(self):
        with self.assertRaises(ValueError):
            M.AgentFinding(finding_id="F", agent_id="a", discipline="astrology")

    def test_invalid_routing_target_rejected(self):
        with self.assertRaises(ValueError):
            M.AgentFinding(finding_id="F", agent_id="a", routing_targets=("Mars",))

    def test_empty_required_id_rejected(self):
        for build in (
            lambda: M.RealityEvent(event_id=""),
            lambda: M.AgentFinding(finding_id="", agent_id="a"),
            lambda: M.AgentFinding(finding_id="F", agent_id=""),
            lambda: M.HandoffEnvelope(envelope_id=""),
            lambda: M.RealitySignal(signal_id=""),
            lambda: M.SignalCluster(cluster_id=""),
            lambda: M.ThemePulse(theme_pulse_id="", state="Warming"),
            lambda: M.OpportunityHypothesisPacket(hypothesis_id=""),
            lambda: M.DiligenceInputBundle(ticker=""),
        ):
            with self.assertRaises(ValueError):
                build()

    def test_valid_theme_pulse_states_all_accepted(self):
        for state in L.THEME_PULSE_STATES:
            M.ThemePulse(theme_pulse_id="P", state=state)

    def test_membership_helpers(self):
        self.assertTrue(L.is_source_authority("canonical"))
        self.assertTrue(L.is_source_authority(""))          # empty = explicit gap
        self.assertFalse(L.is_source_authority("supreme"))
        self.assertTrue(L.is_theme_pulse_state("Broadening"))
        self.assertFalse(L.is_theme_pulse_state("Melting"))


# =========================================================================== #
# C. Boundary -- no trade/score field; forbidden defaults; social; manual      #
# =========================================================================== #
class BoundaryTests(unittest.TestCase):
    def test_no_object_has_trade_or_score_field(self):
        for cls in _THE_EIGHT:
            for f in fields(cls):
                low = f.name.lower()
                for tok in _BANNED_FIELD_TOKENS:
                    self.assertNotIn(
                        tok, low,
                        "{0}.{1} contains banned token {2!r}".format(
                            cls.__name__, f.name, tok))
            # structural guard agrees
            V.assert_no_trade_fields(cls)

    def test_assert_no_trade_fields_catches_a_violation(self):
        @dataclass(frozen=True)
        class Sneaky:
            investability_score: float = 0.0
        with self.assertRaises(AssertionError):
            V.assert_no_trade_fields(Sneaky)

    def test_envelope_default_forbidden_includes_the_four(self):
        env = M.HandoffEnvelope(envelope_id="H")
        for use in ("broker_order", "auto_execute", "buy_sell_recommendation", "hidden_score"):
            self.assertIn(use, env.forbidden_downstream_uses)
        # even when a caller supplies their own forbidden set, the four are merged in
        env2 = M.HandoffEnvelope(envelope_id="H2", forbidden_downstream_uses=("order",))
        for use in L.DEFAULT_FORBIDDEN_DOWNSTREAM_USES:
            self.assertIn(use, env2.forbidden_downstream_uses)
        V.validate_envelope(env)
        V.validate_envelope(env2)

    def test_validate_envelope_rejects_missing_forbidden(self):
        # A hand-rolled envelope-like object missing the mandatory forbidden uses is rejected.
        @dataclass(frozen=True)
        class FakeEnv:
            envelope_id: str = "H"
            allowed_downstream_uses: tuple = field(default_factory=tuple)
            forbidden_downstream_uses: tuple = field(default_factory=tuple)
            conflicts: tuple = field(default_factory=tuple)
            data_gaps: tuple = field(default_factory=tuple)
            evidence_refs: tuple = field(default_factory=tuple)
        with self.assertRaises(ValueError):
            V.validate_envelope(FakeEnv())

    def test_social_event_defaults_to_rumor_and_cannot_be_verified(self):
        # narrative discipline -> rumor authority + rumor claim by default
        soc = M.RealityEvent(event_id="X1", discipline="narrative", source_type="x")
        self.assertEqual(soc.source_authority, "rumor")
        self.assertEqual(soc.claim_status, "rumor")
        # cannot be a verified_fact
        with self.assertRaises(ValueError):
            M.RealityEvent(event_id="X2", discipline="narrative", claim_status="verified_fact")
        with self.assertRaises(ValueError):
            M.RealityEvent(event_id="X3", source_type="twitter", claim_status="verified_fact")
        # BUT an explicit company_claim / reported_claim on a social event is permitted
        ok = M.RealityEvent(event_id="X4", discipline="narrative", claim_status="company_claim")
        self.assertEqual(ok.claim_status, "company_claim")
        M.RealityEvent(event_id="X5", source_type="social", claim_status="reported_claim")

    def test_social_verified_guard_directly(self):
        rumor = M.RealityEvent(event_id="X", discipline="narrative")
        V.assert_social_not_verified(rumor)          # rumor is fine
        ok = M.RealityEvent(event_id="X", discipline="narrative", claim_status="reported_claim")
        V.assert_social_not_verified(ok)             # reported_claim is fine

    def test_rumor_authority_cannot_be_verified_fact(self):
        # A rumor-tier source cannot produce a verified_fact, even off the narrative path.
        with self.assertRaises(ValueError):
            M.RealityEvent(
                event_id="R1", source_authority="rumor", claim_status="verified_fact")
        # a rumor event with the default rumor claim is fine
        rumor_default = M.RealityEvent(event_id="R2", source_authority="rumor")
        self.assertEqual(rumor_default.claim_status, "")   # unset -> explicit gap, not a fact
        V.assert_social_not_verified(rumor_default)
        # an explicit rumor claim is fine
        M.RealityEvent(event_id="R3", source_authority="rumor", claim_status="rumor")

    def test_assert_social_not_verified_catches_x_social_source_type(self):
        # source_type spelled "x_social" is not an EXACT social token, so the object is
        # constructible -- but the guard still rejects a verified_fact off it.
        evt = M.RealityEvent(
            event_id="XS1", source_type="x_social", claim_status="verified_fact")
        with self.assertRaises(AssertionError):
            V.assert_social_not_verified(evt)
        # a rumor-authority verified event is likewise rejected by the guard
        with self.assertRaises(AssertionError):
            V.assert_social_not_verified(
                type("E", (), {"claim_status": "verified_fact",
                               "source_authority": "rumor",
                               "source_type": "", "discipline": ""})())
        # and a legitimate reported_claim / company_claim x_social event is NOT over-blocked
        V.assert_social_not_verified(
            M.RealityEvent(event_id="XS2", source_type="x_social",
                           claim_status="reported_claim"))
        V.assert_social_not_verified(
            M.RealityEvent(event_id="XS3", source_type="x_social",
                           claim_status="company_claim"))

    def test_manual_analyst_cannot_be_canonical(self):
        with self.assertRaises(ValueError):
            M.RealityEvent(event_id="E", source_authority="canonical", claim_status="manual")
        with self.assertRaises(ValueError):
            M.RealityEvent(event_id="E", source_authority="canonical", claim_status="analyst_estimate")
        # helper form
        with self.assertRaises(AssertionError):
            V.assert_manual_not_canonical("canonical", "manual")
        V.assert_manual_not_canonical("manual", "manual")        # fine
        # authority ladder proof: manual ranks strictly below canonical
        self.assertLess(L.authority_rank("manual"), L.authority_rank("canonical"))
        self.assertLess(L.authority_rank("rumor"), L.authority_rank("canonical"))

    def test_no_numeric_investability_field_anywhere(self):
        # No field on any of the 8 is typed as a bare number acting as a metric key.
        for cls in _THE_EIGHT:
            for f in fields(cls):
                low = f.name.lower()
                self.assertNotIn("investab", low)
                self.assertNotIn("rating", low)


# =========================================================================== #
# D. Compatibility -- AST guards, offline, deterministic, demo byte-identical   #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "beautifulsoup4", "selenium", "scrapy", "lxml", "mechanize", "pycurl",
            "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal", "sched"}

    def _py_files(self):
        return [os.path.join(_PKG_DIR, f) for f in sorted(os.listdir(_PKG_DIR))
                if f.endswith(".py")]

    @staticmethod
    def _read(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _imported_modules(self, tree):
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:  # ignore relative intra-package imports
                    mods.append((node.module or "").split(".")[0])
        return mods

    def test_package_imports_no_network_scheduler_or_broker(self):
        for path in self._py_files():
            tree = ast.parse(self._read(path))
            for m in self._imported_modules(tree):
                self.assertNotIn(m, self._NET, "{0} imports network {1}".format(path, m))
                self.assertNotIn(m, self._FORBIDDEN, "{0} imports forbidden {1}".format(path, m))

    def test_package_defines_no_scoring_or_ranking_function(self):
        for path in self._py_files():
            tree = ast.parse(self._read(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    low = node.name.lower()
                    for tok in ("score", "rank", "rating"):
                        self.assertNotIn(tok, low, "{0}: {1}".format(path, node.name))

    def test_package_source_has_no_broker_or_order_affordance(self):
        blob = ""
        for path in self._py_files():
            blob += self._read(path).lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "cron", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_construction_and_validation_are_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            objs = _one_of_each()
            V.validate_event(objs["event"])
            V.validate_finding(objs["finding"])
            V.validate_signal(objs["signal"])
            V.validate_theme_pulse(objs["pulse"])
            V.validate_envelope(objs["envelope"])
        finally:
            socket.socket = real
        self.assertEqual(objs["event"].source_authority, "canonical")

    def test_builds_are_byte_identical_deterministic(self):
        # Same inputs (incl. injected timestamps) -> identical object repr, twice.
        a = _one_of_each()
        b = _one_of_each()
        for name in a:
            self.assertEqual(repr(a[name]), repr(b[name]), name)

    def test_no_wall_clock_in_id_or_timestamp_path(self):
        # timestamps are injected strings; the package never reads the wall clock.
        blob = ""
        for path in self._py_files():
            blob += self._read(path)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_source_authority_reused_from_accepted_ladder(self):
        # 012 must not fork/weaken the 010/011 authority vocabulary.
        from evidence_ingestion.source_model import SOURCE_AUTHORITIES as ACCEPTED
        self.assertEqual(L.SOURCE_AUTHORITIES, ACCEPTED)


# =========================================================================== #
# D (cont). Existing behaviour unaffected -- demo default byte-identical        #
# =========================================================================== #
class ExistingBehaviourTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_demo_a_")
        d2 = tempfile.mkdtemp(prefix="rm_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))
        # the reality-mesh substrate leaves no trace in the demo surface
        with open(p1["universe.html"], encoding="utf-8") as fh:
            self.assertNotIn("reality_mesh", fh.read())


if __name__ == "__main__":
    unittest.main()
