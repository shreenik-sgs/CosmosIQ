"""Reality Intelligence -- the Observation input format for manually-supplied
source material.

An Observation here is the canonical, immutable record of one piece of
manually-supplied source material about a domain. It carries the raw excerpt plus
a small, explicit extracted signal (polarity + strength + optional metric). It
makes no judgement and forms no opportunity -- it is evidence, not an assessment.
The Intelligence Assessment generator (``intelligence_assessment.py``) consumes
Observations and synthesises an assessment from them.

The Observation is content-addressed (a deterministic id over source type, entity,
excerpt, and as-of date), so the same source material always yields the same
Observation id, supporting deterministic replay.
"""

from __future__ import annotations

from typing import Optional

from eios_core.canonical_objects import Observation
from eios_core.ids import stable_id, iso_from_epoch
from eios_core.provenance import make_provenance

# The kinds of manually-supplied source material accepted in this MVP.
SOURCE_TYPES = frozenset({
    "earnings_excerpt",
    "news_excerpt",
    "analyst_note_excerpt",
    "filing_excerpt",
    "infrastructure_milestone",
    "capacity_power_demand_signal",
})

# The explicit signal an Observation carries toward (not a recommendation about) a
# domain's state. "supportive"/"contradictory" are relative to the domain reading,
# never to any investment action.
POLARITIES = frozenset({"supportive", "contradictory", "neutral"})


def make_source_observation(
    *,
    source_type: str,
    domain: str,
    entity: str,
    excerpt: str,
    as_of: str,
    polarity: str = "neutral",
    signal_strength: float = 1.0,
    metric: Optional[dict] = None,
    source_ref: str = "",
    actor: str = "analyst",
    now: float,
) -> Observation:
    """Build an Observation from a single manually-supplied source excerpt.

    ``now`` is explicit epoch-seconds (deterministic); ``as_of`` is the date the
    source material refers to. Validation is strict: unknown source types or
    polarities are rejected, and the excerpt may not be empty.
    """
    if source_type not in SOURCE_TYPES:
        raise ValueError(
            "unknown source_type: {0} (allowed: {1})".format(source_type, sorted(SOURCE_TYPES))
        )
    if polarity not in POLARITIES:
        raise ValueError(
            "unknown polarity: {0} (allowed: {1})".format(polarity, sorted(POLARITIES))
        )
    if not excerpt or not excerpt.strip():
        raise ValueError("a source Observation requires a non-empty excerpt")

    content = {
        "source_type": source_type,
        "domain": domain,
        "entity": entity,
        "excerpt": excerpt,
        "polarity": polarity,
        "signal_strength": float(signal_strength),
        "metric": dict(metric) if metric else None,
        "as_of": as_of,
        "source_ref": source_ref,
    }
    oid = stable_id("OBS", source_type, entity, excerpt[:80], str(as_of))
    prov = make_provenance(actor=actor, created_at=iso_from_epoch(now), sources=())
    return Observation(id=oid, version=1, provenance=prov, content=content)
