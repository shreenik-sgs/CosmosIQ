"""UNIVERSE-DISCOVERY UD-4 -- the DYNAMIC theme graph from the operator-accepted universe (OFFLINE).

ADDITIVE + HONESTY-CRITICAL. The operator-accepted, evidence-grounded universe (UD-3) becomes the
watchlist AND the theme graph that drives discovery + the diligence lineage -- WITHOUT ever
fabricating a theme, a company, or a value-chain / chokepoint analysis. Runs entirely OFFLINE under
a socket kill-switch -- no network, no scheduler, no broker, no wall clock; acceptances use real
UD-1-shaped grounding refs so no grounding transport is exercised. Proves:

* :func:`build_accepted_theme_graph` monitored_tickers == EXACTLY the accepted tickers; an accepted
  seed theme reuses the theme's REAL bottleneck(s) (resolves via ``_theme_refs_for`` to the real
  theme); an accepted NEW theme gets a NEUTRAL operator scaffold (``is_chokepoint=False``, no
  invented chokepoint rationale), clearly operator-defined;
* an EMPTY accepted universe -> a graph with 0 monitored tickers (NEVER the seed fallback);
* :func:`run_lineage_on_accepted_universe` preserves lineage honesty end-to-end: a graph-connected
  accepted ticker WITH real evidence reaches AT MOST ``ineligible_missing_diligence`` (never
  eligible); an accepted ticker WITHOUT evidence stays ``blocked_insufficient_evidence``;
* ADDITIVE: :func:`build_seed_theme_graph` is byte-identical, a default
  ``run_diligence_lineage(graph=None)`` is unchanged, and the dynamic graph is referentially whole;
* the accepted-graph provenance side-map is honest; no trade / score field anywhere.
"""

from __future__ import annotations

import copy
import os
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from reality_mesh import (
    accept_universe_entry,
    accepted_graph_provenance,
    accepted_watchlist,
    build_accepted_theme_graph,
    build_seed_theme_graph,
    run_diligence_lineage,
    run_lineage_on_accepted_universe,
)
from reality_mesh.discovery import _theme_refs_for
from reality_mesh.dynamic_universe import OPERATOR_MEMBERSHIP_LABEL
from reality_mesh.models import RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import EventStore, RunStore, SignalStore

_NOW = "2026-07-15T12:00:00Z"


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline UD-4 tests")


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG


def _accept(store, ticker, theme_id, theme_label, *, ref="sec:fts/0001-26-1"):
    """Accept a ticker with a REAL UD-1-shaped grounding ref -> canonical, offline (no transport)."""
    return accept_universe_entry(
        store, ticker=ticker, theme_id=theme_id, theme_label=theme_label,
        accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
        grounding_refs=(ref,))


def _seed_run(store, *, run_id="RUN-UD4", watchlist=(), signals=(), events=(), dq="healthy"):
    RunStore(store).append(
        PulseRun(run_id=run_id, started_at="2026-07-15T10:00:00",
                 completed_at="2026-07-15T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=tuple(watchlist), themes=("optical-networking",),
                 data_quality_status=dq),
        run_id=run_id, timestamp="2026-07-15T10:00:05")
    for sig in signals:
        SignalStore(store).append(sig, run_id=run_id, timestamp="2026-07-15T10:00:05")
    for ev in events:
        EventStore(store).append(ev, run_id=run_id, timestamp="2026-07-15T10:00:05")
    return run_id


# A real (non-social) fused signal + canonical SEC event for COHR (a graph-connected optics ticker).
_COHR_SIGNAL = RealitySignal(
    signal_id="sig-cohr-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("COHR",), affected_themes=("optics",),
    direction_label="improving", magnitude_label="major", confidence_label="high",
    corroboration_status="corroborated", evidence_refs=("ev-cohr-1",),
    source_refs=("sec:cohr:0001",))
_COHR_EVENT = RealityEvent(
    event_id="E-cohr-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("COHR",),
    source_refs=("sec:cohr:0001",), evidence_refs=("ev-cohr-1",))


# =========================================================================== #
# A. Mapping: seed-theme reuse vs neutral new-theme scaffold                     #
# =========================================================================== #
class MappingTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ud4_map_")
        _accept(self.store, "COHR", "optics", "Datacenter Optics")
        _accept(self.store, "LITE", "optics", "Datacenter Optics")
        _accept(self.store, "QBIT", "quantum-sensing", "Quantum Sensing")
        self.graph = build_accepted_theme_graph(self.store)

    def test_monitored_tickers_are_exactly_the_accepted_tickers(self):
        self.assertEqual(set(self.graph.monitored_tickers), {"COHR", "LITE", "QBIT"})
        self.assertEqual(accepted_watchlist(self.store), ("COHR", "LITE", "QBIT"))

    def test_seed_theme_ticker_resolves_to_the_real_theme(self):
        for ticker in ("COHR", "LITE"):
            node = self.graph.company(ticker)
            themes = _theme_refs_for(self.graph, node.linked_bottleneck_refs)
            self.assertEqual(themes, ("optics",))            # the REAL seed theme
            # it links to a REAL seed bottleneck (reused, not invented)
            self.assertIn("bn-transceiver", node.linked_bottleneck_refs)

    def test_new_theme_ticker_resolves_to_a_neutral_operator_scaffold(self):
        node = self.graph.company("QBIT")
        themes = _theme_refs_for(self.graph, node.linked_bottleneck_refs)
        self.assertEqual(themes, ("quantum-sensing",))
        # the scaffold bottleneck is NEUTRAL -- not a chokepoint, operator-defined labelled.
        bns = {b.bottleneck_id: b for b in self.graph.bottlenecks}
        for ref in node.linked_bottleneck_refs:
            bn = bns[ref]
            self.assertFalse(bn.is_chokepoint)
            self.assertEqual(bn.name, OPERATOR_MEMBERSHIP_LABEL)

    def test_graph_is_referentially_whole(self):
        # constructing the ThemeGraph would have raised on any dangling ref; re-affirm it built.
        self.assertTrue(self.graph.value_chains and self.graph.bottlenecks)

    def test_deterministic_build(self):
        self.assertEqual(build_accepted_theme_graph(self.store),
                         build_accepted_theme_graph(self.store))

    def test_a_ticker_accepted_under_two_themes_is_one_monitored_node(self):
        _accept(self.store, "COHR", "grid-equipment", "Grid Equipment")
        g = build_accepted_theme_graph(self.store)
        self.assertEqual(g.monitored_tickers.count("COHR"), 1)
        themes = _theme_refs_for(g, g.company("COHR").linked_bottleneck_refs)
        self.assertIn("optics", themes)
        self.assertIn("grid-equipment", themes)              # both real themes merged


# =========================================================================== #
# B. Empty accepted universe -> 0 monitored tickers (never the seed fallback)    #
# =========================================================================== #
class EmptyUniverseTests(unittest.TestCase):
    def test_empty_universe_is_an_empty_honest_graph(self):
        store = tempfile.mkdtemp(prefix="ud4_empty_")
        g = build_accepted_theme_graph(store)
        self.assertEqual(g.monitored_tickers, ())
        self.assertEqual(g.themes, ())                       # NOT the seed fallback
        self.assertEqual(accepted_watchlist(store), ())

    def test_empty_universe_is_not_the_seed_graph(self):
        store = tempfile.mkdtemp(prefix="ud4_empty2_")
        self.assertNotEqual(build_accepted_theme_graph(store), build_seed_theme_graph())


# =========================================================================== #
# C. Lineage honesty preserved end-to-end over the DYNAMIC graph                 #
# =========================================================================== #
class LineageHonestyTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="ud4_lineage_")
        _accept(self.store, "COHR", "optics", "Datacenter Optics")   # graph-connected + evidence
        _accept(self.store, "GEV", "grid-equipment", "Grid Equipment")  # connected, NO evidence
        self.run_id = _seed_run(
            self.store, watchlist=("COHR", "GEV"),
            signals=(_COHR_SIGNAL,), events=(_COHR_EVENT,))
        self.result = run_lineage_on_accepted_universe(
            self.store, run_id=self.run_id, now=_NOW)

    def _find(self, ticker):
        return next(o for o in self.result.outcomes if o.ticker == ticker)

    def test_only_accepted_tickers_are_assessed(self):
        self.assertEqual({o.ticker for o in self.result.outcomes}, {"COHR", "GEV"})

    def test_evidenced_connected_ticker_reaches_at_most_missing_diligence(self):
        cohr = self._find("COHR")
        self.assertEqual(cohr.discovery_state, "diligence_candidate")
        self.assertEqual(cohr.candidate_state, "ineligible_missing_diligence")
        self.assertNotEqual(cohr.candidate_state, "eligible")
        self.assertEqual(cohr.investment_diligence_ref, "")  # honestly empty -- never fabricated

    def test_accepted_ticker_without_evidence_stays_blocked(self):
        gev = self._find("GEV")
        self.assertEqual(gev.discovery_state, "blocked_insufficient_evidence")
        self.assertEqual(gev.candidate_state, "")            # no capital standing assembled

    def test_nothing_is_forced_eligible(self):
        self.assertFalse(any(o.candidate_state == "eligible" for o in self.result.outcomes))

    def test_failed_dq_run_never_promotes(self):
        store = tempfile.mkdtemp(prefix="ud4_dqfail_")
        _accept(store, "COHR", "optics", "Datacenter Optics")
        rid = _seed_run(store, run_id="RUN-FAIL", watchlist=("COHR",),
                        signals=(_COHR_SIGNAL,), events=(_COHR_EVENT,), dq="failed")
        result = run_lineage_on_accepted_universe(store, run_id=rid, now=_NOW)
        cohr = next(o for o in result.outcomes if o.ticker == "COHR")
        self.assertEqual(cohr.discovery_state, "blocked_dq_failed")
        self.assertNotEqual(cohr.candidate_state, "eligible")


# =========================================================================== #
# D. ADDITIVE: seed byte-identical; default lineage unchanged                    #
# =========================================================================== #
class AdditiveTests(unittest.TestCase):
    def test_seed_graph_is_byte_identical(self):
        a = build_seed_theme_graph()
        b = build_seed_theme_graph()
        self.assertEqual(a, b)
        # building the dynamic graph does NOT mutate the seed it derives from.
        store = tempfile.mkdtemp(prefix="ud4_add_")
        _accept(store, "COHR", "optics", "Datacenter Optics")
        before = copy.deepcopy(build_seed_theme_graph())
        build_accepted_theme_graph(store)
        self.assertEqual(build_seed_theme_graph(), before)

    def test_default_run_diligence_lineage_graph_none_unchanged(self):
        # A default lineage over the SEED graph (graph=None) is unaffected by UD-4 -- the seed
        # optics ticker COHR still reaches the honest slice ceiling.
        store = tempfile.mkdtemp(prefix="ud4_default_")
        _seed_run(store, run_id="RUN-DEF", watchlist=("COHR", "IREN"),
                  signals=(_COHR_SIGNAL,), events=(_COHR_EVENT,))
        result = run_diligence_lineage(
            store, run_id="RUN-DEF", watchlist=("COHR", "IREN"), now=_NOW)
        cohr = next(o for o in result.outcomes if o.ticker == "COHR")
        iren = next(o for o in result.outcomes if o.ticker == "IREN")
        self.assertEqual(cohr.candidate_state, "ineligible_missing_diligence")
        self.assertEqual(iren.discovery_state, "blocked_insufficient_evidence")

    def test_explicit_base_is_reused_not_seed(self):
        # passing a custom base is honoured (the builder never silently swaps in the seed).
        store = tempfile.mkdtemp(prefix="ud4_base_")
        _accept(store, "COHR", "optics", "Datacenter Optics")
        g = build_accepted_theme_graph(store, base=build_seed_theme_graph())
        self.assertIn("COHR", g.monitored_tickers)


# =========================================================================== #
# E. Provenance side-map is honest                                              #
# =========================================================================== #
class ProvenanceTests(unittest.TestCase):
    def test_provenance_carries_authority_refs_and_operator_flag(self):
        store = tempfile.mkdtemp(prefix="ud4_prov_")
        _accept(store, "COHR", "optics", "Datacenter Optics")
        _accept(store, "QBIT", "quantum-sensing", "Quantum Sensing")
        prov = accepted_graph_provenance(store)
        self.assertEqual(prov["COHR"]["source_authority"], "canonical")
        self.assertTrue(prov["COHR"]["source_refs"])
        self.assertFalse(prov["COHR"]["operator_defined_themes"])   # real seed theme
        self.assertTrue(prov["QBIT"]["operator_defined_themes"])    # scaffold theme


if __name__ == "__main__":
    unittest.main()
