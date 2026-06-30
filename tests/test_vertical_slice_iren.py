from __future__ import annotations

import os as _os, sys as _sys
_SRC=_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),"src")
if _SRC not in _sys.path:
    _sys.path.insert(0,_SRC)

import unittest

from runtime.vertical_slice_runner import run_iren_slice


class TestVerticalSliceIREN(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_iren_slice()

    def test_first_preview_quantity_about_200(self):
        # intended_allocation 2000 / limit 10.00 -> 200 shares.
        self.assertEqual(self.r.ticket_preview1.quantity, 200)
        self.assertEqual(self.r.ticket_preview1.order_type, "limit")
        self.assertEqual(self.r.ticket_preview1.instrument, "IREN")
        self.assertEqual(self.r.ticket_preview1.intended_allocation, 2000.0)

    def test_stale_revalidation_returns_to_preview(self):
        res = self.r.revalidate_stale
        self.assertEqual(res.status, "return_to_preview")
        self.assertIn("preview_stale", res.reasons)
        self.assertIn("market_moved", res.reasons)

    def test_re_preview_has_new_hash_and_requantified(self):
        p1, p2 = self.r.ticket_preview1, self.r.ticket_preview2
        self.assertEqual(p1.id, p2.id)  # same ticket id (idempotent identity)
        self.assertNotEqual(p1.preview_hash, p2.preview_hash)
        self.assertGreater(p2.version, p1.version)
        # 2000 / 10.40 -> 192 shares.
        self.assertEqual(p2.quantity, 192)
        self.assertAlmostEqual(p2.preview_price, 10.40, places=2)

    def test_fresh_revalidation_ok(self):
        self.assertTrue(self.r.revalidate_ok.ok)

    def test_confirmation_bound_to_new_preview_hash(self):
        confirmed = self.r.ticket_confirmed
        self.assertEqual(confirmed.state, "confirmed")
        self.assertEqual(confirmed.confirmation, self.r.ticket_preview2.preview_hash)

    def test_manual_placement_records_broker_order_id_and_time(self):
        placed = self.r.ticket_placed
        self.assertEqual(placed.state, "placed")
        self.assertEqual(placed.broker_order_id, "IBKR-12345")
        self.assertIsNotNone(placed.placed_at)

    def test_partial_then_full_fill_aggregates_to_filled(self):
        agg = self.r.aggregate
        self.assertEqual(agg.outcome, "filled")
        self.assertEqual(agg.cumulative_filled, 192)
        self.assertAlmostEqual(agg.average_price, 10.39, places=2)

    def test_reconciliation_passes_with_capital_within_tolerance(self):
        recon = self.r.reconciliation
        self.assertTrue(recon.all_reconciled, msg=str(recon.divergences()))
        link8 = next(l for l in recon.links if l.name == "capital_to_intended_allocation")
        self.assertTrue(link8.reconciled)
        # intended 2000 vs actual ~1994.88
        actual = sum(f.quantity * f.price for f in self.r.fills)
        self.assertAlmostEqual(actual, 1994.8, places=1)
        self.assertLess(abs(2000.0 - actual), 10.40)

    def test_audit_trail_contains_required_events(self):
        audit = self.r.audit_trail
        for event in ("stale_detected", "returned_to_preview", "placed_by_user",
                      "partial_fill", "fill_recorded", "reconciled"):
            self.assertTrue(audit.has_event(event), msg="missing event: {0}".format(event))
        placed_event = audit.events_of("placed_by_user")[0]
        self.assertEqual(placed_event.payload["broker_order_id"], "IBKR-12345")

    def test_feedback_observation_binds_ticket_and_fills(self):
        fb = self.r.feedback_observation
        source_ids = {ref.object_id for ref in fb.provenance.sources}
        self.assertIn(self.r.ticket_placed.id, source_ids)
        for f in self.r.fills:
            self.assertIn(f.id, source_ids)

    def test_replay_reconstructs_end_state_without_reactuating(self):
        audit = self.r.audit_trail
        tickets_before = len(self.r.registry)

        state1 = audit.replay()
        state2 = audit.replay()

        # Idempotent: two replays are identical.
        self.assertEqual(state1, state2)
        # No duplicate ticket created; replay does not touch the registry.
        self.assertEqual(len(state1.tickets), 1)
        self.assertEqual(len(self.r.registry), tickets_before)

        tid = self.r.ticket_placed.id
        reconstructed = state1.tickets[tid]
        self.assertEqual(reconstructed["state"], "reconciled")
        self.assertEqual(reconstructed["broker_order_id"], "IBKR-12345")
        self.assertEqual(len(state1.fills), 2)


if __name__ == "__main__":
    unittest.main()
