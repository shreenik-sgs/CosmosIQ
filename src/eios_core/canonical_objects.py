"""Canonical object base types and the ADR-0010 bifurcation.

ADR-0010 (The Cognition-Actuation Boundary) divides every object the system
holds into two kinds:

* ``ReasoningObject`` -- what is known, judged, or recommended. Reversible.
  Free to be revised, withdrawn, and replayed. Everything upstream of the Order.
* ``OperationalObject`` -- the record of a *deed* in the world. Its truth is
  fact, not warrant ("did it happen?", not "is it justified?"). The Order
  (ManualTradeTicket) is the only operational object in this slice.

``Observation`` bridges the two: what returns from the world (a fill, a
divergence) is recorded as an Observation -- a reasoning object -- and may flow
*up* as evidence, never as purpose.

All canonical objects are frozen dataclasses, so constructing a downstream
object can never mutate an upstream one. State transitions are expressed by
building a new value (``dataclasses.replace``), not by in-place edits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .graph_refs import Ref
from .provenance import Provenance


@dataclass(frozen=True)
class CanonicalObject:
    """Base for every object: a stable id, a version, and provenance."""

    id: str = ""
    version: int = 1
    provenance: Provenance = field(default_factory=Provenance)

    def ref(self, kind: Optional[str] = None) -> Ref:
        """Return a versioned ``Ref`` to this object for downstream binding."""
        return Ref(object_id=self.id, version=self.version, kind=kind or type(self).__name__)


@dataclass(frozen=True)
class ReasoningObject(CanonicalObject):
    """What is known, judged, or recommended -- reversible cognition."""


@dataclass(frozen=True)
class OperationalObject(CanonicalObject):
    """The record of a deed in the world -- irreversible actuation."""


@dataclass(frozen=True)
class Observation(ReasoningObject):
    """An observation of reality, the bridge from operational fact back to
    cognition. Carries free-form ``content``; its upstream evidence is bound in
    ``provenance.sources``.
    """

    content: Any = None

    @property
    def sources(self):
        return self.provenance.sources


@dataclass(frozen=True)
class Decision(ReasoningObject):
    """A reasoning object expressing a choice. ``InvestmentAction`` is a typed
    Decision. A Decision is still cognition -- it forms a verdict; it does not
    carry it out.
    """

    content: Any = None
