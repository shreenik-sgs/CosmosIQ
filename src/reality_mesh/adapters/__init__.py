"""Source adapters for the Reality Mesh (IMPLEMENTATION-014A).

The source/ingestion plane specified in ``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013.md``:
adapters emit :class:`~reality_mesh.models.RealityEvent`s ONLY (never an ``AgentFinding`` --
they observe, they do not interpret), assign source authority immediately, preserve raw
payload refs, and turn every source failure into a VISIBLE gap/health record -- never a
crash, never a fabricated value, never a silent demo fallback.

This slice contains the adapter runtime (:mod:`reality_mesh.adapters.base`), the FIRST
concrete adapter, the LOCAL-FILE-BACKED :class:`LocalMarketDataAdapter`
(:mod:`reality_mesh.adapters.local_market_data`) feeding the Market Regime / Sector Rotation
/ Theme Rotation agents -- LOCAL FILES ONLY: no credential, no rate limit -- and the 014B
SEC/FMP evidence adapter :class:`SecFmpEvidenceAdapter`
(:mod:`reality_mesh.adapters.evidence_sources`) feeding the News/Filings +
Financial-Inflection consumers via explicitly INJECTED transports (the 010D bundle shape).
There is still NO production network path (that is the LAST onboarding stage of the
contract's §4 sequence and does not exist in this slice -- ``fetch_checked`` refuses a
``network_required`` adapter unless its transports were injected, in which case no ambient
network is possible).

Deterministic, stdlib-only, Python 3.9, OFFLINE. No scheduler / broker / trading / scoring.
"""

from __future__ import annotations

from .base import (
    ADAPTER_CREDENTIALS_STATUSES,
    ADAPTER_FAILURE_MODES,
    ADAPTER_RATE_LIMIT_STATUSES,
    ADAPTER_RESULT_STATUSES,
    ADAPTER_SOURCE_HEALTH_LABELS,
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
    source_health_from_result,
)
from .evidence_sources import (
    FINANCIAL_INFLECTION_CONSUMER_GAP,
    FMP_TRANSPORT_KEYS,
    SEC_FMP_EVIDENCE_ADAPTER_ID,
    SEC_FMP_EVIDENCE_DESCRIPTOR,
    SEC_FMP_EVIDENCE_DISCIPLINES,
    SEC_TRANSPORT_KEYS,
    SecFmpEvidenceAdapter,
)
from .local_market_data import (
    LOCAL_MARKET_DATA_ADAPTER_ID,
    LOCAL_MARKET_DATA_DESCRIPTOR,
    LOCAL_MARKET_DATA_DISCIPLINES,
    LOCAL_MARKET_DATA_FILES,
    STALE_AFTER_HOURS,
    LocalMarketDataAdapter,
)

__all__ = [
    # runtime (base)
    "ADAPTER_RESULT_STATUSES",
    "ADAPTER_CREDENTIALS_STATUSES",
    "ADAPTER_RATE_LIMIT_STATUSES",
    "ADAPTER_FAILURE_MODES",
    "ADAPTER_SOURCE_HEALTH_LABELS",
    "SourceAdapterDescriptor",
    "SourceAdapterResult",
    "SourceAdapter",
    "deterministic_adapter_run_id",
    "source_health_from_result",
    # local market-data adapter
    "LOCAL_MARKET_DATA_ADAPTER_ID",
    "LOCAL_MARKET_DATA_DESCRIPTOR",
    "LOCAL_MARKET_DATA_DISCIPLINES",
    "LOCAL_MARKET_DATA_FILES",
    "STALE_AFTER_HOURS",
    "LocalMarketDataAdapter",
    # SEC/FMP evidence adapter (014B)
    "SEC_FMP_EVIDENCE_ADAPTER_ID",
    "SEC_FMP_EVIDENCE_DESCRIPTOR",
    "SEC_FMP_EVIDENCE_DISCIPLINES",
    "SEC_TRANSPORT_KEYS",
    "FMP_TRANSPORT_KEYS",
    "FINANCIAL_INFLECTION_CONSUMER_GAP",
    "SecFmpEvidenceAdapter",
]
