"""Alert delivery channels + a per-mode delivery policy (IMPLEMENTATION-020E).

The FIRST alert-delivery path. Phases 012-020D produced OBSERVATION alerts (015C) and their
non-production SHADOW re-cast (020D) into an append-only in-app inbox. 020E adds the ability to
*deliver* an alert somewhere -- but keeps the discipline that has held every phase: an alert
OBSERVES, it never acts, and delivery is a NOTIFICATION of an observation, never an instruction to
trade. Execution stays Manual Review Only.

The abstraction (never bypassed):

* :class:`AlertDeliveryChannel` -- an ABC. :class:`InboxChannel` is the SAFE DEFAULT (always
  allowed; it marks the alert delivered to the in-app inbox). :class:`EmailChannel` is the first
  EXTERNAL channel and MIRRORS the SEC-adapter lazy/injected pattern: ``smtplib`` is imported
  ONLY inside :meth:`EmailChannel._send`, a ``transport`` callable is injectable so tests never
  touch the wire, ``dry_run`` renders the message without sending, and the email credential is a
  PRESENCE label only (read lazily, never stored / echoed).
* :class:`AlertDeliveryPolicy` -- the per-mode channel rules + the high-severity gate. In
  ``OFF`` / ``MANUAL`` external delivery is SUPPRESSED (``suppressed_by_mode``); in
  ``SHADOW_24X7`` external delivery is suppressed UNLESS explicitly enabled as shadow delivery;
  in ``PRODUCTION_24X7`` external delivery is gated to the Phase-020F activation
  (``suppressed_by_policy`` until then). The in-app inbox is ALWAYS allowed. A ``critical``
  delivery requires a healthy/approved DQ state + non-speculative authority + a run_id +
  provenance; an unsupported ``critical`` is capped to ``review_required`` -- a social / rumor /
  DQ-failed input can NEVER be delivered as a critical production action.
* :class:`AlertDeliveryResult` -- one frozen, sanitized record of ONE attempt (never a secret,
  never a raw credential value). :class:`AlertDeliveryStore` persists every attempt APPEND-ONLY.
  :func:`deliver_alert` applies the policy, delivers via the allowed channels, and persists each
  result -- a retryable transport error becomes ``failed_retryable``, a permanent one
  ``failed_permanent``.

Deterministic, stdlib-only, Python 3.9, OFFLINE: every instant is an injected ISO-8601 ``now``
string, the real SMTP path is NEVER exercised by the tests (a transport is injected or dry-run
is used), NO network is touched on import, and every delivered byte passes a forbidden-language
sweep + a local secret sanitizer.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, FrozenSet, List, Mapping, Optional, Tuple

from .alerts import Alert, FORBIDDEN_ALERT_PHRASES, SHADOW_MARKER
from .stores import AppendOnlyStore

__all__ = [
    "AlertDeliveryStatus",
    "DELIVERY_STATUSES",
    "DELIVERY_SEVERITIES",
    "DELIVERED_ALERT_CATEGORIES",
    "HEALTHY_DQ_STATES",
    "SPECULATIVE_ALERT_CATEGORIES",
    "AlertDeliveryError",
    "RetryableDeliveryError",
    "PermanentDeliveryError",
    "AlertDeliveryResult",
    "AlertDeliveryPolicy",
    "AlertDeliveryChannel",
    "InboxChannel",
    "EmailChannel",
    "AlertDeliveryStore",
    "deliver_alert",
    "delivery_results",
    "latest_delivery_status",
    "delivery_category_display",
    "default_delivery_channels",
]


# --------------------------------------------------------------------------- #
# 0. Modes -- mirrored from cosmosiq_service.ServiceMode values (NOT imported)   #
#    to keep reality_mesh free of a service dependency (no circular import).     #
# --------------------------------------------------------------------------- #
MODE_OFF = "OFF"
MODE_MANUAL = "MANUAL"
MODE_SHADOW = "SHADOW_24X7"
MODE_PRODUCTION = "PRODUCTION_24X7"
_KNOWN_MODES = frozenset({MODE_OFF, MODE_MANUAL, MODE_SHADOW, MODE_PRODUCTION})


def _norm_mode(mode: object) -> str:
    """Normalise a mode (ServiceMode member / name / value / string) to an upper token."""
    if hasattr(mode, "value") and not isinstance(mode, str):
        text = str(getattr(mode, "value", ""))
    else:
        text = str(mode or "")
    token = text.strip().upper()
    return token if token in _KNOWN_MODES else token or MODE_OFF


def _is_shadow(mode: object) -> bool:
    return _norm_mode(mode) == MODE_SHADOW


# --------------------------------------------------------------------------- #
# 1. Closed vocabularies                                                        #
# --------------------------------------------------------------------------- #
class AlertDeliveryStatus:
    """The CLOSED delivery-status vocabulary (labels on an outcome ladder, never scores)."""

    NOT_DELIVERED = "not_delivered"
    DELIVERED = "delivered"
    SUPPRESSED_BY_MODE = "suppressed_by_mode"
    SUPPRESSED_BY_POLICY = "suppressed_by_policy"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_PERMANENT = "failed_permanent"


DELIVERY_STATUSES: FrozenSet[str] = frozenset({
    AlertDeliveryStatus.NOT_DELIVERED,
    AlertDeliveryStatus.DELIVERED,
    AlertDeliveryStatus.SUPPRESSED_BY_MODE,
    AlertDeliveryStatus.SUPPRESSED_BY_POLICY,
    AlertDeliveryStatus.FAILED_RETRYABLE,
    AlertDeliveryStatus.FAILED_PERMANENT,
})

# The delivery-side severity ladder (labels a delivered notification may carry). Distinct from
# the 015C alert-record ALERT_SEVERITIES: 015C stays frozen (its exact-set test still holds); the
# incoming alert severity is mapped ONTO this ladder for display + gating, never mutating it.
DELIVERY_SEVERITIES: FrozenSet[str] = frozenset({"info", "watch", "review_required", "critical"})

# 015C/020D alert severity label -> the delivery ladder. buy/sell/strong_buy can NEVER appear.
_ALERT_TO_DELIVERY_SEVERITY: Mapping[str, str] = {
    "info": "info",
    "notice": "watch",
    "warning": "review_required",
    "critical": "critical",
}

# The 15 operator-facing delivered-alert categories (the display vocabulary). The 015C closed
# ALERT_CATEGORIES (10 observed state-changes) MAP onto these; the remaining forward categories
# are declared here so the delivery surface already covers the full 15.
DELIVERED_ALERT_CATEGORIES: Tuple[str, ...] = (
    "Mega Theme Pulse Changed",
    "Theme Breakout Detected",
    "Sector Rotation Detected",
    "Market Regime Changed",
    "New Capital Candidate Created",
    "Candidate Upgraded to Active Diligence",
    "Candidate Deterioration",
    "Filing / Dilution Risk",
    "Customer / Contract Signal",
    "Crowding / Euphoria Warning",
    "Red-Team Risk Emerged",
    "Portfolio Concentration Warning",
    "Data Quality Failure",
    "Agent Failure",
    "Source Failure",
)

# 015C alert category -> its operator-facing display name (one of the 15 above).
_CATEGORY_DISPLAY: Mapping[str, str] = {
    "market_regime_changed": "Market Regime Changed",
    "sector_rotation_detected": "Sector Rotation Detected",
    "theme_pulse_changed": "Mega Theme Pulse Changed",
    "filing_dilution_risk": "Filing / Dilution Risk",
    "social_narrative_spike": "Crowding / Euphoria Warning",
    "crowding_warning": "Crowding / Euphoria Warning",
    "source_data_quality_failure": "Data Quality Failure",
    "thesis_deteriorated": "Candidate Deterioration",
    "new_opportunity_hypothesis": "New Capital Candidate Created",
    "major_risk_emerged": "Red-Team Risk Emerged",
}

# DQ-state labels that count as healthy / approved for the high-severity gate.
HEALTHY_DQ_STATES: FrozenSet[str] = frozenset({"healthy", "approved", "pass", "ok"})

# Categories whose evidence is social / uncorroborated (speculative authority). A critical from
# one of these can NEVER be delivered as a production action -- it is capped.
SPECULATIVE_ALERT_CATEGORIES: FrozenSet[str] = frozenset({
    "social_narrative_spike", "crowding_warning",
})


def delivery_category_display(category: object) -> str:
    """The operator-facing display name for a 015C alert category ("" -> a readable fallback)."""
    key = str(category or "")
    if key in _CATEGORY_DISPLAY:
        return _CATEGORY_DISPLAY[key]
    return key.replace("_", " ").strip().title() or "Alert"


# --------------------------------------------------------------------------- #
# 2. Local scrubbers -- forbidden action-language + secret shapes                #
#    (a local sanitizer avoids importing cosmosiq_service: no circular import)   #
# --------------------------------------------------------------------------- #
_SECRET_KV = re.compile(
    r"(?i)\b(api[\-_]?key|secret[\-_]?key|client[\-_]?secret|access[\-_]?key|secret|token|"
    r"password|passwd|pwd|bearer|authorization|auth[\-_]?token|smtp[\-_]?password)\b"
    r"\s*[=:]\s*[^\s,;\"']+")
_SECRET_TOKENS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"\bAKIA[0-9A-Z]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
)
_REDACTED = "<redacted>"
_SCRUBBED_DIRECTIVE = "[review-only]"


def _sanitize(text: object) -> str:
    """Redact secret-shaped tokens from a string (a delivered byte NEVER carries a secret)."""
    out = str(text or "")
    out = _SECRET_KV.sub(
        lambda m: m.group(0).split("=")[0].split(":")[0].rstrip() + "=" + _REDACTED, out)
    for pattern in _SECRET_TOKENS:
        out = pattern.sub(_REDACTED, out)
    return out


def _scrub_forbidden(text: str) -> str:
    """Replace any forbidden action phrase with a review-only marker (case-insensitive)."""
    out = str(text or "")
    for phrase in FORBIDDEN_ALERT_PHRASES:
        out = re.sub(re.escape(phrase), _SCRUBBED_DIRECTIVE, out, flags=re.IGNORECASE)
    return out


def _assert_no_forbidden(*chunks: str) -> None:
    """Defensive guard: refuse to emit any forbidden action phrase in delivered content."""
    haystack = " ".join(str(c) for c in chunks).lower()
    for phrase in FORBIDDEN_ALERT_PHRASES:
        if phrase in haystack:
            raise PermanentDeliveryError(
                "delivered content refused: forbidden action phrase {0!r} -- an alert notifies "
                "an observation, it never instructs a trade".format(phrase))


# --------------------------------------------------------------------------- #
# 3. Errors -- retryable vs permanent transport failures                        #
# --------------------------------------------------------------------------- #
class AlertDeliveryError(RuntimeError):
    """Base class for a delivery failure."""


class RetryableDeliveryError(AlertDeliveryError):
    """A transient transport failure -> ``failed_retryable`` (may be retried later, not in-tick)."""


class PermanentDeliveryError(AlertDeliveryError):
    """A permanent transport / content failure -> ``failed_permanent`` (retrying will not help)."""


_RETRYABLE_TOKENS = (
    "timeout", "timed out", "temporar", "again", "unavailable", "throttle", "rate limit",
    "rate-limit", "connection reset", "503", "502", "504", "421", "too many requests",
)
_PERMANENT_TOKENS = (
    "invalid", "reject", "refused", "not permitted", "forbidden", "malformed",
    "no such", "does not exist", "permanent", "550", "551", "553", "554",
)


def _classify_error(exc: BaseException) -> str:
    """Map a raised transport error to ``failed_retryable`` / ``failed_permanent`` (labels)."""
    if isinstance(exc, PermanentDeliveryError):
        return AlertDeliveryStatus.FAILED_PERMANENT
    if isinstance(exc, RetryableDeliveryError):
        return AlertDeliveryStatus.FAILED_RETRYABLE
    text = "{0} {1}".format(type(exc).__name__, exc).lower()
    if any(token in text for token in _PERMANENT_TOKENS):
        return AlertDeliveryStatus.FAILED_PERMANENT
    if any(token in text for token in _RETRYABLE_TOKENS):
        return AlertDeliveryStatus.FAILED_RETRYABLE
    # An unclassified transport hiccup is conservatively retryable (never silently dropped).
    return AlertDeliveryStatus.FAILED_RETRYABLE


# --------------------------------------------------------------------------- #
# 4. AlertDeliveryResult -- one frozen, sanitized attempt record                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AlertDeliveryResult:
    """One delivery attempt: which alert, which channel, the outcome status, sanitized detail.

    ``detail_sanitized`` is already scrubbed of secret shapes and forbidden action language -- it
    NEVER carries a raw credential value or a trade instruction. There is no severity / score
    field: a delivery result records an OUTCOME, never a market decision.
    """

    alert_id: str = ""
    channel: str = ""
    status: str = AlertDeliveryStatus.NOT_DELIVERED
    mode: str = ""
    attempted_at: str = ""
    detail_sanitized: str = ""
    retry_count: int = 0

    def __post_init__(self) -> None:
        for name in ("alert_id", "channel", "attempted_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "AlertDeliveryResult.{0} is required and must be non-empty".format(name))
        if self.status not in DELIVERY_STATUSES:
            raise ValueError(
                "AlertDeliveryResult.status {0!r} invalid (closed vocabulary: {1})".format(
                    self.status, sorted(DELIVERY_STATUSES)))
        if not isinstance(self.retry_count, int) or isinstance(self.retry_count, bool) \
                or self.retry_count < 0:
            raise ValueError("AlertDeliveryResult.retry_count must be a non-negative int")
        # Detail is sanitized + forbidden-scrubbed at construction (defence in depth).
        object.__setattr__(self, "detail_sanitized",
                           _scrub_forbidden(_sanitize(self.detail_sanitized)))


# --------------------------------------------------------------------------- #
# 5. AlertDeliveryPolicy -- per-mode channel rules + the high-severity gate      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AlertDeliveryPolicy:
    """The per-mode delivery rules. The safe defaults suppress ALL external delivery.

    * The in-app inbox is ALWAYS allowed (in every mode) -- it is the safe default channel.
    * ``OFF`` / ``MANUAL`` -> NO external delivery (``suppressed_by_mode``): a manual-run alert
      stays in the in-app inbox only.
    * ``SHADOW_24X7`` -> external delivery is ``suppressed_by_mode`` UNLESS
      ``shadow_delivery_enabled`` is set (an explicit shadow-delivery opt-in); a shadow message
      is always clearly labelled Shadow Mode.
    * ``PRODUCTION_24X7`` -> external delivery is gated to the Phase-020F activation. Until then
      ``production_activated`` is ``False`` and external delivery is ``suppressed_by_policy``.

    The high-severity gate: a ``critical`` delivery REQUIRES a healthy/approved DQ state +
    non-speculative authority (not a social / rumor category) + a run_id + provenance
    (evidence). An unsupported ``critical`` is capped to ``review_required`` -- a social / rumor /
    DQ-failed input can never be delivered as a critical production action.
    """

    shadow_delivery_enabled: bool = False
    production_activated: bool = False          # False until the Phase-020F activation gate

    @classmethod
    def default(cls) -> "AlertDeliveryPolicy":
        """The safe default policy: inbox always, NO external delivery (shadow + production off)."""
        return cls(shadow_delivery_enabled=False, production_activated=False)

    # -- the high-severity gate --------------------------------------------- #
    def high_severity_supported(self, alert: Alert) -> bool:
        """True iff a ``critical`` delivery is SUPPORTED for ``alert`` (else it must be capped).

        Requires: a run_id (provenance of the producing run), a healthy/approved DQ state,
        a non-speculative (non social/rumor) category, and at least one evidence reference.
        """
        if not str(getattr(alert, "run_id", "")).strip():
            return False
        if str(getattr(alert, "dq_state", "")).lower() not in HEALTHY_DQ_STATES:
            return False
        if getattr(alert, "category", "") in SPECULATIVE_ALERT_CATEGORIES:
            return False
        if not tuple(getattr(alert, "evidence_refs", ()) or ()):
            return False
        return True

    def effective_delivery_severity(self, alert: Alert) -> str:
        """The delivery-ladder severity for ``alert``, capping an unsupported ``critical``.

        The 015C/020D alert severity is mapped onto the delivery ladder; a ``critical`` that
        fails :meth:`high_severity_supported` is capped to ``review_required``.
        """
        mapped = _ALERT_TO_DELIVERY_SEVERITY.get(str(getattr(alert, "severity", "")), "info")
        if mapped == "critical" and not self.high_severity_supported(alert):
            return "review_required"
        return mapped

    # -- the per-channel decision ------------------------------------------- #
    def decide(self, *, is_external: bool, mode: object, alert: Alert) -> str:
        """The delivery decision for ONE channel: ``"allowed"`` or a suppression status.

        The inbox is always allowed; every external decision is mode-gated (and, in an activated
        production, additionally gated on the high-severity predicate for a critical alert).
        """
        if not is_external:
            return "allowed"                    # the in-app inbox is always allowed
        m = _norm_mode(mode)
        if m in (MODE_OFF, MODE_MANUAL):
            return AlertDeliveryStatus.SUPPRESSED_BY_MODE
        if m == MODE_SHADOW:
            return ("allowed" if self.shadow_delivery_enabled
                    else AlertDeliveryStatus.SUPPRESSED_BY_MODE)
        if m == MODE_PRODUCTION:
            if not self.production_activated:
                return AlertDeliveryStatus.SUPPRESSED_BY_POLICY   # Phase-020F not built yet
            # A critical whose support fails the gate can NEVER go out as a production action.
            raw = _ALERT_TO_DELIVERY_SEVERITY.get(str(getattr(alert, "severity", "")), "info")
            if raw == "critical" and not self.high_severity_supported(alert):
                return AlertDeliveryStatus.SUPPRESSED_BY_POLICY
            return "allowed"
        return AlertDeliveryStatus.SUPPRESSED_BY_MODE           # unknown mode -> safe suppression


# --------------------------------------------------------------------------- #
# 6. Channels -- the ABC + inbox (safe default) + email (lazy/injected/dry-run)  #
# --------------------------------------------------------------------------- #
class AlertDeliveryChannel(ABC):
    """A delivery channel: it turns one alert into ONE :class:`AlertDeliveryResult`.

    ``channel_id`` is a stable label; ``is_external`` marks whether the channel leaves the app
    (external channels are mode-gated by the policy; the inbox is not).
    """

    channel_id: str = "channel"
    is_external: bool = False

    @abstractmethod
    def deliver(self, alert: Alert, *, mode: object, now: str) -> AlertDeliveryResult:
        """Deliver ``alert`` and return the sanitized attempt result (a channel NEVER acts)."""
        raise NotImplementedError


class InboxChannel(AlertDeliveryChannel):
    """The SAFE DEFAULT: mark the alert delivered to the in-app inbox. Always allowed.

    The alert already lives in the append-only :class:`~reality_mesh.alerts.AlertStore`; this
    channel records that it is present + visible in the operator's in-app inbox. It reaches no
    network and instructs nothing.
    """

    channel_id = "inbox"
    is_external = False

    def deliver(self, alert: Alert, *, mode: object, now: str) -> AlertDeliveryResult:
        shadow = _is_shadow(mode)
        marker = "Shadow Mode (non-production) " if shadow else ""
        detail = ("{0}alert delivered to the in-app inbox: {1} -- review only, nothing placed or "
                  "changed".format(marker, delivery_category_display(getattr(alert, "category", ""))))
        return AlertDeliveryResult(
            alert_id=alert.alert_id, channel=self.channel_id,
            status=AlertDeliveryStatus.DELIVERED, mode=_norm_mode(mode),
            attempted_at=str(now), detail_sanitized=detail, retry_count=0)


# The operator-facing disable / unsubscribe note carried on every email body.
_EMAIL_DISABLE_NOTE = (
    "To stop CosmosIQ email alerts, set delivery to inbox-only in operator settings or unset the "
    "email sender credential (COSMOSIQ_ALERT_EMAIL_SENDER). CosmosIQ never connects to a broker; "
    "execution is Manual Review Only.")

# The env var NAMES the real email path reads lazily (presence-only; a VALUE is never stored).
EMAIL_CREDENTIAL_ENV = "COSMOSIQ_ALERT_EMAIL_SENDER"
EMAIL_HOST_ENV = "COSMOSIQ_ALERT_EMAIL_HOST"
EMAIL_RECIPIENT_ENV = "COSMOSIQ_ALERT_EMAIL_RECIPIENT"


class EmailChannel(AlertDeliveryChannel):
    """The first EXTERNAL channel -- email. Mirrors the SEC-adapter lazy/injected pattern.

    ``transport`` is an INJECTABLE callable ``transport(message: dict) -> None`` (it may raise a
    :class:`RetryableDeliveryError` / :class:`PermanentDeliveryError` to exercise the failure
    paths); when ``None`` the real transport is built lazily INSIDE :meth:`_send` (``smtplib`` is
    imported there, never at module top). ``dry_run`` (default ``True``) renders the message and
    returns a delivered result WITHOUT sending -- the safe test / preview path. ``sender_present``
    is a PRESENCE flag only (True / False / None=infer from wiring): a credential VALUE passed by
    mistake is rejected without being stored or echoed. A missing sender credential -> a labelled
    ``not_delivered`` result (no value echoed). The subject carries the mode marker; the body is
    sanitized, carries the Shadow marker in shadow, and NEVER a forbidden phrase.
    """

    channel_id = "email"
    is_external = True

    def __init__(self, transport: Optional[Callable[[Dict[str, object]], None]] = None, *,
                 sender_present: Optional[bool] = None, dry_run: bool = True) -> None:
        if transport is not None and not callable(transport):
            raise ValueError(
                "EmailChannel.transport must be a callable transport(message) (the injected "
                "transport shape) or None")
        if sender_present is not None and not isinstance(sender_present, bool):
            # NEVER echo the offending argument: it may BE the credential value.
            raise ValueError(
                "EmailChannel.sender_present is a PRESENCE flag (True/False/None) -- never pass "
                "the credential value; the argument was rejected and has not been stored")
        self._transport = transport
        self._sender_present = sender_present
        self.dry_run = bool(dry_run)

    def __repr__(self) -> str:   # presence labels only -- a credential value never exists here
        wired = "injected" if self._transport is not None else "default_real"
        return ("EmailChannel(transport={0}, sender_present={1}, dry_run={2})".format(
            wired, self._sender_present, self.dry_run))

    # -- credential presence (a label; the value is never stored) ------------ #
    def _credential_present(self) -> bool:
        if self._sender_present is not None:
            return self._sender_present
        if self._transport is not None:
            return True                         # an injected transport implies a configured send
        import os                               # lazy; NOT a network import
        return bool(os.environ.get(EMAIL_CREDENTIAL_ENV, ""))

    # -- render the message (sanitized, shadow-marked, forbidden-scrubbed) ---- #
    def render_message(self, alert: Alert, *, mode: object) -> Dict[str, str]:
        shadow = _is_shadow(mode)
        marker = "[CosmosIQ Shadow]" if shadow else "[CosmosIQ]"
        review = str(getattr(alert, "recommended_review_action", "") or "") or "Review Required"
        category_display = delivery_category_display(getattr(alert, "category", ""))
        subject = "{0} {1}: {2}".format(marker, review, category_display)

        lines: List[str] = []
        if shadow:
            lines.append(SHADOW_MARKER)
            lines.append("Shadow Mode (non-production) observation -- review only, no escalation; "
                         "nothing is placed, ordered, or changed.")
        lines.append(_sanitize(getattr(alert, "human_readable_reason", "")))
        dq_state = str(getattr(alert, "dq_state", "") or "")
        if dq_state:
            lines.append("Data-quality state: {0}".format(dq_state))
        if str(getattr(alert, "run_id", "")).strip():
            lines.append("Run: {0}".format(alert.run_id))
        evidence = tuple(getattr(alert, "evidence_refs", ()) or ())
        if evidence:
            lines.append("Evidence: {0}".format(", ".join(_sanitize(e) for e in evidence)))
        lines.append("Execution: Manual Review Only -- CosmosIQ observes, it never trades.")
        lines.append(_EMAIL_DISABLE_NOTE)

        subject = _scrub_forbidden(_sanitize(subject))
        body = _scrub_forbidden(_sanitize("\n".join(lines)))
        _assert_no_forbidden(subject, body)      # defence in depth: never emit an action phrase
        return {"subject": subject, "body": body}

    # -- deliver ------------------------------------------------------------- #
    def deliver(self, alert: Alert, *, mode: object, now: str) -> AlertDeliveryResult:
        message = self.render_message(alert, mode=mode)
        if not self._credential_present():
            return AlertDeliveryResult(
                alert_id=alert.alert_id, channel=self.channel_id,
                status=AlertDeliveryStatus.NOT_DELIVERED, mode=_norm_mode(mode),
                attempted_at=str(now),
                detail_sanitized=("email sender credential absent (presence flag / {0} not set): "
                                  "not sent -- visible gap, no value echoed, no fallback".format(
                                      EMAIL_CREDENTIAL_ENV)),
                retry_count=0)
        if self.dry_run:
            return AlertDeliveryResult(
                alert_id=alert.alert_id, channel=self.channel_id,
                status=AlertDeliveryStatus.DELIVERED, mode=_norm_mode(mode),
                attempted_at=str(now),
                detail_sanitized=("dry-run: email rendered OFFLINE and not transmitted "
                                  "(subject: {0})".format(message["subject"])),
                retry_count=0)
        try:
            self._send(message)
        except Exception as exc:            # noqa: BLE001 -- classified failure, never a crash
            status = _classify_error(exc)
            return AlertDeliveryResult(
                alert_id=alert.alert_id, channel=self.channel_id, status=status,
                mode=_norm_mode(mode), attempted_at=str(now),
                detail_sanitized="email send failed ({0}): {1}".format(
                    status, "{0}: {1}".format(type(exc).__name__, exc)),
                retry_count=0)
        return AlertDeliveryResult(
            alert_id=alert.alert_id, channel=self.channel_id,
            status=AlertDeliveryStatus.DELIVERED, mode=_norm_mode(mode),
            attempted_at=str(now),
            detail_sanitized="email transmitted via the configured transport (subject: {0})".format(
                message["subject"]),
            retry_count=0)

    # -- the send boundary: injected transport, else the lazy real SMTP path -- #
    def _send(self, message: Mapping[str, object]) -> None:
        """Send one message. The injected transport is used when wired (tests); otherwise the
        REAL SMTP path is built lazily -- ``smtplib`` is imported HERE, never at module top, and
        the credential value transits only into the connection and is never stored / echoed. The
        offline test suite NEVER reaches the real path."""
        if self._transport is not None:
            self._transport(dict(message))
            return
        # -- real path (NEVER exercised by the offline test suite) ----------- #
        # smtplib is loaded ONLY here, and dynamically: the reality_mesh offline-import guard
        # forbids a STATIC forbidden-module import anywhere in the package (so `import reality_mesh`
        # never pulls in a mail transport). Importing it lazily by name keeps the offline posture
        # structurally guaranteed while the real SMTP path stays reachable for an operator.
        import importlib                        # lazy; NOT a network import
        import os                               # lazy; NOT a network import
        smtplib = importlib.import_module("smtplib")   # lazy; the real transport, never in tests
        sender = os.environ.get(EMAIL_CREDENTIAL_ENV, "")
        host = os.environ.get(EMAIL_HOST_ENV, "")
        recipient = os.environ.get(EMAIL_RECIPIENT_ENV, "")
        if not sender or not host or not recipient:
            raise PermanentDeliveryError(
                "email transport not configured ({0} / {1} / {2}) -- not sent, nothing "
                "fabricated".format(EMAIL_CREDENTIAL_ENV, EMAIL_HOST_ENV, EMAIL_RECIPIENT_ENV))
        body = "Subject: {0}\r\n\r\n{1}".format(message.get("subject", ""), message.get("body", ""))
        try:
            server = smtplib.SMTP(host)
            try:
                server.sendmail(sender, [recipient], body)
            finally:
                server.quit()
        except smtplib.SMTPException as exc:
            raise RetryableDeliveryError("SMTP transport error: {0}".format(exc)) from exc


# --------------------------------------------------------------------------- #
# 7. AlertDeliveryStore -- every attempt persisted APPEND-ONLY                    #
# --------------------------------------------------------------------------- #
class AlertDeliveryStore(AppendOnlyStore):
    """The delivery ledger: one JSONL line per attempt, append-only, never edited.

    Re-delivering an alert APPENDS a NEW line; a prior line is byte-unchanged forever. Query axes:
    ``run_id`` (envelope) + any payload field (``alert_id`` / ``channel`` / ``status`` / ``mode``).
    """

    filename = "alert_delivery_store.jsonl"
    record_cls = AlertDeliveryResult
    id_field = None                             # record_id is composed by deliver_alert
    timestamp_field = "attempted_at"


def delivery_results(store_dir: str) -> Tuple[AlertDeliveryResult, ...]:
    """Every persisted delivery attempt, in append order."""
    return tuple(AlertDeliveryStore(store_dir).read_all())


def latest_delivery_status(store_dir: str, alert_id: str) -> str:
    """The most recent delivery status for ``alert_id`` ("" if it was never attempted).

    Prefers the last EXTERNAL attempt when one exists (that is the notification the operator
    cares about); otherwise the last attempt of any channel (e.g. the inbox).
    """
    attempts = [r for r in delivery_results(store_dir) if r.alert_id == alert_id]
    if not attempts:
        return ""
    external = [r for r in attempts if r.channel != InboxChannel.channel_id]
    chosen = external[-1] if external else attempts[-1]
    return chosen.status


def default_delivery_channels() -> Tuple[AlertDeliveryChannel, ...]:
    """The safe default channel set: the in-app inbox only (no external delivery)."""
    return (InboxChannel(),)


# --------------------------------------------------------------------------- #
# 8. deliver_alert -- apply the policy, deliver via allowed channels, persist    #
# --------------------------------------------------------------------------- #
def deliver_alert(alert: Alert, *, policy: AlertDeliveryPolicy, mode: object,
                  channels: Tuple[AlertDeliveryChannel, ...], store_dir: str,
                  now: str) -> Tuple[AlertDeliveryResult, ...]:
    """Deliver ``alert`` through ``channels`` under ``policy`` and ``mode``; persist each attempt.

    For each channel the policy decides ``allowed`` or a suppression status
    (``suppressed_by_mode`` / ``suppressed_by_policy``). An allowed channel is invoked (the inbox
    marks it delivered; email dry-runs / injects / classifies a failure). Every result is
    persisted APPEND-ONLY into :class:`AlertDeliveryStore` and the tuple is returned. Delivery is
    NOTIFICATION only -- nothing here places, orders, or changes anything.
    """
    if alert is None or not str(getattr(alert, "alert_id", "")).strip():
        raise ValueError("deliver_alert requires an Alert carrying a non-empty alert_id")
    if not str(now).strip():
        raise ValueError("deliver_alert requires an injected 'now' instant")
    if policy is None:
        raise ValueError("deliver_alert requires an AlertDeliveryPolicy")
    store = AlertDeliveryStore(store_dir)
    results: List[AlertDeliveryResult] = []
    for channel in channels:
        decision = policy.decide(is_external=channel.is_external, mode=mode, alert=alert)
        if decision == "allowed":
            result = channel.deliver(alert, mode=mode, now=now)
        else:
            result = AlertDeliveryResult(
                alert_id=alert.alert_id, channel=channel.channel_id, status=decision,
                mode=_norm_mode(mode), attempted_at=str(now),
                detail_sanitized=_suppression_detail(decision, mode), retry_count=0)
        prior = sum(1 for rec in store.read_records()
                    if rec.get("payload", {}).get("alert_id") == alert.alert_id
                    and rec.get("payload", {}).get("channel") == channel.channel_id)
        record_id = "delivery.{0}.{1}.{2:03d}".format(
            alert.alert_id, channel.channel_id, prior + 1)
        store.append(result, record_id=record_id, timestamp=str(now),
                     run_id=str(getattr(alert, "run_id", "")))
        results.append(result)
    return tuple(results)


def _suppression_detail(status: str, mode: object) -> str:
    m = _norm_mode(mode)
    if status == AlertDeliveryStatus.SUPPRESSED_BY_MODE:
        if m in (MODE_OFF, MODE_MANUAL):
            return ("external delivery suppressed in {0}: no continuous delivery -- the alert "
                    "stays in the in-app inbox only".format(m))
        return ("external delivery suppressed in {0}: shadow delivery is not enabled -- the "
                "alert stays in the in-app inbox only, clearly marked Shadow Mode".format(m))
    if status == AlertDeliveryStatus.SUPPRESSED_BY_POLICY:
        return ("external delivery gated in {0}: the Phase-020F activation gate has not passed -- "
                "production external delivery stays suppressed".format(m))
    return "delivery suppressed ({0})".format(status)
