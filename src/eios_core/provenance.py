"""Provenance -- where an object came from.

Every canonical object records who created it, when, and which upstream objects
it was derived from (as ``Ref`` bindings). Frozen, so provenance is never edited
after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from .graph_refs import Ref


@dataclass(frozen=True)
class Provenance:
    """Immutable record of an object's origin.

    ``sources`` binds upstream objects by ``(id, version)`` -- the spine of the
    derivation graph and the basis for deterministic replay.
    """

    created_at: str = ""
    actor: str = ""
    sources: Tuple[Ref, ...] = field(default_factory=tuple)


def make_provenance(actor: str, created_at: str, sources=()) -> Provenance:
    """Construct a Provenance, normalising ``sources`` to a tuple of Refs."""
    return Provenance(created_at=created_at, actor=actor, sources=tuple(sources))
