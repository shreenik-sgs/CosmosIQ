"""IMPLEMENTATION-013B -- Reality Mesh append-only local stores (Phase-013).

INFRASTRUCTURE ONLY. This suite runs entirely OFFLINE against temp-dir JSONL logs -- no
network, no scheduler, no broker, no live endpoint. It proves the PERSISTENCE_REPLAY_CONTRACT_013
store invariants the gate enforces (TEST_MATRIX_013 §B1-B5 + the global guardrails §I):

* B1 -- RunStore / EventStore / FindingStore / SignalStore / ThemePulseStore / DataQualityStore /
  AuditStore append + read; a persisted RealityEvent/AgentFinding/RealitySignal/ThemePulse
  reconstructs EQUAL to the original;
* B2 -- query by run_id / ticker / theme / time-window (+ agent / discipline / state / category /
  status) returns the right subset;
* B3 -- schema_version stamped + preserved on every record;
* B4 -- APPEND-ONLY: the base exposes no update/delete/__setitem__; after further appends a
  previously-read line is byte-unchanged; a CORRECTION is a new AuditStore record referencing
  (not mutating) the corrected id;
* B5 -- no secret / raw credential key and no score/rank/rating/trade/broker/order key survives
  into a stored record (a persist attempt is REJECTED);
* I  -- stores import no network/scheduler/broker module + define no ``*score``/``*rank`` function
  (AST guards); the whole suite builds under a socket kill-switch; timestamps are injected
  (byte-identical JSONL); local files only; the demo default stays byte-identical.
"""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import fields

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import reality_mesh as rm
from reality_mesh import models as M
from reality_mesh import stores as S

_PKG_DIR = os.path.join(_SRC, "reality_mesh")
_STORES_PY = os.path.join(_PKG_DIR, "stores.py")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted")


# --------------------------------------------------------------------------- #
# Canonical fixtures (fully-populated valid instances)                          #
# --------------------------------------------------------------------------- #
def _pulse_run():
    return rm.PulseRun(
        run_id="RUN1", started_at="2026-06-29T00:00:00Z",
        completed_at="2026-06-29T00:01:00Z", mode="pulse", trigger_type="manual",
        watchlist=("IREN", "NVDA"), themes=("physical_ai",),
        source_adapters_requested=("sec",), source_adapters_used=("sec",),
        agents_requested=("a1",), agents_run=("a1",), agents_failed=(),
        events_created=2, findings_created=1, signals_created=1, theme_pulses_created=1,
        data_quality_status="degraded",
        generated_outputs=("generated/pulse/RUN1.json",),
        schema_version="013.1", runtime_version="013A")


def _event(event_id="E1", companies=("IREN",), themes=("physical_ai",)):
    return M.RealityEvent(
        event_id=event_id, timestamp="2026-06-29T00:00:00Z", source_id="src.sec",
        source_type="sec_filing", source_authority="canonical",
        claim_status="verified_fact", discipline="news_filings", event_type="8-K",
        affected_companies=companies, affected_themes=themes,
        numeric_values=(("market_cap", 5.0e10, "USD"),),
        evidence_refs=("ex1",), source_refs=("sec:0001",),
        confidence_label="high", freshness_label="fresh", half_life="days",
        conflicts=("c1",), data_gaps=("g1",))


def _finding(finding_id="F1", agent_id="tattva.market_regime", companies=("IREN",),
             themes=("physical_ai",)):
    return M.AgentFinding(
        finding_id=finding_id, agent_id=agent_id, agent_layer="reality_intelligence",
        agent_name="Market Regime", discipline="market_regime", input_events=("E1",),
        finding_type="MarketRegimeFinding", affected_companies=companies,
        affected_themes=themes, direction_label="deteriorating",
        magnitude_label="moderate", urgency_label="elevated", confidence_label="moderate",
        freshness_label="recent", half_life="days", source_authority_summary="convenience",
        corroboration_status="uncorroborated", contradiction_status="unopposed",
        evidence_refs=("ex1",), data_gaps=("g1",), routing_targets=("SignalFusion",))


def _signal(signal_id="S1", companies=("IREN",), themes=("physical_ai",),
            discipline="cross_discipline"):
    return M.RealitySignal(
        signal_id=signal_id, signal_type="regime_shift", source_findings=("F1",),
        discipline=discipline, affected_companies=companies, affected_themes=themes,
        direction_label="deteriorating", magnitude_label="major", confidence_label="moderate",
        corroboration_status="corroborated", contradiction_status="disputed",
        evidence_refs=("ex1",), conflicts=("c1",), data_gaps=("g1",),
        routing_targets=("Sphurana",))


def _theme_pulse(theme_pulse_id="P1", theme_id="physical_ai", state="Warming",
                 theme_name="Physical AI"):
    return M.ThemePulse(
        theme_pulse_id=theme_pulse_id, theme_id=theme_id, theme_name=theme_name,
        state=state, source_signal_clusters=("C1",), supporting_signals=("S1",),
        contradicting_signals=("S2",), breadth_label="moderate", rotation_label="rising",
        crowding_label="minor", bottleneck_label="major", confidence_label="moderate",
        evidence_refs=("ex1",), conflicts=("c1",), data_gaps=("g1",))


def _tmp():
    return tempfile.mkdtemp(prefix="rm_stores_")


# =========================================================================== #
# B1. Append + read round-trip (typed reconstruction equals the original)     #
# =========================================================================== #
class AppendReadRoundTripTests(unittest.TestCase):
    def test_run_store_round_trip(self):
        st = S.RunStore(_tmp())
        rid = st.append(_pulse_run())
        self.assertEqual(rid, "RUN1")
        got = st.read_all()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0], _pulse_run())

    def test_event_store_round_trip_equal(self):
        st = S.EventStore(_tmp())
        st.append(_event(), run_id="RUN1")
        got = st.read_all()
        self.assertEqual(got, (_event(),))
        # tuple-of-tuple field survives the JSON list round-trip
        self.assertEqual(got[0].numeric_values, (("market_cap", 5.0e10, "USD"),))
        self.assertIsInstance(got[0].affected_companies, tuple)

    def test_finding_store_round_trip_equal(self):
        st = S.FindingStore(_tmp())
        st.append(_finding(), run_id="RUN1")
        self.assertEqual(st.read_all(), (_finding(),))

    def test_signal_store_round_trip_equal(self):
        st = S.SignalStore(_tmp())
        st.append(_signal(), run_id="RUN1")
        self.assertEqual(st.read_all(), (_signal(),))

    def test_theme_pulse_store_round_trip_equal(self):
        st = S.ThemePulseStore(_tmp())
        st.append(_theme_pulse(), run_id="RUN1")
        self.assertEqual(st.read_all(), (_theme_pulse(),))

    def test_data_quality_store_round_trip(self):
        st = S.DataQualityStore(_tmp())
        rec = S.DataQualityRecord(
            dq_id="DQ1", run_id="RUN1", category="coverage", status="degraded",
            summary="1 uncovered ticker", records=("no coverage for NVDA",), at="t0")
        st.append(rec)
        self.assertEqual(st.read_all(), (rec,))

    def test_audit_store_round_trip(self):
        st = S.AuditStore(_tmp())
        rec = S.AuditRecord(
            audit_id="A1", run_id="RUN1", actor="tattva.market_regime", action="append",
            subject_ref="F1", at="t0")
        st.append(rec)
        got = st.read_all()
        self.assertEqual(got, (rec,))
        self.assertFalse(got[0].is_correction)

    def test_all_seven_stores_present(self):
        self.assertEqual(len(S.STORE_CLASSES), 7)
        for cls in S.STORE_CLASSES:
            self.assertTrue(issubclass(cls, S.AppendOnlyStore))
            self.assertIs(getattr(rm, cls.__name__), cls)

    def test_read_all_empty_when_no_log(self):
        st = S.EventStore(_tmp())
        self.assertEqual(st.read_all(), ())
        self.assertEqual(st.read_records(), ())
        self.assertEqual(st.query(run_id="RUN1"), ())

    def test_multiple_appends_preserve_order(self):
        st = S.EventStore(_tmp())
        for eid in ("E3", "E1", "E2"):
            st.append(_event(event_id=eid), run_id="RUN1")
        self.assertEqual([e.event_id for e in st.read_all()], ["E3", "E1", "E2"])


# =========================================================================== #
# B2. Query by run / ticker / theme / window (+ agent / discipline / state)   #
# =========================================================================== #
class QueryTests(unittest.TestCase):
    def _event_store(self):
        st = S.EventStore(_tmp())
        st.append(_event("E1", companies=("IREN",), themes=("physical_ai",)),
                  run_id="RUN1", timestamp="2026-06-10T00:00:00Z")
        st.append(_event("E2", companies=("NVDA",), themes=("robotics",)),
                  run_id="RUN1", timestamp="2026-06-20T00:00:00Z")
        st.append(_event("E3", companies=("IREN",), themes=("physical_ai",)),
                  run_id="RUN2", timestamp="2026-06-30T00:00:00Z")
        return st

    def test_query_by_run_id(self):
        st = self._event_store()
        self.assertEqual({e.event_id for e in st.query(run_id="RUN1")}, {"E1", "E2"})
        self.assertEqual({e.event_id for e in st.query(run_id="RUN2")}, {"E3"})

    def test_query_by_ticker(self):
        st = self._event_store()
        self.assertEqual({e.event_id for e in st.query(ticker="IREN")}, {"E1", "E3"})
        self.assertEqual({e.event_id for e in st.query(ticker="nvda")}, {"E2"})  # case-insensitive

    def test_query_by_theme(self):
        st = self._event_store()
        self.assertEqual({e.event_id for e in st.query(theme="Physical AI")}, {"E1", "E3"})
        self.assertEqual({e.event_id for e in st.query(theme="robotics")}, {"E2"})

    def test_query_by_time_window(self):
        st = self._event_store()
        window = ("2026-06-05T00:00:00Z", "2026-06-25T00:00:00Z")
        self.assertEqual({e.event_id for e in st.query(time_window=window)}, {"E1", "E2"})

    def test_query_combined_filters(self):
        st = self._event_store()
        self.assertEqual(
            {e.event_id for e in st.query(run_id="RUN1", ticker="IREN")}, {"E1"})

    def test_finding_query_by_agent(self):
        st = S.FindingStore(_tmp())
        st.append(_finding("F1", agent_id="tattva.market_regime"), run_id="RUN1")
        st.append(_finding("F2", agent_id="tattva.sector_rotation"), run_id="RUN1")
        self.assertEqual(
            {f.finding_id for f in st.query(agent="tattva.market_regime")}, {"F1"})
        self.assertEqual(
            {f.finding_id for f in st.query(agent_id="tattva.sector_rotation")}, {"F2"})

    def test_signal_query_by_discipline(self):
        st = S.SignalStore(_tmp())
        st.append(_signal("S1", discipline="cross_discipline"), run_id="RUN1")
        st.append(_signal("S2", discipline="market_regime"), run_id="RUN1")
        self.assertEqual(
            {s.signal_id for s in st.query(discipline="market_regime")}, {"S2"})

    def test_theme_pulse_query_by_state(self):
        st = S.ThemePulseStore(_tmp())
        st.append(_theme_pulse("P1", state="Warming"), run_id="RUN1")
        st.append(_theme_pulse("P2", theme_id="robotics", state="Igniting",
                               theme_name="Robotics"), run_id="RUN1")
        self.assertEqual({p.theme_pulse_id for p in st.query(state="Igniting")}, {"P2"})
        self.assertEqual({p.theme_pulse_id for p in st.query(theme="physical_ai")}, {"P1"})

    def test_data_quality_query_by_category_and_status(self):
        st = S.DataQualityStore(_tmp())
        st.append(S.DataQualityRecord(dq_id="DQ1", run_id="RUN1", category="coverage",
                                      status="degraded"))
        st.append(S.DataQualityRecord(dq_id="DQ2", run_id="RUN1", category="policy",
                                      status="pass"))
        self.assertEqual({r.dq_id for r in st.query(category="policy")}, {"DQ2"})
        self.assertEqual({r.dq_id for r in st.query(status="degraded")}, {"DQ1"})

    def test_audit_query_by_subject(self):
        st = S.AuditStore(_tmp())
        st.append(S.AuditRecord(audit_id="A1", run_id="RUN1", subject_ref="F1", action="append"))
        st.append(S.AuditRecord(audit_id="A2", run_id="RUN1", subject_ref="S1", action="append"))
        self.assertEqual({r.audit_id for r in st.query(subject="F1")}, {"A1"})
        self.assertEqual({r.audit_id for r in st.query(subject_ref="S1")}, {"A2"})

    def test_run_store_query_by_ticker_and_theme(self):
        st = S.RunStore(_tmp())
        st.append(_pulse_run())
        self.assertEqual(len(st.query(ticker="IREN")), 1)
        self.assertEqual(len(st.query(theme="physical_ai")), 1)
        self.assertEqual(len(st.query(ticker="TSLA")), 0)


# =========================================================================== #
# B3. schema_version stamped + preserved on every record                       #
# =========================================================================== #
class SchemaVersionTests(unittest.TestCase):
    def test_schema_version_on_every_record(self):
        specs = [
            (S.RunStore(_tmp()), _pulse_run(), {}),
            (S.EventStore(_tmp()), _event(), {"run_id": "RUN1"}),
            (S.FindingStore(_tmp()), _finding(), {"run_id": "RUN1"}),
            (S.SignalStore(_tmp()), _signal(), {"run_id": "RUN1"}),
            (S.ThemePulseStore(_tmp()), _theme_pulse(), {"run_id": "RUN1"}),
            (S.DataQualityStore(_tmp()),
             S.DataQualityRecord(dq_id="DQ1", run_id="RUN1", category="coverage"), {}),
            (S.AuditStore(_tmp()),
             S.AuditRecord(audit_id="A1", run_id="RUN1", action="append"), {}),
        ]
        for store, item, kw in specs:
            store.append(item, **kw)
            for rec in store.read_records():
                self.assertEqual(rec["schema_version"], S.SCHEMA_VERSION)
                self.assertIn("record_id", rec)
                self.assertIn("run_id", rec)
                self.assertIn("timestamp", rec)

    def test_envelope_carries_run_id_and_timestamp(self):
        st = S.EventStore(_tmp())
        st.append(_event(), run_id="RUN1")
        rec = st.read_records()[0]
        self.assertEqual(rec["run_id"], "RUN1")
        self.assertEqual(rec["timestamp"], "2026-06-29T00:00:00Z")  # pulled from event.timestamp
        self.assertEqual(rec["record_id"], "E1")


# =========================================================================== #
# B4. Append-only: no mutation API; byte-unchanged; correction-not-mutation    #
# =========================================================================== #
class AppendOnlyTests(unittest.TestCase):
    def test_base_exposes_no_mutation_method(self):
        for cls in (S.AppendOnlyStore,) + S.STORE_CLASSES:
            for banned in ("update", "delete", "remove", "__setitem__", "__delitem__",
                           "overwrite", "edit", "mutate"):
                self.assertFalse(
                    hasattr(cls, banned),
                    "{0} must not expose {1}".format(cls.__name__, banned))

    def test_previously_read_line_is_byte_unchanged_after_more_appends(self):
        st = S.EventStore(_tmp())
        st.append(_event("E1"), run_id="RUN1")
        with open(st.path, "rb") as fh:
            first_line = fh.readlines()[0]
        st.append(_event("E2"), run_id="RUN1")
        st.append(_event("E3"), run_id="RUN2")
        with open(st.path, "rb") as fh:
            lines = fh.readlines()
        self.assertEqual(lines[0], first_line)   # original line byte-for-byte unchanged
        self.assertEqual(len(lines), 3)

    def test_correction_is_a_new_audit_record_referencing_the_corrected_id(self):
        st = S.AuditStore(_tmp())
        st.append(S.AuditRecord(audit_id="A1", run_id="RUN1", actor="agent",
                                action="append", subject_ref="F1", at="t0",
                                note="original finding"))
        with open(st.path, "rb") as fh:
            original_line = fh.readlines()[0]

        # A correction is a NEW record referencing the corrected id -- never an edit.
        cid = st.append_correction(
            audit_id="A2", corrects="A1", run_id="RUN1", actor="human",
            subject_ref="F1b", at="t1", reason="finding restated")
        self.assertEqual(cid, "A2")

        with open(st.path, "rb") as fh:
            lines = fh.readlines()
        self.assertEqual(lines[0], original_line)   # corrected record byte-unchanged
        self.assertEqual(len(lines), 2)

        records = st.read_all()
        self.assertEqual(len(records), 2)
        self.assertFalse(records[0].is_correction)
        self.assertTrue(records[1].is_correction)
        self.assertEqual(records[1].corrects, "A1")   # references, not mutates
        self.assertEqual(records[0].audit_id, "A1")   # original untouched

    def test_store_uses_local_file_only(self):
        st = S.RunStore(_tmp())
        st.append(_pulse_run())
        self.assertTrue(os.path.isfile(st.path))
        self.assertTrue(st.path.endswith("run_store.jsonl"))


# =========================================================================== #
# B5. No secret / credential; no score/rank/trade field in any stored record  #
# =========================================================================== #
class NoSecretNoScoreTests(unittest.TestCase):
    def test_credential_key_rejected(self):
        st = S.DataQualityStore(_tmp())
        for bad_key in ("api_key", "TOKEN", "password", "client_secret",
                        "authorization", "private_key"):
            with self.assertRaises(ValueError):
                st.append({"dq_id": "DQ", "run_id": "R", bad_key: "shhh-secret-value"})
        # nothing was written -- no secret survived
        self.assertEqual(st.read_records(), ())

    def test_nested_credential_key_rejected(self):
        st = S.AuditStore(_tmp())
        with self.assertRaises(ValueError):
            st.append({"audit_id": "A1", "run_id": "R",
                       "note": {"headers": {"Authorization": "Bearer abc123"}}})
        self.assertEqual(st.read_records(), ())

    def test_trade_or_score_key_rejected(self):
        st = S.DataQualityStore(_tmp())
        for bad_key in ("investability_score", "rank", "buy_signal", "broker_order",
                        "order_id", "rating"):
            with self.assertRaises(ValueError):
                st.append({"dq_id": "DQ", "run_id": "R", bad_key: 0.9})
        self.assertEqual(st.read_records(), ())

    def test_no_stored_record_carries_a_banned_key(self):
        # Persist one of every typed record, then scan every stored key deeply.
        stores = [
            (S.RunStore(_tmp()), _pulse_run(), {}),
            (S.EventStore(_tmp()), _event(), {"run_id": "RUN1"}),
            (S.FindingStore(_tmp()), _finding(), {"run_id": "RUN1"}),
            (S.SignalStore(_tmp()), _signal(), {"run_id": "RUN1"}),
            (S.ThemePulseStore(_tmp()), _theme_pulse(), {"run_id": "RUN1"}),
        ]
        banned = S.CREDENTIAL_KEY_TOKENS + S.FORBIDDEN_FIELD_TOKENS
        for store, item, kw in stores:
            store.append(item, **kw)
            for rec in store.read_records():
                self.assertIsNone(
                    S._scan_bad_key(rec, banned),
                    "{0} persisted a banned key".format(type(store).__name__))

    def test_no_store_record_class_has_a_trade_or_score_field(self):
        for cls in (S.DataQualityRecord, S.AuditRecord):
            for f in fields(cls):
                low = f.name.lower()
                for tok in S.FORBIDDEN_FIELD_TOKENS:
                    self.assertNotIn(tok, low, "{0}.{1}".format(cls.__name__, f.name))
            rm.assert_no_trade_fields(cls)


# =========================================================================== #
# I. Guardrails -- AST, offline, deterministic, local-only, demo byte-identical #
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

    def test_stores_imports_no_network_scheduler_or_broker(self):
        tree = ast.parse(self._read(_STORES_PY))
        for m in self._imported_modules(tree):
            self.assertNotIn(m, self._NET, "stores imports network {0}".format(m))
            self.assertNotIn(m, self._FORBIDDEN, "stores imports forbidden {0}".format(m))

    def test_stores_defines_no_scoring_or_ranking_function(self):
        tree = ast.parse(self._read(_STORES_PY))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                for tok in ("score", "rank", "rating"):
                    self.assertNotIn(tok, low, "stores defines {0}".format(node.name))

    def test_stores_source_has_no_broker_scheduler_or_order_affordance(self):
        blob = self._read(_STORES_PY).lower()
        for banned in ("place_order", "submit_order", "execute_trade",
                       "schedule.every", "broker.submit"):
            self.assertNotIn(banned, blob, "banned source token: {0}".format(banned))

    def test_no_wall_clock_in_id_or_timestamp_path(self):
        blob = self._read(_STORES_PY)
        for banned in ("time.time(", "datetime.now(", "datetime.utcnow(", "time.monotonic("):
            self.assertNotIn(banned, blob, "wall-clock call: {0}".format(banned))

    def test_stores_write_and_read_are_offline(self):
        real = socket.socket
        socket.socket = _boom_socket
        try:
            st = S.EventStore(_tmp())
            st.append(_event(), run_id="RUN1")
            got = st.read_all()
        finally:
            socket.socket = real
        self.assertEqual(got, (_event(),))

    def test_deterministic_byte_identical_jsonl(self):
        d1, d2 = _tmp(), _tmp()
        a, b = S.EventStore(d1), S.EventStore(d2)
        for eid in ("E1", "E2"):
            a.append(_event(eid), run_id="RUN1")
            b.append(_event(eid), run_id="RUN1")
        with open(a.path, "rb") as fa, open(b.path, "rb") as fb:
            self.assertEqual(fa.read(), fb.read())

    def test_records_sorted_keys_are_deterministic(self):
        st = S.EventStore(_tmp())
        st.append(_event(), run_id="RUN1")
        with open(st.path, encoding="utf-8") as fh:
            line = fh.readline()
        # sort_keys=True -> the envelope keys appear in sorted order
        self.assertTrue(line.index('"payload"') < line.index('"record_id"'))
        self.assertTrue(line.index('"record_id"') < line.index('"schema_version"'))


# =========================================================================== #
# I (cont). Existing behaviour unaffected -- demo default byte-identical        #
# =========================================================================== #
class ExistingBehaviourTests(unittest.TestCase):
    def test_demo_default_byte_identical(self):
        from universe_ui.app import build_universe_app
        d1 = tempfile.mkdtemp(prefix="rm_stores_demo_a_")
        d2 = tempfile.mkdtemp(prefix="rm_stores_demo_b_")
        p1 = build_universe_app(d1)
        p2 = build_universe_app(d2)
        for name in ("universe.html", "dashboard.html", "data_quality.html", "cockpit.html"):
            self.assertEqual(
                open(p1[name], "rb").read(), open(p2[name], "rb").read(),
                "demo not byte-identical: {0}".format(name))
        with open(p1["universe.html"], encoding="utf-8") as fh:
            self.assertIn("reality_mesh.html", fh.read())


if __name__ == "__main__":
    unittest.main()
