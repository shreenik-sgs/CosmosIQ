"""Environment + secrets-policy report (Phase 019). NAMES and presence labels ONLY.

This module never reads, holds, prints, or returns the VALUE of any environment
variable. Presence is computed with ``name in os.environ`` -- the value is never
touched. The secrets policy itself is data here and prose in
``docs/DEPLOYMENT_019.md``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Tuple

# The ONLY env vars the system may use (credentials are explicit call arguments at the
# two sanctioned shells; nothing else reads the environment).
KNOWN_ENV_VARS = (
    ("SEC_USER_AGENT", "identifies the operator to SEC EDGAR (required by SEC fair-use "
                       "policy); consumed only by the live transport shell"),
    ("FMP_API_KEY", "Financial Modeling Prep API key; consumed only by the live "
                    "transport shell"),
)

# Secrets-management policy AS DATA (mirrored in docs/DEPLOYMENT_019.md).
SECRETS_POLICY = (
    "env-only: credentials enter the system exclusively as environment variables passed "
    "explicitly into the sanctioned shells (cosmosiq_app/server.py, "
    "evidence_ingestion/live_transport.py)",
    ".env files are never committed: the CI gate checks `git ls-files` for a tracked .env",
    "stores refuse credential keys: reality_mesh.stores rejects any record key containing "
    "a CREDENTIAL_KEY_TOKENS token (the 013B guard) -- a store can never hold a secret",
    "reports and pages carry env var NAMES + presence labels only, never values",
)


@dataclass(frozen=True)
class EnvVarPresence:
    """One env var: its NAME, a presence label, and what it is for. Never its value."""

    name: str
    presence: str  # "present" | "absent"
    purpose: str


@dataclass(frozen=True)
class EnvReport:
    """Environment facts an operator needs -- labels only, zero secret values."""

    variables: Tuple[EnvVarPresence, ...] = field(default_factory=tuple)
    python_version_label: str = ""
    platform_label: str = ""
    secrets_policy: Tuple[str, ...] = field(default_factory=tuple)


def environment_report() -> EnvReport:
    """Presence labels for the known env vars + python/platform labels.

    ``name in os.environ`` is the ONLY environment access: the value is never read.
    """
    variables = tuple(
        EnvVarPresence(name=name,
                       presence="present" if name in os.environ else "absent",
                       purpose=purpose)
        for name, purpose in KNOWN_ENV_VARS)
    return EnvReport(
        variables=variables,
        python_version_label="{0}.{1}".format(sys.version_info[0], sys.version_info[1]),
        platform_label=sys.platform,
        secrets_policy=SECRETS_POLICY)


def format_env_report(report: EnvReport) -> str:
    lines = ["CosmosIQ environment report",
             "python: " + report.python_version_label,
             "platform: " + report.platform_label,
             "env vars (presence only -- values are never read):"]
    for var in report.variables:
        lines.append("  {0}: {1} -- {2}".format(var.name, var.presence, var.purpose))
    lines.append("secrets policy:")
    for item in report.secrets_policy:
        lines.append("  - " + item)
    return "\n".join(lines)
