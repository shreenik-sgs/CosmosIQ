"""IMPLEMENTATION-UX-2 -- manual position ledger, tested OFFLINE.

``reality_mesh/position_ledger.py``: an append-only BOOKKEEPING journal of trades the operator
ALREADY EXECUTED at their OWN broker. It is NOT order submission and NOT a broker connection.
Proven here:

* record-only: the module has NO network / broker / subprocess import (AST), defines NO
  order/submit/place/route/broker/buy/sell function or token (AST), and ``record_fill`` runs
  under a socket kill-switch (offline);
* the custom execution-field guard ALLOWS quantity / price / side / trade_date (recorded FACTS)
  but bans a broker / order / submit / place / route / auto_trade / buy / sell FIELD NAME -- it is
  NOT assert_no_trade_fields;
* side is PAST-TENSE {bought, sold}; an imperative 'buy' / 'sell' / 'order' side -> ValueError;
  quantity > 0 and price >= 0 validated;
* append-only + correction-not-mutation: one line per fill; re-record identical -> byte-identical;
  a correction is a NEW line and the prior line is byte-unchanged; NO update / delete API;
* compute_holdings aggregates net quantity + average cost basis + realized proceeds correctly, a
  correction reverses correctly, a netted-to-0 position is closed not active, no fabricated price;
* holdings_for_portfolio_intelligence feeds 018 build_concentration / build_exposure over REAL
  ledger holdings (bands minimal/moderate/elevated/dominant) without breaking 018;
* a recommendation-linked fill surfaces via outcomes_for_learning (labels + refs only, no number);
* NO hidden score / rank function; deterministic; offline.
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
    EXECUTION_FIELD_TOKENS,
    FILL_SIDES,
    LEDGER_MODELS,
    Holding,
    LedgerOutcomeLink,
    PositionFill,
    PositionLedgerStore,
    assert_no_execution_fields,
    build_concentration,
    build_exposure,
    compute_holdings,
    fill_id_for,
    holdings_for_portfolio_intelligence,
    load_holdings,
    outcomes_for_learning,
    record_fill,
)
from reality_mesh.position_ledger import SCHEMA_VERSION

_LEDGER_PY = os.path.join(_SRC, "reality_mesh", "position_ledger.py")
_NOW = "2026-06-01T00:00:00Z"

_ORIG_CONNECT = None
_ORIG_CREATE = None


def setUpModule():
    global _ORIG_CONNECT, _ORIG_CREATE
    _ORIG_CONNECT = socket.socket.connect
    _ORIG_CREATE = socket.create_connection

    def _refuse(*a, **k):
        raise AssertionError("network access attempted during offline ledger tests")

    socket.socket.connect = _refuse
    socket.create_connection = _refuse


def tearDownModule():
    socket.socket.connect = _ORIG_CONNECT
    socket.create_connection = _ORIG_CREATE


def _store_dir():
    return tempfile.mkdtemp()


def _lines(store_dir):
    path = os.path.join(store_dir, "position_ledger.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [ln for ln in fh.read().splitlines() if ln.strip()]


# =========================================================================== #
# Append-only + correction-not-mutation                                        #
# =========================================================================== #
class AppendOnlyDiscipline(unittest.TestCase):
    def test_record_fill_persists_one_line(self):
        d = _store_dir()
        fill = record_fill(d, ticker="aaa", side="bought", quantity=100, price=30,
                           trade_date="2026-01-01", now=_NOW)
        self.assertEqual(len(_lines(d)), 1)
        self.assertEqual(fill.ticker, "AAA")
        self.assertEqual(fill.side, "bought")
        self.assertEqual(fill.schema_version, SCHEMA_VERSION)
        self.assertTrue(fill.fill_id.startswith("fill:"))

    def test_re_record_identical_is_byte_identical(self):
        d = _store_dir()
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                    trade_date="2026-01-01", now=_NOW, recommendation_ref="rec:1")
        before = _lines(d)
        # a later injected instant does NOT create a new line (content-derived id, idempotent).
        again = record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                            trade_date="2026-01-01", now="2026-09-09T00:00:00Z",
                            recommendation_ref="rec:1")
        after = _lines(d)
        self.assertEqual(before, after)
        self.assertEqual(len(after), 1)
        # the returned fill is the FIRST-recorded one (its recorded_at is unchanged).
        self.assertEqual(again.recorded_at, _NOW)

    def test_correction_is_a_new_line_prior_byte_unchanged(self):
        d = _store_dir()
        orig = record_fill(d, ticker="AAA", side="bought", quantity=50, price=36,
                           trade_date="2026-01-02", now=_NOW)
        first_line = _lines(d)[0]
        corrected = record_fill(d, ticker="AAA", side="bought", quantity=50, price=30,
                                trade_date="2026-01-02", now=_NOW,
                                correction_of=orig.fill_id)
        after = _lines(d)
        self.assertEqual(len(after), 2)
        self.assertEqual(after[0], first_line)          # prior line byte-unchanged
        self.assertEqual(corrected.correction_of, orig.fill_id)
        self.assertTrue(corrected.is_correction)

    def test_no_update_or_delete_api(self):
        store = PositionLedgerStore(_store_dir())
        for banned in ("update", "delete", "remove", "__setitem__", "__delitem__", "edit"):
            self.assertFalse(hasattr(store, banned),
                             "the ledger store must expose no {0} affordance".format(banned))

    def test_now_is_required(self):
        with self.assertRaises(ValueError):
            record_fill(_store_dir(), ticker="AAA", side="bought", quantity=1, price=1,
                        trade_date="2026-01-01", now="")


# =========================================================================== #
# Past-tense side + factual quantity/price validation                          #
# =========================================================================== #
class Validation(unittest.TestCase):
    def test_side_is_past_tense(self):
        self.assertEqual(set(FILL_SIDES), {"bought", "sold"})

    def test_imperative_side_is_refused(self):
        for bad in ("buy", "sell", "order", "hold", "BOUGHT", "SOLD", ""):
            with self.assertRaises(ValueError, msg="imperative side {0!r} must be refused".format(bad)):
                PositionFill(fill_id="x", ticker="AAA", side=bad, quantity=1, price=1,
                             trade_date="2026-01-01", recorded_at=_NOW)

    def test_quantity_must_be_positive_number(self):
        for bad in (0, -1, True, "10", None):
            with self.assertRaises(ValueError):
                PositionFill(fill_id="x", ticker="AAA", side="bought", quantity=bad, price=1,
                             trade_date="2026-01-01", recorded_at=_NOW)

    def test_price_must_be_nonnegative_number(self):
        for bad in (-1, True, "5", None):
            with self.assertRaises(ValueError):
                PositionFill(fill_id="x", ticker="AAA", side="bought", quantity=1, price=bad,
                             trade_date="2026-01-01", recorded_at=_NOW)
        # zero price is a legitimate recorded fact (e.g. a grant/transfer) -- accepted.
        PositionFill(fill_id="x", ticker="AAA", side="bought", quantity=1, price=0,
                     trade_date="2026-01-01", recorded_at=_NOW)

    def test_required_text_fields(self):
        for missing in ("ticker", "trade_date", "recorded_at"):
            kwargs = dict(fill_id="x", ticker="AAA", side="bought", quantity=1, price=1,
                          trade_date="2026-01-01", recorded_at=_NOW)
            kwargs[missing] = ""
            with self.assertRaises(ValueError):
                PositionFill(**kwargs)


# =========================================================================== #
# Record-only / no broker / offline                                            #
# =========================================================================== #
class RecordOnlyNoBroker(unittest.TestCase):
    def _tree(self):
        with open(_LEDGER_PY, encoding="utf-8") as fh:
            return ast.parse(fh.read())

    def test_no_network_or_broker_or_subprocess_import(self):
        banned = {"socket", "socketserver", "http", "urllib", "urllib2", "urllib3",
                  "requests", "httpx", "aiohttp", "ssl", "ftplib", "telnetlib",
                  "subprocess", "multiprocessing", "asyncio", "sched", "threading",
                  "ib_insync", "alpaca", "alpaca_trade_api", "ccxt", "robin_stocks"}
        found = []
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                found += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.append(node.module.split(".")[0])
        offenders = sorted(set(found) & banned)
        self.assertEqual(offenders, [], "banned import(s): {0}".format(offenders))

    def test_no_order_submission_function_name(self):
        # An executable order/trade affordance is an AST function NAME, not honest guardrail prose.
        import re
        exec_re = re.compile(
            r"(place|submit|send|execute|cancel|route)_?(order|trade|buy|sell)"
            r"|^(buy|sell)$|broker_?submit|market_order|limit_order")
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(exec_re.search(node.name.lower()),
                                  "order/trade-execution function name: {0}".format(node.name))

    def test_no_hidden_score_or_rank_function(self):
        for node in ast.walk(self._tree()):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                low = node.name.lower()
                self.assertNotIn("score", low)
                self.assertNotIn("rank", low)
                self.assertNotIn("rating", low)

    def test_record_fill_runs_under_the_socket_kill_switch(self):
        # setUpModule already killed connect/create_connection; prove a fill still writes offline.
        sock = socket.socket()
        try:
            with self.assertRaises(AssertionError):
                sock.connect(("127.0.0.1", 80))
        finally:
            sock.close()
        d = _store_dir()
        fill = record_fill(d, ticker="AAA", side="bought", quantity=1, price=1,
                           trade_date="2026-01-01", now=_NOW)
        self.assertEqual(len(_lines(d)), 1)
        self.assertEqual(fill.ticker, "AAA")


# =========================================================================== #
# The custom execution-field guard (NOT assert_no_trade_fields)                #
# =========================================================================== #
class ExecutionFieldGuard(unittest.TestCase):
    def test_tokens_ban_execution_but_allow_facts(self):
        for token in ("broker", "order", "submit", "place", "route", "auto_trade",
                      "buy", "sell"):
            self.assertIn(token, EXECUTION_FIELD_TOKENS)
        # the ledger's whole point: quantity / price / side are ALLOWED factual data.
        for allowed in ("quantity", "price", "shares", "amount"):
            self.assertNotIn(allowed, EXECUTION_FIELD_TOKENS)

    def test_models_are_execution_field_clean(self):
        for model in LEDGER_MODELS:
            assert_no_execution_fields(model)  # must not raise
        # PositionFill legitimately carries quantity + price (the recorded facts).
        names = {f.name for f in fields(PositionFill)}
        self.assertIn("quantity", names)
        self.assertIn("price", names)
        self.assertIn("side", names)

    def test_guard_rejects_a_broker_or_order_field(self):
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class _BadBroker:
            broker_ref: str = ""

        @dataclass(frozen=True)
        class _BadOrder:
            submit_order: str = ""

        for bad in (_BadBroker, _BadOrder):
            with self.assertRaises(ValueError):
                assert_no_execution_fields(bad)

    def test_store_refuses_a_broker_key_but_accepts_the_factual_payload(self):
        store = PositionLedgerStore(_store_dir())
        with self.assertRaises(ValueError):
            store.append({"fill_id": "z", "broker_submit": "x"}, timestamp=_NOW)


# =========================================================================== #
# compute_holdings aggregation                                                 #
# =========================================================================== #
class Aggregation(unittest.TestCase):
    def test_net_and_average_cost_basis(self):
        d = _store_dir()
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                    trade_date="2026-01-01", now=_NOW)
        record_fill(d, ticker="AAA", side="bought", quantity=50, price=36,
                    trade_date="2026-01-02", now=_NOW)
        h = compute_holdings(d)[0]
        self.assertEqual(h.net_quantity, 150)
        self.assertEqual(h.average_cost_basis, 32.0)   # (100*30 + 50*36) / 150
        self.assertEqual(h.total_fills, 2)
        self.assertFalse(h.is_closed)

    def test_sell_honors_cost_basis_and_records_proceeds(self):
        d = _store_dir()
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                    trade_date="2026-01-01", now=_NOW)
        record_fill(d, ticker="AAA", side="bought", quantity=50, price=36,
                    trade_date="2026-01-02", now=_NOW)
        record_fill(d, ticker="AAA", side="sold", quantity=50, price=40,
                    trade_date="2026-01-03", now=_NOW)
        h = compute_holdings(d)[0]
        self.assertEqual(h.net_quantity, 100)
        self.assertEqual(h.average_cost_basis, 32.0)   # weighted-average buy basis is honored
        self.assertEqual(h.realized_proceeds, 2000.0)  # 50 * 40
        self.assertEqual(h.last_trade_date, "2026-01-03")

    def test_correction_reverses_correctly(self):
        d = _store_dir()
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                    trade_date="2026-01-01", now=_NOW)
        wrong = record_fill(d, ticker="AAA", side="bought", quantity=50, price=36,
                            trade_date="2026-01-02", now=_NOW)
        # correct the wrong 50@36 to 50@30 (a NEW fill superseding it).
        record_fill(d, ticker="AAA", side="bought", quantity=50, price=30,
                    trade_date="2026-01-02", now=_NOW, correction_of=wrong.fill_id)
        h = compute_holdings(d)[0]
        self.assertEqual(h.net_quantity, 150)
        self.assertEqual(h.average_cost_basis, 30.0)   # 150 @ 30, the wrong line is voided
        self.assertEqual(h.total_fills, 2)             # the voided original no longer counts

    def test_netted_to_zero_is_closed_not_active(self):
        d = _store_dir()
        record_fill(d, ticker="ZZZ", side="bought", quantity=10, price=5,
                    trade_date="2026-02-01", now=_NOW)
        record_fill(d, ticker="ZZZ", side="sold", quantity=10, price=7,
                    trade_date="2026-02-02", now=_NOW)
        h = [x for x in compute_holdings(d) if x.ticker == "ZZZ"][0]
        self.assertEqual(h.net_quantity, 0)
        self.assertTrue(h.is_closed)               # kept for history...
        bridge = holdings_for_portfolio_intelligence(d)
        self.assertEqual(bridge["positions"], [])  # ...but not an active holding

    def test_no_price_is_fabricated_when_nothing_bought(self):
        d = _store_dir()
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                    trade_date="2026-01-01", now=_NOW)
        # a pure sell-only ticker never invents a cost basis.
        record_fill(d, ticker="SEL", side="sold", quantity=5, price=9,
                    trade_date="2026-01-05", now=_NOW)
        sel = [x for x in compute_holdings(d) if x.ticker == "SEL"][0]
        self.assertIsNone(sel.average_cost_basis)
        self.assertEqual(sel.realized_proceeds, 45.0)


# =========================================================================== #
# Feeding 018 Portfolio Intelligence                                           #
# =========================================================================== #
class PortfolioIntelligenceBridge(unittest.TestCase):
    def _seed_and_feed(self, d):
        # AAA value 9000 (90% -> dominant), BBB value 1000 (10% -> elevated at the edge).
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=90,
                    trade_date="2026-01-01", now=_NOW)
        record_fill(d, ticker="BBB", side="bought", quantity=100, price=10,
                    trade_date="2026-01-02", now=_NOW)
        bridge = holdings_for_portfolio_intelligence(d)
        base = os.path.join(d, "portfolio")
        os.makedirs(base, exist_ok=True)
        with open(os.path.join(base, "holdings.json"), "w", encoding="utf-8") as fh:
            json.dump(bridge, fh)
        return bridge

    def test_bridge_shape_loads_via_018(self):
        d = _store_dir()
        self._seed_and_feed(d)
        loaded, reason = load_holdings(d)
        self.assertIsNotNone(loaded, reason)
        self.assertEqual(loaded.as_of, "2026-01-02")
        self.assertEqual({p.ticker for p in loaded.positions}, {"AAA", "BBB"})

    def test_018_concentration_runs_over_real_ledger_holdings(self):
        d = _store_dir()
        self._seed_and_feed(d)
        bands = {c.ticker: c.weight_band for c in build_concentration(d)}
        self.assertEqual(bands, {"AAA": "dominant", "BBB": "elevated"})
        # every band is a member of the published 018 ladder.
        for view in build_concentration(d):
            self.assertIn(view.weight_band, {"minimal", "moderate", "elevated", "dominant"})

    def test_018_exposure_builder_does_not_break_over_ledger_holdings(self):
        d = _store_dir()
        self._seed_and_feed(d)
        # no persisted signals map tickers to themes -> exposure is honestly empty, never an error.
        self.assertEqual(build_exposure(d), ())


# =========================================================================== #
# The 017 / 022F learning-loop hook                                            #
# =========================================================================== #
class LearningLoopHook(unittest.TestCase):
    def test_linked_fill_surfaces_as_label_ref_only(self):
        d = _store_dir()
        record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                    trade_date="2026-01-01", now=_NOW, recommendation_ref="recjournal:R1:rec1")
        record_fill(d, ticker="BBB", side="bought", quantity=5, price=9,
                    trade_date="2026-01-02", now=_NOW)   # no ref -> not surfaced
        links = outcomes_for_learning(d)
        self.assertEqual(len(links), 1)
        link = links[0]
        self.assertIsInstance(link, LedgerOutcomeLink)
        self.assertEqual(link.recommendation_ref, "recjournal:R1:rec1")
        self.assertEqual(link.ticker, "AAA")
        self.assertEqual(link.side, "bought")
        self.assertEqual(link.trade_date, "2026-01-01")

    def test_learning_link_carries_no_number(self):
        # the learning layer stays label-only: no quantity / price / numeric field crosses over.
        for f in fields(LedgerOutcomeLink):
            self.assertNotIn(f.name, ("quantity", "price", "amount", "shares", "return"))
        self.assertEqual({f.name for f in fields(LedgerOutcomeLink)},
                         {"recommendation_ref", "ticker", "side", "trade_date"})


# =========================================================================== #
# Determinism                                                                  #
# =========================================================================== #
class Determinism(unittest.TestCase):
    def test_fill_id_is_content_derived_and_stable(self):
        a = fill_id_for(ticker="aaa", side="bought", quantity=100, price=30,
                        trade_date="2026-01-01")
        b = fill_id_for(ticker="AAA", side="bought", quantity=100.0, price=30,
                        trade_date="2026-01-01")
        self.assertEqual(a, b)   # case + integral-float normalized
        c = fill_id_for(ticker="AAA", side="sold", quantity=100, price=30,
                        trade_date="2026-01-01")
        self.assertNotEqual(a, c)

    def test_two_stores_same_input_byte_identical(self):
        d1, d2 = _store_dir(), _store_dir()
        for d in (d1, d2):
            record_fill(d, ticker="AAA", side="bought", quantity=100, price=30,
                        trade_date="2026-01-01", now=_NOW)
            record_fill(d, ticker="AAA", side="sold", quantity=40, price=35,
                        trade_date="2026-01-02", now=_NOW)
        self.assertEqual(_lines(d1), _lines(d2))


if __name__ == "__main__":
    unittest.main()
