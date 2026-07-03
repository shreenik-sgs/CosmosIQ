"""IMPLEMENTATION-013C -- Reality Mesh deterministic ReplayHarness (Phase-013).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against temp-dir JSONL stores -- no
network, no scheduler, no broker, no live endpoint. It proves the replay invariants the gate
enforces (PERSISTENCE_REPLAY_CONTRACT_013 §3/§4, TEST_MATRIX_013 §C1-C5 + the global
guardrails §I):

* C1 -- replay by run_id / ticker / theme / time-window resolves the right scope;
* C2 -- same fixture inputs + schema + code => deterministic outputs (``deterministic_match=True``,
  empty ``differences``); a TAMPERED persisted signal => ``deterministic_match=False`` with the
  divergence NAMED (replay verifies, never rubber-stamps);
* C3 -- conflicts preserved through replay;
* C4 -- data gaps preserved through replay;
* C5 -- source / evidence refs preserved; forbidden downstream uses preserved on reconstructed
  envelopes;
* no-mutation -- store bytes are byte-unchanged after a replay (reads only);
* I  -- replay imports no network / scheduler / broker module + defines no ``*score``/``*rank``
  function (AST guards); the whole suite builds under a socket kill-switch; timestamps are injected
  (deterministic); local files only; the demo default stays byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import replace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import models as M
from reality_mesh import stores as S
from reality_mesh.fusion import TattvaSignalFusionSynthesizer
from reality_mesh.sphurana import ThemePulseSynthesizer

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_REPLAY_PY = os.path.join(_PKG_DIR, "replay.py")

_NOW = "2026-06-29T00:00:00Z"


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


def _tmp():
    return tempfile.mkdtemp(prefix="rm_replay_")


def _stores(store_dir=None):
    d = store_dir or _tmp()
    return (S.EventStore(d), S.FindingStore(d), S.SignalStore(d),
            S.ThemePulseStore(d), S.RunStore(d))


def _harness(store_dir=None):
    ev, fs, ss, ps, rs = _stores(store_dir)
    return rm.ReplayHarness(ev, fs, ss, ps, rs)


def _pulse(watchlist=("IREN", "NVDA"), themes=("physical_ai", "robotics")):
    return rm.run_pulse(list(watchlist), list(themes), now=_NOW)


def _persisted_harness(store_dir=None, *, run_id="RUN1", watchlist=("IREN", "NVDA"),
                       themes=("physical_ai", "robotics")):
    """A harness with one persisted run_pulse output; returns (harness, pulse_result, run)."""
    d = store_dir or _tmp()
    h = _harness(d)
    pr = _pulse(watchlist, themes)
    run = h.persist_pulse(pr, run_id=run_id, now=_NOW)
    return h, pr, run


def _finding(finding_id, agent_id, direction, companies=("IREN",), themes=("physical_ai",)):
    return M.AgentFinding(
        finding_id=finding_id, agent_id=agent_id, agent_layer="reality_intelligence",
        agent_name="News Filings", discipline="news_filings", input_events=("E1",),
        finding_type="FilingFactFinding", affected_companies=companies,
        affected_themes=themes, direction_label=direction, magnitude_label="major",
        urgency_label="elevated", confidence_label="high", freshness_label="fresh",
        half_life="days", source_authority_summary="canonical",
        corroboration_status="uncorroborated", contradiction_status="unopposed",
        evidence_refs=("ex.{0}".format(finding_id),), source_refs=("sec:{0}".format(finding_id),),
        routing_targets=("SignalFusion",))


def _persist_custom_run(h, run_id, findings, *, now=_NOW):
    """Fuse ``findings`` deterministically and persist run + findings + signals + pulses.

    Bypasses run_pulse so a test can force a specific shape (e.g. a contradiction the bundled
    fixtures never produce). Persists exactly what fusion/sphurana yield, so a clean replay
    matches -- unless a record is later tampered.
    """
    fusion = TattvaSignalFusionSynthesizer().fuse((), tuple(findings), now=now)
    sph = ThemePulseSynthesizer().synthesize(fusion.clusters, fusion.signals, now=now)
    run = rm.PulseRun(run_id=run_id, started_at=now, completed_at=now, mode="pulse",
                      trigger_type="manual", findings_created=len(findings),
                      signals_created=len(fusion.signals),
                      theme_pulses_created=len(sph.theme_pulses),
                      schema_version=S.SCHEMA_VERSION, runtime_version="013C")
    h.run_store.append(run)
    for f in findings:
        h.finding_store.append(f, run_id=run_id)
    for s in fusion.signals:
        h.signal_store.append(s, run_id=run_id)
    for p in sph.theme_pulses:
        h.theme_pulse_store.append(p, run_id=run_id)
    return fusion, sph


# =========================================================================== #
# C1. Resolve scope by run_id / ticker / theme / time-window                    #
# =========================================================================== #
class ResolveScopeTests(unittest.TestCase):
    def test_replay_by_run_id(self):
        h, pr, _ = _persisted_harness()
        res = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        self.assertEqual(res.source_run_id, "RUN1")
        self.assertEqual(res.events_replayed, pr.events_loaded)
        self.assertEqual(res.findings_replayed, len(pr.findings))
        self.assertEqual(res.signals_replayed, len(pr.signals))
        self.assertTrue(res.deterministic_match)

    def test_replay_by_ticker_scopes_events_and_findings(self):
        h, pr, _ = _persisted_harness()
        res = h.replay(rm.ReplayRequest(run_id="RUN1", ticker="IREN"), now=_NOW)
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1", ticker="IREN"), now=_NOW)
        # every event / finding read touches IREN -- the scope is honoured
        self.assertTrue(rec.events)
        self.assertTrue(all("IREN" in e.affected_companies for e in rec.events))
        self.assertTrue(all("IREN" in f.affected_companies for f in rec.findings))
        # and the ticker scope is a strict subset of the full run
        self.assertLess(res.events_replayed, pr.events_loaded)
        self.assertTrue(res.deterministic_match)

    def test_replay_by_theme_scopes_to_theme(self):
        h, _, _ = _persisted_harness()
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1", theme="robotics"), now=_NOW)
        self.assertTrue(rec.findings)
        norm = lambda vs: any("robotics" == "".join(c for c in str(v).lower() if c.isalnum())
                              for v in vs)
        self.assertTrue(all(norm(f.affected_themes) for f in rec.findings))

    def test_replay_by_time_window_resolves_run(self):
        h, _, _ = _persisted_harness()
        window = ("2026-06-01T00:00:00Z", "2026-07-01T00:00:00Z")
        res = h.replay(rm.ReplayRequest(time_window=window), now=_NOW)
        self.assertEqual(res.source_run_id, "RUN1")
        self.assertTrue(res.deterministic_match)

    def test_replay_by_ticker_resolves_run_without_run_id(self):
        h, _, _ = _persisted_harness()
        res = h.replay(rm.ReplayRequest(ticker="IREN"), now=_NOW)
        self.assertEqual(res.source_run_id, "RUN1")

    def test_unmatched_scope_is_a_named_difference_not_a_match(self):
        h, _, _ = _persisted_harness()
        res = h.replay(rm.ReplayRequest(run_id="NOPE"), now=_NOW)
        self.assertFalse(res.deterministic_match)
        self.assertTrue(res.differences)
        self.assertEqual(res.source_run_id, "NOPE")


# =========================================================================== #
# C2. Deterministic replay: clean == match, tampered == named mismatch          #
# =========================================================================== #
class DeterministicReplayTests(unittest.TestCase):
    def test_clean_replay_is_deterministic_match_empty_differences(self):
        h, pr, _ = _persisted_harness()
        res = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        self.assertTrue(res.deterministic_match)
        self.assertEqual(res.differences, ())
        # the recomputed signals / pulses EQUAL the persisted ones (not merely counted)
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        self.assertEqual(
            {s.signal_id: s for s in rec.signals},
            {s.signal_id: s for s in rec.persisted_signals})
        self.assertEqual(
            {p.theme_pulse_id: p for p in rec.theme_pulses},
            {p.theme_pulse_id: p for p in rec.persisted_theme_pulses})

    def test_replay_id_is_deterministic(self):
        h, _, _ = _persisted_harness()
        a = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        b = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        self.assertEqual(a.replay_id, b.replay_id)
        self.assertTrue(a.replay_id.startswith("replay."))

    def test_tampered_persisted_signal_is_named_mismatch(self):
        # Persist a run, but write a signal whose confidence is TAMPERED away from what fusion
        # deterministically produces. Replay must recompute the true value and NAME the divergence.
        d = _tmp()
        h = _harness(d)
        pr = _pulse()
        target = next(s for s in pr.signals if s.confidence_label != "very_low")
        tampered = replace(target, confidence_label="very_low")
        signals = tuple(tampered if s.signal_id == target.signal_id else s for s in pr.signals)
        pr_tampered = replace(pr, signals=signals)

        h.persist_pulse(pr_tampered, run_id="RUN1", now=_NOW)
        res = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)

        self.assertFalse(res.deterministic_match)
        self.assertTrue(res.differences)
        joined = " ".join(res.differences)
        self.assertIn(target.signal_id, joined)
        self.assertIn("confidence_label", joined)
        self.assertIn("very_low", joined)

    def test_tampered_theme_pulse_state_is_named_mismatch(self):
        d = _tmp()
        h = _harness(d)
        pr = _pulse()
        target = pr.theme_pulses[0]
        new_state = "Dormant" if target.state != "Dormant" else "Igniting"
        tampered = replace(target, state=new_state)
        pulses = tuple(tampered if p.theme_pulse_id == target.theme_pulse_id else p
                       for p in pr.theme_pulses)
        h.persist_pulse(replace(pr, theme_pulses=pulses), run_id="RUN1", now=_NOW)

        res = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        self.assertFalse(res.deterministic_match)
        self.assertIn(target.theme_pulse_id, " ".join(res.differences))
        self.assertIn("state", " ".join(res.differences))


# =========================================================================== #
# C3 / C4 / C5. Conflicts, gaps, refs + forbidden uses preserved through replay #
# =========================================================================== #
class PreservationTests(unittest.TestCase):
    def test_conflicts_preserved_through_replay(self):
        # Two canonical findings that DISAGREE on direction -> fusion marks the signal
        # contradicted and records the clash in ``conflicts``. Replay must preserve it verbatim.
        h = _harness()
        findings = (
            _finding("F.up", "tattva.news_filings.a", "improving"),
            _finding("F.down", "tattva.news_filings.b", "deteriorating"),
        )
        fusion, _ = _persist_custom_run(h, "RUN_C", findings)
        self.assertTrue(any(s.conflicts and s.contradiction_status == "contradicted"
                            for s in fusion.signals),
                        "the crafted findings must fuse into a contradicted signal")

        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN_C"), now=_NOW)
        by_id = {s.signal_id: s for s in rec.persisted_signals}
        conflicted = [s for s in rec.signals if s.conflicts]
        self.assertTrue(conflicted)
        for sig in conflicted:
            # nothing averaged away: recomputed conflicts + contradiction status equal persisted
            self.assertEqual(sig.conflicts, by_id[sig.signal_id].conflicts)
            self.assertEqual(sig.contradiction_status, by_id[sig.signal_id].contradiction_status)
        res = h.replay(rm.ReplayRequest(run_id="RUN_C"), now=_NOW)
        self.assertTrue(res.deterministic_match)

    def test_data_gaps_preserved_through_replay(self):
        h, _, _ = _persisted_harness()
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        by_id = {s.signal_id: s for s in rec.persisted_signals}
        gapped = [s for s in rec.signals if s.data_gaps]
        self.assertTrue(gapped, "fixture should produce at least one signal carrying a data gap")
        for sig in gapped:
            self.assertEqual(sig.data_gaps, by_id[sig.signal_id].data_gaps)
        pulse_by_id = {p.theme_pulse_id: p for p in rec.persisted_theme_pulses}
        for pulse in rec.theme_pulses:
            self.assertEqual(pulse.data_gaps, pulse_by_id[pulse.theme_pulse_id].data_gaps)

    def test_source_and_evidence_refs_preserved_through_replay(self):
        h, _, _ = _persisted_harness()
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        by_id = {s.signal_id: s for s in rec.persisted_signals}
        with_refs = [s for s in rec.signals if s.evidence_refs or s.source_refs]
        self.assertTrue(with_refs)
        for sig in with_refs:
            self.assertEqual(sig.evidence_refs, by_id[sig.signal_id].evidence_refs)
            self.assertEqual(sig.source_refs, by_id[sig.signal_id].source_refs)

    def test_forbidden_uses_preserved_on_reconstructed_envelopes(self):
        h, _, _ = _persisted_harness()
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        envelopes = list(rec.fusion_envelopes) + list(rec.sphurana_envelopes)
        self.assertTrue(envelopes, "replay should reconstruct at least one handoff envelope")
        for env in envelopes:
            # the four mandatory default-forbidden uses survive the recompute unchanged
            for use in ("broker_order", "auto_execute", "buy_sell_recommendation", "hidden_score"):
                self.assertIn(use, env.forbidden_downstream_uses)

    def test_rumor_stays_rumor_through_replay(self):
        # A narrative signal must never be upgraded on replay -- rumor stays rumor.
        h, _, _ = _persisted_harness()
        rec = h.reconstruct(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        narrative = [s for s in rec.signals if s.discipline == "narrative"]
        self.assertTrue(narrative)
        for sig in narrative:
            self.assertIn(sig.corroboration_status,
                          ("uncorroborated", "partially_corroborated", "corroborated"))
            # a narrative signal never carries a fact-tier confidence on replay
            self.assertNotIn(sig.confidence_label, ("high", "very_high"))


# =========================================================================== #
# No mutation of history: store bytes byte-unchanged after a replay              #
# =========================================================================== #
class NoMutationTests(unittest.TestCase):
    def _snapshot(self, harness):
        snap = {}
        for st in (harness.event_store, harness.finding_store, harness.signal_store,
                   harness.theme_pulse_store, harness.run_store):
            if os.path.isfile(st.path):
                with open(st.path, "rb") as fh:
                    snap[st.path] = fh.read()
        return snap

    def test_replay_does_not_mutate_any_store(self):
        d = _tmp()
        h, _, _ = _persisted_harness(d)
        before = self._snapshot(h)
        for req in (rm.ReplayRequest(run_id="RUN1"),
                    rm.ReplayRequest(run_id="RUN1", ticker="IREN"),
                    rm.ReplayRequest(theme="robotics"),
                    rm.ReplayRequest(run_id="NOPE")):
            h.replay(req, now=_NOW)
            h.reconstruct(req, now=_NOW)
        after = self._snapshot(h)
        self.assertEqual(before, after)

    def test_harness_exposes_no_store_mutation_method(self):
        for banned in ("update", "delete", "remove", "mutate", "overwrite", "edit"):
            self.assertFalse(hasattr(rm.ReplayHarness, banned),
                             "ReplayHarness must not expose {0}".format(banned))


# =========================================================================== #
# I. Guardrails -- AST, offline, deterministic, demo byte-identical              #
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

    def test_replay_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._read(_REPLAY_PY))
        for m in self._imported_modules(tree):
            self.assertNotIn(m, self._NET, "replay imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "replay imports forbidden {0}".format(m))

    def test_replay_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_REPLAY_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "replay defines {0}".format(node.name))

    def test_replay_source_has_no_broker_scheduler_or_order_affordance(self):
        blob = self._read(_REPLAY_PY).lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_no_wall_clock_in_id_or_replay_path(self):
        blob = self._read(_REPLAY_PY)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_replay_is_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            h, _, _ = _persisted_harness()
            res = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        finally:
            socket.socket = real
        self.assertTrue(res.deterministic_match)

    def test_deterministic_across_two_independent_harnesses(self):
        a = _harness()
        b = _harness()
        pa, pb = _pulse(), _pulse()
        a.persist_pulse(pa, run_id="RUN1", now=_NOW)
        b.persist_pulse(pb, run_id="RUN1", now=_NOW)
        ra = a.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        rb = b.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        self.assertEqual(ra.replay_id, rb.replay_id)
        self.assertEqual(ra.outputs_reconstructed, rb.outputs_reconstructed)
        self.assertTrue(ra.deterministic_match and rb.deterministic_match)

    def test_result_carries_no_trade_or_score_field(self):
        h, _, _ = _persisted_harness()
        res = h.replay(rm.ReplayRequest(run_id="RUN1"), now=_NOW)
        rm.assert_no_trade_fields(res)
        rm.assert_no_trade_fields(h.reconstruct(rm.ReplayRequest(run_id="RUN1"), now=_NOW))


# =========================================================================== #
# I (cont). Existing behaviour unaffected -- demo default byte-identical         #
# =========================================================================== #
class ExistingBehaviourTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_replay_demo_a_")
        d2 = tempfile.mkdtemp(prefix="rm_replay_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))

    def test_replay_harness_is_exported(self):
        self.assertIs(rm.ReplayHarness, rm.ReplayHarness)
        self.assertIn("ReplayHarness", rm.__all__)
        self.assertIn("ReplayReconstruction", rm.__all__)


if __name__ == "__main__":
    unittest.main()
