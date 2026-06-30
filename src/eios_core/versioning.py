"""Integer-based version helpers.

Every canonical object carries a monotonic integer ``version`` (default 1).
Downstream objects bind upstream by ``(id, version)`` so a re-derivation against
a newer upstream version is detectable.
"""

from __future__ import annotations

INITIAL_VERSION = 1


def initial() -> int:
    """Return the starting version for a freshly created object."""
    return INITIAL_VERSION


def bump(version: int) -> int:
    """Return the next version. Versions only ever increase."""
    return int(version) + 1
