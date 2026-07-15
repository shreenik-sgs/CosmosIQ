"""DILIGENCE-LINEAGE (slice 2) -- the OPERATOR diligence-acceptance path to ``eligible``.

INFRASTRUCTURE ONLY. Runs entirely OFFLINE under a socket kill-switch -- no network, no scheduler,
no broker, no live endpoint, no wall clock. Proves the ONLY way a candidate reaches ``eligible`` is
a REAL, persisted, evidence-grounded, OPERATOR-accepted ``thesis_supported`` :class:`InvestmentDiligence`:

* accepting a ``thesis_supported`` thesis for a graph-connected, positive-signal ticker (with a real
  hypothesis + healthy DQ) makes the lineage return that candidate ``eligible``, with
  ``investment_diligence_ref`` = the real diligence_id that RESOLVES in the store;
* a ``thesis_rejected`` / ``insufficient`` thesis leaves it ``ineligible_missing_diligence`` -- never
  eligible;
* acceptance is REFUSED (ValueError) for: a ticker with no opportunity_hypothesis_ref, empty
  evidence_refs, evidence_refs that do not resolve, empty accepted_by, a free-string hypothesis ref;
* a MIXED-direction ticker (no hypothesis) has no path to eligible -- acceptance is refused and the
  candidate stays ineligible_missing_provenance;
* the store is append-only: a correcting record supersedes; the engine NEVER auto-generates a thesis;
* deterministic given the injected ``now``; offline; no trade / score / secret field.
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

from reality_mesh import (
    accept_diligence_thesis,
    run_diligence_lineage,
)
from reality_mesh.investment_diligence import (
    InvestmentDiligence,
    InvestmentDiligenceStore,
    diligence_id_for,
    latest_diligence_for,
)
from reality_mesh.models import RealityEvent, RealitySignal
from reality_mesh.runtime import PulseRun
from reality_mesh.stores import EventStore, RunStore, SignalStore
from reality_mesh.validation import assert_no_trade_fields

_NOW = "2026-07-06T12:00:00Z"

# OKLO is a graph-connected nuclear-fuel ticker; the POSITIVE signal carries no affected_themes so
# the graph enrichment supplies 'nuclear-fuel' and a real hypothesis names OKLO.
_OKLO_POS = RealitySignal(
    signal_id="sig-oklo-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("OKLO",), direction_label="accelerating", magnitude_label="major",
    confidence_label="high", corroboration_status="corroborated", evidence_refs=("ev-oklo-1",),
    source_refs=("sec:oklo:0001",))
_OKLO_MIXED = RealitySignal(
    signal_id="sig-oklo-1", signal_type="fused", discipline="financial_inflection",
    affected_companies=("OKLO",), direction_label="mixed", magnitude_label="major",
    confidence_label="high", corroboration_status="corroborated", evidence_refs=("ev-oklo-1",),
    source_refs=("sec:oklo:0001",))
_OKLO_EVENT = RealityEvent(
    event_id="E-oklo-1", timestamp=_NOW, source_id="src.sec", source_type="sec_filing",
    source_authority="canonical", claim_status="verified_fact", discipline="news_filings",
    event_type="sec_8-k_results_of_operations", affected_companies=("OKLO",),
    source_refs=("sec:oklo:0001",), evidence_refs=("ev-oklo-1",))


def setUpModule():
    global _ORIG
    _ORIG = socket.socket.connect
    socket.socket.connect = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("network attempted during offline slice-2 tests"))


def tearDownModule():
    socket.socket.connect = _ORIG


def _seed(store, *, dq="healthy", signal=_OKLO_POS, run_id="RUN-D"):
    RunStore(store).append(
        PulseRun(run_id=run_id, started_at="2026-07-06T10:00:00",
                 completed_at="2026-07-06T10:00:05", mode="pulse", trigger_type="manual",
                 watchlist=("OKLO",), themes=("nuclear",), data_quality_status=dq),
        run_id=run_id, timestamp="2026-07-06T10:00:05")
    SignalStore(store).append(signal, run_id=run_id, timestamp="2026-07-06T10:00:05")
    EventStore(store).append(_OKLO_EVENT, run_id=run_id, timestamp="2026-07-06T10:00:05")
    return run_id


def _hyp_ref(store, run_id):
    result = run_diligence_lineage(store, run_id=run_id, watchlist=("OKLO",), now=_NOW)
    return next(o for o in result.outcomes if o.ticker == "OKLO").opportunity_hypothesis_ref


# =========================================================================== #
# A. The happy path: a real supporting thesis -> eligible                       #
# =========================================================================== #
class SupportingThesisTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="idil_ok_")
        self.run_id = _seed(self.store)
        self.hyp = _hyp_ref(self.store, self.run_id)

    def test_accepting_a_supporting_thesis_makes_the_candidate_eligible(self):
        self.assertTrue(self.hyp)                                   # a REAL hypothesis exists
        dil = accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="thesis_supported",
            thesis="Nuclear-fuel demand real and corroborated by the filing.",
            key_risks=("regulatory timeline",), evidence_refs=("sig-oklo-1", "ev-oklo-1"),
            accepted_by="operator:sgs", now=_NOW)
        result = run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("OKLO",), now=_NOW)
        out = next(o for o in result.outcomes if o.ticker == "OKLO")
        self.assertEqual(out.candidate_state, "eligible")
        self.assertEqual(out.investment_diligence_ref, dil.diligence_id)
        cand = next(c for c in result.capital_candidates if c.ticker == "OKLO")
        self.assertTrue(cand.is_eligible)

    def test_the_diligence_ref_resolves_in_the_store(self):
        dil = accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="thesis_supported",
            thesis="ok", evidence_refs=("sig-oklo-1",), accepted_by="op", now=_NOW)
        latest = latest_diligence_for(
            self.store, run_id=self.run_id, ticker="OKLO", opportunity_hypothesis_ref=self.hyp)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.diligence_id, dil.diligence_id)
        self.assertIn(dil, InvestmentDiligenceStore(self.store).read_all())

    def test_operator_authority_is_manual_never_canonical(self):
        dil = accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="thesis_supported",
            thesis="ok", evidence_refs=("sig-oklo-1",), accepted_by="op", now=_NOW)
        self.assertEqual(dil.source_authority, "manual")
        with self.assertRaises(ValueError):
            InvestmentDiligence(
                diligence_id="x", ticker="OKLO", run_id=self.run_id,
                opportunity_hypothesis_ref=self.hyp, verdict="thesis_supported",
                thesis="t", evidence_refs=("sig-oklo-1",), accepted_by="op",
                accepted_at=_NOW, source_authority="canonical")


# =========================================================================== #
# B. Non-supporting verdicts stay ineligible; the engine never auto-accepts     #
# =========================================================================== #
class NonSupportingTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="idil_no_")
        self.run_id = _seed(self.store)
        self.hyp = _hyp_ref(self.store, self.run_id)

    def test_rejected_thesis_never_eligible(self):
        accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="thesis_rejected",
            thesis="Guidance does not support it.", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        out = next(o for o in run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out.candidate_state, "ineligible_missing_diligence")

    def test_insufficient_thesis_never_eligible(self):
        accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="insufficient",
            thesis="Not enough to conclude.", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        out = next(o for o in run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out.candidate_state, "ineligible_missing_diligence")

    def test_no_thesis_at_all_stays_missing_diligence(self):
        out = next(o for o in run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out.candidate_state, "ineligible_missing_diligence")
        self.assertEqual(out.investment_diligence_ref, "")


# =========================================================================== #
# C. Acceptance refusals -- an ungrounded / unlinked thesis is honestly refused #
# =========================================================================== #
class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="idil_refuse_")
        self.run_id = _seed(self.store)
        self.hyp = _hyp_ref(self.store, self.run_id)

    def _base(self, **over):
        base = dict(
            ticker="OKLO", run_id=self.run_id, opportunity_hypothesis_ref=self.hyp,
            verdict="thesis_supported", thesis="ok", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        base.update(over)
        return base

    def test_empty_evidence_refs_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(self.store, **self._base(evidence_refs=()))

    def test_unresolved_evidence_refs_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(self.store, **self._base(evidence_refs=("bogus-ref",)))

    def test_empty_accepted_by_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(self.store, **self._base(accepted_by="  "))

    def test_free_string_hypothesis_ref_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(
                self.store, **self._base(opportunity_hypothesis_ref="hyp.fabricated"))

    def test_bad_verdict_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(self.store, **self._base(verdict="thesis_maybe"))

    def test_empty_thesis_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(self.store, **self._base(thesis="   "))

    def test_unknown_run_refused(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(self.store, **self._base(run_id="NOPE"))

    def test_nothing_written_on_a_refused_acceptance(self):
        try:
            accept_diligence_thesis(self.store, **self._base(evidence_refs=("bogus",)))
        except ValueError:
            pass
        self.assertEqual(InvestmentDiligenceStore(self.store).read_all(), ())


# =========================================================================== #
# D. Mixed-direction evidence (no hypothesis) -> no path to eligible            #
# =========================================================================== #
class MixedEvidenceTests(unittest.TestCase):
    def test_mixed_direction_ticker_has_no_hypothesis_and_cannot_be_accepted(self):
        store = tempfile.mkdtemp(prefix="idil_mixed_")
        run_id = _seed(store, signal=_OKLO_MIXED)
        out = next(o for o in run_diligence_lineage(
            store, run_id=run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        # honest: mixed evidence names NO beneficiary -> missing provenance, no hypothesis.
        self.assertEqual(out.candidate_state, "ineligible_missing_provenance")
        self.assertEqual(out.opportunity_hypothesis_ref, "")
        # a thesis for it is REFUSED -- there is no real hypothesis to address.
        with self.assertRaises(ValueError):
            accept_diligence_thesis(
                store, ticker="OKLO", run_id=run_id,
                opportunity_hypothesis_ref="hyp.nuclear-fuel", verdict="thesis_supported",
                thesis="x", evidence_refs=("sig-oklo-1",), accepted_by="op", now=_NOW)
        self.assertEqual(InvestmentDiligenceStore(store).read_all(), ())


# =========================================================================== #
# E. Append-only + correction-not-mutation                                      #
# =========================================================================== #
class AppendOnlyTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="idil_append_")
        self.run_id = _seed(self.store)
        self.hyp = _hyp_ref(self.store, self.run_id)

    def test_store_has_no_update_or_delete(self):
        s = InvestmentDiligenceStore(self.store)
        self.assertFalse(hasattr(s, "update"))
        self.assertFalse(hasattr(s, "delete"))

    def test_a_correction_supersedes_without_mutation(self):
        # accept a rejection first...
        rej = accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="thesis_rejected",
            thesis="initial doubt", evidence_refs=("sig-oklo-1",), accepted_by="op",
            now="2026-07-06T12:00:00Z")
        out1 = next(o for o in run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out1.candidate_state, "ineligible_missing_diligence")
        # ...then a CORRECTING supporting thesis referencing it.
        sup = accept_diligence_thesis(
            self.store, ticker="OKLO", run_id=self.run_id,
            opportunity_hypothesis_ref=self.hyp, verdict="thesis_supported",
            thesis="on review, the filing corroborates it", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now="2026-07-06T13:00:00Z", correction_of=rej.diligence_id)
        # both records persist (append-only); the correction supersedes the rejection.
        records = InvestmentDiligenceStore(self.store).read_all()
        self.assertEqual(len(records), 2)
        self.assertIn(rej, records)                                # prior line byte-unchanged
        latest = latest_diligence_for(
            self.store, run_id=self.run_id, ticker="OKLO", opportunity_hypothesis_ref=self.hyp)
        self.assertEqual(latest.diligence_id, sup.diligence_id)
        out2 = next(o for o in run_diligence_lineage(
            self.store, run_id=self.run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertEqual(out2.candidate_state, "eligible")

    def test_correction_of_must_reference_a_real_prior_record(self):
        with self.assertRaises(ValueError):
            accept_diligence_thesis(
                self.store, ticker="OKLO", run_id=self.run_id,
                opportunity_hypothesis_ref=self.hyp, verdict="thesis_supported",
                thesis="x", evidence_refs=("sig-oklo-1",), accepted_by="op", now=_NOW,
                correction_of="idil:OKLO:deadbeefdeadbeef")

    def test_idempotent_reaccept_writes_no_new_line(self):
        args = dict(
            ticker="OKLO", run_id=self.run_id, opportunity_hypothesis_ref=self.hyp,
            verdict="thesis_supported", thesis="ok", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        accept_diligence_thesis(self.store, **args)
        before = len(InvestmentDiligenceStore(self.store).read_all())
        accept_diligence_thesis(self.store, **args)
        after = len(InvestmentDiligenceStore(self.store).read_all())
        self.assertEqual(before, after)


# =========================================================================== #
# F. Determinism + guards                                                       #
# =========================================================================== #
class GuardTests(unittest.TestCase):
    def test_no_trade_or_score_field_on_the_contract(self):
        assert_no_trade_fields(InvestmentDiligence)

    def test_content_id_is_deterministic(self):
        a = diligence_id_for("R", "OKLO", "hyp.x", _NOW, verdict="thesis_supported",
                             thesis="t", evidence_refs=("e",), accepted_by="op")
        b = diligence_id_for("R", "OKLO", "hyp.x", _NOW, verdict="thesis_supported",
                             thesis="t", evidence_refs=("e",), accepted_by="op")
        self.assertEqual(a, b)

    def test_two_acceptances_same_inputs_produce_equal_records(self):
        s1 = tempfile.mkdtemp(prefix="idil_det1_")
        s2 = tempfile.mkdtemp(prefix="idil_det2_")
        r1 = _seed(s1)
        r2 = _seed(s2)
        h1 = _hyp_ref(s1, r1)
        h2 = _hyp_ref(s2, r2)
        d1 = accept_diligence_thesis(
            s1, ticker="OKLO", run_id=r1, opportunity_hypothesis_ref=h1,
            verdict="thesis_supported", thesis="ok", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        d2 = accept_diligence_thesis(
            s2, ticker="OKLO", run_id=r2, opportunity_hypothesis_ref=h2,
            verdict="thesis_supported", thesis="ok", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        self.assertEqual(d1, d2)

    def test_degraded_dq_with_a_supporting_thesis_is_still_not_eligible(self):
        store = tempfile.mkdtemp(prefix="idil_dq_")
        run_id = _seed(store, dq="degraded")
        hyp = _hyp_ref(store, run_id)
        accept_diligence_thesis(
            store, ticker="OKLO", run_id=run_id, opportunity_hypothesis_ref=hyp,
            verdict="thesis_supported", thesis="ok", evidence_refs=("sig-oklo-1",),
            accepted_by="op", now=_NOW)
        out = next(o for o in run_diligence_lineage(
            store, run_id=run_id, watchlist=("OKLO",), now=_NOW).outcomes
            if o.ticker == "OKLO")
        self.assertNotEqual(out.candidate_state, "eligible")


if __name__ == "__main__":
    unittest.main()
