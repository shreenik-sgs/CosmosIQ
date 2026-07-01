"""evidence_ingestion -- the evidence-ingestion FOUNDATION (IMPLEMENTATION-009A).

Source-authority/class models, provenance-bearing evidence records, fixture-backed
(NO network) source-adapter contracts, a trust-based conflict resolver, and a
mapper that produces ONLY canonical Tattva Observations. This layer captures and
normalises *evidence*; it makes no investment judgement and imports no
reasoning-conclusion layer (genesis / prometheus / personal_cio / execution_manual).
"""

from __future__ import annotations

from .source_model import (
    SOURCE_AUTHORITIES,
    SOURCE_CLASSES,
    EvidenceSource,
    authority_rank,
    authority_for_source_class,
)
from .evidence_records import (
    RawEvidenceRecord,
    NormalizedEvidenceRecord,
    make_raw_evidence_record,
    make_normalized_evidence_record,
)
from .adapters import (
    AdapterResult,
    SourceAdapter,
    SecEdgarAdapter,
    FmpAdapter,
    YFinanceAdapter,
)
from .mapper import map_to_observation
from .conflict import resolve_conflicts, winning_records
from .vertical_slice import (
    run_fixture_ingestion_slice,
    IngestionVerticalSliceResult,
    ProvenanceChain,
    ProvenanceTraceEntry,
)
from .sec_edgar import (
    SEC_SOURCE_NAME,
    SEC_PROVIDER,
    sec_source,
    classify_form,
    detect_offering_flags,
    parse_sec_submissions,
    parse_sec_companyfacts,
)
from .sec_client import SecEdgarClient
from .fmp import (
    FMP_SOURCE_NAME,
    FMP_PROVIDER,
    fmp_source,
    parse_fmp_profile,
    parse_fmp_income_statement,
    parse_fmp_ohlcv,
    parse_fmp_news,
    parse_fmp_ownership,
    map_fmp_record,
    mapping_deferred_reason,
    MappingDeferredError,
)
from .fmp_client import FmpClient
from .yfinance_adapter import (
    YF_SOURCE_NAME,
    YF_PROVIDER,
    YF_RESEARCH_NOTE,
    yf_source,
    parse_yfinance_history,
    parse_yfinance_quote,
    map_yfinance_record,
    mapping_deferred_reason as yf_mapping_deferred_reason,
)
from .yfinance_client import YFinanceClient

__all__ = [
    "SOURCE_AUTHORITIES",
    "SOURCE_CLASSES",
    "EvidenceSource",
    "authority_rank",
    "authority_for_source_class",
    "RawEvidenceRecord",
    "NormalizedEvidenceRecord",
    "make_raw_evidence_record",
    "make_normalized_evidence_record",
    "AdapterResult",
    "SourceAdapter",
    "SecEdgarAdapter",
    "FmpAdapter",
    "YFinanceAdapter",
    "map_to_observation",
    "resolve_conflicts",
    "winning_records",
    "run_fixture_ingestion_slice",
    "IngestionVerticalSliceResult",
    "ProvenanceChain",
    "ProvenanceTraceEntry",
    "SEC_SOURCE_NAME",
    "SEC_PROVIDER",
    "sec_source",
    "classify_form",
    "detect_offering_flags",
    "parse_sec_submissions",
    "parse_sec_companyfacts",
    "SecEdgarClient",
    "FMP_SOURCE_NAME",
    "FMP_PROVIDER",
    "fmp_source",
    "parse_fmp_profile",
    "parse_fmp_income_statement",
    "parse_fmp_ohlcv",
    "parse_fmp_news",
    "parse_fmp_ownership",
    "map_fmp_record",
    "mapping_deferred_reason",
    "MappingDeferredError",
    "FmpClient",
    "YF_SOURCE_NAME",
    "YF_PROVIDER",
    "YF_RESEARCH_NOTE",
    "yf_source",
    "parse_yfinance_history",
    "parse_yfinance_quote",
    "map_yfinance_record",
    "yf_mapping_deferred_reason",
    "YFinanceClient",
]
