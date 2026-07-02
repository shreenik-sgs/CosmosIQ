"""Validation helpers for the Reality Mesh handoff substrate (IMPLEMENTATION-012A).

Pure, offline, stdlib-only guards enforcing the ARCHITECTURE_CONTRACT_012 invariants at the
object boundary. The models validate themselves on construction; these helpers make the same
guarantees callable / introspectable for the router, the gatekeeper, and the test matrix:

* no empty required IDs;
* closed-labels-only (a non-empty label must be a member of its closed vocabulary);
* ``source_refs`` / ``evidence_refs``, ``conflicts`` and ``data_gaps`` are preserved;
* a HandoffEnvelope always carries the four default-forbidden downstream uses;
* an X/social (narrative) claim can never be ``verified_fact`` (rumor/narrative unless
  explicitly ``company_claim`` / ``reported_claim``);
* a manual / analyst datum can never be ``canonical``;
* STRUCTURAL guard: no handoff object exposes any trade-decision / scoring attribute
  (buy / sell / hold / order / trade / broker / score / rank / rating).

``validate_*`` helpers raise ``ValueError`` on a data violation; ``assert_*`` helpers raise
``AssertionError`` on a structural violation. No network, no scheduler, no broker imports.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Tuple

from . import labels as _labels

# Tokens that must NEVER appear in a field name of any handoff object (labels, not trades;
# labels, not numbers). Mirrors the accepted 011 banned-field set.
TRADE_FIELD_TOKENS: Tuple[str, ...] = (
    "buy", "sell", "hold", "order", "trade", "broker", "score", "rank", "rating",
)


def _field_names(obj_or_cls) -> Tuple[str, ...]:
    cls = obj_or_cls if isinstance(obj_or_cls, type) else type(obj_or_cls)
    if not is_dataclass(cls):
        raise TypeError("{0} is not a dataclass".format(cls))
    return tuple(f.name for f in fields(cls))


# --------------------------------------------------------------------------- #
# Structural guards                                                            #
# --------------------------------------------------------------------------- #
def assert_no_trade_fields(obj_or_cls) -> None:
    """Assert the object/class exposes NO trade-decision or scoring field.

    Introspective: checks every dataclass field name for a banned token. Raises
    ``AssertionError`` naming the offending field if any is found.
    """
    for name in _field_names(obj_or_cls):
        low = name.lower()
        for token in TRADE_FIELD_TOKENS:
            if token in low:
                raise AssertionError(
                    "trade/score field {0!r} forbidden on {1}".format(
                        name, obj_or_cls if isinstance(obj_or_cls, type)
                        else type(obj_or_cls).__name__))


def assert_manual_not_canonical(authority: str, claim_status: str = "") -> None:
    """Assert a manual / analyst datum is not marked canonical. Raises ``AssertionError``."""
    manual_like = claim_status in ("manual", "analyst_estimate")
    if authority == "canonical" and manual_like:
        raise AssertionError(
            "invariant violated: a manual/analyst datum marked canonical")


def assert_social_not_verified(event) -> None:
    """Assert a rumor-tier / X-social event is not a ``verified_fact``.

    A social / rumor claim may be ``rumor`` / ``reported_claim`` / ``company_claim`` but
    never ``verified_fact`` by itself (ARCHITECTURE_CONTRACT_012 §C). The check fires when
    ANY of the following holds and ``claim_status == "verified_fact"``:

    * ``discipline`` is the narrative discipline, OR its ``source_type`` is an exact social
      token (``is_social_source``);
    * ``source_authority`` is ``rumor`` -- a rumor-tier source cannot confirm a fact;
    * ``source_type`` contains an X/social substring (``x_social`` / ``social`` / ``twitter``
      / ``x.com`` / ``stocktwits`` / ``reddit``).

    Raises ``AssertionError`` on violation.
    """
    if getattr(event, "claim_status", "") != "verified_fact":
        return
    source_type = getattr(event, "source_type", "")
    authority = getattr(event, "source_authority", "")
    if (
        _labels.is_social_source(
            source_type=source_type, discipline=getattr(event, "discipline", ""))
        or authority == "rumor"
        or _labels.is_social_source_type(source_type)
    ):
        raise AssertionError(
            "invariant violated: rumor/X-social source marked verified_fact")


# --------------------------------------------------------------------------- #
# Label / id / evidence validation (ValueError on violation)                   #
# --------------------------------------------------------------------------- #
def validate_labels(obj) -> None:
    """Validate every closed-label field of ``obj`` (scalar + tuple) against its vocabulary."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if f.name in _labels.SCALAR_LABEL_VOCABULARIES:
            vocab = _labels.SCALAR_LABEL_VOCABULARIES[f.name]
            if not _labels.is_member(vocab, value):
                raise ValueError(
                    "{0}.{1}: invalid label {2!r}".format(
                        type(obj).__name__, f.name, value))
        elif f.name in _labels.TUPLE_LABEL_VOCABULARIES:
            vocab = _labels.TUPLE_LABEL_VOCABULARIES[f.name]
            for element in value:
                if element not in vocab:
                    raise ValueError(
                        "{0}.{1}: invalid label {2!r}".format(
                            type(obj).__name__, f.name, element))


def assert_required_ids(obj, names: Tuple[str, ...]) -> None:
    """Raise ``ValueError`` if any named id field is empty/blank."""
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is a required id and must be non-empty".format(
                    type(obj).__name__, name))


def assert_evidence_preserved(obj) -> None:
    """Assert the object carries the evidence-preserving fields (refs + conflicts + gaps).

    Every evidence-bearing object must expose ``conflicts`` and ``data_gaps`` and at least
    one of ``evidence_refs`` / ``source_refs``. Raises ``AssertionError`` otherwise.
    """
    names = set(_field_names(obj))
    for required in ("conflicts", "data_gaps"):
        if required not in names:
            raise AssertionError(
                "{0} does not preserve {1}".format(type(obj).__name__, required))
    if not ({"evidence_refs", "source_refs"} & names):
        raise AssertionError(
            "{0} preserves neither evidence_refs nor source_refs".format(
                type(obj).__name__))


def validate_event(event) -> None:
    """Full validation of a :class:`RealityEvent`."""
    assert_required_ids(event, ("event_id",))
    validate_labels(event)
    assert_manual_not_canonical(event.source_authority, event.claim_status)
    assert_social_not_verified(event)
    assert_no_trade_fields(event)
    assert_evidence_preserved(event)


def validate_finding(finding) -> None:
    """Full validation of an :class:`AgentFinding`."""
    assert_required_ids(finding, ("finding_id", "agent_id"))
    validate_labels(finding)
    # A finding carries an authority SUMMARY (no claim_status); it must not roll up to a
    # canonical summary off a manual/analyst finding-discipline. Authority alone is guarded.
    assert_no_trade_fields(finding)
    assert_evidence_preserved(finding)


def validate_signal(signal) -> None:
    """Full validation of a :class:`RealitySignal`."""
    assert_required_ids(signal, ("signal_id",))
    validate_labels(signal)
    assert_no_trade_fields(signal)
    assert_evidence_preserved(signal)


def validate_theme_pulse(pulse) -> None:
    """Full validation of a :class:`ThemePulse`."""
    assert_required_ids(pulse, ("theme_pulse_id",))
    validate_labels(pulse)
    assert_no_trade_fields(pulse)
    assert_evidence_preserved(pulse)


def validate_envelope(envelope) -> None:
    """Full validation of a :class:`HandoffEnvelope` including the mandatory forbidden uses."""
    assert_required_ids(envelope, ("envelope_id",))
    validate_labels(envelope)
    assert_no_trade_fields(envelope)
    missing = _labels.DEFAULT_FORBIDDEN_DOWNSTREAM_USES - set(envelope.forbidden_downstream_uses)
    if missing:
        raise ValueError(
            "HandoffEnvelope missing mandatory forbidden downstream uses: {0}".format(
                sorted(missing)))
    # A use may not be simultaneously allowed and forbidden.
    both = set(envelope.allowed_downstream_uses) & set(envelope.forbidden_downstream_uses)
    if both:
        raise ValueError(
            "HandoffEnvelope use both allowed and forbidden: {0}".format(sorted(both)))
