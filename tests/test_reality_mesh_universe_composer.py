"""UNIVERSE-DISCOVERY UD-5 -- the engine composes its own universe (OFFLINE, mocked transports).

Proves ADR-0011 where it is easiest to get wrong:

* the engine ACCEPTS on its own, and SIGNS as itself -- never with a person's name;
* the evidence gate is untouched by autonomy: it refuses the engine exactly as it refuses a person;
* the BOUND is occupancy, not mention -- a company that NAMES a chokepoint but supplies none of its
  capacity (a customer: Ford ships ADAS, Ford does not gate ADAS) is DECLINED and recorded, not
  admitted and not silently dropped;
* the mandate stays a mandate: a ticker pasted into it is refused, so the file cannot rot back into
  the hand-typed watchlist ADR-0011 ended;
* a sweep never re-admits what the universe already holds.

Fully OFFLINE: every payload arrives through an injected mock transport.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh.accepted_universe import accepted_universe          # noqa: E402
from reality_mesh.dynamic_universe import accepted_watchlist          # noqa: E402
from reality_mesh.universe_composer import (                          # noqa: E402
    compose_universe,
    engine_principal,
)
from reality_mesh.universe_mandate import (                           # noqa: E402
    MandateEntry,
    chokepoint_mandates,
    validate_mandate,
)

_NOW = "2026-07-16T12:00:00Z"

# OCCU supplies the capacity (it is in the occupant industry). CUST merely talks about it.
_OCCUPANT = "OCCU"
_CUSTOMER = "CUST"


def _mandate(**kw):
    base = dict(bottleneck_id="bn-test", bottleneck_name="Test chokepoint", theme_id="t-test",
                theme_name="Test Theme", phrases=("some scarce capacity",),
                occupant_industries=("Semiconductors",))
    base.update(kw)
    return (MandateEntry(**base),)


def _sec_bundle():
    """Both companies' filings discuss the chokepoint -- a MENTION each, nothing more."""
    def _search(query, forms=()):
        return {"hits": {"total": {"value": 2}, "hits": [
            {"_id": "0000000111-26-000001:d10k.htm",
             "_source": {"ciks": ["111"], "adsh": "0000000111-26-000001",
                         "display_names": ["Occupant Inc (OCCU) (CIK 0000000111)"],
                         "form": "10-K", "file_date": "2026-06-30"}},
            {"_id": "0000000222-26-000002:d10k.htm",
             "_source": {"ciks": ["222"], "adsh": "0000000222-26-000002",
                         "display_names": ["Customer Co (CUST) (CIK 0000000222)"],
                         "form": "10-K", "file_date": "2026-06-30"}},
        ]}}

    def _company_tickers():
        return {"0": {"cik_str": 111, "ticker": _OCCUPANT, "title": "Occupant Inc"},
                "1": {"cik_str": 222, "ticker": _CUSTOMER, "title": "Customer Co"}}

    return {"search": _search, "company_tickers": _company_tickers}


def _fmp_screen(rows=None):
    """Only OCCU is in the occupant industry -- CUST is not, whatever its filing says."""
    def _screen(*, sector="", industry="", market_cap_min=None, limit=50):
        if rows is not None:
            return rows
        return [{"symbol": _OCCUPANT, "companyName": "Occupant Inc", "sector": "Technology",
                 "industry": "Semiconductors", "marketCap": 1000000000}]
    return _screen


def _compose(store, **kw):
    kw.setdefault("mandates", _mandate())
    kw.setdefault("sec_transport", _sec_bundle())
    kw.setdefault("fmp_transport", _fmp_screen())
    return compose_universe(store, now=_NOW, **kw)


class MandateStaysAMandate(unittest.TestCase):
    def test_a_ticker_in_the_mandate_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            validate_mandate({"bn-x": {"phrases": ("NVDA",),
                                       "occupant_industries": ("Semiconductors",)}})
        self.assertIn("TICKER", str(ctx.exception))

    def test_a_mandate_without_occupant_industries_is_refused(self):
        # Without the occupancy half a MENTION would admit -- the exact bug this bound fixes.
        with self.assertRaises(ValueError) as ctx:
            validate_mandate({"bn-x": {"phrases": ("advanced packaging",),
                                       "occupant_industries": ()}})
        self.assertIn("occupant industry", str(ctx.exception))

    def test_every_mandated_chokepoint_is_real_and_has_occupants(self):
        entries = chokepoint_mandates()
        self.assertTrue(entries, "the seed map's chokepoints must be mandated")
        for entry in entries:
            self.assertTrue(entry.phrases, entry.bottleneck_id)
            self.assertTrue(entry.occupant_industries, entry.bottleneck_id)
            self.assertTrue(entry.theme_id, entry.bottleneck_id)


class TheEngineSignsAsItself(unittest.TestCase):
    def test_accepted_entries_carry_the_engine_principal_not_a_person(self):
        with tempfile.TemporaryDirectory() as d:
            result = _compose(d)
            self.assertTrue(result.accepted, "the occupant should have been admitted")
            for entry in result.accepted:
                self.assertEqual(entry.accepted_by_kind, "engine")
                self.assertEqual(entry.accepted_by, engine_principal())
                self.assertTrue(entry.accepted_by.startswith("cosmosiq-engine/"))
                # the signature names the POLICY, so the store says which rule admitted it
                self.assertIn("ud5-chokepoint", entry.accepted_by)

    def test_the_evidence_gate_still_applies_to_the_engine(self):
        # Every admitted entry carries REAL grounding refs and a real authority -- autonomy
        # removed the human from the decision, not the evidence from the record.
        with tempfile.TemporaryDirectory() as d:
            for entry in _compose(d).accepted:
                self.assertTrue(entry.source_refs)
                self.assertIn(entry.source_authority, ("canonical", "convenience", "manual"))
                self.assertNotEqual(entry.source_authority, "ai_suggestion")

    def test_a_sweep_reads_no_clock(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                compose_universe(d, now="", mandates=_mandate())


class TheBoundIsOccupancyNotMention(unittest.TestCase):
    def test_a_company_that_only_mentions_the_chokepoint_is_declined(self):
        with tempfile.TemporaryDirectory() as d:
            result = _compose(d)
            self.assertIn(_OCCUPANT, result.tickers)
            self.assertNotIn(_CUSTOMER, result.tickers,
                             "a customer of the capacity must never be admitted as its gatekeeper")

    def test_the_declined_company_is_recorded_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            declined = _compose(d).occupancy_not_established
            self.assertTrue(any(_CUSTOMER in row for row in declined),
                            "the pool considered and declined is part of the record")

    def test_no_occupancy_pool_admits_nobody_rather_than_everybody(self):
        # If the occupancy screen yields nothing, the honest failure is an EMPTY universe -- never
        # a fallback to "admit whoever mentioned it".
        with tempfile.TemporaryDirectory() as d:
            result = _compose(d, fmp_transport=_fmp_screen(rows=[]))
            self.assertEqual(result.accepted, ())
            self.assertTrue(any("not occupancy" in g or "admitting nothing" in g
                                for g in result.data_gaps))


class ASweepIsRepeatable(unittest.TestCase):
    def test_a_second_sweep_does_not_readmit_the_same_company(self):
        with tempfile.TemporaryDirectory() as d:
            first = _compose(d)
            second = _compose(d)
            self.assertTrue(first.accepted)
            self.assertEqual(second.accepted, (), "the universe must not gain duplicates")
            self.assertIn(_OCCUPANT, second.already_present)
            self.assertEqual(len(accepted_universe(d)), len(first.accepted))

    def test_the_composed_universe_is_what_the_watchlist_resolves_to(self):
        # This is the whole point: the service's scope now comes from what the engine composed.
        with tempfile.TemporaryDirectory() as d:
            result = _compose(d)
            self.assertEqual(set(accepted_watchlist(d)), set(result.tickers))


if __name__ == "__main__":
    unittest.main()
