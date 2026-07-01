"""Tests for the IMPLEMENTATION-009E ingestion vertical slice.

Fixture-backed only -- NO network, NO API keys/secrets, NO scheduling. The slice
takes SEC / FMP / yfinance evidence, arbitrates by source authority, maps the
SUPPORTED winning records into canonical Tattva Observations, and runs the
EXISTING Reality Intelligence (Tattva) layer -- and STOPS THERE. It never
produces a genesis / prometheus / personal_cio / execution_manual object.
"""

import ast
import json
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from eios_core.canonical_objects import Observation

from evidence_ingestion import (
    run_fixture_ingestion_slice,
    IngestionVerticalSliceResult,
    winning_records,
    resolve_conflicts,
    NormalizedEvidenceRecord,
)
from reality_intelligence.intelligence_assessment import IntelligenceAssessment

_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "slice")
_SLICE_MODULE = os.path.join(_SRC, "evidence_ingestion", "vertical_slice.py")

# Reasoning-conclusion object types the slice must NEVER produce or import.
from genesis.opportunity_hypothesis import OpportunityHypothesis
from prometheus.investment_thesis import InvestmentThesis
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction
from execution_manual.manual_execution_intent import ManualExecutionIntent

_FORBIDDEN_TYPES = (
    OpportunityHypothesis, InvestmentThesis, InvestmentAction,
    PersonalizedAction, ManualExecutionIntent,
)

_NOW = 1750000000.0
_PERIOD = "2026-03-31"
_SHARED_OHLCV_DATE = "2026-06-26"


def _load(name):
    with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
        return json.load(fh)


def _run(**overrides):
    kw = dict(
        subject="IREN",
        domain="ai-infrastructure",
        sec_submissions=_load("sec_submissions_iren.json"),
        sec_companyfacts=_load("sec_companyfacts_iren.json"),
        fmp_income_statement=_load("fmp_income_statement_iren.json"),
        fmp_profile=_load("fmp_profile_iren.json"),
        fmp_ohlcv=_load("fmp_ohlcv_iren.json"),
        fmp_news=_load("fmp_news_iren.json"),
        fmp_ownership=_load("fmp_ownership_iren.json"),
        yf_history=_load("yf_history_iren.json"),
        yf_quote=_load("yf_quote_iren.json"),
        now=_NOW,
        yf_quote_as_of=_PERIOD,
    )
    kw.update(overrides)
    return run_fixture_ingestion_slice(**kw)


class SliceRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = _run()

    # --- shape / determinism ------------------------------------------------
    def test_result_is_the_frozen_slice_result(self):
        self.assertIsInstance(self.r, IngestionVerticalSliceResult)
        # frozen: cannot reassign a field.
        with self.assertRaises(Exception):
            self.r.subject = "OTHER"

    def test_deterministic_two_runs_identical_ids(self):
        a, b = _run(), _run()
        self.assertEqual([o.id for o in a.observations], [o.id for o in b.observations])
        self.assertEqual([n.id for n in a.normalized_records],
                         [n.id for n in b.normalized_records])
        self.assertEqual(a.intelligence_assessment.id, b.intelligence_assessment.id)
        self.assertEqual(a.resolved_facts, b.resolved_facts)

    def test_raw_and_normalized_from_all_three_sources(self):
        by_src = {}
        for n in self.r.normalized_records:
            by_src.setdefault(n.source.source_name, 0)
            by_src[n.source.source_name] += 1
        for name in ("SEC EDGAR", "FMP", "yfinance"):
            self.assertGreater(by_src.get(name, 0), 0, "no records from {0}".format(name))
        # a raw-record ref exists for every normalized record.
        self.assertEqual(len(self.r.raw_records), len(self.r.normalized_records))
        for ref in self.r.raw_records:
            self.assertEqual(ref.kind, "RawEvidenceRecord")
            self.assertTrue(ref.object_id)

    def test_authority_summary_has_canonical_convenience_fallback(self):
        a = self.r.authority_summary
        self.assertGreater(a.get("canonical", 0), 0)    # SEC
        self.assertGreater(a.get("convenience", 0), 0)  # FMP
        self.assertGreater(a.get("fallback", 0), 0)     # yfinance

    def test_source_coverage_summary_counts_contributions(self):
        cov = self.r.source_coverage_summary
        self.assertIn("SEC EDGAR", cov)
        self.assertIn("FMP", cov)
        self.assertIn("yfinance", cov)
        # yfinance contributes evidence but zero Observations (all deferred).
        self.assertEqual(cov["yfinance"]["observations"], 0)
        self.assertGreater(cov["yfinance"]["records"], 0)
        # SEC contributes Observations; FMP has overridden financial facts.
        self.assertGreater(cov["SEC EDGAR"]["observations"], 0)
        self.assertGreater(cov["FMP"]["overridden"], 0)

    # --- arbitration: SEC > FMP > yfinance ----------------------------------
    def test_sec_financial_wins_over_fmp_same_period_revenue(self):
        key = ("IREN", "financial_fact", "revenue", _PERIOD, "USD")
        self.assertEqual(self.r.resolved_facts[key], 120000000)  # SEC, not FMP 118M
        # winning_records agrees the SEC record owns the fact.
        winners = winning_records(self.r.normalized_records)
        self.assertEqual(winners[key].normalized_type, "sec_xbrl_revenue")
        self.assertEqual(winners[key].source_authority, "canonical")
        # Only the SEC revenue Observation exists; FMP revenue is overridden.
        rev_obs = [o for o in self.r.observations
                   if o.content.get("financial_metric") == "revenue"]
        self.assertEqual(len(rev_obs), 1)
        self.assertEqual(rev_obs[0].content.get("source_authority"), "canonical")
        # FMP revenue is present as an overridden deferred record with a reason.
        overridden = [
            (rec, rs) for rec, rs in zip(self.r.deferred_records, self.r.deferred_reasons)
            if rec.normalized_type == "fmp_financial_revenue"
        ]
        self.assertEqual(len(overridden), 1)
        self.assertIn("overridden by higher-authority SEC EDGAR", overridden[0][1])

    def test_sec_shares_win_over_fmp_and_yf_same_period(self):
        key = ("IREN", "financial_fact", "shares_outstanding", _PERIOD, "shares")
        self.assertEqual(self.r.resolved_facts[key], 210000000)  # SEC canonical
        winners = winning_records(self.r.normalized_records)
        self.assertEqual(winners[key].normalized_type, "sec_xbrl_shares_outstanding")
        # FMP shares overridden (mapping suppressed); yf shares deferred entirely.
        deferred_types = {rec.normalized_type for rec in self.r.deferred_records}
        self.assertIn("fmp_financial_shares_outstanding", deferred_types)
        self.assertIn("yf_quote_shares_outstanding", deferred_types)
        # No FMP/yf shares Observation was produced.
        share_obs = [o for o in self.r.observations
                     if o.content.get("financial_metric") == "shares_outstanding"]
        self.assertTrue(all(o.content.get("source_authority") == "canonical"
                            for o in share_obs))

    def test_fmp_ohlcv_wins_over_yfinance_same_date_field(self):
        key = ("IREN", "market_data", _SHARED_OHLCV_DATE, "close")
        self.assertEqual(self.r.resolved_facts[key], 21.10)  # FMP convenience beats yf
        winners = winning_records(self.r.normalized_records)
        self.assertEqual(winners[key].source_authority, "convenience")
        self.assertEqual(winners[key].source.source_name, "FMP")
        # Both remain DEFERRED evidence -- neither becomes an Observation.
        self.assertNotIn("fmp_ohlcv",
                         {o.content.get("source_type") for o in self.r.observations})

    def test_yfinance_fills_gap_only_when_sec_fmp_absent(self):
        # 2026-06-24 exists only in the yfinance history -> yfinance wins by default.
        gap_key = ("IREN", "market_data", "2026-06-24", "close")
        self.assertEqual(self.r.resolved_facts[gap_key], 19.45)
        winners = winning_records(self.r.normalized_records)
        self.assertEqual(winners[gap_key].source_authority, "fallback")

    def test_different_periods_do_not_falsely_conflict(self):
        # FMP-only OHLCV date and yf-only OHLCV date are distinct keys, no warning.
        self.assertIn(("IREN", "market_data", "2026-06-27", "close"), self.r.resolved_facts)
        self.assertIn(("IREN", "market_data", "2026-06-24", "close"), self.r.resolved_facts)
        # No conflict warning names a cross-period pairing.
        for w in self.r.conflict_warnings:
            self.assertNotIn("2026-06-24", w)
            self.assertNotIn("2026-06-27", w)

    def test_ohlcv_never_conflicts_with_a_filing_fact(self):
        for key in self.r.resolved_facts:
            if len(key) >= 2 and key[1] == "market_data":
                # a market-data key never collides with a financial_fact key.
                self.assertNotIn("financial_fact", key)
        # And no conflict warning mixes a price field with a financial metric.
        for w in self.r.conflict_warnings:
            self.assertFalse("market_data" in w and "financial_fact" in w)

    def test_conflict_warnings_name_both_sources_and_authorities(self):
        rev = [w for w in self.r.conflict_warnings
               if "financial_fact/revenue" in w][0]
        self.assertIn("SEC EDGAR", rev)
        self.assertIn("FMP", rev)
        self.assertIn("canonical", rev)
        self.assertIn("convenience", rev)

    # --- Observation mapping + deferred behaviour ---------------------------
    def test_supported_records_map_to_expected_observation_types(self):
        stypes = {o.content.get("source_type") for o in self.r.observations}
        # financial report (SEC XBRL / FMP gap financials), capital-structure event
        # (S-3), contract win (8-K), news / press release (FMP news).
        self.assertIn("financial_report", stypes)
        self.assertIn("capital_structure_event", stypes)
        self.assertIn("contract_win", stypes)
        self.assertTrue({"news_excerpt", "press_release"} & stypes)
        for o in self.r.observations:
            self.assertIsInstance(o, Observation)

    def test_unsupported_categories_are_deferred_with_reasons(self):
        deferred = dict(zip(
            [rec.normalized_type for rec in self.r.deferred_records],
            self.r.deferred_reasons,
        ))
        for nt in ("fmp_ohlcv", "fmp_profile", "fmp_ownership",
                   "yf_ohlcv", "yf_quote", "yf_quote_shares_outstanding"):
            self.assertIn(nt, deferred, "missing deferred {0}".format(nt))
            self.assertTrue(deferred[nt])  # a non-empty explicit reason
        # deferred evidence is NOT hidden: every deferred record is retained.
        self.assertEqual(len(self.r.deferred_records), len(self.r.deferred_reasons))
        self.assertGreater(len(self.r.deferred_records), 0)

    def test_data_gaps_labelled_by_kind(self):
        kinds = {g[0] for g in self.r.data_gaps}
        self.assertIn("tattva_vocabulary_deferred", kinds)
        self.assertIn("overridden_financial_fact", kinds)
        # each gap entry is (kind, detail) with a non-empty detail.
        for kind, detail in self.r.data_gaps:
            self.assertTrue(kind)
            self.assertTrue(detail)

    # --- Tattva assessment produced, stops there ----------------------------
    def test_tattva_assessment_is_produced_from_observations(self):
        ia = self.r.intelligence_assessment
        self.assertIsInstance(ia, IntelligenceAssessment)
        self.assertEqual(ia.domain, "ai-infrastructure")
        self.assertGreaterEqual(len(ia.signals), 1)
        # multiple signal families surfaced from the aligned multi-source evidence.
        self.assertGreaterEqual(len({s.signal_type for s in ia.signals}), 2)
        # bound to exactly the produced Observations.
        self.assertEqual(set(ia.grounding_observation_ids),
                         {o.id for o in self.r.observations})
        bound = {ref.object_id for ref in ia.provenance.sources}
        self.assertEqual(bound, {o.id for o in self.r.observations})

    def test_no_assessment_when_no_observations(self):
        r = run_fixture_ingestion_slice(
            subject="IREN", domain="ai-infrastructure",
            fmp_ohlcv=_load("fmp_ohlcv_iren.json"),  # deferred-only input
            now=_NOW,
        )
        self.assertEqual(len(r.observations), 0)
        self.assertIsNone(r.intelligence_assessment)
        self.assertGreater(len(r.deferred_records), 0)  # still not hidden

    def test_stops_at_tattva_no_downstream_objects(self):
        # No field on the result is a genesis/prometheus/personal_cio/kriya object.
        for name in type(self.r).__dataclass_fields__:
            val = getattr(self.r, name)
            candidates = val if isinstance(val, (tuple, list)) else (val,)
            for c in candidates:
                self.assertNotIsInstance(c, _FORBIDDEN_TYPES)
        # The IA carries no opportunity / thesis / action field.
        ia_fields = set(type(self.r.intelligence_assessment).__dataclass_fields__)
        for bad in ("opportunity", "thesis", "investment_action", "action",
                    "personalized_action", "allocation"):
            self.assertNotIn(bad, ia_fields)

    # --- provenance preserved Observation -> normalized -> raw -> source ----
    def test_every_observation_preserves_full_provenance_chain(self):
        chain = self.r.provenance_chain
        self.assertEqual(len(chain.traces), len(self.r.observations))
        self.assertEqual(chain.intelligence_assessment_id,
                         self.r.intelligence_assessment.id)
        norm_by_id = {n.id: n for n in self.r.normalized_records}
        obs_by_id = {o.id: o for o in self.r.observations}
        for t in chain.traces:
            obs = obs_by_id[t.observation_id]
            # Observation -> NormalizedEvidenceRecord
            self.assertEqual(obs.provenance.sources[0].object_id, t.normalized_record_id)
            norm = norm_by_id[t.normalized_record_id]
            # NormalizedEvidenceRecord -> RawEvidenceRecord
            self.assertEqual(norm.source_record_ref.object_id, t.raw_record_ref.object_id)
            self.assertEqual(t.raw_record_ref.kind, "RawEvidenceRecord")
            # -> source (name / authority / class / provider)
            self.assertEqual(t.source_name, norm.source.source_name)
            self.assertEqual(t.source_authority, norm.source_authority)
            self.assertEqual(t.source_class, norm.source_class)
            self.assertEqual(t.source_provider, norm.source.provider)
            # the Observation itself carries the source authority forward.
            self.assertEqual(obs.content.get("source_authority"), norm.source_authority)


class SliceStaticGuardTests(unittest.TestCase):
    """AST / static guards proving no network, no secrets, and Tattva boundary."""

    @classmethod
    def setUpClass(cls):
        with open(_SLICE_MODULE, "r") as fh:
            cls.src = fh.read()
        cls.tree = ast.parse(cls.src)

    def test_no_network_or_secret_imports(self):
        banned = {"requests", "urllib", "http", "socket", "aiohttp", "httpx",
                  "os", "subprocess", "sched", "asyncio", "threading"}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertNotIn(a.name.split(".")[0], banned)
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn((node.module or "").split(".")[0], banned)

    def test_no_secret_or_key_access(self):
        # No env / secret ACCESS (prose mentioning "no secrets" is fine).
        self.assertNotIn("os.environ", self.src)
        self.assertNotIn("getenv", self.src.lower())
        banned_ids = ("api_key", "apikey", "secret", "token", "password", "access_key")
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute):
                self.assertNotEqual(node.attr, "environ")
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, ("getenv",))
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        tlow = tgt.id.lower()
                        for b in banned_ids:
                            self.assertNotIn(b, tlow,
                                             "assigns secret-like {0}".format(tgt.id))

    def test_imports_only_ingestion_reality_and_core(self):
        # The slice must NOT import a downstream reasoning / actuation layer:
        # it stops at Tattva (evidence_ingestion + reality_intelligence + eios_core).
        forbidden_pkgs = {"genesis", "prometheus", "personal_cio",
                          "execution_manual", "infinite_canvas", "runtime"}
        for node in ast.walk(self.tree):
            mods = []
            if isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
            elif isinstance(node, ast.Import):
                mods.extend(a.name for a in node.names)
            for m in mods:
                top = m.split(".")[0]
                self.assertNotIn(top, forbidden_pkgs,
                                 "slice imports forbidden layer {0}".format(m))

    def test_no_fixture_carries_secret(self):
        for name in os.listdir(_FIXTURE_DIR):
            with open(os.path.join(_FIXTURE_DIR, name), "r") as fh:
                blob = fh.read().lower()
            self.assertNotIn("shreenik", blob)
            self.assertNotIn("api_key", blob)
            self.assertNotIn("secret", blob)


if __name__ == "__main__":
    unittest.main()
