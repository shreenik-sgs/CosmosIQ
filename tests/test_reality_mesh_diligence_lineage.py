"""DILIGENCE-LINEAGE (slice 1) -- the end-to-end discovery -> hypothesis -> candidate pass.

INFRASTRUCTURE ONLY. Runs entirely OFFLINE under a socket kill-switch -- no network, no
scheduler, no broker, no live endpoint, no wall clock. Proves the orchestration ONLY composes
the already-built stages and reports each ticker's HONEST state:

* a GRAPH-CONNECTED, real-evidence-corroborated ticker (COHR) with healthy DQ becomes a
  ``diligence_candidate`` AND is assembled into a :class:`CapitalCandidate` whose honest state is
  ``ineligible_missing_diligence`` -- the slice-1 ceiling -- with REAL refs (its fused-signal refs
  resolve in the SignalStore; its opportunity-hypothesis ref is the run's real Sphurana packet id).
  It is NEVER ``eligible`` (no accepted diligence thesis exists);
* a GRAPH-UNCONNECTED ticker (IREN) is ``blocked_insufficient_evidence`` and reaches NO
  CapitalCandidate -- honest, not a bug;
* a FAILED-DQ run yields ``blocked_dq_failed`` in discovery and, for any diligence candidate,
  ``ineligible_dq_failed`` -- never a promoted candidate off a failed run;
* NO outcome is ever ``eligible`` in slice 1 (the unforgeable ceiling holds); NO ref is
  fabricated; deterministic given the injected ``now``; offline.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from reality_mesh import run_diligence_lineage
from reality_mesh.capital_candidate import CapitalCandidateStore, published_candidates
from reality_mesh.models import RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.sphurana import ThemePulseSynthesizer
from reality_mesh.stores import EventStore, RunStore, SignalStore

_NOW = "2026-07-06T12:00:00Z"

# A real (non-social) fused signal for COHR (a graph-connected optics ticker). It carries the
# affected_theme 'optics' so the 012F synthesizer produces a hypothesis naming COHR -- the honest
# link, never a fabricated one.
_COHR_SIGNAL = RealitySignal(
    signal_id="sig-cohr-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("COHR",), affected_themes=("optics",),
    direction_label="improving", magnitude_label="major", confidence_label="high",
    corroboration_status="corroborated", evidence_refs=("ev-cohr-1",),
    source_refs=("sec:cohr:0001",))

# A canonical SEC filing for COHR (extra real corroboration -- non-social).
_COHR_EVENT = RealityEvent(
    event_id="E-cohr-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("COHR",),
    source_refs=("sec:cohr:0001",), evidence_refs=("ev-cohr-1",))

# A real signal for IREN -- a ticker that is NOT in the seed theme graph (so it must come out
# blocked_insufficient_evidence, honestly).
_IREN_SIGNAL = RealitySignal(
    signal_id="sig-iren-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("IREN",), direction_label="improving", magnitude_label="minor")


def _boom_socket(*a, **k):
    raise AssertionError("network access attempted during the offline lineage tests")


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = _boom_socket


def tearDownModule():
    socket.socket.connect = _ORIG


def _seed(store_dir, *, dq="healthy", run_id="RUN-L", watchlist=("COHR", "IREN"),
          signals=(_COHR_SIGNAL,), events=(_COHR_EVENT,)):
    RunStore(store_dir).append(
        PulseRun(run_id=run_id, started_at="2026-07-06T10:00:00",
                 completed_at="2026-07-06T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=tuple(watchlist), themes=("optical-networking",),
                 data_quality_status=dq),
        run_id=run_id, timestamp="2026-07-06T10:00:05")
    for sig in signals:
        SignalStore(store_dir).append(sig, run_id=run_id, timestamp="2026-07-06T10:00:05")
    for ev in events:
        EventStore(store_dir).append(ev, run_id=run_id, timestamp="2026-07-06T10:00:05")
    return run_id


def _outcome(result, ticker):
    return next(o for o in result.outcomes if o.ticker == ticker)


# =========================================================================== #
# A. Graph-connected + corroborated -> diligence_candidate -> missing_diligence #
# =========================================================================== #
class GraphConnectedTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="lineage_ok_")
        self.run_id = _seed(self.store)
        self.result = run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("COHR", "IREN"), now=_NOW)

    def test_cohr_is_a_diligence_candidate(self):
        cohr = next(d for d in self.result.discovery_candidates if d.ticker == "COHR")
        self.assertEqual(cohr.discovery_state, "diligence_candidate")
        self.assertIn("theme_relevant", cohr.factor_flags)

    def test_cohr_capital_candidate_is_ineligible_missing_diligence_not_eligible(self):
        cands = [c for c in self.result.capital_candidates if c.ticker == "COHR"]
        self.assertEqual(len(cands), 1)
        cand = cands[0]
        self.assertEqual(cand.candidate_state, "ineligible_missing_diligence")
        self.assertNotEqual(cand.candidate_state, "eligible")
        self.assertFalse(cand.is_eligible)
        # the diligence ref is HONESTLY empty in slice 1 -- never fabricated.
        self.assertEqual(cand.investment_diligence_ref, "")

    def test_cohr_refs_are_real_and_resolve_in_the_stores(self):
        cand = next(c for c in self.result.capital_candidates if c.ticker == "COHR")
        # the fused-signal refs resolve in the SignalStore for this run.
        stored_ids = {s.signal_id for s in SignalStore(self.store).query(run_id=self.run_id)}
        self.assertTrue(cand.reality_signal_refs)
        for ref in cand.reality_signal_refs:
            self.assertIn(ref, stored_ids)
        # the opportunity-hypothesis ref is the run's REAL Sphurana packet naming COHR.
        self.assertTrue(cand.opportunity_hypothesis_ref)
        sph = ThemePulseSynthesizer().synthesize(
            signals=tuple(SignalStore(self.store).query(run_id=self.run_id)), now=_NOW)
        packet_ids = {h.hypothesis_id for h in sph.hypotheses}
        self.assertIn(cand.opportunity_hypothesis_ref, packet_ids)
        linked = next(h for h in sph.hypotheses
                      if h.hypothesis_id == cand.opportunity_hypothesis_ref)
        self.assertIn("COHR", linked.beneficiary_candidates)

    def test_cohr_outcome_names_the_exact_missing_link(self):
        out = _outcome(self.result, "COHR")
        self.assertEqual(out.discovery_state, "diligence_candidate")
        self.assertEqual(out.candidate_state, "ineligible_missing_diligence")
        self.assertIn("accepted diligence thesis", out.missing_link)

    def test_persistence_is_append_only_and_idempotent(self):
        # the candidate landed in the append-only 020A store...
        pub = [c for c in published_candidates(self.store) if c.ticker == "COHR"]
        self.assertEqual(len(pub), 1)
        self.assertEqual(pub[0].candidate_state, "ineligible_missing_diligence")
        # ...and a second identical pass writes no new line (content-derived id, idempotent).
        before = len(CapitalCandidateStore(self.store).read_all())
        run_diligence_lineage(self.store, run_id=self.run_id,
                              watchlist=("COHR", "IREN"), now=_NOW)
        after = len(CapitalCandidateStore(self.store).read_all())
        self.assertEqual(before, after)

    def test_diligence_input_stub_recorded_but_not_a_publication(self):
        path = os.path.join(self.store, "diligence_inputs", "COHR.json")
        self.assertTrue(os.path.isfile(path))

    def test_no_outcome_is_eligible_the_ceiling_holds(self):
        for out in self.result.outcomes:
            self.assertNotEqual(out.candidate_state, "eligible")
        for cand in self.result.capital_candidates:
            self.assertFalse(cand.is_eligible)


# =========================================================================== #
# B. Graph-unconnected -> blocked_insufficient_evidence, NO CapitalCandidate    #
# =========================================================================== #
class GraphUnconnectedTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="lineage_unconn_")
        self.run_id = _seed(self.store)
        self.result = run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("COHR", "IREN"), now=_NOW)

    def test_iren_off_graph_and_off_evidence_is_blocked_insufficient_evidence(self):
        # IREN is not in the seed graph and carries no evidence in this run -> the honest
        # "nothing to go on" block. It never reaches a diligence candidate.
        out = _outcome(self.result, "IREN")
        self.assertEqual(out.discovery_state, "blocked_insufficient_evidence")
        self.assertFalse(out.graph_connected)
        self.assertIn("not in the theme graph", out.missing_link)

    def test_iren_reaches_no_capital_candidate(self):
        self.assertEqual([c for c in self.result.capital_candidates if c.ticker == "IREN"], [])
        out = _outcome(self.result, "IREN")
        self.assertEqual(out.candidate_state, "")

    def test_off_graph_ticker_WITH_evidence_is_monitor_only_never_diligence(self):
        # An off-graph ticker that DOES carry real evidence is monitor_only (kept on watch) --
        # the honest state the real live store shows for IREN/AAOI/INOD/OUST. It still reaches
        # NO CapitalCandidate: off-graph never becomes a diligence candidate.
        store = tempfile.mkdtemp(prefix="lineage_monitor_")
        run_id = _seed(store, signals=(_COHR_SIGNAL, _IREN_SIGNAL))
        result = run_diligence_lineage(
            store, run_id=run_id, watchlist=("IREN",), now=_NOW)
        out = _outcome(result, "IREN")
        self.assertEqual(out.discovery_state, "monitor_only")
        self.assertEqual(out.candidate_state, "")
        self.assertEqual([c for c in result.capital_candidates if c.ticker == "IREN"], [])


# =========================================================================== #
# C. Failed / degraded data quality -> honest blocks, never eligible            #
# =========================================================================== #
class DataQualityTests(unittest.TestCase):
    def test_failed_dq_blocks_discovery_and_any_candidate(self):
        store = tempfile.mkdtemp(prefix="lineage_dqfail_")
        run_id = _seed(store, dq="failed")
        result = run_diligence_lineage(
            store, run_id=run_id, watchlist=("COHR", "IREN"), now=_NOW)
        cohr = _outcome(result, "COHR")
        self.assertEqual(cohr.discovery_state, "blocked_dq_failed")
        # a failed-DQ run promotes NO diligence candidate, so no CapitalCandidate is assembled.
        self.assertEqual(result.capital_candidates, ())
        for out in result.outcomes:
            self.assertNotEqual(out.candidate_state, "eligible")

    def test_degraded_dq_never_eligible(self):
        store = tempfile.mkdtemp(prefix="lineage_dqdeg_")
        run_id = _seed(store, dq="degraded")
        result = run_diligence_lineage(
            store, run_id=run_id, watchlist=("COHR",), now=_NOW)
        cohr = _outcome(result, "COHR")
        # degraded DQ still allows discovery (not failed), but a candidate off it is never
        # eligible -- and in slice 1 it is missing_diligence anyway.
        self.assertIn(cohr.discovery_state, ("diligence_candidate", "monitor_only"))
        for out in result.outcomes:
            self.assertNotEqual(out.candidate_state, "eligible")


# =========================================================================== #
# D. Determinism + guards                                                       #
# =========================================================================== #
class DeterminismTests(unittest.TestCase):
    def test_two_runs_same_inputs_produce_equal_outcomes(self):
        s1 = tempfile.mkdtemp(prefix="lineage_det1_")
        s2 = tempfile.mkdtemp(prefix="lineage_det2_")
        r1 = run_diligence_lineage(s1, run_id=_seed(s1), watchlist=("COHR", "IREN"), now=_NOW)
        r2 = run_diligence_lineage(s2, run_id=_seed(s2), watchlist=("COHR", "IREN"), now=_NOW)
        self.assertEqual(r1.outcomes, r2.outcomes)
        self.assertEqual(r1.capital_candidates, r2.capital_candidates)

    def test_unknown_run_raises(self):
        store = tempfile.mkdtemp(prefix="lineage_norun_")
        with self.assertRaises(ValueError):
            run_diligence_lineage(store, run_id="NOPE", watchlist=("COHR",), now=_NOW)

    def test_persist_false_writes_nothing(self):
        store = tempfile.mkdtemp(prefix="lineage_ro_")
        run_id = _seed(store)
        run_diligence_lineage(store, run_id=run_id, watchlist=("COHR", "IREN"),
                              now=_NOW, persist=False)
        self.assertEqual(published_candidates(store), ())
        self.assertFalse(os.path.isdir(os.path.join(store, "diligence_inputs")))


# =========================================================================== #
# E. Slice 1b -- graph theme-enrichment closes the hypothesis gap (honestly)     #
# =========================================================================== #
# A company-level fused signal (financial_inflection / news_filings) carries NO affected_themes,
# so before slice 1b Sphurana grouped it under no theme and formed no hypothesis -> every ticker
# stuck at ineligible_missing_provenance. Slice 1b theme-enriches the signals from the REAL graph
# relationship (company -> bottleneck -> value chain -> theme) so a real hypothesis can form --
# WITHOUT touching direction / polarity, so mixed evidence still yields NO beneficiary.

# OKLO is a graph-connected nuclear-fuel ticker. This POSITIVE signal carries NO affected_themes:
# the enrichment must supply 'nuclear-fuel' from the graph so a hypothesis names OKLO.
_OKLO_POS_SIGNAL = RealitySignal(
    signal_id="sig-oklo-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("OKLO",),                       # NOTE: no affected_themes -- graph supplies it
    direction_label="accelerating", magnitude_label="major", confidence_label="high",
    corroboration_status="corroborated", evidence_refs=("ev-oklo-1",),
    source_refs=("sec:oklo:0001",))

# Same OKLO signal but MIXED direction -- the enrichment must NOT force positivity.
_OKLO_MIXED_SIGNAL = RealitySignal(
    signal_id="sig-oklo-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("OKLO",),
    direction_label="mixed", magnitude_label="major", confidence_label="high",
    corroboration_status="corroborated", evidence_refs=("ev-oklo-1",),
    source_refs=("sec:oklo:0001",))

_OKLO_EVENT = RealityEvent(
    event_id="E-oklo-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("OKLO",),
    source_refs=("sec:oklo:0001",), evidence_refs=("ev-oklo-1",))


class ThemeEnrichmentTests(unittest.TestCase):
    def test_positive_untagged_graph_signal_forms_a_real_hypothesis_and_reaches_missing_diligence(self):
        # The signal carries NO affected_themes; the graph supplies 'nuclear-fuel'. With a POSITIVE
        # direction, Sphurana names OKLO a beneficiary -> a REAL hypothesis ref -> the candidate
        # advances to the slice-1 ceiling (ineligible_missing_diligence), NOT eligible.
        store = tempfile.mkdtemp(prefix="lineage_enrich_pos_")
        run_id = _seed(store, watchlist=("OKLO",),
                       signals=(_OKLO_POS_SIGNAL,), events=(_OKLO_EVENT,))
        result = run_diligence_lineage(
            store, run_id=run_id, watchlist=("OKLO",), now=_NOW)
        out = _outcome(result, "OKLO")
        self.assertEqual(out.discovery_state, "diligence_candidate")
        self.assertEqual(out.candidate_state, "ineligible_missing_diligence")
        self.assertTrue(out.opportunity_hypothesis_ref)          # a REAL packet id, not ""
        # the ceiling still holds: never eligible, diligence ref honestly empty.
        cand = next(c for c in result.capital_candidates if c.ticker == "OKLO")
        self.assertFalse(cand.is_eligible)
        self.assertEqual(cand.investment_diligence_ref, "")

    def test_the_linked_hypothesis_resolves_to_a_real_packet_naming_the_ticker(self):
        store = tempfile.mkdtemp(prefix="lineage_enrich_resolve_")
        run_id = _seed(store, watchlist=("OKLO",),
                       signals=(_OKLO_POS_SIGNAL,), events=(_OKLO_EVENT,))
        result = run_diligence_lineage(
            store, run_id=run_id, watchlist=("OKLO",), now=_NOW)
        cand = next(c for c in result.capital_candidates if c.ticker == "OKLO")
        # the packet must exist among the ENRICHED synthesis and name OKLO as a beneficiary --
        # replicate the module's own enrichment view to resolve it.
        from reality_mesh.diligence_lineage import _enrich_signal_themes
        from reality_mesh.theme_graph import build_seed_theme_graph
        enriched = _enrich_signal_themes(
            tuple(SignalStore(store).query(run_id=run_id)), build_seed_theme_graph())
        sph = ThemePulseSynthesizer().synthesize(signals=enriched, now=_NOW)
        packet = next(h for h in sph.hypotheses
                      if h.hypothesis_id == cand.opportunity_hypothesis_ref)
        self.assertIn("OKLO", packet.beneficiary_candidates)

    def test_mixed_direction_enriched_signal_still_names_no_beneficiary(self):
        # Enrichment adds ONLY the theme; direction stays 'mixed', so Sphurana names NO
        # beneficiary -> no hypothesis links OKLO -> the honest ineligible_missing_provenance.
        store = tempfile.mkdtemp(prefix="lineage_enrich_mixed_")
        run_id = _seed(store, watchlist=("OKLO",),
                       signals=(_OKLO_MIXED_SIGNAL,), events=(_OKLO_EVENT,))
        result = run_diligence_lineage(
            store, run_id=run_id, watchlist=("OKLO",), now=_NOW)
        out = _outcome(result, "OKLO")
        self.assertEqual(out.discovery_state, "diligence_candidate")
        self.assertEqual(out.candidate_state, "ineligible_missing_provenance")
        self.assertEqual(out.opportunity_hypothesis_ref, "")     # NO forced beneficiary
        for o in result.outcomes:
            self.assertNotEqual(o.candidate_state, "eligible")

    def test_off_graph_ticker_gets_no_theme_and_no_hypothesis(self):
        # IREN is not in the seed graph, so enrichment supplies NO theme (never fabricated) and
        # no hypothesis can name it -- even with a POSITIVE direction.
        pos_iren = RealitySignal(
            signal_id="sig-iren-1", signal_type="fused", discipline="financial_inflection",
            affected_companies=("IREN",), direction_label="accelerating",
            magnitude_label="major", confidence_label="high",
            corroboration_status="corroborated", evidence_refs=("ev-iren-1",),
            source_refs=("sec:iren:0001",))
        from reality_mesh.diligence_lineage import _enrich_signal_themes
        from reality_mesh.theme_graph import build_seed_theme_graph
        enriched = _enrich_signal_themes((pos_iren,), build_seed_theme_graph())
        self.assertEqual(enriched[0].affected_themes, ())        # no theme fabricated
        sph = ThemePulseSynthesizer().synthesize(signals=enriched, now=_NOW)
        self.assertEqual(sph.hypotheses, ())

    def test_enrichment_does_not_rewrite_the_persisted_signals(self):
        # The persisted signal must stay theme-less; enrichment is an in-memory view only, and the
        # candidate's reality_signal_refs stay the real, unchanged ids.
        store = tempfile.mkdtemp(prefix="lineage_enrich_nostore_")
        run_id = _seed(store, watchlist=("OKLO",),
                       signals=(_OKLO_POS_SIGNAL,), events=(_OKLO_EVENT,))
        run_diligence_lineage(store, run_id=run_id, watchlist=("OKLO",), now=_NOW)
        stored = SignalStore(store).query(run_id=run_id)
        self.assertEqual(stored[0].affected_themes, ())          # store not rewritten

    def test_enrichment_is_deterministic(self):
        from reality_mesh.diligence_lineage import _enrich_signal_themes
        from reality_mesh.theme_graph import build_seed_theme_graph
        g = build_seed_theme_graph()
        e1 = _enrich_signal_themes((_OKLO_POS_SIGNAL,), g)
        e2 = _enrich_signal_themes((_OKLO_POS_SIGNAL,), g)
        self.assertEqual(e1, e2)
        self.assertEqual(e1[0].affected_themes, ("nuclear-fuel",))
        # two full runs on identical inputs produce identical outcomes.
        s1 = tempfile.mkdtemp(prefix="lineage_enrich_det1_")
        s2 = tempfile.mkdtemp(prefix="lineage_enrich_det2_")
        r1 = run_diligence_lineage(
            s1, run_id=_seed(s1, watchlist=("OKLO",), signals=(_OKLO_POS_SIGNAL,),
                             events=(_OKLO_EVENT,)),
            watchlist=("OKLO",), now=_NOW)
        r2 = run_diligence_lineage(
            s2, run_id=_seed(s2, watchlist=("OKLO",), signals=(_OKLO_POS_SIGNAL,),
                             events=(_OKLO_EVENT,)),
            watchlist=("OKLO",), now=_NOW)
        self.assertEqual(r1.outcomes, r2.outcomes)


if __name__ == "__main__":
    unittest.main()
