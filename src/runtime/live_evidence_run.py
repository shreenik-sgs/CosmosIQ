"""CLI-side credential resolution for the on-demand real-evidence run (010D).

This tiny module is the ONE place credentials are read from the environment, kept OUT
of the ``evidence_ingestion`` and ``universe_ui`` packages (whose audits forbid any
environment access). It reads env ONLY; it holds no literal key, never prints a
credential, and touches NO network (network lives solely in
``evidence_ingestion.live_transport``).

Contract:

* ``SEC_USER_AGENT`` -- a descriptive contact identity SEC's fair-access policy
  requires (NOT a secret). Absent -> the builder records a visible SEC data gap.
* ``FMP_API_KEY`` -- the FMP convenience-source key. Absent -> the builder records a
  visible FMP ``credentials_missing`` data gap and degrades (SEC can still succeed).

Both are surfaced as booleans (present / absent) for logging WITHOUT echoing the
value, so nothing sensitive reaches stdout or the generated HTML.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple


def resolve_live_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Return ``(sec_user_agent, fmp_api_key)`` from the environment (or ``None``)."""
    sec_user_agent = os.environ.get("SEC_USER_AGENT") or None
    fmp_api_key = os.environ.get("FMP_API_KEY") or None
    return sec_user_agent, fmp_api_key


def credential_presence() -> Dict[str, bool]:
    """Booleans only -- for safe logging. NEVER returns the credential values."""
    sec_user_agent, fmp_api_key = resolve_live_credentials()
    return {"sec_user_agent_present": bool(sec_user_agent),
            "fmp_api_key_present": bool(fmp_api_key)}
