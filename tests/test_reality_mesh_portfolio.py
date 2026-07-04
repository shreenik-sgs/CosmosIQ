"""IMPLEMENTATION-018A -- read-only portfolio intelligence core, tested OFFLINE.

``reality_mesh/portfolio.py``: frozen label/count records + pure builders over the
operator-recorded holdings file and the persisted 013B stores. Proven here:

* holdings load: missing -> (None, honest reason); malformed / bad shape -> a NAMED
  error; stale ``as_of`` (older than the latest persisted run) -> ``stale`` label;
* exposure maps positions to themes ONLY via persisted signals / theme pulses;
* concentration bands correct AT the published threshold edges, and the band is the
  ONLY value kept -- no float / ratio / weight field exists on any record (introspected);
* correlation labels from shared persisted-theme membership (no numeric correlation);
* rotation alignment against seeded pulse states (aligned / against / no_signal);
* candidate comparison labels (new_theme / adds_concentration / diversifies /
  no_theme_signal; ValueError with the honest reason when no holdings exist);
* every record is assert_no_trade_fields-clean; building mutates no stored byte;
  the module is AST-clean (no network / clock / scheduler import) and offline.
"""

from __future__ import annotations

import ast
import json
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

from reality_mesh import (
    BAND_UNKNOWN,
    CANDIDATE_COMPARISON_LABELS,
    CONCENTRATION_BANDS,
    CORRELATION_LABELS,
    HOLDINGS_RELPATH,
    HOLDINGS_FRESHNESS_LABELS,
    PORTFOLIO_RECORDS,
    PORTFOLIO_THRESHOLDS,
    ROTATION_ALIGNMENT_LABELS,
    STATE_ALIGNMENT,
    THEME_PULSE_STATES,
    RealitySignal,
    ThemePulse,
    assert_no_trade_fields,
    band_for_position_weight,
    band_for_theme_weight,
    build_concentration,
    build_correlation_labels,
    build_exposure,
    build_rotation_alignment,
    compare_candidate,
    load_holdings,
    ticker_theme_map,
)
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import RunStore, SignalStore, ThemePulseStore

_PORTFOLIO_PY = os.path.join(_SRC, "reality_mesh", "portfolio.py")

_RUN_AT = "2026-07-01T00:00:00Z"

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("network access attempted during offline portfolio tests"))


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT


def _write_holdings(store_dir, payload):
    base = os.path.join(store_dir, "portfolio")
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "holdings.json")
    with open(path, "w", encoding="utf-8") as fh:
        if isinstance(payload, str):
            fh.write(payload)
        else:
            json.dump(payload, fh)
    return path


def _seed_run(store_dir, run_id="R1", started_at=_RUN_AT):
    RunStore(store_dir).append(
        PulseRun(run_id=run_id, started_at=started_at, completed_at=started_at,
                 mode="pulse", trigger_type="manual"),
        run_id=run_id, timestamp=started_at)


def _seed_signal(store_dir, signal_id, companies, themes, run_id="R1"):
    SignalStore(store_dir).append(
        RealitySignal(signal_id=signal_id, affected_companies=tuple(companies),
                      affected_themes=tuple(themes)),
        run_id=run_id, timestamp=_RUN_AT)


def _seed_pulse(store_dir, theme_id, state, run_id="R1", beneficiaries=()):
    ThemePulseStore(store_dir).append(
        ThemePulse(theme_pulse_id="tp.{0}.{1}".format(run_id, theme_id),
                   theme_id=theme_id, theme_name=theme_id, state=state,
                   beneficiary_candidates=tuple(beneficiaries)),
        run_id=run_id, timestamp=_RUN_AT)


# =========================================================================== #
# 1. Loading the holdings statement -- honest in every failure mode            #
# =========================================================================== #
class LoadHoldingsTests(unittest.TestCase):
    def test_missing_file_is_none_plus_honest_reason(self):
        with tempfile.TemporaryDirectory() as d:
            loaded, reason = load_holdings(d)
            self.assertIsNone(loaded)
            self.assertIn("no holdings recorded", reason)
            self.assertIn(HOLDINGS_RELPATH, reason)

    def test_malformed_json_names_the_parse_error(self):
        with tempfile.TemporaryDirectory() as d:
            _write_holdings(d, "{not json")
            loaded, reason = load_holdings(d)
            self.assertIsNone(loaded)
            self.assertIn("could not be parsed", reason)
            self.assertIn("nothing is guessed", reason)

    def test_bad_shapes_are_named_not_guessed(self):
        cases = (
            ([1, 2], "JSON object"),
            ({"positions": []}, "as_of"),
            ({"as_of": "2026-01-01", "positions": "nope"}, "list"),
            ({"as_of": "2026-01-01", "positions": [{"quantity": 1}]}, "ticker"),
            ({"as_of": "2026-01-01", "positions": [{"ticker": "A"}]}, "quantity"),
        )
        for payload, token in cases:
            with tempfile.TemporaryDirectory() as d:
                _write_holdings(d, payload)
                loaded, reason = load_holdings(d)
                self.assertIsNone(loaded, payload)
                self.assertIn(token, reason)

    def test_no_persisted_run_means_no_run_to_compare(self):
        with tempfile.TemporaryDirectory() as d:
            _write_holdings(d, {"as_of": "2026-01-01T00:00:00Z",
                                "positions": [{"ticker": "a", "quantity": 1}]})
            loaded, reason = load_holdings(d)
            self.assertEqual(reason, "")
            self.assertEqual(loaded.freshness_label, "no_run_to_compare")

    def test_stale_and_current_labels_against_the_latest_run(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _write_holdings(d, {"as_of": "2026-06-30T00:00:00Z",
                                "positions": [{"ticker": "A", "quantity": 1}]})
            loaded, _ = load_holdings(d)
            self.assertEqual(loaded.freshness_label, "stale")
            self.assertIn("STALE", loaded.basis)
            _write_holdings(d, {"as_of": "2026-07-02T00:00:00Z",
                                "positions": [{"ticker": "A", "quantity": 1}]})
            loaded, _ = load_holdings(d)
            self.assertEqual(loaded.freshness_label, "current")

    def test_positions_are_carried_verbatim_as_text(self):
        with tempfile.TemporaryDirectory() as d:
            _write_holdings(d, {"as_of": "2026-01-01", "cash": 500, "positions": [
                {"ticker": "iren", "quantity": 100, "cost_basis": 15.5,
                 "account_label": "taxable-main", "liquidity_note": "thin float"},
                {"ticker": "ZZZZ", "quantity": 5},
            ]})
            loaded, _ = load_holdings(d)
            self.assertEqual(loaded.position_count, 2)
            first, second = loaded.positions
            self.assertEqual(first.ticker, "IREN")             # normalized upper
            self.assertEqual(first.quantity_text, "100")
            self.assertEqual(first.cost_basis_text, "15.5")
            self.assertEqual(first.account_label, "taxable-main")
            self.assertEqual(first.liquidity_note, "thin float")
            self.assertEqual(second.cost_basis_text, "")       # honest absence
            self.assertEqual(second.liquidity_note, "")
            self.assertTrue(loaded.cash_recorded)
            self.assertEqual(loaded.cash_text, "500")


# =========================================================================== #
# 2. Concentration bands -- thresholds as data, edges exact, band-only records #
# =========================================================================== #
class ConcentrationBandTests(unittest.TestCase):
    def test_band_edges_enter_the_higher_band(self):
        t = PORTFOLIO_THRESHOLDS
        self.assertEqual(band_for_position_weight(t["position_weight_moderate_pct"] - 0.1),
                         "minimal")
        self.assertEqual(band_for_position_weight(t["position_weight_moderate_pct"]),
                         "moderate")
        self.assertEqual(band_for_position_weight(t["position_weight_elevated_pct"] - 0.1),
                         "moderate")
        self.assertEqual(band_for_position_weight(t["position_weight_elevated_pct"]),
                         "elevated")
        self.assertEqual(band_for_position_weight(t["position_weight_dominant_pct"] - 0.1),
                         "elevated")
        self.assertEqual(band_for_position_weight(t["position_weight_dominant_pct"]),
                         "dominant")
        self.assertEqual(band_for_theme_weight(t["theme_exposure_dominant_pct"]),
                         "dominant")
        self.assertEqual(band_for_theme_weight(t["theme_exposure_moderate_pct"] - 0.1),
                         "minimal")

    def test_built_bands_at_the_edges_from_a_recorded_file(self):
        # Values engineered so the recorded total is exactly 1000 (no cash):
        # 4.9% / 5.0% / 9.9% / 10.0% / 19.9% / 20.0% / 30.3%.
        entries = (("AAAA", 49, "minimal"), ("BBBB", 50, "moderate"),
                   ("CCCC", 99, "moderate"), ("DDDD", 100, "elevated"),
                   ("EEEE", 199, "elevated"), ("FFFF", 200, "dominant"),
                   ("GGGG", 303, "dominant"))
        with tempfile.TemporaryDirectory() as d:
            _write_holdings(d, {"as_of": "2026-01-01", "positions": [
                {"ticker": name, "quantity": 1, "cost_basis": value}
                for name, value, _band in entries]})
            views = build_concentration(d)
            got = {view.ticker: view.weight_band for view in views}
            for name, _value, band in entries:
                self.assertEqual(got[name], band, name)

    def test_unweighable_position_is_unknown_with_a_named_gap(self):
        with tempfile.TemporaryDirectory() as d:
            _write_holdings(d, {"as_of": "2026-01-01", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 100},
                {"ticker": "ZZZZ", "quantity": 5},          # no cost basis
            ]})
            views = {v.ticker: v for v in build_concentration(d)}
            self.assertEqual(views["ZZZZ"].weight_band, BAND_UNKNOWN)
            self.assertTrue(any("ZZZZ" in gap for gap in views["ZZZZ"].data_gaps))
            self.assertEqual(views["AAAA"].weight_band, "dominant")

    def test_no_ratio_or_weight_value_is_stored_anywhere(self):
        # Introspection: every field on every built record is a string, bool,
        # int volume, or tuple of strings -- NEVER a float; and no field name
        # suggests a stored ratio.
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.a", ("AAAA", "BBBB"), ("alpha",))
            _seed_pulse(d, "alpha", "Igniting")
            _write_holdings(d, {"as_of": "2026-07-02", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 60},
                {"ticker": "BBBB", "quantity": 1, "cost_basis": 40}]})
            loaded, _ = load_holdings(d)
            records = ((loaded,) + loaded.positions + build_concentration(d)
                       + build_exposure(d) + build_correlation_labels(d)
                       + build_rotation_alignment(d)
                       + (compare_candidate(d, "AAAA"),))
            for record in records:
                for f in fields(record):
                    value = getattr(record, f.name)
                    self.assertNotIsInstance(value, float,
                                             "{0}.{1}".format(type(record).__name__,
                                                              f.name))
                    self.assertNotIn("ratio", f.name.lower())
                    self.assertNotIn("pct", f.name.lower())
                    if isinstance(value, tuple):
                        for element in value:
                            # tuples carry strings (or nested frozen records,
                            # e.g. positions) -- never a number
                            self.assertIsInstance(element,
                                                  (str,) + PORTFOLIO_RECORDS)
                    else:
                        self.assertIsInstance(value, (str, bool, int))

    def test_every_record_class_is_trade_field_clean(self):
        for cls in PORTFOLIO_RECORDS:
            assert_no_trade_fields(cls)        # raises AssertionError on violation


# =========================================================================== #
# 3. Exposure -- persisted mapping only, never guessed                          #
# =========================================================================== #
class ExposureTests(unittest.TestCase):
    def test_exposure_maps_only_via_persisted_records(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.1", ("AAAA", "BBBB"), ("alpha",))
            _seed_signal(d, "sig.2", ("BBBB",), ("beta",))
            _seed_pulse(d, "gamma", "Warming", beneficiaries=("CCCC",))
            _write_holdings(d, {"as_of": "2026-07-02", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 25},
                {"ticker": "BBBB", "quantity": 1, "cost_basis": 25},
                {"ticker": "CCCC", "quantity": 1, "cost_basis": 25},
                {"ticker": "XXXX", "quantity": 1, "cost_basis": 25}]})
            views = {v.theme_id: v for v in build_exposure(d)}
            self.assertEqual(set(views), {"alpha", "beta", "gamma"})
            self.assertEqual(views["alpha"].position_tickers, ("AAAA", "BBBB"))
            self.assertEqual(views["alpha"].position_count, 2)
            self.assertEqual(views["beta"].position_tickers, ("BBBB",))
            self.assertEqual(views["gamma"].position_tickers, ("CCCC",))
            # XXXX has no persisted mapping and appears under no theme.
            for view in views.values():
                self.assertNotIn("XXXX", view.position_tickers)
            # bands: alpha = 50% -> dominant; beta/gamma = 25% -> elevated
            self.assertEqual(views["alpha"].exposure_band, "dominant")
            self.assertEqual(views["beta"].exposure_band, "elevated")

    def test_theme_map_ignores_unheld_and_is_upper_normalized(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.1", ("aaaa",), ("alpha",))
            mapping = ticker_theme_map(d)
            self.assertEqual(mapping, {"AAAA": ("alpha",)})

    def test_no_holdings_means_empty_builders(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.1", ("AAAA",), ("alpha",))
            self.assertEqual(build_exposure(d), ())
            self.assertEqual(build_concentration(d), ())
            self.assertEqual(build_correlation_labels(d), ())
            self.assertEqual(build_rotation_alignment(d), ())


# =========================================================================== #
# 4. Correlation labels -- shared membership, no number                        #
# =========================================================================== #
class CorrelationLabelTests(unittest.TestCase):
    def _store(self):
        d = tempfile.mkdtemp(prefix="pf_corr_")
        _seed_run(d)
        _seed_signal(d, "sig.1", ("TTTT", "UUUU"), ("alpha", "beta"))
        _seed_signal(d, "sig.2", ("VVVV",), ("alpha", "gamma"))
        _seed_signal(d, "sig.3", ("WWWW",), ("delta",))
        _write_holdings(d, {"as_of": "2026-07-02", "positions": [
            {"ticker": t, "quantity": 1, "cost_basis": 10}
            for t in ("TTTT", "UUUU", "VVVV", "WWWW", "NOPE")]})
        return d

    def test_labels_from_shared_theme_membership(self):
        d = self._store()
        views = {(v.ticker_a, v.ticker_b): v for v in build_correlation_labels(d)}
        self.assertEqual(views[("TTTT", "UUUU")].correlation_label, "co_exposed")
        self.assertEqual(views[("TTTT", "UUUU")].shared_themes, ("alpha", "beta"))
        self.assertEqual(views[("TTTT", "VVVV")].correlation_label,
                         "partially_co_exposed")
        self.assertEqual(views[("TTTT", "VVVV")].shared_themes, ("alpha",))
        self.assertEqual(views[("TTTT", "WWWW")].correlation_label, "distinct")
        self.assertEqual(views[("NOPE", "TTTT")].correlation_label, "unknown")
        for view in views.values():
            self.assertIn(view.correlation_label, CORRELATION_LABELS)

    def test_single_position_yields_no_pair(self):
        with tempfile.TemporaryDirectory() as d:
            _write_holdings(d, {"as_of": "2026-01-01", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 10}]})
            self.assertEqual(build_correlation_labels(d), ())


# =========================================================================== #
# 5. Rotation alignment -- persisted states through the published table         #
# =========================================================================== #
class RotationAlignmentTests(unittest.TestCase):
    def test_alignment_labels_against_seeded_pulse_states(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.1", ("AAAA",), ("alpha",))
            _seed_signal(d, "sig.2", ("BBBB",), ("beta",))
            _seed_signal(d, "sig.3", ("CCCC",), ("gamma",))   # no pulse for gamma
            _seed_pulse(d, "alpha", "Igniting")
            _seed_pulse(d, "beta", "Exhausting")
            _write_holdings(d, {"as_of": "2026-07-02", "positions": [
                {"ticker": t, "quantity": 1, "cost_basis": 10}
                for t in ("AAAA", "BBBB", "CCCC", "DDDD")]})
            rows = {(v.ticker, v.theme_id): v for v in build_rotation_alignment(d)}
            self.assertEqual(rows[("AAAA", "alpha")].alignment_label, "aligned")
            self.assertEqual(rows[("AAAA", "alpha")].theme_state, "Igniting")
            self.assertEqual(rows[("AAAA", "alpha")].run_id, "R1")
            self.assertEqual(rows[("BBBB", "beta")].alignment_label, "against")
            self.assertEqual(rows[("CCCC", "gamma")].alignment_label, "no_signal")
            self.assertEqual(rows[("CCCC", "gamma")].theme_state, "")
            self.assertEqual(rows[("DDDD", "")].alignment_label, "no_signal")
            for row in rows.values():
                self.assertIn(row.alignment_label, ROTATION_ALIGNMENT_LABELS)

    def test_latest_persisted_state_wins(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d, "R1", "2026-07-01T00:00:00Z")
            _seed_run(d, "R2", "2026-07-02T00:00:00Z")
            _seed_signal(d, "sig.1", ("AAAA",), ("alpha",))
            _seed_pulse(d, "alpha", "Igniting", run_id="R1")
            _seed_pulse(d, "alpha", "Breaking down", run_id="R2")
            _write_holdings(d, {"as_of": "2026-07-02", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 10}]})
            (row,) = build_rotation_alignment(d)
            self.assertEqual(row.theme_state, "Breaking down")
            self.assertEqual(row.alignment_label, "against")
            self.assertEqual(row.run_id, "R2")

    def test_state_alignment_table_covers_every_pulse_state(self):
        self.assertEqual(set(STATE_ALIGNMENT), set(THEME_PULSE_STATES))
        self.assertTrue(set(STATE_ALIGNMENT.values()) <= ROTATION_ALIGNMENT_LABELS)


# =========================================================================== #
# 6. Candidate comparison -- labels, honest absence                             #
# =========================================================================== #
class CandidateComparisonTests(unittest.TestCase):
    def _store(self):
        d = tempfile.mkdtemp(prefix="pf_cmp_")
        _seed_run(d)
        _seed_signal(d, "sig.1", ("HHHH",), ("alpha", "beta"))
        _seed_signal(d, "sig.2", ("SAME",), ("alpha",))       # not held; all-overlap
        _seed_signal(d, "sig.3", ("MIXX",), ("alpha", "zeta"))
        _seed_signal(d, "sig.4", ("FRSH",), ("omega",))
        _write_holdings(d, {"as_of": "2026-07-02", "positions": [
            {"ticker": "HHHH", "quantity": 1, "cost_basis": 10}]})
        return d

    def test_labels(self):
        d = self._store()
        self.assertEqual(compare_candidate(d, "HHHH").comparison_label,
                         "adds_concentration")            # already recorded
        self.assertTrue(compare_candidate(d, "HHHH").already_recorded)
        self.assertEqual(compare_candidate(d, "SAME").comparison_label,
                         "adds_concentration")            # all themes already held
        self.assertEqual(compare_candidate(d, "FRSH").comparison_label, "new_theme")
        mixed = compare_candidate(d, "MIXX")
        self.assertEqual(mixed.comparison_label, "diversifies")
        self.assertEqual(mixed.overlapping_themes, ("alpha",))
        self.assertEqual(mixed.new_themes, ("zeta",))
        unmapped = compare_candidate(d, "NONE")
        self.assertEqual(unmapped.comparison_label, "no_theme_signal")
        self.assertTrue(unmapped.data_gaps)
        for label in ("adds_concentration", "new_theme", "diversifies",
                      "no_theme_signal"):
            self.assertIn(label, CANDIDATE_COMPARISON_LABELS)

    def test_supplied_themes_take_precedence_over_the_empty_mapping(self):
        d = self._store()
        self.assertEqual(compare_candidate(d, "NONE", ("omega2",)).comparison_label,
                         "new_theme")
        self.assertEqual(compare_candidate(d, "NONE", ("alpha",)).comparison_label,
                         "adds_concentration")

    def test_no_holdings_raises_the_honest_reason(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as ctx:
                compare_candidate(d, "AAAA")
            self.assertIn("no holdings recorded", str(ctx.exception))


# =========================================================================== #
# 7. Discipline: deterministic, byte-safe, pure module                          #
# =========================================================================== #
class DisciplineTests(unittest.TestCase):
    def test_builders_are_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.1", ("AAAA", "BBBB"), ("alpha",))
            _seed_pulse(d, "alpha", "Warming")
            _write_holdings(d, {"as_of": "2026-07-02", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 60},
                {"ticker": "BBBB", "quantity": 1, "cost_basis": 40}]})
            for builder in (build_exposure, build_concentration,
                            build_correlation_labels, build_rotation_alignment):
                self.assertEqual(builder(d), builder(d), builder.__name__)
            self.assertEqual(load_holdings(d), load_holdings(d))

    def test_building_mutates_no_stored_byte(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_run(d)
            _seed_signal(d, "sig.1", ("AAAA",), ("alpha",))
            _seed_pulse(d, "alpha", "Warming")
            path = _write_holdings(d, {"as_of": "2026-07-02", "positions": [
                {"ticker": "AAAA", "quantity": 1, "cost_basis": 60}]})
            watched = [os.path.join(d, name) for name in os.listdir(d)
                       if name.endswith(".jsonl")] + [path]

            def _bytes(p):
                with open(p, "rb") as fh:
                    return fh.read()

            before = {p: _bytes(p) for p in watched}
            load_holdings(d)
            build_exposure(d)
            build_concentration(d)
            build_correlation_labels(d)
            build_rotation_alignment(d)
            compare_candidate(d, "AAAA")
            for p in watched:
                self.assertEqual(_bytes(p), before[p], p)

    def test_vocabularies_are_closed_and_published(self):
        self.assertEqual(CONCENTRATION_BANDS,
                         ("minimal", "moderate", "elevated", "dominant"))
        self.assertEqual(HOLDINGS_FRESHNESS_LABELS,
                         frozenset({"current", "stale", "no_run_to_compare"}))
        for key in ("position_weight_moderate_pct", "position_weight_elevated_pct",
                    "position_weight_dominant_pct", "theme_exposure_moderate_pct",
                    "theme_exposure_elevated_pct", "theme_exposure_dominant_pct"):
            self.assertIn(key, PORTFOLIO_THRESHOLDS)

    def test_module_is_ast_clean_no_network_clock_or_scheduler(self):
        banned = {"socket", "socketserver", "http", "urllib", "requests", "ssl",
                  "select", "selectors", "sched", "asyncio", "threading",
                  "multiprocessing", "subprocess", "smtplib", "ftplib", "time",
                  "datetime", "random", "uuid"}
        with open(_PORTFOLIO_PY, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                mods = [(node.module or "").split(".")[0]]
            for module in mods:
                self.assertNotIn(module, banned, module)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr,
                                 ("now", "utcnow", "today", "time", "monotonic",
                                  "sleep"))
        self.assertFalse(any(isinstance(n, ast.While) for n in ast.walk(tree)))

    def test_offline_kill_switch_is_active(self):
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
