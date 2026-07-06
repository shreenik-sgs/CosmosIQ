"""Production ENVIRONMENT PROFILES (IMPLEMENTATION-023A). PURE, OFFLINE, deterministic.

Phases 012-022H shipped the offline reality mesh, the supervised operator service
(:class:`cosmosiq_service.service.ServiceMode`), the recommendation activation gate
(:class:`reality_mesh.recommendation_activation.RecommendationMode`), and the 019A presence-only
secrets pattern (:mod:`cosmosiq_ops.env_config`). THIS slice makes the *posture* of each running
environment EXPLICIT and DECLARED, so mode / source / scheduler / alert / secret / network / UI
behaviour is never implicit or guessed -- and, above all, so that **production is NEVER the
default**.

A profile is a DECLARATION, not a switch. It states what an environment is *allowed* to look like;
it never itself enables production. Actually entering a production 24x7 service or a production
recommendation mode STILL requires the 020F service-activation gate and the 022H recommendation-
activation gate plus explicit operator sign-off. ``production_allowed=True`` on the ``production``
profile is a *posture declaration* those runtime gates read -- it is not a promotion and cannot
substitute for the gates.

The discipline that keeps this safe + testable, mirroring the rest of ``cosmosiq_ops``:

* the DEFAULT profile is SAFE -- :data:`DEFAULT_PROFILE_ID` is ``test_offline`` (network blocked,
  fixtures only, everything off), NEVER ``production``;
* :func:`resolve_profile` returns the safe default when no name is given; the ``production``
  profile is reachable ONLY when its name is passed EXPLICITLY;
* every closed vocabulary is validated in ``__post_init__`` -- an out-of-vocabulary value is a
  hard ``ValueError``;
* a ``network_behavior=blocked`` profile MUST draw from ``fixture_only`` / ``local_file`` sources
  -- a blocked environment can never claim a live source;
* a ``production_allowed=True`` profile MUST carry the production service + recommendation modes
  AND must NOT be the default;
* secrets are PRESENCE-LABELLED only -- ``secret_behavior`` is a *label* (``none_required`` /
  ``presence_checked`` / ``required_live``); no field ever holds a secret VALUE, exactly as 019A;
* NO score / rank / buy / sell / order / trade field exists anywhere on a profile.

Stdlib-only, Python 3.9, OFFLINE. No network on import; nothing here reads a secret value, and
importing this module starts nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

# The profiles DECLARE the accepted upstream mode vocabularies; they never re-implement them.
from cosmosiq_service.service import ServiceMode
from reality_mesh.recommendation_activation import (
    RECOMMENDATION_MODES,
    RecommendationMode,
)

__all__ = [
    "SOURCE_BEHAVIORS",
    "SCHEDULER_BEHAVIORS",
    "ALERT_BEHAVIORS",
    "SECRET_BEHAVIORS",
    "LOGGING_LEVELS",
    "NETWORK_BEHAVIORS",
    "SERVICE_MODES",
    "EnvironmentProfile",
    "PROFILES",
    "DEFAULT_PROFILE_ID",
    "default_profile",
    "get_profile",
    "resolve_profile",
]

# --------------------------------------------------------------------------- #
# Closed vocabularies (posture only -- never a score / rank / trade dimension)  #
# --------------------------------------------------------------------------- #
#: Where an environment is allowed to draw evidence from.
SOURCE_BEHAVIORS: Tuple[str, ...] = ("fixture_only", "local_file", "live")
#: Whether the 015 cadence scheduler runs.
SCHEDULER_BEHAVIORS: Tuple[str, ...] = ("off", "on")
#: How alerts are surfaced (never external delivery below production).
ALERT_BEHAVIORS: Tuple[str, ...] = (
    "off",
    "in_app_inbox",
    "shadow_inbox",
    "production_delivery",
)
#: The 019A presence-only secret posture -- a LABEL, never a value.
SECRET_BEHAVIORS: Tuple[str, ...] = ("none_required", "presence_checked", "required_live")
#: Structured-log verbosity label.
LOGGING_LEVELS: Tuple[str, ...] = ("debug", "info", "warn")
#: Whether the environment may reach the network AT ALL (lazily, at the sanctioned shell).
NETWORK_BEHAVIORS: Tuple[str, ...] = ("blocked", "lazy_live")
#: The closed set of accepted service-mode values (mirrors ServiceMode).
SERVICE_MODES: Tuple[str, ...] = tuple(m.value for m in ServiceMode)

#: Source behaviours that require NO network reach.
_OFFLINE_SOURCES = frozenset({"fixture_only", "local_file"})

# The safe default is declared BEFORE any profile is constructed so __post_init__ can enforce
# "a production_allowed profile is NOT the default".
DEFAULT_PROFILE_ID = "test_offline"


@dataclass(frozen=True)
class EnvironmentProfile:
    """One environment's DECLARED posture. Closed-vocabulary, presence-only, no score/trade.

    Every field is a DECLARATION an operator (and the runtime gates) can read; none of them
    enables production by itself. ``production_allowed`` is a posture flag -- the 020F + 022H
    activation gates and operator sign-off still decide whether production is actually entered.
    """

    profile_id: str
    service_mode: str            # a ServiceMode value
    recommendation_mode: str     # a RecommendationMode value
    source_behavior: str         # SOURCE_BEHAVIORS
    scheduler_behavior: str      # SCHEDULER_BEHAVIORS
    alert_behavior: str          # ALERT_BEHAVIORS
    secret_behavior: str         # SECRET_BEHAVIORS -- a LABEL only, never a value
    persistence_path: str        # a path TEMPLATE / label (not a live secret)
    logging_level: str           # LOGGING_LEVELS
    network_behavior: str        # NETWORK_BEHAVIORS
    ui_labels: Tuple[str, ...] = field(default_factory=tuple)  # honest mode-strip labels
    production_allowed: bool = False  # a DECLARATION -- gates still decide

    def __post_init__(self) -> None:
        _in_vocab("service_mode", self.service_mode, SERVICE_MODES)
        _in_vocab("recommendation_mode", self.recommendation_mode, RECOMMENDATION_MODES)
        _in_vocab("source_behavior", self.source_behavior, SOURCE_BEHAVIORS)
        _in_vocab("scheduler_behavior", self.scheduler_behavior, SCHEDULER_BEHAVIORS)
        _in_vocab("alert_behavior", self.alert_behavior, ALERT_BEHAVIORS)
        _in_vocab("secret_behavior", self.secret_behavior, SECRET_BEHAVIORS)
        _in_vocab("logging_level", self.logging_level, LOGGING_LEVELS)
        _in_vocab("network_behavior", self.network_behavior, NETWORK_BEHAVIORS)

        if not isinstance(self.ui_labels, tuple):
            raise ValueError("ui_labels must be a tuple of honest mode-strip labels")
        if not isinstance(self.production_allowed, bool):
            raise ValueError("production_allowed must be a bool declaration")

        # A blocked environment can NEVER claim a live source.
        if self.network_behavior == "blocked" and self.source_behavior not in _OFFLINE_SOURCES:
            raise ValueError(
                "profile {0!r}: network_behavior=blocked requires an offline source "
                "(fixture_only/local_file), not {1!r}".format(
                    self.profile_id, self.source_behavior))

        # A production-declared profile must be mode-consistent AND must NOT be the default.
        if self.production_allowed:
            if self.service_mode != ServiceMode.PRODUCTION_24X7.value:
                raise ValueError(
                    "profile {0!r}: production_allowed=True requires service_mode "
                    "{1!r}".format(self.profile_id, ServiceMode.PRODUCTION_24X7.value))
            if self.recommendation_mode != RecommendationMode.PRODUCTION_MANUAL_REVIEW:
                raise ValueError(
                    "profile {0!r}: production_allowed=True requires recommendation_mode "
                    "{1!r}".format(
                        self.profile_id, RecommendationMode.PRODUCTION_MANUAL_REVIEW))
            if self.profile_id == DEFAULT_PROFILE_ID:
                raise ValueError(
                    "the default profile can NEVER declare production_allowed=True "
                    "(profile {0!r})".format(self.profile_id))


def _in_vocab(field_name: str, value: object, vocab: Tuple[str, ...]) -> None:
    if value not in vocab:
        raise ValueError(
            "invalid {0} {1!r} (closed vocabulary: {2})".format(
                field_name, value, list(vocab)))


# --------------------------------------------------------------------------- #
# The five declared profiles                                                    #
# --------------------------------------------------------------------------- #
PROFILES: Mapping[str, EnvironmentProfile] = {
    # An operator's own machine: manual service, shadow recommendations, local files, no
    # scheduler, in-app alerts, presence-checked secrets, verbose logs, lazy live reach allowed.
    "local_dev": EnvironmentProfile(
        profile_id="local_dev",
        service_mode=ServiceMode.MANUAL.value,
        recommendation_mode=RecommendationMode.SHADOW,
        source_behavior="local_file",
        scheduler_behavior="off",
        alert_behavior="in_app_inbox",
        secret_behavior="presence_checked",
        persistence_path="./var/local_dev",
        logging_level="debug",
        network_behavior="lazy_live",
        ui_labels=("Local Dev", "Shadow", "Broker Disabled", "Execution Manual Review Only"),
        production_allowed=False,
    ),
    # The SAFE default: everything off, fixtures only, NETWORK BLOCKED, no secret required.
    "test_offline": EnvironmentProfile(
        profile_id="test_offline",
        service_mode=ServiceMode.OFF.value,
        recommendation_mode=RecommendationMode.OFF,
        source_behavior="fixture_only",
        scheduler_behavior="off",
        alert_behavior="off",
        secret_behavior="none_required",
        persistence_path="<tmp>/test_offline",
        logging_level="info",
        network_behavior="blocked",
        ui_labels=("Test Offline", "Network Blocked", "Fixtures Only", "Broker Disabled"),
        production_allowed=False,
    ),
    # Continuous SHADOW against local files: shadow inbox only, no external delivery.
    "shadow_local": EnvironmentProfile(
        profile_id="shadow_local",
        service_mode=ServiceMode.SHADOW_24X7.value,
        recommendation_mode=RecommendationMode.SHADOW,
        source_behavior="local_file",
        scheduler_behavior="on",
        alert_behavior="shadow_inbox",
        secret_behavior="presence_checked",
        persistence_path="./var/shadow_local",
        logging_level="info",
        network_behavior="lazy_live",
        ui_labels=("Shadow 24x7", "Shadow", "Local Files", "Broker Disabled"),
        production_allowed=False,
    ),
    # Continuous SHADOW against LIVE sources: still shadow inbox, live secrets required.
    "shadow_live": EnvironmentProfile(
        profile_id="shadow_live",
        service_mode=ServiceMode.SHADOW_24X7.value,
        recommendation_mode=RecommendationMode.SHADOW,
        source_behavior="live",
        scheduler_behavior="on",
        alert_behavior="shadow_inbox",
        secret_behavior="required_live",
        persistence_path="./var/shadow_live",
        logging_level="info",
        network_behavior="lazy_live",
        ui_labels=("Shadow 24x7 (Live)", "Shadow", "Live Source", "Broker Disabled"),
        production_allowed=False,
    ),
    # PRODUCTION posture -- DECLARED only. The 020F + 022H gates + operator sign-off still decide.
    "production": EnvironmentProfile(
        profile_id="production",
        service_mode=ServiceMode.PRODUCTION_24X7.value,
        recommendation_mode=RecommendationMode.PRODUCTION_MANUAL_REVIEW,
        source_behavior="live",
        scheduler_behavior="on",
        alert_behavior="production_delivery",
        secret_behavior="required_live",
        persistence_path="./var/production",
        logging_level="warn",
        network_behavior="lazy_live",
        ui_labels=("Production 24x7", "Production Manual Review",
                   "Broker Disabled", "Execution Manual Review Only"),
        production_allowed=True,
    ),
}


def default_profile() -> EnvironmentProfile:
    """Return the SAFE default profile -- never the production profile."""
    return PROFILES[DEFAULT_PROFILE_ID]


def get_profile(profile_id: str) -> EnvironmentProfile:
    """Look up a profile by id. Unknown -> ``ValueError``."""
    try:
        return PROFILES[profile_id]
    except KeyError:
        raise ValueError(
            "unknown environment profile {0!r} (known: {1})".format(
                profile_id, sorted(PROFILES)))


def resolve_profile(name: Optional[str] = None) -> EnvironmentProfile:
    """Resolve a profile.

    ``None`` -> the SAFE default. The ``production`` profile is reachable ONLY by passing its
    name EXPLICITLY -- there is no path by which ``resolve_profile(None)`` returns production.
    """
    if name is None:
        return default_profile()
    return get_profile(name)
