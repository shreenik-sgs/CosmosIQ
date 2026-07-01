"""Source-authority and source-class models for evidence ingestion.

Every piece of evidence carries a *source authority* -- how much the system may
trust the origin -- and a *source class* -- the concrete kind of origin. The
class deterministically implies a default authority (``authority_for_source_class``)
and authorities are totally ordered (``authority_rank``) so a conflict resolver
can prefer a canonical SEC filing over a convenience API without any judgement
about the underlying facts.

This module is pure metadata + validation. It performs NO network access, reads
NO secrets, and holds NO API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# How much the origin may be trusted, from most to least authoritative.
SOURCE_AUTHORITIES = frozenset(
    {"canonical", "primary", "convenience", "fallback", "manual", "rumor"}
)

# Total ordering over authorities -- higher wins a conflict.
_AUTHORITY_ORDER = {
    "canonical": 6,
    "primary": 5,
    "convenience": 4,
    "manual": 3,
    "fallback": 2,
    "rumor": 1,
}

# The concrete kind of origin a piece of evidence came from.
SOURCE_CLASSES = frozenset(
    {
        "official_filing",
        "company_ir",
        "paid_api",
        "free_api",
        "manual_input",
        "market_data",
        "regulatory",
        "press_release",
        "rumor_or_unverified",
    }
)

# Deterministic class -> default authority mapping.
_CLASS_TO_AUTHORITY = {
    "official_filing": "canonical",
    "regulatory": "canonical",
    "company_ir": "primary",
    "press_release": "primary",
    "paid_api": "convenience",
    "market_data": "convenience",
    "free_api": "fallback",
    "manual_input": "manual",
    "rumor_or_unverified": "rumor",
}


def authority_rank(authority: str) -> int:
    """Return the total-ordering rank of a source authority (higher = stronger)."""
    if authority not in _AUTHORITY_ORDER:
        raise ValueError(
            "unknown source_authority: {0} (allowed: {1})".format(
                authority, sorted(SOURCE_AUTHORITIES)
            )
        )
    return _AUTHORITY_ORDER[authority]


def authority_for_source_class(source_class: str) -> str:
    """Map a source class to its default authority. Unknown class -> ValueError.

    No silent acceptance: an unrecognised class is an error, never a default.
    """
    if source_class not in _CLASS_TO_AUTHORITY:
        raise ValueError(
            "unknown source_class: {0} (allowed: {1})".format(
                source_class, sorted(SOURCE_CLASSES)
            )
        )
    return _CLASS_TO_AUTHORITY[source_class]


@dataclass(frozen=True)
class EvidenceSource:
    """Immutable description of where a piece of evidence came from."""

    source_name: str
    source_authority: str
    source_class: str
    source_ref: str = ""
    provider: str = ""
    retrieved_at: str = ""
    as_of: str = ""
    license_note: str = ""
    reliability: Optional[object] = None

    def __post_init__(self) -> None:
        if self.source_authority not in SOURCE_AUTHORITIES:
            raise ValueError(
                "unknown source_authority: {0} (allowed: {1})".format(
                    self.source_authority, sorted(SOURCE_AUTHORITIES)
                )
            )
        if self.source_class not in SOURCE_CLASSES:
            raise ValueError(
                "unknown source_class: {0} (allowed: {1})".format(
                    self.source_class, sorted(SOURCE_CLASSES)
                )
            )
