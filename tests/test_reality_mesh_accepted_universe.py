"""UNIVERSE-DISCOVERY UD-3 -- the operator universe-acceptance store + grounding (OFFLINE).

HONESTY-CRITICAL. Only GROUNDED (real-evidence-backed) entries may be accepted; an unverified AI
suggestion CANNOT enter the universe without grounding against a REAL source; the engine NEVER
auto-accepts. Runs entirely OFFLINE under a socket kill-switch -- no network, no scheduler, no
broker, no live endpoint, no wall clock; the UD-1 grounding transport is mock-injected (the real
network path is never exercised). Proves:

* accepting a ticker grounded by a real-shaped UD-1 discovery (mock transport) persists an
  :class:`AcceptedUniverseEntry` whose source_authority MATCHES the grounding (SEC -> canonical,
  screener -> convenience), records the origin, and is returned by :func:`accepted_universe`;
* an unverified ai_suggestion with NO grounding is REFUSED (ValueError, nothing written); the SAME
  suggestion, once grounded (mock UD-1 resolves the ticker), is accepted with
  ``origin="ai_suggestion_grounded"`` + real provenance + the grounding's authority (never
  ai_suggestion, never canonical-unless-SEC);
* empty accepted_by / unresolved grounding refs / bad origin+verdict are refused;
* the store is append-only and correction supersedes (never a mutation); operator-attributed;
* no trade / score / secret field anywhere; deterministic; it does NOT touch graph / pulse / lineage.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh import (
    AcceptedUniverseEntry,
    AcceptedUniverseStore,
    accept_universe_entry,
    accepted_universe,
    ground_universe_candidate,
)
from reality_mesh.accepted_universe import UNIVERSE_AUTHORITIES, entry_id_for
from reality_mesh.validation import assert_no_trade_fields

_NOW = "2026-07-15T12:00:00Z"

# A stand-in credential VALUE used ONLY to prove it never leaks into any entry / grounding / gap.
_FAKE_CREDENTIAL = "sk-FAKEVALUE-hunter2-000"

_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: UD-3 acceptance + grounding must run fully offline on mock "
            "transports -- the real network path is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


# --------------------------------------------------------------------------- #
# Real-shaped mock UD-1 transports (fixture-shaped; fully offline)               #
# --------------------------------------------------------------------------- #
def _fts_payload_for(ticker, cik, accession):
    return {"hits": {"total": {"value": 1}, "hits": [
        {"_id": "{0}:d10k.htm".format(accession),
         "_source": {"ciks": [str(cik)], "adsh": accession,
                     "display_names": ["{0} Limited ({0}) (CIK {1})".format(ticker, cik)],
                     "form": "10-K", "file_date": "2026-06-30"}},
    ]}}


def _sec_bundle(ticker="IREN", cik="1878848", accession="0001878848-26-000050", *, empty=False):
    def _search(query, forms=()):
        if empty:
            return {"hits": {"total": {"value": 0}, "hits": []}}
        return _fts_payload_for(ticker, cik, accession)

    def _company_tickers():
        return {"0": {"cik_str": int(cik), "ticker": ticker, "title": "{0} Limited".format(ticker)}}

    return {"search": _search, "company_tickers": _company_tickers}


def _fmp_screen(ticker="IREN", *, empty=False):
    def _screen(*, sector="", industry="", market_cap_min=None, limit=50):
        if empty:
            return []
        return [{"symbol": ticker, "companyName": "{0} Limited".format(ticker),
                 "marketCap": 1200000000, "sector": "Technology", "industry": "Semiconductors"}]
    return _screen


def _transport(*, sec_ticker="IREN", fmp_ticker="IREN", sec_empty=False, fmp_empty=False):
    return {"sec": _sec_bundle(ticker=sec_ticker, empty=sec_empty),
            "fmp": _fmp_screen(ticker=fmp_ticker, empty=fmp_empty)}


def _blob(entry):
    parts = [entry.entry_id, entry.ticker, entry.theme_id, entry.theme_label,
             entry.source_authority, entry.grounded_by, entry.origin, entry.accepted_by,
             entry.verdict, entry.note]
    parts.extend(entry.source_refs)
    return " ".join(parts)


# =========================================================================== #
# A. Contract: the frozen entry is honest + trade/score-clean                   #
# =========================================================================== #
class ContractTests(unittest.TestCase):
    def test_entry_is_trade_and_score_clean(self):
        assert_no_trade_fields(AcceptedUniverseEntry)
        names = {f for f in AcceptedUniverseEntry.__dataclass_fields__}
        for banned in ("score", "rank", "rating", "buy", "sell", "order", "trade", "broker"):
            self.assertFalse(any(banned in n.lower() for n in names))

    def test_authority_may_never_be_ai_suggestion(self):
        with self.assertRaises(ValueError):
            AcceptedUniverseEntry(
                entry_id="auni:X:1", ticker="X", theme_id="t", theme_label="T",
                source_refs=("fmp:screener/-/-",), source_authority="ai_suggestion",
                grounded_by="g", origin="evidence_discovery", accepted_by="op",
                accepted_at=_NOW)

    def test_entry_requires_grounding_provenance(self):
        with self.assertRaises(ValueError):     # no source_refs -> ungrounded
            AcceptedUniverseEntry(
                entry_id="auni:X:1", ticker="X", theme_id="t", theme_label="T",
                source_refs=(), source_authority="convenience", grounded_by="g",
                origin="evidence_discovery", accepted_by="op", accepted_at=_NOW)
        with self.assertRaises(ValueError):     # empty accepted_by
            AcceptedUniverseEntry(
                entry_id="auni:X:1", ticker="X", theme_id="t", theme_label="T",
                source_refs=("fmp:screener/-/-",), source_authority="convenience",
                grounded_by="g", origin="evidence_discovery", accepted_by="", accepted_at=_NOW)
        with self.assertRaises(ValueError):     # bad origin
            AcceptedUniverseEntry(
                entry_id="auni:X:1", ticker="X", theme_id="t", theme_label="T",
                source_refs=("fmp:screener/-/-",), source_authority="convenience",
                grounded_by="g", origin="taken_on_faith", accepted_by="op", accepted_at=_NOW)

    def test_entry_id_is_content_derived_from_theme_and_ticker(self):
        a = entry_id_for("physical-ai", "iren", accepted_at=_NOW)
        b = entry_id_for("physical-ai", "IREN", accepted_at=_NOW)
        self.assertEqual(a, b)                                    # ticker up-cased, stable
        self.assertTrue(a.startswith("auni:IREN:"))
        self.assertNotEqual(a, entry_id_for("physical-ai", "IREN", accepted_at=_NOW, note="x"))


# =========================================================================== #
# B. Grounding: UD-1 confirms the ticker is a REAL company (mock transport)      #
# =========================================================================== #
class GroundingTests(unittest.TestCase):
    def test_sec_grounding_is_canonical(self):
        g = ground_universe_candidate(
            ticker="IREN", theme_hint="physical ai",
            transport=_transport(fmp_empty=True), now=_NOW)
        self.assertTrue(g.grounded)
        self.assertEqual(g.source_authority, "canonical")        # SEC filing hit
        self.assertTrue(any(r.startswith("sec:") for r in g.source_refs))
        self.assertEqual(g.checked_at, _NOW)

    def test_screener_only_grounding_is_convenience(self):
        g = ground_universe_candidate(
            ticker="IREN", theme_hint="Technology",
            transport=_transport(sec_empty=True), now=_NOW)
        self.assertTrue(g.grounded)
        self.assertEqual(g.source_authority, "convenience")      # screener row only
        self.assertTrue(any(r.startswith("fmp:screener/") for r in g.source_refs))

    def test_unresolved_ticker_is_an_honest_gap_not_grounded(self):
        g = ground_universe_candidate(
            ticker="GHOST", theme_hint="physical ai",
            transport=_transport(), now=_NOW)                    # transports surface IREN, not GHOST
        self.assertFalse(g.grounded)
        self.assertEqual(g.source_refs, ())
        self.assertTrue(g.data_gaps)

    def test_grounding_is_offline_safe_with_no_transport_and_no_creds(self):
        # transport None + empty env -> credentials_missing gaps, NO network, not grounded.
        g = ground_universe_candidate(
            ticker="IREN", theme_hint="physical ai", env={}, now=_NOW)
        self.assertFalse(g.grounded)


# =========================================================================== #
# C. Acceptance: the ONLY producer; grounded -> honest authority + persisted     #
# =========================================================================== #
class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="auni_ok_")

    def test_accept_grounded_by_sec_is_canonical_and_persisted(self):
        entry = accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            transport=_transport(fmp_empty=True))
        self.assertEqual(entry.source_authority, "canonical")
        self.assertEqual(entry.verdict, "accepted")
        self.assertEqual(entry.accepted_by, "operator:sgs")
        self.assertTrue(any(r.startswith("sec:") for r in entry.source_refs))
        got = accepted_universe(self.store)
        self.assertEqual([e.entry_id for e in got], [entry.entry_id])

    def test_accept_grounded_by_screener_is_convenience(self):
        entry = accept_universe_entry(
            self.store, ticker="IREN", theme_id="tech", theme_label="Technology",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            transport=_transport(sec_empty=True))
        self.assertEqual(entry.source_authority, "convenience")  # never canonical off a screener
        self.assertTrue(any(r.startswith("fmp:screener/") for r in entry.source_refs))

    def test_accept_with_supplied_real_ud1_refs_needs_no_transport(self):
        entry = accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            grounding_refs=("sec:fts/0001878848-26-000050", "sec:cik/0001878848"))
        self.assertEqual(entry.source_authority, "canonical")

    def test_operator_manual_needs_explicit_ref_and_is_manual(self):
        entry = accept_universe_entry(
            self.store, ticker="ACME", theme_id="niche", theme_label="Niche theme",
            accepted_by="operator:sgs", now=_NOW, origin="operator_manual",
            grounding_refs=("operator:my-own-primary-research-note-2026",))
        self.assertEqual(entry.source_authority, "manual")       # never laundered to canonical
        with self.assertRaises(ValueError):                      # no explicit ref -> refused
            accept_universe_entry(
                self.store, ticker="ACME", theme_id="niche", theme_label="Niche theme",
                accepted_by="operator:sgs", now=_NOW, origin="operator_manual")

    def test_rejected_verdict_is_recorded_but_not_in_universe(self):
        accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            verdict="rejected", transport=_transport())
        self.assertEqual(accepted_universe(self.store), ())      # honest: not in the universe
        self.assertEqual(len(AcceptedUniverseStore(self.store).read_all()), 1)  # but persisted

    def test_no_secret_leaks_into_the_entry(self):
        entry = accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            env={"FMP_API_KEY": _FAKE_CREDENTIAL, "SEC_USER_AGENT": "ua"},
            transport=_transport(fmp_empty=True))
        self.assertNotIn(_FAKE_CREDENTIAL, _blob(entry))


# =========================================================================== #
# D. HONESTY-CRITICAL: ungrounded AI suggestion refused; grounded -> accepted    #
# =========================================================================== #
class AiSuggestionGroundingTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="auni_ai_")

    def test_ungrounded_ai_suggestion_is_refused_nothing_written(self):
        # A raw UD-2 lead: no real grounding_refs, and the mock UD-1 does NOT resolve the ticker.
        with self.assertRaises(ValueError):
            accept_universe_entry(
                self.store, ticker="HYPE", theme_id="ai-fad", theme_label="AI Fad",
                accepted_by="operator:sgs", now=_NOW, origin="ai_suggestion_grounded",
                grounding_refs=("ai:suggestion:001",),           # NOT a real UD-1 ref shape
                transport=_transport())                          # resolves IREN only, not HYPE
        self.assertEqual(AcceptedUniverseStore(self.store).read_all(), ())  # nothing written

    def test_same_suggestion_after_grounding_is_accepted_with_honest_authority(self):
        # The SAME lead, now the ticker (IREN) DOES resolve against real UD-1 (mock) -> accepted.
        entry = accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="ai_suggestion_grounded",
            grounding_refs=("ai:suggestion:001",),               # ignored: not real grounding
            transport=_transport(fmp_empty=True))                # SEC resolves IREN
        self.assertEqual(entry.origin, "ai_suggestion_grounded")  # records it was GROUNDED
        self.assertEqual(entry.source_authority, "canonical")     # inherits SEC grounding
        self.assertNotEqual(entry.source_authority, "ai_suggestion")
        self.assertTrue(any(r.startswith("sec:") for r in entry.source_refs))
        self.assertEqual([e.ticker for e in accepted_universe(self.store)], ["IREN"])

    def test_screener_grounded_suggestion_is_convenience_never_canonical(self):
        entry = accept_universe_entry(
            self.store, ticker="IREN", theme_id="tech", theme_label="Technology",
            accepted_by="operator:sgs", now=_NOW, origin="ai_suggestion_grounded",
            transport=_transport(sec_empty=True))                # only the screener resolves
        self.assertEqual(entry.source_authority, "convenience")
        self.assertNotEqual(entry.source_authority, "canonical")  # never laundered up


# =========================================================================== #
# E. Refusals: no operator, no grounding, injected-now required                  #
# =========================================================================== #
class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="auni_no_")

    def test_empty_accepted_by_is_refused(self):
        with self.assertRaises(ValueError):
            accept_universe_entry(
                self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
                accepted_by="", now=_NOW, transport=_transport())
        self.assertEqual(AcceptedUniverseStore(self.store).read_all(), ())

    def test_missing_now_is_refused(self):
        with self.assertRaises(ValueError):
            accept_universe_entry(
                self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
                accepted_by="operator:sgs", now="", transport=_transport())

    def test_unresolved_grounding_refs_are_refused(self):
        with self.assertRaises(ValueError):
            accept_universe_entry(
                self.store, ticker="GHOST", theme_id="physical-ai", theme_label="Physical AI",
                accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
                grounding_refs=("not-a-real-ref",), transport=_transport())
        self.assertEqual(AcceptedUniverseStore(self.store).read_all(), ())


# =========================================================================== #
# F. Append-only + correction supersession                                       #
# =========================================================================== #
class AppendOnlyCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp(prefix="auni_corr_")

    def test_reaccept_is_idempotent(self):
        kw = dict(ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
                  accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery")
        a = accept_universe_entry(self.store, transport=_transport(fmp_empty=True), **kw)
        b = accept_universe_entry(self.store, transport=_transport(fmp_empty=True), **kw)
        self.assertEqual(a.entry_id, b.entry_id)
        self.assertEqual(len(AcceptedUniverseStore(self.store).read_all()), 1)

    def test_correction_supersedes_never_mutates(self):
        first = accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            note="initial", transport=_transport(fmp_empty=True))
        corrected = accept_universe_entry(
            self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now="2026-07-15T13:00:00Z", origin="evidence_discovery",
            verdict="rejected", note="on reflection, out of scope",
            correction_of=first.entry_id, transport=_transport(fmp_empty=True))
        records = AcceptedUniverseStore(self.store).read_all()
        self.assertEqual(len(records), 2)                        # both lines on disk (append-only)
        self.assertEqual(records[0], first)                      # original byte-unchanged
        # The correction rejected it -> the ticker is NO LONGER in the working universe.
        self.assertEqual(accepted_universe(self.store), ())
        self.assertEqual(corrected.correction_of, first.entry_id)

    def test_correction_of_unknown_id_is_refused(self):
        with self.assertRaises(ValueError):
            accept_universe_entry(
                self.store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
                accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
                correction_of="auni:IREN:doesnotexist", transport=_transport(fmp_empty=True))


# =========================================================================== #
# G. Determinism + isolation from the theme graph / pulse / lineage              #
# =========================================================================== #
class DeterminismIsolationTests(unittest.TestCase):
    def test_deterministic_given_injected_now(self):
        s1 = tempfile.mkdtemp(prefix="auni_d1_")
        s2 = tempfile.mkdtemp(prefix="auni_d2_")
        kw = dict(ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
                  accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery")
        e1 = accept_universe_entry(s1, transport=_transport(fmp_empty=True), **kw)
        e2 = accept_universe_entry(s2, transport=_transport(fmp_empty=True), **kw)
        self.assertEqual(e1.entry_id, e2.entry_id)
        self.assertEqual(e1, e2)

    def test_acceptance_writes_only_the_universe_log(self):
        store = tempfile.mkdtemp(prefix="auni_iso_")
        accept_universe_entry(
            store, ticker="IREN", theme_id="physical-ai", theme_label="Physical AI",
            accepted_by="operator:sgs", now=_NOW, origin="evidence_discovery",
            transport=_transport(fmp_empty=True))
        files = set(os.listdir(store))
        self.assertIn("accepted_universe.jsonl", files)
        # No theme-graph / pulse / lineage / candidate store is written by acceptance (UD-4 does).
        for forbidden in ("theme_graph.jsonl", "signal_store.jsonl", "event_store.jsonl",
                          "capital_candidate_store.jsonl", "investment_diligence.jsonl"):
            self.assertNotIn(forbidden, files)


if __name__ == "__main__":
    unittest.main()
