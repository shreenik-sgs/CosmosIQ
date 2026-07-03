"""IMPLEMENTATION-013E -- Reality Mesh DataQualityGateRunner (Phase-013).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE -- no network, no scheduler, no broker, no
live endpoint. It proves the DATA_QUALITY_GATE_CONTRACT_013 + SECURITY_POLICY_CONTRACT_013 gate
invariants (TEST_MATRIX_013 §F1-F8 + the global guardrails §I):

* F1 -- an X/social record carrying ``verified_fact`` -> fail (never warn);
* F2 -- a manual/analyst value marked ``canonical`` -> fail;
* F3 -- a hidden ``score`` / ``rank`` / ``investability`` field on a record -> fail;
* F4 -- a ``buy`` / ``sell`` / ``order`` / ``submit`` field or affordance -> fail;
* F5 -- an API key in a generated-output text -> fail AND a network-on-import signature -> fail;
* F6 -- a real/pulse run whose data equals the demo data -> fail (silent demo fallback);
* F7 -- a value present with NO source/evidence ref -> fail (missing data filled without source);
* F8 -- a scheduler/broker token in a provided module source -> fail (guardrail gate);
* clean pulse (from ``run_pulse`` fixtures) -> all gates pass/warn, overall NOT failed;
* warn-vs-fail distinction holds (thin coverage warns; a violated invariant fails);
* gate results carry NO secret value + NO score/trade field; overall-status roll-up;
* I  -- gates.py imports no network/scheduler/broker module + defines no ``*score``/``*rank``
  function (AST); the whole suite runs under a socket kill-switch; deterministic; local-only.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import gates as G
from reality_mesh import pulse as P
from reality_mesh.models import AgentFinding, RealityEvent, RealitySignal

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_GATES_PY = os.path.join(_PKG_DIR, "gates.py")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Duck-typed "bad" records: the frozen 012 models REJECT these at construction, #
# so a laundering record can only reach the gate as a dict / duck object.       #
# --------------------------------------------------------------------------- #
def _social_verified_dict(rid="X1"):
    return {"event_id": rid, "source_type": "x_social", "discipline": "narrative",
            "claim_status": "verified_fact", "source_authority": "rumor"}


def _manual_canonical_dict(rid="M1"):
    return {"event_id": rid, "source_authority": "canonical", "claim_status": "manual"}


def _clean_pulse():
    """A CLEAN manual pulse + its loaded events (fixture-backed, offline, deterministic)."""
    result = rm.run_pulse(["IREN", "NVDA"], ["physical_ai"], now="2026-06-29T00:00:00Z")
    events = P._load_pulse_events(rm.DEFAULT_PULSE_FIXTURE_DIR)
    return result, events


# =========================================================================== #
# F1. X/social verified_fact -> fail (never warn)                             #
# =========================================================================== #
class SocialVerifiedFactTests(unittest.TestCase):
    def test_social_verified_fact_is_a_hard_fail(self):
        g = G.DataQualityGateRunner()
        res = g.check_social_weak_signal([_social_verified_dict()])
        self.assertEqual(res.status, "fail")
        self.assertEqual(res.category, "social_weak_signal")
        self.assertIn("X1", res.subject_refs)

    def test_social_verified_fact_via_substring_source_type(self):
        g = G.DataQualityGateRunner()
        rec = {"event_id": "X2", "source_type": "TwitterFeed",
               "claim_status": "verified_fact"}
        self.assertEqual(g.check_social_weak_signal([rec]).status, "fail")

    def test_rumor_authority_verified_fact_fails(self):
        g = G.DataQualityGateRunner()
        rec = {"event_id": "X3", "source_authority": "rumor",
               "claim_status": "verified_fact"}
        self.assertEqual(g.check_social_weak_signal([rec]).status, "fail")

    def test_uncorroborated_social_only_warns(self):
        g = G.DataQualityGateRunner()
        rec = {"event_id": "X4", "source_type": "x_social", "claim_status": "rumor",
               "source_authority": "rumor", "corroboration_status": "uncorroborated"}
        self.assertEqual(g.check_social_weak_signal([rec]).status, "warn")


# =========================================================================== #
# F2. manual/analyst canonical -> fail                                        #
# =========================================================================== #
class ManualCanonicalTests(unittest.TestCase):
    def test_manual_canonical_is_a_hard_fail(self):
        g = G.DataQualityGateRunner()
        res = g.check_manual_analyst_authority([_manual_canonical_dict()])
        self.assertEqual(res.status, "fail")
        self.assertIn("M1", res.subject_refs)

    def test_analyst_estimate_canonical_fails(self):
        g = G.DataQualityGateRunner()
        rec = {"event_id": "M2", "source_authority": "canonical",
               "claim_status": "analyst_estimate"}
        self.assertEqual(g.check_manual_analyst_authority([rec]).status, "fail")

    def test_manual_but_not_canonical_only_warns(self):
        g = G.DataQualityGateRunner()
        rec = {"event_id": "M3", "source_authority": "manual", "claim_status": "manual"}
        self.assertEqual(g.check_manual_analyst_authority([rec]).status, "warn")


# =========================================================================== #
# F3 + F4. hidden score/rank field + buy/sell/order affordance -> fail        #
# =========================================================================== #
class GuardrailFieldTests(unittest.TestCase):
    def test_hidden_score_field_fails(self):
        g = G.DataQualityGateRunner()
        res = g.check_scheduler_broker_trading_guardrail(
            [{"signal_id": "S1", "investability_score": 0.9}])
        self.assertEqual(res.status, "fail")

    def test_rank_field_fails(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail([{"id": "r", "rank": 3}]).status,
            "fail")

    def test_buy_field_fails(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail([{"id": "r", "buy_signal": 1}]).status,
            "fail")

    def test_broker_order_field_fails(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail(
                [{"id": "r", "broker_order": "x"}]).status,
            "fail")

    def test_submit_affordance_field_fails(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail(
                [{"id": "r", "submit_order": True}]).status,
            "fail")

    def test_no_false_positive_on_innocuous_field_names(self):
        g = G.DataQualityGateRunner()
        # 'underscore' contains 'score', 'threshold' contains 'hold', 'border' contains 'order'
        rec = {"id": "r", "underscore_note": 1, "threshold_label": "x", "border_ref": "y"}
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail([rec]).status, "pass")

    def test_real_012_records_have_no_forbidden_field(self):
        g = G.DataQualityGateRunner()
        _, events = _clean_pulse()
        res = g.check_scheduler_broker_trading_guardrail(list(events))
        self.assertEqual(res.status, "pass")


# =========================================================================== #
# F5. API key in output -> fail; network-on-import -> fail                     #
# =========================================================================== #
class SecuritySecretsTests(unittest.TestCase):
    def test_api_key_in_output_fails(self):
        g = G.DataQualityGateRunner()
        res = g.check_security_secrets(["dashboard config api_key=SUPERSECRETVALUE123 end"])
        self.assertEqual(res.status, "fail")
        self.assertEqual(res.category, "security_secrets")

    def test_secret_value_is_never_in_the_findings(self):
        g = G.DataQualityGateRunner()
        res = g.check_security_secrets(["token: sk-ABCDEFGHIJKLMNOP1234567890"])
        self.assertEqual(res.status, "fail")
        for finding in res.findings + res.subject_refs:
            self.assertNotIn("sk-ABCDEFGHIJKLMNOP", finding)
            self.assertNotIn("ABCDEFGHIJKLMNOP1234567890", finding)

    def test_aws_and_pem_keys_detected(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_security_secrets(["AKIAIOSFODNN7EXAMPLE"]).status, "fail")
        self.assertEqual(
            g.check_security_secrets(
                ["-----BEGIN RSA PRIVATE KEY-----\nabc"]).status, "fail")

    def test_network_call_on_import_fails(self):
        g = G.DataQualityGateRunner()
        src = "import urllib.request\ndata = urllib.request.urlopen('http://x').read()\n"
        res = g.check_security_secrets([], module_sources={"bad": src})
        self.assertEqual(res.status, "fail")
        self.assertIn("bad", res.subject_refs)

    def test_requests_call_on_import_fails(self):
        g = G.DataQualityGateRunner()
        src = "import requests\nRESP = requests.get('http://x')\n"
        self.assertEqual(
            g.check_security_secrets([], module_sources={"m": src}).status, "fail")

    def test_lazy_network_inside_function_passes(self):
        g = G.DataQualityGateRunner()
        # the accepted single lazy boundary: a network call INSIDE a function is fine
        src = ("import json\n\ndef fetch(url):\n    import urllib.request\n"
               "    return urllib.request.urlopen(url).read()\n")
        self.assertEqual(
            g.check_security_secrets([], module_sources={"m": src}).status, "pass")

    def test_clean_output_passes(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_security_secrets(["<html>Physical AI theme is Warming</html>"]).status,
            "pass")

    def test_security_gate_result_is_typed_subset(self):
        g = G.DataQualityGateRunner()
        res = g.security_gate_result(["api_key=SECRETXYZ123"])
        self.assertIsInstance(res, G.SecurityGateResult)
        self.assertEqual(res.status, "fail")


# =========================================================================== #
# F6. real/pulse mode silently uses demo data -> fail                          #
# =========================================================================== #
class DemoFallbackTests(unittest.TestCase):
    def test_real_mode_equal_to_demo_data_fails(self):
        g = G.DataQualityGateRunner()
        res = g.check_demo_fallback(
            run_mode="pulse", data_signature="SIG-A", demo_signature="SIG-A")
        self.assertEqual(res.status, "fail")

    def test_enriched_mode_equal_to_demo_fails(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_demo_fallback(run_mode="enriched", data_signature="Z",
                                  demo_signature="Z").status, "fail")

    def test_real_mode_with_distinct_data_passes(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_demo_fallback(run_mode="pulse", data_signature="REAL",
                                  demo_signature="DEMO").status, "pass")

    def test_demo_mode_is_exempt(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_demo_fallback(run_mode="demo", data_signature="D",
                                  demo_signature="D").status, "pass")


# =========================================================================== #
# F7. missing data filled without source -> fail                               #
# =========================================================================== #
class DataGapTests(unittest.TestCase):
    def test_value_with_no_source_ref_fails(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="V1", numeric_values=(("revenue", 100.0, "USD"),))
        res = g.check_data_gap([ev])
        self.assertEqual(res.status, "fail")
        self.assertIn("V1", res.subject_refs)

    def test_dict_value_with_no_source_fails(self):
        g = G.DataQualityGateRunner()
        res = g.check_data_gap([{"id": "d1", "value": 42}])
        self.assertEqual(res.status, "fail")

    def test_value_with_a_source_ref_passes(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="V2", numeric_values=(("revenue", 100.0, "USD"),),
                          source_refs=("sec:0001",))
        self.assertEqual(g.check_data_gap([ev]).status, "pass")

    def test_value_with_evidence_ref_passes(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="V3", numeric_values=(("x", 1.0, "u"),),
                          evidence_refs=("ex1",))
        self.assertEqual(g.check_data_gap([ev]).status, "pass")


# =========================================================================== #
# F8. scheduler/broker/streaming token in a module source -> fail (guardrail)  #
# =========================================================================== #
class SchedulerBrokerGuardrailTests(unittest.TestCase):
    def test_scheduler_token_fails(self):
        g = G.DataQualityGateRunner()
        src = "import sched\nschedule.every(5).minutes.do(job)\n"
        res = g.check_scheduler_broker_trading_guardrail([], module_sources={"sch": src})
        self.assertEqual(res.status, "fail")
        self.assertIn("sch", res.subject_refs)

    def test_background_scheduler_fails(self):
        g = G.DataQualityGateRunner()
        src = "sched = BackgroundScheduler()\n"
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail(
                [], module_sources={"m": src}).status, "fail")

    def test_broker_order_source_fails(self):
        g = G.DataQualityGateRunner()
        src = "broker.submit(order)\nresult = place_order(ticker)\n"
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail(
                [], module_sources={"m": src}).status, "fail")

    def test_html_trade_affordance_fails(self):
        g = G.DataQualityGateRunner()
        src = '<button onclick="placeOrder()">Buy</button>'
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail(
                [], module_sources={"ui": src}).status, "fail")

    def test_clean_module_source_passes(self):
        g = G.DataQualityGateRunner()
        src = "import json\n\ndef summarize(x):\n    return sorted(x)\n"
        self.assertEqual(
            g.check_scheduler_broker_trading_guardrail(
                [], module_sources={"m": src}).status, "pass")

    def test_policy_gate_result_is_typed_subset(self):
        g = G.DataQualityGateRunner()
        res = g.policy_gate_result(
            [_social_verified_dict(), _manual_canonical_dict()],
            module_sources={"m": "import sched\n"})
        self.assertIsInstance(res, G.PolicyGateResult)
        self.assertEqual(res.status, "fail")


# =========================================================================== #
# Freshness / conflict / schema / replay checkers (the remaining categories)   #
# =========================================================================== #
class RemainingCheckerTests(unittest.TestCase):
    def test_stale_presented_as_fresh_fails(self):
        g = G.DataQualityGateRunner()
        rec = {"id": "f1", "freshness_label": "fresh",
               "conflicts": ("value is stale as of last quarter",)}
        self.assertEqual(g.check_freshness([rec]).status, "fail")

    def test_honest_stale_only_warns(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_freshness([{"id": "f2", "freshness_label": "stale"}]).status, "warn")

    def test_dropped_contradiction_fails(self):
        g = G.DataQualityGateRunner()
        rec = {"id": "c1", "contradiction_status": "contradicted", "conflicts": ()}
        self.assertEqual(g.check_conflict([rec]).status, "fail")

    def test_preserved_contradiction_passes(self):
        g = G.DataQualityGateRunner()
        rec = {"id": "c2", "contradiction_status": "contradicted", "conflicts": ("both sides",)}
        self.assertEqual(g.check_conflict([rec]).status, "pass")

    def test_schema_major_mismatch_fails(self):
        g = G.DataQualityGateRunner()
        rec = {"id": "s1", "schema_version": "999.0"}
        self.assertEqual(
            g.check_schema_validation([rec], expected_schema_version="013.1").status, "fail")

    def test_schema_minor_drift_warns(self):
        g = G.DataQualityGateRunner()
        rec = {"id": "s2", "schema_version": "013.7"}
        self.assertEqual(
            g.check_schema_validation([rec], expected_schema_version="013.1").status, "warn")

    def test_schema_match_passes(self):
        g = G.DataQualityGateRunner()
        rec = {"id": "s3", "schema_version": "013.1"}
        self.assertEqual(
            g.check_schema_validation([rec], expected_schema_version="013.1").status, "pass")

    def test_replay_divergence_fails(self):
        g = G.DataQualityGateRunner()
        rr = rm.ReplayResult(replay_id="RP1", source_run_id="RUN1",
                             deterministic_match=False, differences=("a != b",))
        self.assertEqual(g.check_replayability([rr]).status, "fail")

    def test_replay_deterministic_passes(self):
        g = G.DataQualityGateRunner()
        rr = rm.ReplayResult(replay_id="RP2", source_run_id="RUN1",
                             deterministic_match=True)
        self.assertEqual(g.check_replayability([rr]).status, "pass")

    def test_replay_signature_mismatch_fails(self):
        g = G.DataQualityGateRunner()
        self.assertEqual(
            g.check_replayability((), signatures=("A", "B")).status, "fail")


# =========================================================================== #
# Source-authority warn-vs-fail distinction                                    #
# =========================================================================== #
class SourceAuthorityTests(unittest.TestCase):
    def test_lower_overrode_higher_fails(self):
        g = G.DataQualityGateRunner()
        res = g.check_source_authority(
            (), overrides=[("market_cap", "rumor", "canonical")])
        self.assertEqual(res.status, "fail")

    def test_dict_override_fails(self):
        g = G.DataQualityGateRunner()
        res = g.check_source_authority(
            (), overrides=[{"metric": "rev", "kept": "fallback", "overridden": "primary"}])
        self.assertEqual(res.status, "fail")

    def test_higher_overrode_lower_passes(self):
        g = G.DataQualityGateRunner()
        res = g.check_source_authority(
            (), overrides=[("rev", "canonical", "rumor")])
        self.assertEqual(res.status, "pass")

    def test_thin_coverage_only_warns(self):
        g = G.DataQualityGateRunner()
        # a record that DECLARES an authority field but left it empty -> thin coverage warn
        ev = RealityEvent(event_id="A1", source_authority="")
        res = g.check_source_authority([ev])
        self.assertEqual(res.status, "warn")


# =========================================================================== #
# Clean pulse -> all pass/warn, overall NOT failed; overall roll-up            #
# =========================================================================== #
class CleanPulseAndRollupTests(unittest.TestCase):
    def test_clean_pulse_all_pass_or_warn_overall_not_failed(self):
        g = G.DataQualityGateRunner()
        result, events = _clean_pulse()
        results, overall = g.run(
            signals=result.signals, findings=result.findings, events=events,
            authority_by_signal=result.authority_by_signal,
            run_mode="pulse", data_signature="pulse-real", demo_signature="demo-universe")
        self.assertEqual(len(results), 11)
        for res in results:
            self.assertIn(res.status, ("pass", "warn"),
                          "{0} unexpectedly {1}".format(res.category, res.status))
        self.assertIn(overall, ("healthy", "degraded"))
        self.assertNotIn(overall, ("failed", "blocked_by_policy"))

    def test_eleven_categories_present_and_ordered(self):
        g = G.DataQualityGateRunner()
        results, _ = g.run()
        self.assertEqual(tuple(r.category for r in results), G.GATE_CATEGORIES)
        self.assertEqual(len(G.GATE_CATEGORIES), 11)

    def test_empty_run_is_healthy(self):
        g = G.DataQualityGateRunner()
        results, overall = g.run()
        self.assertEqual(overall, "healthy")
        self.assertTrue(all(r.status == "pass" for r in results))

    def test_data_quality_fail_rolls_to_failed(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="V1", numeric_values=(("x", 1.0, "u"),))  # no source
        _, overall = g.run(events=[ev])
        self.assertEqual(overall, "failed")

    def test_policy_fail_rolls_to_blocked_by_policy(self):
        g = G.DataQualityGateRunner()
        _, overall = g.run(records=[_social_verified_dict()])
        self.assertEqual(overall, "blocked_by_policy")

    def test_security_fail_rolls_to_blocked_by_policy(self):
        g = G.DataQualityGateRunner()
        _, overall = g.run(generated_output_texts=["api_key=SECRETVALUE123"])
        self.assertEqual(overall, "blocked_by_policy")

    def test_blocked_by_policy_outranks_failed(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="V1", numeric_values=(("x", 1.0, "u"),))  # data fail
        _, overall = g.run(events=[ev], records=[_social_verified_dict()])  # + policy fail
        self.assertEqual(overall, "blocked_by_policy")

    def test_warn_only_rolls_to_degraded(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="A1", source_authority="")  # thin coverage warn
        _, overall = g.run(events=[ev])
        self.assertEqual(overall, "degraded")


# =========================================================================== #
# Gate records carry no secret value + no score/trade field                    #
# =========================================================================== #
class GateRecordHygieneTests(unittest.TestCase):
    def test_no_gate_record_class_has_a_trade_or_score_field(self):
        for cls in (G.DataQualityGateResult, G.SecurityGateResult, G.PolicyGateResult):
            for f in fields(cls):
                for tok in ("buy", "sell", "hold", "order", "trade", "broker",
                            "score", "rank", "rating"):
                    self.assertNotIn(tok, f.name.lower(),
                                     "{0}.{1}".format(cls.__name__, f.name))
            rm.assert_no_trade_fields(cls)

    def test_gate_result_status_is_validated(self):
        with self.assertRaises(ValueError):
            G.DataQualityGateResult(category="x", status="bogus")

    def test_gate_result_requires_category(self):
        with self.assertRaises(ValueError):
            G.DataQualityGateResult(category="", status="pass")

    def test_no_secret_value_survives_into_any_gate_finding(self):
        g = G.DataQualityGateRunner()
        secret = "sk-DEADBEEFCAFEBABE0123456789"
        results, _ = g.run(
            generated_output_texts=["api_key=" + secret],
            module_sources={"m": "import sched\n"})
        for res in results:
            for text in res.findings + res.subject_refs:
                self.assertNotIn(secret, text)
                self.assertNotIn("DEADBEEF", text)


# =========================================================================== #
# Determinism                                                                  #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_run_is_deterministic(self):
        result, events = _clean_pulse()
        a = G.DataQualityGateRunner().run(
            signals=result.signals, findings=result.findings, events=events,
            authority_by_signal=result.authority_by_signal)
        b = G.DataQualityGateRunner().run(
            signals=result.signals, findings=result.findings, events=events,
            authority_by_signal=result.authority_by_signal)
        self.assertEqual(a, b)

    def test_findings_and_refs_are_sorted_stable(self):
        g = G.DataQualityGateRunner()
        recs = [{"id": "z", "buy_signal": 1}, {"id": "a", "sell_signal": 1}]
        r1 = g.check_scheduler_broker_trading_guardrail(recs)
        r2 = g.check_scheduler_broker_trading_guardrail(list(reversed(recs)))
        self.assertEqual(r1.subject_refs, r2.subject_refs)


# =========================================================================== #
# I. Guardrails -- AST, offline, read-only, no wall-clock                       #
# =========================================================================== #
class GuardrailTests(unittest.TestCase):
    _NET = {"urllib", "http", "socket", "requests", "aiohttp", "httpx", "urllib3",
            "bs4", "beautifulsoup4", "selenium", "scrapy", "lxml", "mechanize", "pycurl",
            "websocket", "websockets"}
    _FORBIDDEN = {"sched", "asyncio", "subprocess", "socketserver", "threading",
                  "multiprocessing", "smtplib", "ftplib", "signal"}

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
                if node.level == 0:
                    mods.append((node.module or "").split(".")[0])
        return mods

    def test_gates_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._read(_GATES_PY))
        for m in self._imported_modules(tree):
            self.assertNotIn(m, self._NET, "gates imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "gates imports forbidden {0}".format(m))

    def test_gates_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_GATES_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "gates defines {0}".format(node.name))

    def test_gates_source_has_no_wall_clock(self):
        blob = self._read(_GATES_PY)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(",
                       "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_gate_run_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            result, events = _clean_pulse()
            _, overall = G.DataQualityGateRunner().run(
                signals=result.signals, findings=result.findings, events=events)
        finally:
            socket.socket = real
        self.assertIn(overall, ("healthy", "degraded"))

    def test_runner_is_read_only_no_mutation_of_inputs(self):
        g = G.DataQualityGateRunner()
        ev = RealityEvent(event_id="RO1", numeric_values=(("x", 1.0, "u"),),
                          source_refs=("s",))
        before = repr(ev)
        g.run(events=[ev])
        self.assertEqual(repr(ev), before)  # frozen input untouched


if __name__ == "__main__":
    unittest.main()
