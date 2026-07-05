"""IMPLEMENTATION-020H -- the End-to-End Evidence-to-Candidate Trial. OFFLINE.

Proves the whole CosmosIQ intelligence chain runs once end to end and produces an HONEST,
traceable output:

* every trace line cites a REAL persisted record id (run / event / finding / signal / theme_pulse
  / candidate) -- the ids resolve back in the append-only stores, none are invented;
* CapitalCandidate publication goes through the store + the 019B eligibility gate: NO candidate is
  forged eligible; a blocked candidate carries its EXACT reason; an eligible candidate (when the
  evidence + a healthy run support it) carries FULL real provenance;
* the honest default trial over the bundled fixtures yields NO eligible candidate -- the focus
  ticker is blocked `ineligible_stale` because the run's Trust/Data-Quality is degraded (the run
  carries uncorroborated social/rumor records, kept weak by design);
* NO fixture ticker leaks into the DEFAULT product UI (an empty store renders `/`, `/runs`,
  `/candidates` clean);
* shadow-only: any alert is `mode = SHADOW_24X7`, inbox-only, no external delivery, no production
  escalation, no forbidden action phrase; a trade-like route is refused (403);
* replay of the run is deterministic (`deterministic_match = True`);
* the report carries NO secret / NO forbidden trade phrase / NO hidden score field;
* NO network on import; demo + default builds are byte-identical.
"""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import unittest

from cosmosiq_app.api import dispatch
from cosmosiq_ops import __main__ as ops_main
from cosmosiq_ops.ci_gate import (
    SECRET_KEY_TOKENS,
    SECRET_VALUE_PATTERNS,
    check_demo_build_byte_identical,
)
from cosmosiq_ops.e2e_trace import (
    CandidateTrace,
    E2ETraceResult,
    SignalTrace,
    SourceRecordTrace,
    render_e2e_trace_report,
    run_e2e_trial,
)
from reality_mesh.alerts import FORBIDDEN_ALERT_PHRASES, SHADOW_MODE_VALUE
from reality_mesh.capital_candidate import CapitalCandidateStore
from reality_mesh.stores import (
    EventStore,
    FindingStore,
    RunStore,
    SignalStore,
    ThemePulseStore,
)

_NOW = "2026-06-29T14:30:00Z"
_WATCHLIST = ("IREN", "AAOI", "INOD")
_THEMES = ("ai-infrastructure", "power-and-grid", "optical-networking",
           "physical-ai", "space-and-defense")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PULSE_FIXTURES = os.path.join(_REPO_ROOT, "tests", "fixtures", "reality_mesh", "pulse")

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError("network blocked: the E2E trial must run fully offline")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


def _run_default():
    store_dir = tempfile.mkdtemp()
    result = run_e2e_trial(store_dir, watchlist=_WATCHLIST, themes=_THEMES, now=_NOW)
    return store_dir, result


def _healthy_fixture_dir() -> str:
    """A curated OFFLINE fixture subset (no social) -> a HEALTHY-DQ pulse for the eligible path."""
    fx = tempfile.mkdtemp()
    for name in ("news_filings.json", "theme_rotation.json"):
        shutil.copy(os.path.join(_PULSE_FIXTURES, name), os.path.join(fx, name))
    return fx


class E2ETrialPersistenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store_dir, cls.result = _run_default()

    def test_result_shape_and_run_identity(self):
        self.assertIsInstance(self.result, E2ETraceResult)
        self.assertTrue(self.result.run_id)
        self.assertEqual(self.result.focus_ticker, "IREN")
        self.assertEqual(self.result.watchlist, _WATCHLIST)

    def test_trace_ids_resolve_in_the_persisted_stores(self):
        rid = self.result.run_id
        # the run itself
        self.assertTrue(RunStore(self.store_dir).query(run_id=rid))
        # every cited event / finding id is a real persisted record
        event_ids = {e.event_id for e in EventStore(self.store_dir).query(run_id=rid)}
        finding_ids = {f.finding_id for f in FindingStore(self.store_dir).query(run_id=rid)}
        signal_ids = {s.signal_id for s in SignalStore(self.store_dir).query(run_id=rid)}
        theme_ids = {t.theme_pulse_id
                     for t in ThemePulseStore(self.store_dir).query(run_id=rid)}
        self.assertTrue(self.result.event_sample_ids)
        for eid in self.result.event_sample_ids:
            self.assertIn(eid, event_ids)
        for fid in self.result.finding_sample_ids:
            self.assertIn(fid, finding_ids)
        self.assertTrue(self.result.signals)
        for sig in self.result.signals:
            self.assertIn(sig.signal_id, signal_ids)
        self.assertTrue(self.result.theme_pulses)
        for tp in self.result.theme_pulses:
            self.assertIn(tp.theme_pulse_id, theme_ids)

    def test_candidates_persisted_via_store_and_gate_no_forged(self):
        persisted = {c.candidate_id for c in CapitalCandidateStore(self.store_dir).read_all()}
        self.assertTrue(self.result.candidates)
        for cand in self.result.candidates:
            self.assertIn(cand.candidate_id, persisted)
        # Every persisted candidate carries the current run id in its content-derived id.
        for cand in CapitalCandidateStore(self.store_dir).read_all():
            self.assertEqual(cand.run_id, self.result.run_id)
        # No candidate is ever forged eligible.
        self.assertEqual(self.result.forged_eligible, ())
        # Any eligible candidate MUST carry full real provenance (unforgeable).
        for cand in self.result.candidates:
            if cand.is_eligible:
                self.assertTrue(cand.reality_signal_refs)
                self.assertTrue(cand.opportunity_hypothesis_ref)
                self.assertTrue(cand.investment_diligence_ref)
                self.assertEqual(cand.trust_data_quality_state, "healthy")

    def test_honest_outcome_is_all_blocked_with_exact_reasons(self):
        # The bundled-fixture run is degraded (uncorroborated social/rumor kept weak) -> no
        # eligible candidate. This is a VALID, acceptable honest outcome.
        self.assertEqual(self.result.candidate_outcome, "all_blocked")
        self.assertEqual(self.result.eligible_count, 0)
        self.assertEqual(self.result.dq_overall, "degraded")
        by_ticker = {c.ticker: c for c in self.result.candidates}
        # IREN: full real lineage present (real thesis) but blocked ONLY on the degraded run.
        iren = by_ticker["IREN"]
        self.assertEqual(iren.candidate_state, "ineligible_stale")
        self.assertTrue(iren.investment_diligence_ref.startswith("THS-"))
        self.assertTrue(iren.opportunity_hypothesis_ref.startswith("OPH-"))
        self.assertIn("data quality", iren.basis.lower())
        # INOD: no fixture coverage -> no signals -> missing provenance (exact reason).
        inod = by_ticker["INOD"]
        self.assertEqual(inod.candidate_state, "ineligible_missing_provenance")
        self.assertEqual(inod.reality_signal_refs, ())

    def test_diligence_and_hypothesis_are_real_records(self):
        # The pulse produced a real OpportunityHypothesisPacket for the moving theme.
        hyp_ids = {h.hypothesis_id for h in self.result.hypotheses}
        self.assertIn("hyp.physical-ai", hyp_ids)
        # A real diligence thesis was produced for IREN over the local research fixture.
        iren_dil = next(d for d in self.result.diligence if d.ticker == "IREN")
        self.assertTrue(iren_dil.produced)
        self.assertTrue(iren_dil.investment_diligence_ref.startswith("THS-"))
        # INOD has no research fixture -> an explicit gap, no fabricated thesis.
        inod_dil = next(d for d in self.result.diligence if d.ticker == "INOD")
        self.assertFalse(inod_dil.produced)
        self.assertTrue(inod_dil.gap_reason)

    def test_theme_pulses_and_data_insufficient(self):
        states = {t.theme_id: t.state for t in self.result.theme_pulses}
        self.assertEqual(states.get("physical-ai"), "Broadening")
        # The themes with no covering signal honestly render Data insufficient.
        for theme in ("ai-infrastructure", "power-and-grid", "optical-networking",
                      "space-and-defense"):
            self.assertIn(theme, self.result.themes_data_insufficient)

    def test_sec_gap_is_honest_credentials_missing(self):
        self.assertFalse(self.result.sec_configured)
        self.assertEqual(
            self.result.sec_source_health.get("source_health"), "credentials_missing")
        self.assertEqual(self.result.sec_source_health.get("events_created"), 0)
        # Every source record labelled; none dresses a fixture as live/canonical.
        by_id = {s.source_id: s for s in self.result.source_records}
        self.assertIn("offline_pulse_fixtures", by_id)
        self.assertIn("NOT live", by_id["offline_pulse_fixtures"].provenance)

    def test_replay_deterministic(self):
        self.assertTrue(self.result.replay_deterministic_match)
        self.assertEqual(self.result.replay_differences, ())

    def test_shadow_only_no_external_no_escalation(self):
        for alert in self.result.shadow_alerts:
            self.assertEqual(alert.mode, SHADOW_MODE_VALUE)
            self.assertEqual(alert.delivery, "in_app_inbox_only")
        self.assertFalse(self.result.external_delivery_occurred)
        self.assertFalse(self.result.production_escalation_occurred)
        self.assertEqual(self.result.alert_forbidden_phrase_hits, ())

    def test_ui_routes_all_render(self):
        self.assertTrue(self.result.ui_routes)
        for route in self.result.ui_routes:
            self.assertEqual(route.status, 200, route.route)
        # The exact surfaces the user must be able to open are present.
        routes = {r.route for r in self.result.ui_routes}
        for expected in ("/", "/runs", "/candidates", "/companies/IREN",
                         "/candidates/IREN", "/alerts",
                         "/replay/" + self.result.run_id):
            self.assertIn(expected, routes)


class EligiblePathTest(unittest.TestCase):
    """When the evidence + a HEALTHY run support it, the chain reaches an eligible candidate
    with FULL REAL provenance -- proving the pipeline is not stuck at 'always blocked'."""

    def test_eligible_candidate_shows_full_real_provenance(self):
        fx = _healthy_fixture_dir()
        store_dir = tempfile.mkdtemp()
        result = run_e2e_trial(
            store_dir, watchlist=("IREN",), themes=("physical-ai",), now=_NOW,
            fixture_dir=fx)
        self.assertEqual(result.dq_overall, "healthy")
        self.assertEqual(result.candidate_outcome, "eligible")
        self.assertEqual(result.eligible_count, 1)
        self.assertEqual(result.forged_eligible, ())
        cand = next(c for c in result.candidates if c.is_eligible)
        self.assertEqual(cand.ticker, "IREN")
        # full REAL provenance -- real signal refs + real thesis refs + healthy DQ
        self.assertTrue(cand.reality_signal_refs)
        self.assertTrue(cand.opportunity_hypothesis_ref.startswith("OPH-"))
        self.assertTrue(cand.investment_diligence_ref.startswith("THS-"))
        self.assertEqual(cand.trust_data_quality_state, "healthy")
        # the eligible candidate id resolves in the persisted store
        persisted = {c.candidate_id for c in CapitalCandidateStore(store_dir).read_all()}
        self.assertIn(cand.candidate_id, persisted)


class NoFixtureLeakTest(unittest.TestCase):
    def test_empty_store_default_ui_is_clean(self):
        empty = tempfile.mkdtemp()
        for path in ("/", "/runs", "/candidates"):
            resp = dispatch({"method": "GET", "path": path, "query": {}, "body": None},
                            store_dir=empty, now=_NOW)
            self.assertEqual(resp.get("status"), 200)
            body = str(resp.get("body", ""))
            for ticker in _WATCHLIST + ("AMBA", "OUST"):
                self.assertNotIn(ticker, body,
                                 "fixture ticker {0} leaked into {1}".format(ticker, path))


class NoTradeControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store_dir, cls.result = _run_default()
        cls.report = render_e2e_trace_report(cls.result, generated_at=_NOW)

    def test_no_trade_route_on_any_surface(self):
        # No rendered UI route carries a trade token.
        for route in self.result.ui_routes:
            low = route.route.lower()
            for token in ("buy", "sell", "order", "submit", "trade", "broker"):
                self.assertNotIn(token, low)
        # A trade-like path is refused outright (403), never routed.
        for path in ("/api/orders", "/buy/IREN", "/execute", "/broker/submit"):
            resp = dispatch({"method": "POST", "path": path, "query": {}, "body": None},
                            store_dir=self.store_dir, now=_NOW)
            self.assertEqual(resp.get("status"), 403)

    def test_report_no_secret_no_forbidden_phrase_no_hidden_score(self):
        blob = self.report.lower()
        for phrase in FORBIDDEN_ALERT_PHRASES:
            self.assertNotIn(phrase, blob)
        for pattern in SECRET_VALUE_PATTERNS:
            self.assertIsNone(pattern.search(self.report))
        for token in SECRET_KEY_TOKENS:
            self.assertNotIn(token, blob)
        # No hidden score / rank / rating / sizing field on any trace contract.
        for cls in (E2ETraceResult, CandidateTrace, SignalTrace, SourceRecordTrace):
            names = set(cls.__dataclass_fields__)
            for banned in ("score", "rank", "rating", "sizing"):
                self.assertFalse(any(banned in n for n in names),
                                 "{0} carries a {1} field".format(cls.__name__, banned))

    def test_report_answers_every_required_question(self):
        for section in (
                "## 0. Run identity",
                "## 1. What source data came in",
                "## 2. What RealityEvents",
                "## 3. Which ThemePulse changed",
                "## 4. Was an OpportunityHypothesis created?",
                "## 5. Was Investment Diligence triggered?",
                "## 6. ForwardScenario state",
                "## 7. Was a CapitalCandidate published?",
                "## 8. Trust / Data-Quality verdict",
                "## 9. Did any alert fire?",
                "## 10. Was replay successful?",
                "## 11. Where in the app this renders",
                "## 12. Honesty caveats"):
            self.assertIn(section, self.report)
        # honest labels present
        self.assertIn("credentials_missing", self.report)
        self.assertIn("NOT live", self.report)
        self.assertIn("ineligible_stale", self.report)


class DeterminismAndOfflineTest(unittest.TestCase):
    def test_no_network_on_import(self):
        # Execute the module's import-time code in ISOLATION under the armed socket kill-switch
        # (without mutating the cached module): importing reaches no network.
        import importlib.util
        import sys
        path = os.path.join(_REPO_ROOT, "src", "cosmosiq_ops", "e2e_trace.py")
        name = "_e2e_trace_import_probe"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module            # needed for annotation resolution on load
        try:
            spec.loader.exec_module(module)
            self.assertTrue(callable(module.run_e2e_trial))
        finally:
            sys.modules.pop(name, None)

    def test_demo_build_byte_identical(self):
        self.assertEqual(check_demo_build_byte_identical().status, "pass")

    def test_deterministic_run_id_and_report(self):
        s1, r1 = _run_default()
        s2, r2 = _run_default()
        self.assertEqual(r1.run_id, r2.run_id)
        self.assertEqual(r1.candidate_outcome, r2.candidate_outcome)
        self.assertEqual(
            render_e2e_trace_report(r1, generated_at=_NOW).replace(s1, "S"),
            render_e2e_trace_report(r2, generated_at=_NOW).replace(s2, "S"))


class CliTest(unittest.TestCase):
    def test_e2e_trace_subcommand_runs_and_writes_report(self):
        work = tempfile.mkdtemp()
        report_out = os.path.join(work, "E2E_TRACE.md")
        rc = ops_main.main(["e2e-trace", "--work-dir", work, "--now", _NOW,
                            "--report-out", report_out])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(report_out))
        with open(report_out, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("IMPLEMENTATION-020H", text)
        self.assertIn("credentials_missing", text)


if __name__ == "__main__":
    unittest.main()
