"""Production secrets / config hardening (IMPLEMENTATION-023B). PRESENCE-ONLY, OFFLINE.

This module turns the 019A presence-only secret pattern (:mod:`cosmosiq_ops.env_config`) and the
023A environment profiles (:mod:`cosmosiq_ops.env_profiles`) into an explicit, testable
config-validation surface:

* :data:`CONFIG_SCHEMA` / :data:`REQUIRED_ENV_VARS` -- for each source / capability, which env var
  NAMES it requires (SEC live -> ``SEC_USER_AGENT``; FMP live -> ``FMP_API_KEY``; production alert
  email delivery -> the 020E email env vars);
* :func:`required_env_vars_for_profile` -- derives, from a 023A profile's
  ``source_behavior`` / ``secret_behavior`` / ``alert_behavior``, exactly which env vars a running
  environment must have configured;
* :func:`validate_secrets` -- a PRESENCE-ONLY validation: it computes ``name in env`` (os.environ or
  an injected mapping) and NEVER reads, stores, logs, or echoes a value. A missing REQUIRED var
  produces a check whose ``blocks_what`` names the live source it blocks -- an honest gap, never a
  crash, never a silent fixture fallback;
* :func:`is_secret_free` / :func:`file_is_secret_free` / :func:`secret_scan_paths` -- reuse the
  CI gate's secret-VALUE patterns so a rendered string, the ``.env.example`` template, or a
  config file can be proven free of real secret values for CI use.

The discipline (identical to 019A / 023A):

* every function is presence-only -- ``name in mapping`` is the ONLY access; a value is never read;
* a value passed by mistake (e.g. into the ``env`` argument as a non-mapping) is REFUSED without
  being echoed;
* the real ``.env`` is NEVER committed -- :data:`ENV_UNTRACKED_RULE` documents the gitignore rule,
  and the CI gate (:func:`cosmosiq_ops.ci_gate.check_env_not_tracked`) fails on a tracked ``.env``;
* NO score / rank / buy / sell / order / trade field exists anywhere here.

Stdlib-only, Python 3.9, OFFLINE. No network on import; nothing here reads a secret value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple, Union

from cosmosiq_ops.ci_gate import SECRET_VALUE_PATTERNS
from cosmosiq_ops.env_profiles import EnvironmentProfile, get_profile
from reality_mesh.alert_delivery import (
    EMAIL_CREDENTIAL_ENV,
    EMAIL_HOST_ENV,
    EMAIL_RECIPIENT_ENV,
)

__all__ = [
    "CapabilityConfig",
    "CONFIG_SCHEMA",
    "REQUIRED_ENV_VARS",
    "ALL_CONFIG_ENV_VARS",
    "ENV_UNTRACKED_RULE",
    "SecretCheck",
    "SecretsReport",
    "required_env_vars_for_profile",
    "validate_secrets",
    "format_secrets_report",
    "is_secret_free",
    "secret_value_findings",
    "file_is_secret_free",
    "secret_scan_paths",
]

# The documented rule that keeps a REAL .env out of version control (mirrored in .gitignore and
# .env.example). The CI gate re-proves it with `git ls-files`.
ENV_UNTRACKED_RULE = (
    "a real .env is NEVER committed: `.env` / `.env.*` are gitignored (with `!.env.example`), and "
    "the CI gate (cosmosiq_ops.ci_gate.check_env_not_tracked) fails if any .env is tracked; only "
    ".env.example (NAMES + fake placeholders) is committed"
)


# --------------------------------------------------------------------------- #
# The config schema -- per-capability required env var NAMES (never values)     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CapabilityConfig:
    """One capability's env-var contract: NAMES only, plus the source it gates.

    ``required_env_vars`` are the env var NAMES this capability cannot run without; ``label`` is the
    operator-facing name of the live source / capability the missing var BLOCKS. No field ever holds
    a value.
    """

    capability: str
    label: str
    required_env_vars: Tuple[str, ...]
    optional_env_vars: Tuple[str, ...] = field(default_factory=tuple)


#: The single source of truth: which env var NAMES each source / capability requires.
CONFIG_SCHEMA: Tuple[CapabilityConfig, ...] = (
    CapabilityConfig(
        capability="sec_live",
        label="SEC EDGAR live source",
        required_env_vars=("SEC_USER_AGENT",),
    ),
    CapabilityConfig(
        capability="fmp_live",
        label="FMP live source",
        required_env_vars=("FMP_API_KEY",),
    ),
    CapabilityConfig(
        capability="alert_email_delivery",
        label="production alert email delivery",
        required_env_vars=(EMAIL_CREDENTIAL_ENV, EMAIL_HOST_ENV, EMAIL_RECIPIENT_ENV),
    ),
)

#: capability -> its required env var NAMES (a flat convenience view of CONFIG_SCHEMA).
REQUIRED_ENV_VARS: Mapping[str, Tuple[str, ...]] = {
    entry.capability: entry.required_env_vars for entry in CONFIG_SCHEMA
}

#: Every env var NAME the config surface knows, in schema order (deterministic).
ALL_CONFIG_ENV_VARS: Tuple[str, ...] = tuple(
    var for entry in CONFIG_SCHEMA for var in entry.required_env_vars
)

#: env var NAME -> the source / capability label it blocks when absent.
_VAR_BLOCKS: Mapping[str, str] = {
    var: entry.label for entry in CONFIG_SCHEMA for var in entry.required_env_vars
}


# --------------------------------------------------------------------------- #
# Deriving the required env vars for a 023A profile                             #
# --------------------------------------------------------------------------- #
def _resolve(profile: Union[EnvironmentProfile, str]) -> EnvironmentProfile:
    if isinstance(profile, EnvironmentProfile):
        return profile
    return get_profile(str(profile))


def required_env_vars_for_profile(
    profile: Union[EnvironmentProfile, str]
) -> Tuple[str, ...]:
    """The env var NAMES a running ``profile`` MUST have configured, derived from its posture.

    * a ``live`` source (``source_behavior == "live"`` / ``secret_behavior == "required_live"``)
      requires the SEC + FMP live credentials;
    * a ``production_delivery`` alert posture additionally requires the email delivery credentials.

    A fixture-only / local-file offline profile requires NOTHING. Returns the NAMES in schema order
    (deterministic); never a value.
    """
    prof = _resolve(profile)
    capabilities = []
    if prof.source_behavior == "live" or prof.secret_behavior == "required_live":
        capabilities.extend(("sec_live", "fmp_live"))
    if prof.alert_behavior == "production_delivery":
        capabilities.append("alert_email_delivery")

    required = []
    for entry in CONFIG_SCHEMA:
        if entry.capability in capabilities:
            for var in entry.required_env_vars:
                if var not in required:
                    required.append(var)
    return tuple(required)


# --------------------------------------------------------------------------- #
# The presence-only report                                                      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SecretCheck:
    """One env var's presence: its NAME, a presence bool, whether it is required, what it blocks.

    ``present`` is computed with ``name in env`` -- the VALUE is never read. ``blocks_what`` names
    the live source / capability that a missing REQUIRED var blocks. No value is ever held here.
    """

    var_name: str
    present: bool
    required: bool
    blocks_what: str


@dataclass(frozen=True)
class SecretsReport:
    """A profile's secret-config validation -- presence LABELS only, never a value.

    ``checks`` covers every known config env var; a var is ``required`` iff the profile's posture
    needs it. The report NEVER stores or renders a value: it is safe to log or persist.
    """

    profile_id: str
    checks: Tuple[SecretCheck, ...] = field(default_factory=tuple)

    def missing_required(self) -> Tuple[str, ...]:
        """The NAMES of required env vars that are absent (empty -> all required present)."""
        return tuple(c.var_name for c in self.checks if c.required and not c.present)

    def blocked_sources(self) -> Tuple[str, ...]:
        """The distinct source / capability labels blocked by a missing required var, in order."""
        seen: list = []
        for c in self.checks:
            if c.required and not c.present and c.blocks_what and c.blocks_what not in seen:
                seen.append(c.blocks_what)
        return tuple(seen)

    def all_required_present(self) -> bool:
        """True iff every required env var for this profile is present."""
        return not self.missing_required()


def validate_secrets(
    profile: Union[EnvironmentProfile, str], *, env: Optional[Mapping[str, str]] = None
) -> SecretsReport:
    """Validate ``profile``'s secret config against ``env`` (os.environ if None). PRESENCE ONLY.

    ``name in mapping`` is the ONLY access performed: a value is never read, stored, logged, or
    echoed. A required var that is absent yields a check whose ``blocks_what`` names the live source
    it blocks -- surfaced via :meth:`SecretsReport.missing_required` /
    :meth:`SecretsReport.blocked_sources`. This never crashes and never triggers a fixture
    fallback; it reports an honest "not configured" gap the caller can act on.
    """
    prof = _resolve(profile)
    if env is not None and not isinstance(env, Mapping):
        # NEVER echo the argument -- it may BE a secret value passed by mistake.
        raise ValueError(
            "validate_secrets env must be a Mapping of NAME->value (presence is read via "
            "`name in env`; the value is never touched) -- the argument was rejected and has "
            "not been stored or echoed")
    mapping: Mapping[str, str] = os.environ if env is None else env

    required = frozenset(required_env_vars_for_profile(prof))
    checks = tuple(
        SecretCheck(
            var_name=var,
            present=var in mapping,      # membership ONLY -- the value is never read
            required=var in required,
            blocks_what=_VAR_BLOCKS.get(var, ""),
        )
        for var in ALL_CONFIG_ENV_VARS
    )
    return SecretsReport(profile_id=prof.profile_id, checks=checks)


def format_secrets_report(report: SecretsReport) -> str:
    """Render a :class:`SecretsReport` -- presence LABELS only, never a value."""
    lines = [
        "CosmosIQ secrets-config report",
        "profile: " + report.profile_id,
        "env vars (presence only -- values are never read):",
    ]
    for check in report.checks:
        presence = "present" if check.present else "absent"
        tag = "required" if check.required else "optional"
        suffix = " -- blocks: {0}".format(check.blocks_what) if check.blocks_what else ""
        lines.append("  {0}: {1} [{2}]{3}".format(check.var_name, presence, tag, suffix))
    missing = report.missing_required()
    if missing:
        lines.append("MISSING REQUIRED (blocks live source): " + ", ".join(missing))
        lines.append("blocked sources: " + ", ".join(report.blocked_sources()))
    else:
        lines.append("all required env vars present")
    lines.append("rule: " + ENV_UNTRACKED_RULE)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Secret-VALUE scanning for CI (reuses the CI gate's secret-value patterns)      #
# --------------------------------------------------------------------------- #
def secret_value_findings(text: object) -> Tuple[str, ...]:
    """Findings for any secret-shaped VALUE in ``text`` (reuses the CI gate patterns)."""
    haystack = str(text or "")
    return tuple(
        "secret-like value matching {0}".format(pattern.pattern)
        for pattern in SECRET_VALUE_PATTERNS
        if pattern.search(haystack)
    )


def is_secret_free(text: object) -> bool:
    """True iff ``text`` (a rendered string) carries NO secret-shaped value."""
    return not secret_value_findings(text)


def file_is_secret_free(path: str) -> bool:
    """True iff the file at ``path`` carries NO secret-shaped value (e.g. .env.example)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return is_secret_free(fh.read())


def secret_scan_paths(repo_root: str) -> Tuple[str, ...]:
    """The config files a CI secret-VALUE scan should cover, if present under ``repo_root``.

    ``.env.example`` (the committed template) and any ``.env`` that leaked into the checkout -- so
    CI can prove neither carries a real secret value.
    """
    candidates = (".env.example", ".env")
    return tuple(
        os.path.join(repo_root, name)
        for name in candidates
        if os.path.isfile(os.path.join(repo_root, name))
    )
