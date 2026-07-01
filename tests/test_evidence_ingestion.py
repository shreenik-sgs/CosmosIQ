"""Tests for the evidence-ingestion FOUNDATION (IMPLEMENTATION-009A).

Fixture-based only -- NO network, NO API keys, NO investment reasoning. Verifies
the source-authority/class model, evidence records, fixture-backed adapters, the
conflict resolver, and the observation mapper (including that a rumor cannot
raise confidence, proven through the real Tattva assessment).
"""

import ast
import os
import sys
import unittest

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from eios_core.canonical_objects import Observation

from evidence_ingestion import (
    EvidenceSource,
    authority_rank,
    authority_for_source_class,
    make_raw_evidence_record,
    make_normalized_evidence_record,
    SecEdgarAdapter,
    FmpAdapter,
    YFinanceAdapter,
    map_to_observation,
    resolve_conflicts,
)

from reality_intelligence.intelligence_assessment import generate_intelligence_assessment

# Reasoning-conclusion object types the mapper must NEVER produce.
from genesis.opportunity_hypothesis import OpportunityHypothesis
from prometheus.investment_thesis import InvestmentThesis
from prometheus.investment_action import InvestmentAction
from personal_cio.personalized_action import PersonalizedAction


# --------------------------------------------------------------------------- #
# Inline fixtures (dependency-injected local data -- no network, no keys).      #
# --------------------------------------------------------------------------- #

SEC_FIXTURES = {
    "IREN-8K-2026Q2": {
        "source_name": "SEC EDGAR",
        "source_ref": "https-omitted://edgar/8-K",  # not fetched; label only
        "raw_type": "8-K",
        "normalized_type": "8-K",
        "ticker": "IREN",
        "cik": "0001878848",
        "as_of": "2026-05-01",
        "event_date": "2026-05-01",
        "evidence_quality": 0.95,
        "confidence": 0.9,
        "payload": {"item": "1.01", "counterparty": "Microsoft", "contract_value": 500.0},
        "extracted_fields": {
            "catalyst_type": "contract_win",
            "expected_direction": "positive",
            "contract_value": 500.0,
            "counterparty": "Microsoft",
        },
    },
    "IREN-10Q-2026Q1": {
        "source_name": "SEC EDGAR",
        "raw_type": "10-Q",
        "normalized_type": "10-Q",
        "ticker": "IREN",
        "cik": "0001878848",
        "period_end": "2026-03-31",
        "evidence_quality": 0.95,
        "confidence": 0.9,
        "payload": {"revenue": 120.0, "prior_revenue": 100.0},
        "extracted_fields": {
            "financial_metric": "revenue",
            "metric_value": 120.0,
            "prior_value": 100.0,
        },
    },
    # Same FACT (financial_metric "revenue"), canonical value, for the conflict
    # test. Its SEC-specific normalized_type deliberately DIFFERS from the FMP
    # record's -- arbitration must key on the shared metric, not the type.
    "IREN-REV": {
        "source_name": "SEC EDGAR",
        "raw_type": "10-Q",
        "normalized_type": "sec_xbrl_revenue",
        "ticker": "IREN",
        "period_end": "2026-03-31",
        "evidence_quality": 0.95,
        "confidence": 0.9,
        "payload": {"revenue": 120.0},
        "extracted_fields": {"financial_metric": "revenue", "metric_value": 120.0},
    },
    # A confirmed contract catalyst for the rumor comparison.
    "IREN-CONTRACT": {
        "source_name": "SEC EDGAR",
        "raw_type": "8-K",
        "normalized_type": "8-K",
        "ticker": "IREN",
        "event_date": "2026-05-01",
        "evidence_quality": 0.9,
        "confidence": 0.9,
        "payload": {"item": "1.01"},
        "extracted_fields": {
            "catalyst_type": "contract_win",
            "expected_direction": "positive",
        },
    },
}

FMP_FIXTURES = {
    "IREN-QUOTE": {
        "source_name": "Financial Modeling Prep",
        "raw_type": "quote",
        "normalized_type": "financial_snapshot",
        "ticker": "IREN",
        "period_end": "2026-03-31",
        "evidence_quality": 0.6,
        "confidence": 0.6,
        "payload": {"revenue": 118.0},
        "extracted_fields": {
            "financial_metric": "revenue",
            "metric_value": 118.0,
            "prior_value": 100.0,
        },
    },
    # Same FACT (financial_metric "revenue"), a DIFFERENT (convenience) value, for
    # the conflict test. Its FMP-specific normalized_type deliberately DIFFERS from
    # the SEC record's -- proving cross-source arbitration keys on the metric.
    "IREN-REV": {
        "source_name": "Financial Modeling Prep",
        "raw_type": "quote",
        "normalized_type": "fmp_financial_revenue",
        "ticker": "IREN",
        "period_end": "2026-03-31",
        "evidence_quality": 0.6,
        "confidence": 0.6,
        "payload": {"revenue": 118.0},
        "extracted_fields": {"financial_metric": "revenue", "metric_value": 118.0},
    },
    # Partial-coverage fixture: lacks 'prior_value'.
    "IREN-PARTIAL": {
        "source_name": "Financial Modeling Prep",
        "raw_type": "quote",
        "normalized_type": "financial_snapshot",
        "ticker": "IREN",
        "period_end": "2026-03-31",
        "evidence_quality": 0.6,
        "confidence": 0.6,
        "payload": {"revenue": 118.0},
        "extracted_fields": {"financial_metric": "revenue", "metric_value": 118.0},
    },
}

YF_FIXTURES = {
    "IREN-HISTORY": {
        "source_name": "yfinance",
        "raw_type": "history",
        "normalized_type": "financial_snapshot",
        "ticker": "IREN",
        "period_end": "2026-03-31",
        "evidence_quality": 0.4,
        "confidence": 0.4,
        "payload": {"close": 12.5},
        "extracted_fields": {
            "financial_metric": "close",
            "metric_value": 12.5,
            "prior_value": 10.0,
        },
    },
}

RUMOR_FIXTURES = {
    "IREN-RUMOR": {
        "source_name": "AnonBlog",
        "raw_type": "rumor",
        "normalized_type": "rumor",
        "ticker": "IREN",
        "event_date": "2026-05-01",
        "evidence_quality": 0.9,  # deliberately HIGH to prove status still discounts
        "confidence": 0.9,
        "payload": {"chatter": "unverified contract win"},
        "extracted_fields": {
            "catalyst_type": "contract_win",
            "expected_direction": "positive",
        },
    },
}


def _rumor_source():
    return EvidenceSource(
        source_name="AnonBlog",
        source_authority="rumor",
        source_class="rumor_or_unverified",
        provider="blog",
    )


class SourceModelTests(unittest.TestCase):
    def test_class_to_authority_mapping(self):
        self.assertEqual(authority_for_source_class("official_filing"), "canonical")
        self.assertEqual(authority_for_source_class("regulatory"), "canonical")
        self.assertEqual(authority_for_source_class("company_ir"), "primary")
        self.assertEqual(authority_for_source_class("press_release"), "primary")
        self.assertEqual(authority_for_source_class("paid_api"), "convenience")
        self.assertEqual(authority_for_source_class("market_data"), "convenience")
        self.assertEqual(authority_for_source_class("free_api"), "fallback")
        self.assertEqual(authority_for_source_class("manual_input"), "manual")
        self.assertEqual(authority_for_source_class("rumor_or_unverified"), "rumor")

    def test_unknown_class_raises(self):
        with self.assertRaises(ValueError):
            authority_for_source_class("mystery")

    def test_authority_ordering(self):
        self.assertGreater(authority_rank("canonical"), authority_rank("convenience"))
        self.assertGreater(authority_rank("convenience"), authority_rank("fallback"))
        self.assertGreater(authority_rank("manual"), authority_rank("fallback"))
        self.assertGreater(authority_rank("fallback"), authority_rank("rumor"))

    def test_evidence_source_validation(self):
        with self.assertRaises(ValueError):
            EvidenceSource("x", "bogus", "official_filing")
        with self.assertRaises(ValueError):
            EvidenceSource("x", "canonical", "bogus")


class AdapterAuthorityTests(unittest.TestCase):
    def test_sec_filing_evidence_maps_to_canonical_authority(self):
        res = SecEdgarAdapter(SEC_FIXTURES).fetch({"subject": "IREN-8K-2026Q2", "now": 0})
        self.assertTrue(res.records)
        rec = res.records[0]
        self.assertEqual(rec.source_authority, "canonical")
        self.assertEqual(rec.source_class, "official_filing")
        obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
        self.assertEqual(obs.content["source_reliability"], "high")

    def test_fmp_evidence_maps_to_paid_convenience_authority(self):
        res = FmpAdapter(FMP_FIXTURES).fetch({"subject": "IREN-QUOTE", "now": 0})
        rec = res.records[0]
        self.assertEqual(rec.source_authority, "convenience")
        self.assertEqual(rec.source_class, "paid_api")
        obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
        self.assertEqual(obs.content["source_reliability"], "moderate")

    def test_yfinance_evidence_maps_to_fallback_authority(self):
        res = YFinanceAdapter(YF_FIXTURES).fetch({"subject": "IREN-HISTORY", "now": 0})
        rec = res.records[0]
        self.assertEqual(rec.source_authority, "fallback")
        self.assertEqual(rec.source_class, "free_api")
        obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
        self.assertEqual(obs.content["source_reliability"], "low")

    def test_unknown_subject_produces_error_not_silence(self):
        res = SecEdgarAdapter(SEC_FIXTURES).fetch({"subject": "NOPE", "now": 0})
        self.assertFalse(res.records)
        self.assertTrue(res.errors)
        self.assertFalse(res.complete)

    def test_adapter_result_exposes_partial_coverage(self):
        res = FmpAdapter(FMP_FIXTURES).fetch(
            {"subject": "IREN-PARTIAL", "fields": ("prior_value",), "now": 0}
        )
        self.assertFalse(res.complete)
        self.assertTrue(res.warnings)
        self.assertIn("partial coverage", res.warnings[0])


class ConflictTests(unittest.TestCase):
    def test_canonical_sec_value_wins_over_conflicting_fmp_value(self):
        sec = SecEdgarAdapter(SEC_FIXTURES).fetch({"subject": "IREN-REV", "now": 0}).records[0]
        fmp = FmpAdapter(FMP_FIXTURES).fetch({"subject": "IREN-REV", "now": 0}).records[0]
        # The two records genuinely differ by normalized_type (sec_xbrl_revenue vs
        # fmp_financial_revenue) but share metric + period -- arbitration keys on the
        # family-scoped financial fact identity, not the source-specific type.
        self.assertNotEqual(sec.normalized_type, fmp.normalized_type)
        resolved, warns = resolve_conflicts((sec, fmp))
        key = ("IREN-REV", "financial_fact", "revenue", "2026-03-31", "")
        self.assertEqual(resolved[key], 120.0)  # SEC canonical value wins
        self.assertTrue(warns)
        self.assertIn("conflict", warns[0])

    def test_equal_values_are_not_a_conflict(self):
        sec = SecEdgarAdapter(SEC_FIXTURES).fetch({"subject": "IREN-REV", "now": 0}).records[0]
        # A fallback record carrying the SAME metric/period ("revenue" @ 2026-03-31)
        # and identical value under a DIFFERENT normalized_type -- it groups on the
        # financial fact key, and equal values must NOT raise a conflict.
        yf_fixtures = {
            "IREN-REV": {
                "source_name": "yfinance",
                "raw_type": "history",
                "normalized_type": "yf_history_revenue",
                "ticker": "IREN",
                "period_end": "2026-03-31",
                "extracted_fields": {"financial_metric": "revenue", "metric_value": 120.0},
            }
        }
        yf = YFinanceAdapter(yf_fixtures).fetch({"subject": "IREN-REV", "now": 0}).records[0]
        self.assertNotEqual(sec.normalized_type, yf.normalized_type)
        _, warns = resolve_conflicts((sec, yf))
        self.assertEqual(warns, ())


class EvidenceRecordTests(unittest.TestCase):
    def test_raw_record_gets_stable_checksum(self):
        src = EvidenceSource("SEC EDGAR", "canonical", "official_filing")
        a = make_raw_evidence_record(
            src, subject="S", raw_type="8-K", raw_payload={"x": 1},
            retrieved_at="t", as_of="d", now=0,
        )
        b = make_raw_evidence_record(
            src, subject="S", raw_type="8-K", raw_payload={"x": 1},
            retrieved_at="LATER", as_of="d", now=99,  # non-content fields differ
        )
        c = make_raw_evidence_record(
            src, subject="S", raw_type="8-K", raw_payload={"x": 2},
            retrieved_at="t", as_of="d", now=0,
        )
        self.assertEqual(a.id, b.id)          # same payload -> same id/checksum
        self.assertEqual(a.checksum, a.id)
        self.assertNotEqual(a.id, c.id)       # different payload -> different id

    def test_normalized_record_preserves_source_provenance(self):
        raw = SecEdgarAdapter(SEC_FIXTURES).fetch(
            {"subject": "IREN-8K-2026Q2", "now": 0}
        ).records[0]
        # authority/class carried from raw source
        self.assertEqual(raw.source_authority, "canonical")
        self.assertEqual(raw.source_class, "official_filing")
        # provenance binds a RawEvidenceRecord
        kinds = [r.kind for r in raw.provenance.sources]
        self.assertIn("RawEvidenceRecord", kinds)


class MapperTests(unittest.TestCase):
    def test_missing_fields_produce_warnings_not_invented_values(self):
        raw = make_raw_evidence_record(
            EvidenceSource("SEC EDGAR", "canonical", "official_filing"),
            subject="IREN", raw_type="10-Q", raw_payload={"revenue": 120.0},
            retrieved_at="t", as_of="2026-03-31", now=0,
        )
        norm = make_normalized_evidence_record(
            raw, normalized_type="10-Q",
            extracted_fields={"financial_metric": "revenue", "metric_value": 120.0},
            period_end="2026-03-31", evidence_quality=0.9, confidence=0.9, now=0,
        )
        obs, warnings = map_to_observation(norm, domain="ai-infrastructure", now=0)
        self.assertTrue(any("prior_value" in w for w in warnings))
        self.assertIsNone(obs.content["prior_value"])  # not fabricated

    def test_mapper_produces_only_observation(self):
        rec = SecEdgarAdapter(SEC_FIXTURES).fetch(
            {"subject": "IREN-8K-2026Q2", "now": 0}
        ).records[0]
        obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
        self.assertIsInstance(obs, Observation)
        self.assertNotIsInstance(obs, OpportunityHypothesis)
        self.assertNotIsInstance(obs, InvestmentThesis)
        self.assertNotIsInstance(obs, InvestmentAction)
        self.assertNotIsInstance(obs, PersonalizedAction)
        # provenance binds a NormalizedEvidenceRecord
        kinds = [r.kind for r in obs.provenance.sources]
        self.assertEqual(kinds, ["NormalizedEvidenceRecord"])

    def test_rumor_evidence_cannot_raise_confidence(self):
        rumor_rec = _make_rumor_record()
        rumor_obs, _ = map_to_observation(rumor_rec, domain="ai-infrastructure", now=0)
        self.assertEqual(rumor_obs.content["catalyst_status"], "speculative_rumor")
        self.assertEqual(rumor_obs.content["source_reliability"], "low")

        # The SAME evidence marked confirmed (SEC canonical contract).
        confirmed_rec = SecEdgarAdapter(SEC_FIXTURES).fetch(
            {"subject": "IREN-CONTRACT", "now": 0}
        ).records[0]
        confirmed_obs, _ = map_to_observation(confirmed_rec, domain="ai-infrastructure", now=0)
        self.assertEqual(confirmed_obs.content["catalyst_status"], "confirmed")

        # Prove the discount via the real Tattva assessment.
        ia_rumor = generate_intelligence_assessment(
            [rumor_obs], domain="ai-infrastructure", now=0
        )
        ia_conf = generate_intelligence_assessment(
            [confirmed_obs], domain="ai-infrastructure", now=0
        )
        self.assertLess(ia_rumor.confidence, ia_conf.confidence)


class DeterminismTests(unittest.TestCase):
    def test_deterministic_fixture_ingestion(self):
        def run():
            rec = SecEdgarAdapter(SEC_FIXTURES).fetch(
                {"subject": "IREN-8K-2026Q2", "now": 0}
            ).records[0]
            obs, _ = map_to_observation(rec, domain="ai-infrastructure", now=0)
            return rec.id, obs.id

        self.assertEqual(run(), run())


# --------------------------------------------------------------------------- #
# Static / structural guards.                                                  #
# --------------------------------------------------------------------------- #

_PKG_DIR = os.path.join(_SRC, "evidence_ingestion")


def _pkg_sources():
    for name in os.listdir(_PKG_DIR):
        if name.endswith(".py"):
            with open(os.path.join(_PKG_DIR, name), "r") as fh:
                yield name, fh.read()


class GuardTests(unittest.TestCase):
    def test_no_network_imports(self):
        banned = {"requests", "urllib", "http", "socket", "aiohttp", "httpx"}
        for name, src in _pkg_sources():
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        top = a.name.split(".")[0]
                        self.assertNotIn(top, banned, "{0} imports {1}".format(name, top))
                elif isinstance(node, ast.ImportFrom):
                    top = (node.module or "").split(".")[0]
                    self.assertNotIn(top, banned, "{0} imports {1}".format(name, top))

    def test_no_secrets_or_api_keys(self):
        # Guard against secret *assignments* and environment secret reads -- an
        # AST scan, so prose in docstrings/comments is not a false positive.
        banned_ids = ("api_key", "apikey", "secret", "token", "password", "access_key")
        for name, src in _pkg_sources():
            tree = ast.parse(src)
            for node in ast.walk(tree):
                # No os.environ / getenv access anywhere.
                if isinstance(node, ast.Attribute):
                    self.assertNotEqual(
                        node.attr, "environ", "{0} reads os.environ".format(name)
                    )
                if isinstance(node, ast.Name):
                    self.assertNotIn(
                        node.id, ("getenv",), "{0} calls getenv".format(name)
                    )
                # No assignment target named like a secret/key/token/password.
                if isinstance(node, ast.Assign):
                    for tgt in node.targets:
                        if isinstance(tgt, ast.Name):
                            low = tgt.id.lower()
                            for b in banned_ids:
                                self.assertNotIn(
                                    b, low, "{0} assigns secret-like {1}".format(name, tgt.id)
                                )

    def test_evidence_ingestion_imports_no_reasoning_layer(self):
        banned = {"genesis", "prometheus", "personal_cio", "execution_manual"}
        for name, src in _pkg_sources():
            tree = ast.parse(src)
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [(node.module or "").split(".")[0]]
                for m in mods:
                    self.assertNotIn(m, banned, "{0} imports reasoning layer {1}".format(name, m))


def _make_rumor_record():
    raw = make_raw_evidence_record(
        _rumor_source(), subject="IREN", ticker="IREN", raw_type="rumor",
        raw_payload={"chatter": "unverified contract win"},
        retrieved_at="t", as_of="2026-05-01", now=0,
    )
    return make_normalized_evidence_record(
        raw, normalized_type="rumor",
        extracted_fields={"catalyst_type": "contract_win", "expected_direction": "positive"},
        event_date="2026-05-01", evidence_quality=0.9, confidence=0.9, now=0,
    )


if __name__ == "__main__":
    unittest.main()
