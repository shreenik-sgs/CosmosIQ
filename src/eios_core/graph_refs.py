"""Graph reference -- a typed, versioned pointer to another canonical object.

Provenance binds upstream objects by ``Ref(object_id, version, kind)`` rather
than by holding the object itself, so the dependency graph is explicit and a
downstream object never mutates its upstream (ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ref:
    """An immutable (id, version, kind) pointer to a canonical object."""

    object_id: str
    version: int = 1
    kind: str = ""
