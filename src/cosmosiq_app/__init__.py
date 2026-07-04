"""CosmosIQ application package (IMPLEMENTATION-016A) -- the first full-product slice.

Two modules, deliberately separated:

* :mod:`cosmosiq_app.api` -- the PURE dispatcher. ``dispatch(request, *, store_dir, now="")``
  maps a plain request dict onto the Phase-013/015 stores and returns a plain response dict.
  No sockets, no ``http`` import, no network, no wall clock -- this is the entire product
  surface, and it is what the offline test suite exercises.
* :mod:`cosmosiq_app.server` -- the THIN operator-started shell: stdlib ``http.server``
  wrapping :func:`~cosmosiq_app.api.dispatch`, bound to 127.0.0.1 by default, started ONLY
  by ``python3 -m cosmosiq_app --store-dir ...``, stopped by Ctrl-C. The shell is NOT
  imported here (importing :mod:`cosmosiq_app` must never pull in ``http``), NOT imported by
  the tests, and NOT imported by anything in :mod:`reality_mesh`.

READ-ONLY plus explicit manual actions (ack / pause / resume / manual pulse / settings).
There is NO trading endpoint of any kind -- a trade-like route is refused with 403.
Deterministic, stdlib-only, Python 3.9.
"""

from __future__ import annotations

from .api import APP_NAME, EXECUTION_REFUSAL, SettingsStore, dispatch

__all__ = [
    "APP_NAME",
    "EXECUTION_REFUSAL",
    "SettingsStore",
    "dispatch",
]
