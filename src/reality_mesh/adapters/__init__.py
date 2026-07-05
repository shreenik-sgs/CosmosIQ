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
Financial-Inflection consumers via explicitly INJECTED transports (the 010D bundle shape),
and the 014C company IR documents adapter :class:`CompanyDocumentsAdapter`
(:mod:`reality_mesh.adapters.company_documents`) reading OPERATOR-DROPPED local
investor-presentation / earnings-transcript extracts -- everything a company says about
itself is a ``company_claim`` at ``primary`` authority, never a verified fact, never
canonical.
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
from .company_documents import (
    COMPANY_DOCUMENTS_ADAPTER_ID,
    COMPANY_DOCUMENTS_DESCRIPTOR,
    COMPANY_DOCUMENTS_DISCIPLINES,
    DESCRIPTOR_ONLY_CONSUMER_GAPS,
    DOCUMENT_STALE_AFTER_DAYS,
    IR_DECK_FILENAMES,
    TAM_NOT_INDEPENDENTLY_VERIFIED_GAP,
    TRANSCRIPT_FILE_PREFIX,
    CompanyDocumentsAdapter,
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
from .sec_edgar_live import (
    SEC_EDGAR_LIVE_ADAPTER_ID,
    SEC_EDGAR_LIVE_DESCRIPTOR,
    SEC_EDGAR_LIVE_DISCIPLINES,
    SEC_EDGAR_LIVE_EVENT_TYPES,
    SEC_EDGAR_LIVE_FULL_BODY_FOLLOWUP_GAP,
    SEC_EDGAR_LIVE_MINIMUM_FORMS,
    SEC_EDGAR_LIVE_RISK_EVENT_TYPES,
    SEC_EDGAR_LIVE_TRANSPORT_KEYS,
    SecEdgarLiveAdapter,
)
from .local_macro_data import (
    LOCAL_MACRO_DATA_ADAPTER_ID,
    LOCAL_MACRO_DATA_DESCRIPTOR,
    LOCAL_MACRO_DATA_DISCIPLINES,
    MACRO_READINGS_FILENAME,
    MACRO_STALE_AFTER_HOURS,
    LocalMacroDataAdapter,
)
from .local_market_data import (
    LOCAL_MARKET_DATA_ADAPTER_ID,
    LOCAL_MARKET_DATA_DESCRIPTOR,
    LOCAL_MARKET_DATA_DISCIPLINES,
    LOCAL_MARKET_DATA_FILES,
    STALE_AFTER_HOURS,
    LocalMarketDataAdapter,
)
from .local_price_history import (
    LOCAL_PRICE_HISTORY_ADAPTER_ID,
    LOCAL_PRICE_HISTORY_DESCRIPTOR,
    LOCAL_PRICE_HISTORY_DISCIPLINES,
    PRICE_HISTORY_FILE_SUFFIX,
    PRICE_HISTORY_INDICATOR_UNITS,
    PRICE_HISTORY_STALE_AFTER_HOURS,
    LocalPriceHistoryAdapter,
)
from .social_exports import (
    PROMOTER_BOT_RISK_VISIBLE_PCT,
    SOCIAL_EXPORT_ACCOUNT_TYPES,
    SOCIAL_EXPORT_FILE_PREFIX,
    SOCIAL_EXPORT_STALE_AFTER_HOURS,
    SOCIAL_EXPORTS_ADAPTER_ID,
    SOCIAL_EXPORTS_DESCRIPTOR,
    SOCIAL_EXPORTS_DISCIPLINES,
    SocialExportsAdapter,
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
    # local macro-data adapter (014F)
    "LOCAL_MACRO_DATA_ADAPTER_ID",
    "LOCAL_MACRO_DATA_DESCRIPTOR",
    "LOCAL_MACRO_DATA_DISCIPLINES",
    "MACRO_READINGS_FILENAME",
    "MACRO_STALE_AFTER_HOURS",
    "LocalMacroDataAdapter",
    # local market-data adapter
    "LOCAL_MARKET_DATA_ADAPTER_ID",
    "LOCAL_MARKET_DATA_DESCRIPTOR",
    "LOCAL_MARKET_DATA_DISCIPLINES",
    "LOCAL_MARKET_DATA_FILES",
    "STALE_AFTER_HOURS",
    "LocalMarketDataAdapter",
    # local price-history adapter (014D)
    "LOCAL_PRICE_HISTORY_ADAPTER_ID",
    "LOCAL_PRICE_HISTORY_DESCRIPTOR",
    "LOCAL_PRICE_HISTORY_DISCIPLINES",
    "PRICE_HISTORY_FILE_SUFFIX",
    "PRICE_HISTORY_INDICATOR_UNITS",
    "PRICE_HISTORY_STALE_AFTER_HOURS",
    "LocalPriceHistoryAdapter",
    # SEC/FMP evidence adapter (014B)
    "SEC_FMP_EVIDENCE_ADAPTER_ID",
    "SEC_FMP_EVIDENCE_DESCRIPTOR",
    "SEC_FMP_EVIDENCE_DISCIPLINES",
    "SEC_TRANSPORT_KEYS",
    "FMP_TRANSPORT_KEYS",
    "FINANCIAL_INFLECTION_CONSUMER_GAP",
    "SecFmpEvidenceAdapter",
    # SEC EDGAR live filings adapter -- first production LIVE source (020B)
    "SEC_EDGAR_LIVE_ADAPTER_ID",
    "SEC_EDGAR_LIVE_DESCRIPTOR",
    "SEC_EDGAR_LIVE_DISCIPLINES",
    "SEC_EDGAR_LIVE_TRANSPORT_KEYS",
    "SEC_EDGAR_LIVE_EVENT_TYPES",
    "SEC_EDGAR_LIVE_RISK_EVENT_TYPES",
    "SEC_EDGAR_LIVE_MINIMUM_FORMS",
    "SEC_EDGAR_LIVE_FULL_BODY_FOLLOWUP_GAP",
    "SecEdgarLiveAdapter",
    # company IR documents adapter (014C)
    "COMPANY_DOCUMENTS_ADAPTER_ID",
    "COMPANY_DOCUMENTS_DESCRIPTOR",
    "COMPANY_DOCUMENTS_DISCIPLINES",
    "DESCRIPTOR_ONLY_CONSUMER_GAPS",
    "DOCUMENT_STALE_AFTER_DAYS",
    "IR_DECK_FILENAMES",
    "TAM_NOT_INDEPENDENTLY_VERIFIED_GAP",
    "TRANSCRIPT_FILE_PREFIX",
    "CompanyDocumentsAdapter",
    # X/social local-export adapter (014E)
    "SOCIAL_EXPORTS_ADAPTER_ID",
    "SOCIAL_EXPORTS_DESCRIPTOR",
    "SOCIAL_EXPORTS_DISCIPLINES",
    "SOCIAL_EXPORT_FILE_PREFIX",
    "SOCIAL_EXPORT_STALE_AFTER_HOURS",
    "SOCIAL_EXPORT_ACCOUNT_TYPES",
    "PROMOTER_BOT_RISK_VISIBLE_PCT",
    "SocialExportsAdapter",
]
