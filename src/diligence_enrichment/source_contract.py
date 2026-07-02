"""Source-authority + claim-status CONTRACT for diligence enrichment (IMPLEMENTATION-011A).

Pure, offline metadata. This module REUSES and stays ALIGNED WITH the existing evidence
ingestion authority order (``evidence_ingestion.source_model``) -- it does NOT weaken it.
Canonical / primary (SEC filings, company IR / investor presentations, official transcripts,
regulatory) outrank convenience (FMP), which outranks fallback (yfinance), which outranks
manual / analyst. A manual / analyst estimate is NEVER canonical.

Two orthogonal vocabularies:

* **Source authority** (how much the ORIGIN may be trusted) -- reused verbatim from
  ``source_model`` (``canonical`` / ``primary`` / ``convenience`` / ``fallback`` /
  ``manual`` / ``rumor``), with the same total order (``authority_rank``).
* **Claim status** (what KIND of assertion the datum is): ``verified_fact`` /
  ``company_claim`` / ``analyst_estimate`` / ``inferred`` / ``manual``. A company statement
  is ``company_claim``, not ``verified_fact``.

The mapping from a diligence SOURCE CATEGORY (sec_filing, investor_presentation, fmp, ...)
to its authority + default claim status lives here.
"""

from __future__ import annotations

from typing import Tuple

from evidence_ingestion.source_model import (  # reuse, do NOT redefine
    SOURCE_AUTHORITIES,
    authority_rank,
)

# The closed claim-status vocabulary for enrichment values.
CLAIM_STATUSES = frozenset(
    {"verified_fact", "company_claim", "analyst_estimate", "inferred", "manual"}
)


class ClaimStatus:
    """Named constants for the claim-status vocabulary (readability helper)."""
    VERIFIED_FACT = "verified_fact"
    COMPANY_CLAIM = "company_claim"
    ANALYST_ESTIMATE = "analyst_estimate"
    INFERRED = "inferred"
    MANUAL = "manual"


# Diligence source CATEGORIES -> (authority, default claim status). Every authority value
# is a member of the existing ``SOURCE_AUTHORITIES`` set -- nothing new is invented, and
# manual / analyst never map to ``canonical``.
_CATEGORY_TO_AUTHORITY_CLAIM = {
    # canonical / primary
    "sec_filing": ("canonical", ClaimStatus.VERIFIED_FACT),
    "regulatory": ("canonical", ClaimStatus.VERIFIED_FACT),
    "company_ir": ("primary", ClaimStatus.COMPANY_CLAIM),
    "investor_presentation": ("primary", ClaimStatus.COMPANY_CLAIM),
    "earnings_transcript": ("primary", ClaimStatus.COMPANY_CLAIM),
    "press_release": ("primary", ClaimStatus.COMPANY_CLAIM),
    # convenience (FMP)
    "fmp": ("convenience", ClaimStatus.VERIFIED_FACT),
    "market_data": ("convenience", ClaimStatus.VERIFIED_FACT),
    # fallback (yfinance)
    "yfinance": ("fallback", ClaimStatus.VERIFIED_FACT),
    "free_api": ("fallback", ClaimStatus.VERIFIED_FACT),
    # manual / analyst -- NEVER canonical
    "manual": ("manual", ClaimStatus.MANUAL),
    "analyst_estimate": ("manual", ClaimStatus.ANALYST_ESTIMATE),
    "inferred": ("manual", ClaimStatus.INFERRED),
}

SOURCE_CATEGORIES = frozenset(_CATEGORY_TO_AUTHORITY_CLAIM.keys())


def authority_for_category(category: str) -> str:
    """Map a diligence source category to its source authority. Unknown -> ValueError."""
    if category not in _CATEGORY_TO_AUTHORITY_CLAIM:
        raise ValueError(
            "unknown enrichment source category: {0} (allowed: {1})".format(
                category, sorted(SOURCE_CATEGORIES)))
    return _CATEGORY_TO_AUTHORITY_CLAIM[category][0]


def claim_status_for_category(category: str) -> str:
    """Map a diligence source category to its DEFAULT claim status. Unknown -> ValueError."""
    if category not in _CATEGORY_TO_AUTHORITY_CLAIM:
        raise ValueError(
            "unknown enrichment source category: {0} (allowed: {1})".format(
                category, sorted(SOURCE_CATEGORIES)))
    return _CATEGORY_TO_AUTHORITY_CLAIM[category][1]


def is_canonical(authority: str) -> bool:
    """True iff the authority is the top canonical tier."""
    return authority == "canonical"


def mark_company_claim(value):
    """Return a copy of an :class:`EnrichmentValue` marked ``company_claim``.

    A company statement (guidance, an IR-deck assertion) is a CLAIM the company made, not a
    verified fact -- this stamps it as such without changing the datum. Imported lazily to
    keep this contract module free of model-layer import cycles.
    """
    from dataclasses import replace
    return replace(value, claim_status=ClaimStatus.COMPANY_CLAIM)


def assert_manual_not_canonical(authority: str, claim_status: str = "") -> None:
    """Guard: a manual / analyst datum must NEVER be treated as canonical.

    Raises ``ValueError`` if a ``manual`` / ``analyst_estimate`` / ``manual``-authority datum
    is stamped ``canonical``. Used by the adapters so a manual TAM can never be laundered into
    a canonical fact.
    """
    manual_like = (
        authority == "manual"
        or claim_status in (ClaimStatus.MANUAL, ClaimStatus.ANALYST_ESTIMATE))
    if manual_like and is_canonical(authority):
        raise ValueError(
            "invariant violated: a manual / analyst estimate was marked canonical")
    if claim_status in (ClaimStatus.MANUAL, ClaimStatus.ANALYST_ESTIMATE) and authority == "canonical":
        raise ValueError(
            "invariant violated: an analyst estimate was marked canonical")


def manual_is_not_canonical() -> bool:
    """Structural proof that ``manual`` ranks strictly below ``canonical`` in the reused order."""
    return authority_rank("manual") < authority_rank("canonical")


def ordered_authorities() -> Tuple[str, ...]:
    """The reused authorities, strongest first (for display / tests)."""
    return tuple(sorted(SOURCE_AUTHORITIES, key=authority_rank, reverse=True))
