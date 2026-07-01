"""Conflict resolver -- when two sources disagree, the higher authority wins.

Given several NormalizedEvidenceRecords, group their extracted fields by
``(subject, normalized_type, field)``. When the same field carries DIFFERENT
values from sources of different authority, keep the value from the highest
``authority_rank`` (a canonical SEC filing beats a convenience FMP row) and emit
a conflict warning naming both sources and both values. Equal values are not a
conflict. This performs NO investment judgement -- only trust arbitration over
evidence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .source_model import authority_rank
from .evidence_records import NormalizedEvidenceRecord


def resolve_conflicts(
    normalized_records: Tuple[NormalizedEvidenceRecord, ...],
) -> Tuple[Dict[Tuple[str, str, str], Any], Tuple[str, ...]]:
    """Resolve field-level conflicts across records by source authority.

    Returns ``(resolved, conflict_warnings)`` where ``resolved`` maps
    ``(subject, normalized_type, field)`` -> the winning value.
    """
    records = list(normalized_records)

    # Collect every (key -> list of (value, record)) observation.
    grouped: Dict[Tuple[str, str, str], List[Tuple[Any, NormalizedEvidenceRecord]]] = {}
    for rec in records:
        for field, value in (rec.extracted_fields or {}).items():
            key = (rec.subject, rec.normalized_type, field)
            grouped.setdefault(key, []).append((value, rec))

    resolved: Dict[Tuple[str, str, str], Any] = {}
    warnings: List[str] = []

    for key, entries in grouped.items():
        # Winner = highest authority rank; ties keep first-seen.
        winner_value, winner_rec = max(
            entries, key=lambda vr: authority_rank(vr[1].source_authority)
        )
        resolved[key] = winner_value

        for value, rec in entries:
            if rec is winner_rec:
                continue
            if value != winner_value:
                subject, normalized_type, field = key
                warnings.append(
                    "conflict on {0}/{1}/{2}: kept {3!r} from {4} ({5}) over "
                    "{6!r} from {7} ({8})".format(
                        subject,
                        normalized_type,
                        field,
                        winner_value,
                        winner_rec.source.source_name if winner_rec.source else "?",
                        winner_rec.source_authority,
                        value,
                        rec.source.source_name if rec.source else "?",
                        rec.source_authority,
                    )
                )

    return resolved, tuple(warnings)
