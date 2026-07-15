"""UNIVERSE-DISCOVERY UD-1 -- evidence-driven ticker discovery (OFFLINE, mocked transports).

Discovery-only: the two producers surface provenanced :class:`DiscoveredUniverseCandidate`s from
REAL sources (FMP company screener + SEC EDGAR full-text search). Per the UD-1 contract:

* every candidate traces to a REAL screener row or a REAL filing hit -- a miss / empty / 429 /
  timeout / malformed / unmapped-CIK is a VISIBLE gap, NEVER a fabricated ticker or theme, and
  NEVER a fixture/demo fallback;
* ``sec_fulltext`` = canonical, ``fmp_screener`` = convenience; on a same-ticker dedupe the
  HIGHER authority (canonical) wins and BOTH provenance refs are preserved;
* NO ambient network: every payload arrives through an injected mock transport (the real path is
  built lazily and NEVER exercised here); the whole module runs under a socket kill-switch;
* credentials are PRESENCE only (read from an injected ``env``, value never echoed/stored);
* stdlib-only, deterministic (injected ``now`` + content-derived ids), no score/rank/trade field;
* it does NOT read/write the theme graph and does NOT touch any pulse store (discovery only).
"""
import ast
import os
import re
import socket
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reality_mesh.universe_discovery import (
    DISCOVERY_METHODS,
    DISCOVERY_METHOD_AUTHORITY,
    DiscoveredUniverseCandidate,
    UniverseDiscoveryResult,
    candidate_id_for,
    discover_via_fmp_screener,
    discover_via_sec_fulltext,
    merge_universe_discovery,
)
from reality_mesh.labels import authority_rank
from reality_mesh.validation import assert_no_trade_fields

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PY = os.path.join(_HERE, "..", "src", "reality_mesh", "universe_discovery.py")
_TRANSPORT_PY = os.path.join(_HERE, "..", "src", "evidence_ingestion", "live_transport.py")
_NOW = "2026-07-05T14:00:00Z"

# A stand-in credential VALUE used ONLY to prove it never leaks into any candidate / result / gap.
_FAKE_CREDENTIAL = "sk-FAKEVALUE-hunter2-000"

# The socket kill-switch stays armed for the WHOLE module (every path must run offline).
_ORIG_CONNECT = None


def setUpModule():
    global _ORIG_CONNECT
    _ORIG_CONNECT = socket.socket.connect

    def _blocked(*_a, **_k):
        raise AssertionError(
            "network blocked: universe discovery must run fully offline on mock transports -- "
            "the real network path is never exercised in tests")

    socket.socket.connect = _blocked


def tearDownModule():
    if _ORIG_CONNECT is not None:
        socket.socket.connect = _ORIG_CONNECT


# --------------------------------------------------------------------------- #
# Real-shaped mock transports (fixture-shaped dicts; fully offline)             #
# --------------------------------------------------------------------------- #
def _screener_rows():
    """A real-shaped FMP /stable/company-screener JSON array (Technology / Semiconductors)."""
    return [
        {"symbol": "IREN", "companyName": "IREN Limited", "marketCap": 1200000000,
         "sector": "Technology", "industry": "Semiconductors", "beta": 2.1},
        {"symbol": "AAOI", "companyName": "Applied Optoelectronics, Inc.",
         "marketCap": 900000000, "sector": "Technology", "industry": "Semiconductors"},
        {"companyName": "No Ticker Row", "marketCap": 5},   # symbol-less: MUST be skipped
    ]


def _fmp_screen(**overrides):
    rows = overrides.pop("rows", None)

    def _screen(*, sector="", industry="", market_cap_min=None, limit=50):
        return _screener_rows() if rows is None else rows
    return _screen


def _fts_payload():
    """A real-shaped efts.sec.gov FTS hits document for a phrase, incl. one UNMAPPED CIK.

    Mirrors the ACTUAL EDGAR FTS shape: the filer CIK(s) live in ``ciks`` (a list); the
    accession is the leading segment of ``_id`` (also mirrored in ``adsh``).
    """
    return {"hits": {"total": {"value": 2}, "hits": [
        {"_id": "0001878848-26-000050:d10k.htm",
         "_source": {"ciks": ["1878848"], "adsh": "0001878848-26-000050",
                     "display_names": ["IREN Limited (IREN) (CIK 0001878848)"],
                     "form": "10-K", "file_date": "2026-06-30"}},
        {"_id": "0000999999-26-000001:d.htm",
         "_source": {"ciks": ["999999"], "adsh": "0000999999-26-000001",
                     "display_names": ["Unmapped Co (ZZZZ) (CIK 0000999999)"],
                     "form": "10-K", "file_date": "2026-06-01"}},
    ]}}


def _company_tickers():
    """A real-shaped company_tickers.json object (only IREN mapped; the 999999 CIK is unmapped)."""
    return {"0": {"cik_str": 1878848, "ticker": "IREN", "title": "IREN Limited"}}


def _sec_bundle(**overrides):
    def _search(query, forms=()):
        return _fts_payload()

    bundle = {"search": _search, "company_tickers": _company_tickers}
    bundle.update(overrides)
    return bundle


def _raise_429(*_a, **_k):
    raise RuntimeError("HTTP 429 Too Many Requests (rate exceeded)")


def _raise_timeout(*_a, **_k):
    raise RuntimeError("connection timed out / reset by peer (simulated source failure)")


def _blob(result):
    parts = list(result.data_gaps)
    for name, label in result.source_health:
        parts.extend((name, label))
    for c in result.candidates:
        parts.extend((c.candidate_id, c.ticker, c.company_name, c.theme_hint,
                      c.discovery_method, c.source_authority, c.evidence_note))
        parts.extend(c.source_refs)
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# 1. Contract: the frozen candidate + closed vocab + authority mapping           #
# --------------------------------------------------------------------------- #
class ContractTests(unittest.TestCase):
    def test_methods_and_authority_mapping(self):
        self.assertEqual(DISCOVERY_METHODS, ("fmp_screener", "sec_fulltext"))
        self.assertEqual(DISCOVERY_METHOD_AUTHORITY["fmp_screener"], "convenience")
        self.assertEqual(DISCOVERY_METHOD_AUTHORITY["sec_fulltext"], "canonical")
        # canonical strictly outranks convenience (the dedupe rule)
        self.assertGreater(authority_rank("canonical"), authority_rank("convenience"))

    def test_candidate_is_trade_and_score_clean(self):
        assert_no_trade_fields(DiscoveredUniverseCandidate)
        assert_no_trade_fields(UniverseDiscoveryResult)
        names = {f for f in DiscoveredUniverseCandidate.__dataclass_fields__}
        for banned in ("score", "rank", "rating", "buy", "sell", "order", "trade", "broker"):
            self.assertFalse(any(banned in n.lower() for n in names))

    def test_candidate_requires_ticker_method_authority_and_provenance(self):
        with self.assertRaises(ValueError):     # empty ticker
            DiscoveredUniverseCandidate(candidate_id="udc:x", ticker="",
                                        discovery_method="fmp_screener",
                                        source_authority="convenience", source_refs=("r",))
        with self.assertRaises(ValueError):     # no provenance ref -> would be fabricated
            DiscoveredUniverseCandidate(candidate_id="udc:x", ticker="X",
                                        discovery_method="fmp_screener",
                                        source_authority="convenience", source_refs=())
        with self.assertRaises(ValueError):     # invalid method
            DiscoveredUniverseCandidate(candidate_id="udc:x", ticker="X",
                                        discovery_method="made_up",
                                        source_authority="convenience", source_refs=("r",))
        with self.assertRaises(ValueError):     # invalid discovery authority
            DiscoveredUniverseCandidate(candidate_id="udc:x", ticker="X",
                                        discovery_method="fmp_screener",
                                        source_authority="rumor", source_refs=("r",))

    def test_candidate_id_is_content_derived_from_ticker(self):
        self.assertEqual(candidate_id_for("iren"), candidate_id_for("IREN"))
        self.assertNotEqual(candidate_id_for("IREN"), candidate_id_for("AAOI"))
        self.assertTrue(candidate_id_for("IREN").startswith("udc:IREN:"))


# --------------------------------------------------------------------------- #
# 2. FMP screener producer -> convenience candidates with provenance             #
# --------------------------------------------------------------------------- #
class FmpScreenerTests(unittest.TestCase):
    def test_screener_rows_become_convenience_candidates(self):
        r = discover_via_fmp_screener(
            sector="Technology", industry="Semiconductors",
            transport=_fmp_screen(), now=_NOW)
        tickers = {c.ticker for c in r.candidates}
        self.assertEqual(tickers, {"IREN", "AAOI"})         # symbol-less row skipped, not faked
        for c in r.candidates:
            self.assertEqual(c.discovery_method, "fmp_screener")
            self.assertEqual(c.source_authority, "convenience")
            self.assertIn("fmp:screener/Technology/Semiconductors", c.source_refs)
            self.assertEqual(c.theme_hint, "Technology / Semiconductors")
            self.assertEqual(c.discovered_at, _NOW)
        iren = next(c for c in r.candidates if c.ticker == "IREN")
        self.assertEqual(iren.company_name, "IREN Limited")
        self.assertIn("1200000000", iren.evidence_note)     # real market cap, not fabricated
        self.assertEqual(r.health_of("fmp_screener"), "healthy")

    def test_empty_screener_is_a_gap_zero_fabricated(self):
        r = discover_via_fmp_screener(sector="Nowhere", transport=_fmp_screen(rows=[]), now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertTrue(any("no companies" in g for g in r.data_gaps))
        self.assertNotIn("fixture", _blob(r).lower())

    def test_screener_429_is_rate_limited_gap_zero_fabricated(self):
        r = discover_via_fmp_screener(sector="Technology", transport=_raise_429, now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("fmp_screener"), "rate_limited")
        self.assertTrue(any("429" in g or "rate limit" in g.lower() for g in r.data_gaps))
        self.assertTrue(any("not retried" in g.lower() for g in r.data_gaps))

    def test_screener_timeout_is_source_unavailable_gap(self):
        r = discover_via_fmp_screener(sector="Technology", transport=_raise_timeout, now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("fmp_screener"), "source_unavailable")
        self.assertTrue(any("unavailable" in g for g in r.data_gaps))

    def test_screener_malformed_is_a_gap(self):
        r = discover_via_fmp_screener(
            sector="Technology", transport=lambda **k: "not-a-list", now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertTrue(any("malformed" in g for g in r.data_gaps))


# --------------------------------------------------------------------------- #
# 3. SEC full-text producer -> canonical candidates w/ accession + CIK provenance #
# --------------------------------------------------------------------------- #
class SecFulltextTests(unittest.TestCase):
    def test_filing_hits_become_canonical_candidates_with_real_provenance(self):
        r = discover_via_sec_fulltext(
            "silicon photonics", forms=("10-K",), transport=_sec_bundle(), now=_NOW)
        self.assertEqual([c.ticker for c in r.candidates], ["IREN"])
        c = r.candidates[0]
        self.assertEqual(c.discovery_method, "sec_fulltext")
        self.assertEqual(c.source_authority, "canonical")
        self.assertIn("sec:fts/0001878848-26-000050", c.source_refs)   # REAL accession
        self.assertIn("sec:cik/0001878848", c.source_refs)             # REAL CIK
        self.assertEqual(c.theme_hint, "silicon photonics")
        self.assertEqual(c.company_name, "IREN Limited")
        self.assertIn("silicon photonics", c.evidence_note)
        self.assertIn("10-K", c.evidence_note)
        self.assertEqual(r.health_of("sec_fulltext"), "healthy")

    def test_unmapped_cik_is_an_honest_gap_never_dropped_or_guessed(self):
        r = discover_via_sec_fulltext("silicon photonics", transport=_sec_bundle(), now=_NOW)
        self.assertNotIn("ZZZZ", {c.ticker for c in r.candidates})     # never guessed from display
        self.assertTrue(any("CIK 0000999999" in g and "never guessed" in g
                            for g in r.data_gaps))

    def test_empty_query_is_a_gap(self):
        r = discover_via_sec_fulltext("   ", transport=_sec_bundle(), now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertTrue(any("empty query" in g for g in r.data_gaps))

    def test_fts_429_is_rate_limited_gap(self):
        r = discover_via_sec_fulltext(
            "silicon photonics", transport=_sec_bundle(search=_raise_429), now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("sec_fulltext"), "rate_limited")

    def test_fts_timeout_is_source_unavailable_gap(self):
        r = discover_via_sec_fulltext(
            "silicon photonics", transport=_sec_bundle(search=_raise_timeout), now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("sec_fulltext"), "source_unavailable")

    def test_fts_malformed_is_a_parse_gap(self):
        r = discover_via_sec_fulltext(
            "silicon photonics", transport=_sec_bundle(search=lambda q, f=(): {"nope": 1}),
            now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("sec_fulltext"), "failed")
        self.assertTrue(any("malformed" in g for g in r.data_gaps))

    def test_unwired_company_tickers_maps_nothing_and_is_a_gap(self):
        r = discover_via_sec_fulltext(
            "silicon photonics", transport={"search": _sec_bundle()["search"]}, now=_NOW)
        self.assertEqual(r.candidates, ())      # no CIK map -> nothing mappable, nothing guessed
        self.assertTrue(any("company_tickers" in g for g in r.data_gaps))


# --------------------------------------------------------------------------- #
# 4. Dedupe across methods: canonical > convenience, BOTH refs preserved         #
# --------------------------------------------------------------------------- #
class DedupeTests(unittest.TestCase):
    def setUp(self):
        self.fmp = discover_via_fmp_screener(
            sector="Technology", industry="Semiconductors",
            transport=_fmp_screen(), now=_NOW)
        self.sec = discover_via_sec_fulltext(
            "silicon photonics", transport=_sec_bundle(), now=_NOW)
        self.merged = merge_universe_discovery(self.fmp, self.sec)

    def test_same_ticker_collapses_to_one_candidate_with_canonical_authority(self):
        irens = [c for c in self.merged.candidates if c.ticker == "IREN"]
        self.assertEqual(len(irens), 1)                     # one candidate, not two
        iren = irens[0]
        self.assertEqual(iren.source_authority, "canonical")            # the HIGHER authority
        self.assertEqual(iren.discovery_method, "sec_fulltext")         # the higher-authority method

    def test_both_provenance_refs_are_preserved_on_the_merged_candidate(self):
        iren = next(c for c in self.merged.candidates if c.ticker == "IREN")
        self.assertIn("sec:fts/0001878848-26-000050", iren.source_refs)     # canonical ref
        self.assertIn("sec:cik/0001878848", iren.source_refs)              # canonical ref
        self.assertIn("fmp:screener/Technology/Semiconductors", iren.source_refs)  # convenience ref

    def test_convenience_only_ticker_survives_the_merge(self):
        aaoi = [c for c in self.merged.candidates if c.ticker == "AAOI"]
        self.assertEqual(len(aaoi), 1)
        self.assertEqual(aaoi[0].source_authority, "convenience")
        self.assertEqual(aaoi[0].source_refs, ("fmp:screener/Technology/Semiconductors",))

    def test_merge_unions_health_and_gaps(self):
        methods = {name for name, _label in self.merged.source_health}
        self.assertEqual(methods, {"fmp_screener", "sec_fulltext"})
        # the sec unmapped-CIK gap is carried through the merge
        self.assertTrue(any("never guessed" in g for g in self.merged.data_gaps))

    def test_merge_is_deterministic(self):
        again = merge_universe_discovery(
            discover_via_fmp_screener(sector="Technology", industry="Semiconductors",
                                      transport=_fmp_screen(), now=_NOW),
            discover_via_sec_fulltext("silicon photonics", transport=_sec_bundle(), now=_NOW))
        self.assertEqual(self.merged, again)


# --------------------------------------------------------------------------- #
# 5. Credentials: PRESENCE only; missing -> visible gap; value never leaks        #
# --------------------------------------------------------------------------- #
class CredentialTests(unittest.TestCase):
    def test_missing_fmp_key_is_credentials_missing_gap_no_crash(self):
        r = discover_via_fmp_screener(sector="Technology", env={}, now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("fmp_screener"), "credentials_missing")
        self.assertTrue(any("FMP_API_KEY" in g for g in r.data_gaps))

    def test_missing_sec_user_agent_is_credentials_missing_gap_no_crash(self):
        r = discover_via_sec_fulltext("silicon photonics", env={}, now=_NOW)
        self.assertEqual(r.candidates, ())
        self.assertEqual(r.health_of("sec_fulltext"), "credentials_missing")
        self.assertTrue(any("SEC_USER_AGENT" in g for g in r.data_gaps))

    def test_credential_value_never_appears_in_any_output(self):
        # even if a caller passed the key via env, presence is used but the VALUE never surfaces:
        # here the injected mock transport is used, so no network; prove no leak in the outputs.
        env = {"FMP_API_KEY": _FAKE_CREDENTIAL, "SEC_USER_AGENT": _FAKE_CREDENTIAL}
        r1 = discover_via_fmp_screener(
            sector="Technology", industry="Semiconductors",
            transport=_fmp_screen(), env=env, now=_NOW)
        r2 = discover_via_sec_fulltext(
            "silicon photonics", transport=_sec_bundle(), env=env, now=_NOW)
        for r in (r1, r2):
            low = _blob(r).lower()
            self.assertNotIn(_FAKE_CREDENTIAL.lower(), low)
            for bad in ("apikey=", "api_key=", "sec_user_agent=", "secret", "password"):
                self.assertNotIn(bad, low)
            self.assertNotRegex(low, r"\bsk-[a-z0-9]{6}")


# --------------------------------------------------------------------------- #
# 6. NO network on import; offline; no score/rank def names; stdlib-only          #
# --------------------------------------------------------------------------- #
class NoAmbientNetworkTests(unittest.TestCase):
    _BANNED = ("socket", "urllib", "http", "requests", "aiohttp", "httpx",
               "websocket", "websockets", "ftplib", "smtplib", "telnetlib")

    def _imports(self, path):
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names.append(node.module or "")
        return names

    def test_universe_discovery_imports_no_network_module(self):
        for name in self._imports(_MODULE_PY):
            for root in self._BANNED:
                self.assertFalse(name == root or name.startswith(root + "."),
                                 "network import {0!r} in universe_discovery.py".format(name))

    def test_universe_discovery_imports_no_third_party(self):
        # stdlib-only: every import resolves to stdlib or the in-repo packages -- no pip dependency.
        stdlib_ok = {"__future__", "hashlib", "re", "dataclasses", "typing", "os", "json"}
        local_ok = {"reality_mesh", "evidence_ingestion"}
        for name in self._imports(_MODULE_PY):
            if name == "":
                continue
            root = name.split(".", 1)[0]
            self.assertTrue(root in stdlib_ok or root in local_ok,
                            "unexpected non-stdlib import {0!r}".format(name))

    def test_transport_helpers_keep_urllib_lazy(self):
        # the new fmp_screener_transport / sec_fts_transport must not import urllib at module top
        with open(_TRANSPORT_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in tree.body:      # MODULE-LEVEL statements only
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertFalse(a.name.startswith("urllib"),
                                     "urllib imported at module top of live_transport.py")

    def test_no_score_rank_or_rating_function_defs(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertFalse(re.search(r"(score|rank|rating)", node.name),
                                 "banned fn name {0!r}".format(node.name))

    def test_default_real_transports_are_function_local(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn("def _default_fmp_transport", source)
        self.assertIn("def _default_sec_transport", source)
        self.assertIn("from evidence_ingestion.live_transport import fmp_screener_transport",
                      source)
        self.assertIn("from evidence_ingestion.live_transport import sec_fts_transport", source)


# --------------------------------------------------------------------------- #
# 7. Discovery-only: does NOT touch the theme graph or any pulse store            #
# --------------------------------------------------------------------------- #
class DiscoveryOnlyTests(unittest.TestCase):
    def test_module_does_not_import_theme_graph_pulse_or_lineage(self):
        with open(_MODULE_PY, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        forbidden = ("theme_graph", "pulse", "pulse_persistence", "diligence_lineage",
                     "capital_candidate", "stores")
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.ImportFrom):
                mods.append((node.module or "").split(".")[-1])
            elif isinstance(node, ast.Import):
                mods.extend(a.name.split(".")[-1] for a in node.names)
            for m in mods:
                self.assertNotIn(m, forbidden,
                                 "UD-1 discovery must not import {0!r}".format(m))

    def test_result_has_no_graph_or_engine_side_effect_surface(self):
        # the producers return a plain result object; there is no accept / publish / graph API
        r = discover_via_fmp_screener(
            sector="Technology", transport=_fmp_screen(), now=_NOW)
        self.assertIsInstance(r, UniverseDiscoveryResult)
        for banned in ("accept", "publish", "graph", "engine", "pulse"):
            self.assertFalse(any(banned in name for name in dir(r)
                                 if not name.startswith("_")),
                             "UD-1 result exposes a {0!r} affordance".format(banned))


if __name__ == "__main__":
    unittest.main()
