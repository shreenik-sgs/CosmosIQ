"""Deterministic identity generation.

`stable_id` is a pure function of its inputs: the same prefix and parts always
produce the same id, and no wall-clock time is consulted. This is what makes
ticket idempotency (EXEC-002 AR-2001/2002) and deterministic replay possible.
"""

from __future__ import annotations

import hashlib
import datetime
from typing import Any


def stable_id(prefix: str, *parts: Any) -> str:
    """Return a deterministic, content-addressed id of the form ``PREFIX-<hex>``.

    The digest is taken over the ``|``-joined string form of ``parts``. Calling
    this with identical arguments always yields the same id (no ``now()``).
    """
    payload = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return "{0}-{1}".format(prefix, digest[:16])


def iso_from_epoch(epoch: float) -> str:
    """Deterministic ISO-8601 (UTC) string for an explicit epoch-seconds value.

    Uses the supplied timestamp only -- never the current clock -- so it is safe
    inside id-generation and replay-affecting code paths.
    """
    return (
        datetime.datetime.utcfromtimestamp(float(epoch)).replace(microsecond=0).isoformat()
        + "Z"
    )
