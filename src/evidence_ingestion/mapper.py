"""IngestionToObservationMapper -- turn a NormalizedEvidenceRecord into a
canonical Tattva ``Observation`` and NOTHING else.

This is the seam between the evidence-ingestion layer and the reality-intelligence
(Tattva) layer. It produces ONLY an ``Observation`` -- never an
OpportunityHypothesis, InvestmentThesis, InvestmentAction, PersonalizedAction, or
any other reasoning/conclusion object. It performs no scoring and forms no
opinion: it maps trust metadata to Tattva's existing hint vocabulary and lets the
downstream Intelligence Assessment do the (discounted) inference.

Discipline enforced here:
* authority -> ``source_reliability`` (canonical/primary=high, convenience/manual=
  moderate, fallback/rumor=low);
* a rumor catalyst is stamped ``catalyst_status="speculative_rumor"`` so Tattva's
  status weight discounts it -- a rumor can never inflate confidence;
* fields absent from ``extracted_fields`` become explicit warnings, NEVER
  fabricated values.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional, Tuple

from eios_core.ids import iso_from_epoch
from eios_core.provenance import make_provenance

from reality_intelligence.source_observation import make_source_observation, SOURCE_TYPES

from .evidence_records import NormalizedEvidenceRecord


# Authority -> source-reliability tag Tattva understands.
_AUTHORITY_TO_RELIABILITY = {
    "canonical": "high",
    "primary": "high",
    "convenience": "moderate",
    "manual": "moderate",
    "fallback": "low",
    "rumor": "low",
}

# Authority -> catalyst confirmation discipline. A rumor is ALWAYS
# speculative_rumor so the Tattva status weight discounts it.
_AUTHORITY_TO_CATALYST_STATUS = {
    "canonical": "confirmed",
    "primary": "confirmed",
    "convenience": "probable",
    "manual": "probable",
    "fallback": "possible",
    "rumor": "speculative_rumor",
}

# Source types that represent a catalyst event (drive Tattva catalyst extraction).
_CATALYST_SOURCE_TYPES = frozenset(
    {"contract_win", "capital_structure_event", "press_release", "regulatory_event", "sec_filing"}
)

# Default catalyst_type derived from the chosen source_type when the fixture
# does not name one explicitly.
_SOURCE_TYPE_DEFAULT_CATALYST = {
    "contract_win": "contract_win",
    "capital_structure_event": "capital_structure",
    "press_release": "announcement",
    "regulatory_event": "regulatory",
    "sec_filing": "filing_event",
}


def _pick_source_type(normalized_type: str, source_class: str) -> str:
    """Map a normalized_type/source_class to a valid Tattva SOURCE_TYPES member.

    Unknown / unmappable combinations raise ValueError (no silent default).
    """
    nt = str(normalized_type or "").lower()
    sc = str(source_class or "").lower()

    def has(*needles: str) -> bool:
        return any(n in nt for n in needles)

    # Capital-structure events (dilution / shelf / ATM / offerings).
    if has("s-3", "s3", "424b", "atm", "shelf", "capital", "offering", "dilut"):
        st = "capital_structure_event"
    # Financial reports (periodic financials / XBRL).
    elif has("10-k", "10k", "10-q", "10q", "xbrl", "financial", "earnings"):
        st = "financial_report"
    # Contracts / material events (8-K).
    elif has("contract", "8-k", "8k", "material_event"):
        st = "contract_win"
    elif sc == "rumor_or_unverified" or has("rumor", "unverified", "chatter"):
        st = "news_excerpt"
    elif sc == "press_release" or has("press_release", "press release"):
        st = "press_release"
    elif sc == "regulatory" or has("regulatory", "regulation"):
        st = "regulatory_event"
    elif sc == "official_filing":
        st = "sec_filing"
    elif sc in ("paid_api", "free_api", "market_data") and has("news"):
        st = "news_excerpt"
    else:
        raise ValueError(
            "cannot map normalized_type={0!r} / source_class={1!r} to a source_type".format(
                normalized_type, source_class
            )
        )
    if st not in SOURCE_TYPES:  # defensive; every branch above is a valid member
        raise ValueError("derived source_type not in SOURCE_TYPES: {0}".format(st))
    return st


# Fields the mapper expects (and will warn about if absent) per category.
_EXPECTED_FIELDS = {
    "financial_report": ("financial_metric", "metric_value", "prior_value"),
}
_EXPECTED_CATALYST_FIELDS = ("expected_direction",)


def map_to_observation(
    normalized_record: NormalizedEvidenceRecord,
    *,
    domain: str,
    actor: str = "evidence-ingestion",
    now: float,
) -> Tuple[Any, Tuple[str, ...]]:
    """Map a NormalizedEvidenceRecord to a Tattva Observation + warnings.

    Returns ``(Observation, warnings)``. Produces ONLY an Observation; never a
    reasoning/conclusion object. Missing extracted fields become warnings, not
    invented values.
    """
    norm = normalized_record
    fields: Dict[str, Any] = dict(norm.extracted_fields or {})
    warnings: List[str] = list(norm.warnings or ())

    authority = norm.source_authority
    source_class = norm.source_class

    source_type = _pick_source_type(norm.normalized_type, source_class)
    source_reliability = _AUTHORITY_TO_RELIABILITY.get(authority, "low")

    is_catalyst = source_type in _CATALYST_SOURCE_TYPES or bool(
        fields.get("catalyst_type") or fields.get("expected_direction")
    )

    # Determine which fields we EXPECT, and warn about any that are absent.
    expected: Tuple[str, ...] = _EXPECTED_FIELDS.get(source_type, ())
    if is_catalyst:
        expected = expected + _EXPECTED_CATALYST_FIELDS
    for f in expected:
        if fields.get(f) is None:
            warnings.append(
                "missing field '{0}' for {1} (subject={2}); left unset, not fabricated".format(
                    f, source_type, norm.subject
                )
            )

    # Pull values ONLY where present; absent -> None (never fabricated).
    metric_name = fields.get("metric_name")
    metric_value = fields.get("metric_value")
    metric_unit = fields.get("metric_unit")
    prior_value = fields.get("prior_value")
    observed_change = fields.get("observed_change")
    financial_metric = fields.get("financial_metric")
    expected_direction = fields.get("expected_direction")

    catalyst_type = None
    catalyst_status = None
    if is_catalyst:
        catalyst_type = fields.get("catalyst_type") or _SOURCE_TYPE_DEFAULT_CATALYST.get(
            source_type, "event"
        )
        catalyst_status = _AUTHORITY_TO_CATALYST_STATUS.get(authority, "possible")

    entity = norm.ticker or norm.subject
    as_of = norm.event_date or norm.period_end or ""
    excerpt = (
        fields.get("excerpt")
        or "{0} for {1}".format(norm.normalized_type or source_type, norm.subject or entity)
    )
    source_name = norm.source.source_name if norm.source is not None else ""
    provider = norm.source.provider if norm.source is not None else ""

    obs = make_source_observation(
        source_type=source_type,
        domain=domain,
        entity=entity,
        excerpt=excerpt,
        as_of=as_of,
        source_ref=source_name,
        source_reliability=source_reliability,
        evidence_quality=norm.evidence_quality,
        metric_name=metric_name,
        metric_value=metric_value,
        metric_unit=metric_unit,
        prior_value=prior_value,
        observed_change=observed_change,
        catalyst_type=catalyst_type,
        catalyst_status=catalyst_status,
        expected_direction=expected_direction,
        financial_metric=financial_metric,
        actor=actor,
        now=now,
    )

    # Enrich content + rebind provenance to the evidence record WITHOUT touching
    # Tattva. Extra content keys are ignored by the assessment generator.
    enriched_content = dict(obs.content)
    enriched_content.update(
        {
            "source_authority": norm.source_authority,
            "source_class": norm.source_class,
            "source_name": source_name,
            "provider": provider,
            "normalized_record_id": norm.id,
        }
    )
    prov = make_provenance(
        actor=actor,
        created_at=iso_from_epoch(now),
        sources=(norm.ref("NormalizedEvidenceRecord"),),
    )
    obs = dataclasses.replace(obs, content=enriched_content, provenance=prov)
    return obs, tuple(warnings)
