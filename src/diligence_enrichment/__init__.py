"""Investment Diligence Input Enrichment Foundation (IMPLEMENTATION-011A).

A disciplined ENRICHMENT layer of typed models + source contracts + fixture-backed
adapters. It collects, normalizes, traces and feeds the missing diligence INPUTS
(market cap, TAM, value-chain, bottleneck, company IR, leadership, ...) into
terrain / Nivesha WITHOUT inventing them.

These are EVIDENCE / ENRICHMENT models, NOT investment-decision models: there is NO
buy / sell / hold field, NO rank / score / rating field, and NO numeric investability
metric anywhere. The package introduces no new scoring, ranking or reasoning and does
NOT change Nivesha / Sphurana / Tattva logic.

Source authority stays EXPLICIT and is never weakened: canonical / primary (SEC
filings, company IR / investor presentations, official transcripts, regulatory) >
convenience (FMP) > fallback (yfinance) > manual / analyst. Manual / analyst estimates
are NEVER treated as canonical; company statements are marked ``company_claim`` (never
``verified_fact``); an unsupported field becomes an explicit DATA GAP, never a
fabricated value.

Deterministic, stdlib-only, Python 3.9. No network on import, no network anywhere in
this package, no scheduler, no broker, no OCR, no scraping.
"""

from __future__ import annotations

from .models import (
    BottleneckEvidenceProfile,
    CompanyDiligenceProfile,
    CompanyIREvidenceProfile,
    DiligenceEnrichmentBundle,
    EnrichmentValue,
    LeadershipEvidenceProfile,
    LeadershipMember,
    MarketAndValuationSnapshot,
    TAMRevenuePoolEstimate,
    ValueChainEvidenceProfile,
    ValueChainLayerEvidence,
)
from .source_contract import (
    CLAIM_STATUSES,
    SOURCE_CATEGORIES,
    ClaimStatus,
    assert_manual_not_canonical,
    authority_for_category,
    claim_status_for_category,
    is_canonical,
    manual_is_not_canonical,
    mark_company_claim,
)
from .enrich import build_diligence_enrichment_bundle
from .coverage import (
    EnrichmentAreaCoverage,
    EnrichmentCoverageDiagnostic,
    TickerEnrichmentCoverage,
    build_enrichment_coverage,
)
from .nivesha_adapter import (
    InvestmentDiligenceInputMapping,
    MappedField,
    NiveshaInputMapping,
    run_nivesha_thesis_on_enrichment,
    to_nivesha_diligence_inputs,
)

__all__ = [
    "BottleneckEvidenceProfile",
    "CompanyDiligenceProfile",
    "CompanyIREvidenceProfile",
    "DiligenceEnrichmentBundle",
    "EnrichmentValue",
    "LeadershipEvidenceProfile",
    "LeadershipMember",
    "MarketAndValuationSnapshot",
    "TAMRevenuePoolEstimate",
    "ValueChainEvidenceProfile",
    "ValueChainLayerEvidence",
    "CLAIM_STATUSES",
    "SOURCE_CATEGORIES",
    "ClaimStatus",
    "assert_manual_not_canonical",
    "authority_for_category",
    "claim_status_for_category",
    "is_canonical",
    "manual_is_not_canonical",
    "mark_company_claim",
    "build_diligence_enrichment_bundle",
    "EnrichmentAreaCoverage",
    "EnrichmentCoverageDiagnostic",
    "TickerEnrichmentCoverage",
    "build_enrichment_coverage",
    "MappedField",
    "NiveshaInputMapping",
    "InvestmentDiligenceInputMapping",
    "run_nivesha_thesis_on_enrichment",
    "to_nivesha_diligence_inputs",
]
