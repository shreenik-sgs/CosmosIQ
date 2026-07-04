"""CosmosIQ application package (IMPLEMENTATION-016A/016B) -- the first full-product slice.

Modules, deliberately separated (016B adds :mod:`cosmosiq_app.pages` +
:mod:`cosmosiq_app.app_assets`: PURE server-rendered HTML pages over the same stores,
served by the dispatcher at ``/``, ``/runs``, ``/runs/<id>``, ``/replay/<id>``,
``/alerts``, ``/settings`` -- no JavaScript, no external asset, no trade affordance):

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
from .pages import (
    render_alert_inbox,
    render_app_home,
    render_not_found,
    render_replay_view,
    render_run_detail,
    render_run_history,
    render_settings_page,
)

__all__ = [
    "APP_NAME",
    "EXECUTION_REFUSAL",
    "SettingsStore",
    "dispatch",
    "render_alert_inbox",
    "render_app_home",
    "render_not_found",
    "render_replay_view",
    "render_run_detail",
    "render_run_history",
    "render_settings_page",
]
