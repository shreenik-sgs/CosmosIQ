"""Outcome learning for the Reality Mesh (IMPLEMENTATION-017A).

The Learning & Feedback core: append-only outcome records plus reliability /
accuracy roll-ups, computed by comparing a PAST persisted claim to a LATER
persisted observation, both cited by id. Learning OBSERVES the 013B stores --
it never acts, never edits history, and never fabricates certainty:

* **Append-only; NO rewriting history.** An :class:`OutcomeRecord` NEVER
  modifies the signal / theme pulse / run it evaluates -- it is a NEW record
  that cites the earlier claim and the later observation by id. A later
  resolution is ANOTHER new record; the earlier ``unresolved`` line stays
  byte-unchanged forever, and so does every upstream store line.
* **No retroactive certainty.** Where the later observation does not exist,
  the outcome is ``unresolved`` -- an honest state, not a guess. An
  ``unresolved`` record carries NO observed run id and NO observed value
  (enforced at construction), and a resolved record MUST cite the run it was
  observed in.
* **Labels + counts, never a metric.** Reliability / accuracy is expressed as
  closed labels (``improving`` / ``stable`` / ``deteriorating`` /
  ``insufficient_history``) plus VOLUME counts (followed_through /
  contradicted / faded / unresolved). NO ratio / percentage / numeric field is
  ever stored -- every record field is a string or a volume count, and the
  013B store guard would refuse a metric key anyway.
* **Thresholds as data.** :data:`LEARNING_THRESHOLDS` carries the minimum
  resolved-outcome volume (3) below which every roll-up honestly reads
  ``insufficient_history`` -- no label pretends confidence.
* **Source reliability is learned, never upgraded backwards.** A rumor-tier
  source whose claims repeatedly fail rolls up as ``deteriorating``; a NEW
  roll-up with new evidence is a NEW appended record -- a past record is
  never revised upward (or at all).
* **Deterministic + offline.** Every id derives from record content, so a
  re-track / re-roll appends nothing new (idempotent guard); every timestamp
  is an injected string (no wall clock); persistence is local append-only
  JSONL only.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no daemon.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Dict, FrozenSet, List, Mapping, Tuple

from . import labels as _labels
from .alerts import CATEGORY_SEVERITY, Alert, AlertStore
from .stores import AppendOnlyStore, RunStore, SignalStore, ThemePulseStore
from .validation import assert_no_trade_fields

__all__ = [
    "OUTCOME_LABELS",
    "SUBJECT_KINDS",
    "RELIABILITY_LABELS",
    "LEARNING_THRESHOLDS",
    "RISK_CLAIM_STATES",
    "OutcomeRecord",
    "SignalReliabilityRecord",
    "ThemePulseAccuracyRecord",
    "SourceReliabilityRecord",
    "LEARNING_RECORDS",
    "OutcomeStore",
    "LearningStore",
    "LEARNING_STORE_CLASSES",
    "OutcomeTracker",
    "persisted_run_ids",
    "track_outcomes",
    "record_outcomes",
    "roll_signal_reliability",
    "roll_theme_pulse_accuracy",
    "roll_source_reliability",
    "record_learning_rollups",
    "emit_outcome_alerts",
]

# --------------------------------------------------------------------------- #
# Closed vocabularies + thresholds-as-data                                     #
# --------------------------------------------------------------------------- #

# What a later persisted run showed about an earlier persisted claim. CLOSED --
# ``unresolved`` is the honest no-later-observation state, never a guess.
OUTCOME_LABELS: FrozenSet[str] = frozenset(
    {"followed_through", "contradicted", "faded", "unresolved"})

# What kind of persisted subject an outcome evaluates.
SUBJECT_KINDS: FrozenSet[str] = frozenset({"signal", "theme_pulse", "finding"})

# The reliability / accuracy label ladder shared by every roll-up record.
# ``insufficient_history`` is mandatory below the resolved-outcome threshold.
RELIABILITY_LABELS: FrozenSet[str] = frozenset(
    {"improving", "stable", "deteriorating", "insufficient_history"})

# Thresholds live as DATA, not as buried constants: below this many RESOLVED
# outcomes a roll-up label reads ``insufficient_history`` -- no label pretends
# confidence off a tiny sample.
LEARNING_THRESHOLDS: Mapping[str, int] = {"min_resolved_outcomes": 3}

# Theme-pulse states whose CLAIM, when later followed through, is a confirmed
# risk state (feeds the reserved ``major_risk_emerged`` alert category).
RISK_CLAIM_STATES: FrozenSet[str] = frozenset(
    {"Crowded", "Exhausting", "Breaking down"})

# Direction polarity groups (labels, never numbers): same polarity persisted =
# followed through; opposite polarity = contradicted; a drop to neutral = faded.
_POSITIVE_DIRECTIONS = frozenset({"improving", "accelerating", "rising"})
_NEGATIVE_DIRECTIONS = frozenset({"deteriorating", "decelerating", "falling"})
_REVERSAL_DIRECTION = "reversing"

# The theme-pulse momentum ladder (rising arc) and the deterioration arc.
# Movement UP an arc is follow-through; movement against it is contradiction.
_RISING_STATE_LADDER = {
    "Dormant": 0, "Warming": 1, "Igniting": 2, "Broadening": 3, "Crowded": 4}
_DETERIORATION_STATE_LADDER = {"Exhausting": 0, "Breaking down": 1}


# --------------------------------------------------------------------------- #
# Shared record validation (strings + volume counts ONLY -- never a metric)    #
# --------------------------------------------------------------------------- #
def _require_text(obj, names: Tuple[str, ...]) -> None:
    """Raise ``ValueError`` if any named required text field is empty/blank."""
    for name in names:
        value = getattr(obj, name, "")
        if not isinstance(value, str) or value.strip() == "":
            raise ValueError(
                "{0}.{1} is required and must be non-empty".format(
                    type(obj).__name__, name))


def _require_label(obj, name: str, vocab: FrozenSet[str], *,
                   allow_empty: bool = False) -> None:
    value = getattr(obj, name, "")
    if allow_empty and value == "":
        return
    if value not in vocab:
        raise ValueError(
            "{0}.{1}: invalid label {2!r} (closed vocabulary: {3})".format(
                type(obj).__name__, name, value, sorted(vocab)))


def _require_counts(obj, names: Tuple[str, ...]) -> None:
    """Every named field must be a non-negative int VOLUME (never a float/bool)."""
    for name in names:
        value = getattr(obj, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                "{0}.{1} must be a non-negative integer volume count, got "
                "{2!r}".format(type(obj).__name__, name, value))


def _forbid_metric_values(obj) -> None:
    """No float anywhere on a learning record: a ratio is NEVER stored as a field."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, float):
            raise ValueError(
                "{0}.{1} is a float -- a learning record stores labels and "
                "volume counts only, never a numeric metric".format(
                    type(obj).__name__, f.name))
        if isinstance(value, tuple):
            for element in value:
                if isinstance(element, float):
                    raise ValueError(
                        "{0}.{1} contains a float -- a learning record never "
                        "stores a numeric metric".format(
                            type(obj).__name__, f.name))


def _require_window(obj) -> None:
    value = getattr(obj, "window")
    coerced = tuple(value)
    if len(coerced) != 2 or not all(isinstance(v, str) for v in coerced):
        raise ValueError(
            "{0}.window must be a (first_run_id, last_run_id) pair of "
            "strings".format(type(obj).__name__))
    object.__setattr__(obj, "window", coerced)


# --------------------------------------------------------------------------- #
# 1. OutcomeRecord -- one past claim vs one later observation, both cited      #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OutcomeRecord:
    """One appended learning fact: what a LATER run showed about a PAST claim.

    The record cites the past subject (``subject_id`` in ``subject_run_id``)
    and -- when resolved -- the later observation (``observed`` in
    ``observed_run_id``). It NEVER modifies the subject it evaluates. An
    ``unresolved`` outcome carries NO observed run and NO observed value: the
    honest no-later-observation state, enforced at construction, never a guess.
    """

    outcome_id: str = ""
    subject_kind: str = ""                  # closed: SUBJECT_KINDS
    subject_id: str = ""                    # the persisted claim record, by id
    subject_run_id: str = ""                # the run that persisted the claim
    subject_discipline: str = ""            # closed: DISCIPLINES ("" = unscoped)
    subject_theme_id: str = ""              # theme scope for theme_pulse subjects
    claimed: str = ""                       # the persisted claim AT THE TIME, quoted
    observed_run_id: str = ""               # "" when unresolved
    observed: str = ""                      # what the later run showed; "" when unresolved
    outcome_label: str = ""                 # closed: OUTCOME_LABELS
    basis: str = ""                         # plain English citing both ids
    created_at: str = ""                    # injected timestamp (no wall clock)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("outcome_id", "subject_id", "subject_run_id",
                             "claimed", "basis", "created_at"))
        _require_label(self, "subject_kind", SUBJECT_KINDS)
        _require_label(self, "outcome_label", OUTCOME_LABELS)
        _require_label(self, "subject_discipline", _labels.DISCIPLINES,
                       allow_empty=True)
        for f in fields(self):
            if not isinstance(getattr(self, f.name), str):
                raise ValueError(
                    "OutcomeRecord.{0} must be a string -- an outcome record "
                    "is citations + labels only".format(f.name))
        if self.outcome_label == "unresolved":
            if self.observed_run_id or self.observed:
                raise ValueError(
                    "OutcomeRecord: an 'unresolved' outcome must carry NO "
                    "observed run / observed value -- unresolved is the honest "
                    "no-later-observation state, never a fabricated certainty")
        else:
            if not self.observed_run_id.strip():
                raise ValueError(
                    "OutcomeRecord: a resolved outcome ({0!r}) must cite the "
                    "run it was observed in".format(self.outcome_label))
        _forbid_metric_values(self)


# --------------------------------------------------------------------------- #
# 2. Roll-up records -- labels + volume counts, windowed, basis-cited          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SignalReliabilityRecord:
    """Per-discipline signal reliability: outcome VOLUMES + a closed label.

    ``reliability_label`` compares hit vs miss volumes; below the
    ``min_resolved_outcomes`` threshold it reads ``insufficient_history``. No
    numeric reliability value exists here -- counts are volumes, and a ratio
    is never stored as a field.
    """

    learning_id: str = ""
    discipline: str = ""                    # closed: DISCIPLINES ("" = unscoped)
    window: Tuple[str, str] = ("", "")      # (first_run_id, last_run_id)
    followed_through_count: int = 0         # volume count
    contradicted_count: int = 0             # volume count
    faded_count: int = 0                    # volume count
    unresolved_count: int = 0               # volume count
    reliability_label: str = ""             # closed: RELIABILITY_LABELS
    basis: str = ""                         # plain English citing the window runs
    created_at: str = ""                    # injected timestamp

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "basis", "created_at"))
        _require_label(self, "discipline", _labels.DISCIPLINES, allow_empty=True)
        _require_label(self, "reliability_label", RELIABILITY_LABELS)
        _require_counts(self, ("followed_through_count", "contradicted_count",
                               "faded_count", "unresolved_count"))
        _require_window(self)
        _forbid_metric_values(self)


@dataclass(frozen=True)
class ThemePulseAccuracyRecord:
    """Per-theme pulse accuracy: transition VOLUMES + a closed label."""

    learning_id: str = ""
    theme_id: str = ""
    window: Tuple[str, str] = ("", "")      # (first_run_id, last_run_id)
    transitions_observed: int = 0           # volume count (resolved outcomes)
    transitions_followed_through: int = 0   # volume count
    transitions_reversed: int = 0           # volume count (contradicted)
    accuracy_label: str = ""                # closed: RELIABILITY_LABELS
    basis: str = ""                         # plain English citing the window runs
    created_at: str = ""                    # injected timestamp

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "theme_id", "basis", "created_at"))
        _require_label(self, "accuracy_label", RELIABILITY_LABELS)
        _require_counts(self, ("transitions_observed",
                               "transitions_followed_through",
                               "transitions_reversed"))
        _require_window(self)
        _forbid_metric_values(self)


@dataclass(frozen=True)
class SourceReliabilityRecord:
    """Per-source-tier (or per-adapter) reliability: outcome VOLUMES + a label.

    Social / rumor reliability is learned here: a rumor tier whose claims
    repeatedly fail is labelled ``deteriorating``. A past record is NEVER
    retroactively upgraded -- new evidence appends a NEW record; the earlier
    line stays byte-unchanged forever.
    """

    learning_id: str = ""
    source_kind: str = ""                   # closed: SOURCE_AUTHORITIES ("" if adapter-scoped)
    adapter_id: str = ""                    # "" if authority-tier-scoped
    window: Tuple[str, str] = ("", "")      # (first_run_id, last_run_id)
    followed_through_count: int = 0         # volume count
    contradicted_count: int = 0             # volume count
    faded_count: int = 0                    # volume count
    unresolved_count: int = 0               # volume count
    reliability_label: str = ""             # closed: RELIABILITY_LABELS
    basis: str = ""                         # plain English citing the window runs
    created_at: str = ""                    # injected timestamp

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "basis", "created_at"))
        _require_label(self, "source_kind", _labels.SOURCE_AUTHORITIES,
                       allow_empty=True)
        _require_label(self, "reliability_label", RELIABILITY_LABELS)
        _require_counts(self, ("followed_through_count", "contradicted_count",
                               "faded_count", "unresolved_count"))
        _require_window(self)
        if not self.source_kind.strip() and not self.adapter_id.strip():
            raise ValueError(
                "SourceReliabilityRecord requires source_kind (authority tier) "
                "or adapter_id -- an unscoped reliability record is refused")
        _forbid_metric_values(self)


# The four learning records (for registry / test introspection).
LEARNING_RECORDS = (
    OutcomeRecord,
    SignalReliabilityRecord,
    ThemePulseAccuracyRecord,
    SourceReliabilityRecord,
)

_ROLLUP_CLASS_BY_NAME = {
    "SignalReliabilityRecord": SignalReliabilityRecord,
    "ThemePulseAccuracyRecord": ThemePulseAccuracyRecord,
    "SourceReliabilityRecord": SourceReliabilityRecord,
}


# --------------------------------------------------------------------------- #
# 3. The learning stores -- 013B AppendOnlyStore composition                    #
# --------------------------------------------------------------------------- #
class OutcomeStore(AppendOnlyStore):
    """Append-only outcome log (``outcome_store.jsonl``): one line per outcome.

    Query axes: ``run_id`` (the subject's run) / ``subject_kind`` /
    ``outcome_label`` / ``subject_discipline`` / ``theme`` (over
    ``subject_theme_id``). Never updated, never rewritten -- a later
    resolution is a NEW line, and the ``unresolved`` line it supersedes stays
    byte-unchanged forever.
    """

    filename = "outcome_store.jsonl"
    record_cls = OutcomeRecord
    id_field = "outcome_id"
    timestamp_field = "created_at"
    theme_fields = ("subject_theme_id",)


class LearningStore(AppendOnlyStore):
    """Append-only roll-up log (``learning_store.jsonl``) for the three
    reliability / accuracy record shapes.

    The envelope's ``record_type`` names the shape, so a mixed log
    reconstructs each line to its own frozen record class. Append-only like
    every 013B store: a fresh roll-up is a NEW line, never a revision.
    """

    filename = "learning_store.jsonl"
    record_cls = None                       # mixed shapes; resolved per line
    id_field = "learning_id"
    timestamp_field = "created_at"

    def append(self, item, *, run_id: str = "", timestamp: str = "",
               record_id: str = "") -> str:
        if type(item).__name__ not in _ROLLUP_CLASS_BY_NAME:
            raise TypeError(
                "LearningStore accepts only the roll-up records ({0}); got "
                "{1}".format(sorted(_ROLLUP_CLASS_BY_NAME), type(item).__name__))
        self.record_cls = type(item)        # instance-level, for the envelope
        try:
            return super().append(
                item, run_id=run_id, timestamp=timestamp, record_id=record_id)
        finally:
            self.record_cls = None

    def _reconstruct(self, record):
        cls = _ROLLUP_CLASS_BY_NAME.get(str(record.get("record_type", "")))
        if cls is None:
            raise ValueError(
                "LearningStore cannot reconstruct record_type {0!r}".format(
                    record.get("record_type", "")))
        self.record_cls = cls
        try:
            return super()._reconstruct(record)
        finally:
            self.record_cls = None


# The two learning stores (ADDITIVE: the 013B spine still counts seven).
LEARNING_STORE_CLASSES = (OutcomeStore, LearningStore)


# --------------------------------------------------------------------------- #
# 4. Outcome tracking -- pure read-and-compare over the 013B stores            #
# --------------------------------------------------------------------------- #
def persisted_run_ids(store_dir: str) -> Tuple[str, ...]:
    """Distinct run ids from the RunStore spine, in append sequence."""
    seen: List[str] = []
    for record in RunStore(store_dir).read_records():
        rid = str(record.get("run_id", "") or "")
        if rid and rid not in seen:
            seen.append(rid)
    return tuple(seen)


def _slug(text: str) -> str:
    """A deterministic id-safe token: lowercase alnum, other runs -> '-'."""
    out: List[str] = []
    last_dash = True
    for ch in str(text).lower():
        if ch.isalnum():
            out.append(ch)
            last_dash = False
        elif not last_dash:
            out.append("-")
            last_dash = True
    return "".join(out).strip("-") or "unnamed"


def _norm_theme(text: str) -> str:
    """Case / hyphen / underscore-insensitive theme token (mirrors stores)."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _signal_subject_key(signal) -> Tuple[str, Tuple[str, ...], Tuple[str, ...]]:
    """The cross-run identity of a signal: discipline + companies + themes."""
    return (
        getattr(signal, "discipline", ""),
        tuple(sorted(str(c).strip().upper()
                     for c in getattr(signal, "affected_companies", ()) or ())),
        tuple(sorted(_norm_theme(t)
                     for t in getattr(signal, "affected_themes", ()) or ())),
    )


def _pulse_theme_key(pulse) -> str:
    """The cross-run identity of a theme pulse: its normalized theme."""
    return _norm_theme(
        getattr(pulse, "theme_id", "") or getattr(pulse, "theme_name", ""))


def _direction_polarity(direction: str) -> str:
    if direction in _POSITIVE_DIRECTIONS:
        return "positive"
    if direction in _NEGATIVE_DIRECTIONS:
        return "negative"
    return "neutral"


def _direction_outcome(claimed: str, observed: str) -> str:
    """Compare two persisted direction labels -> an OUTCOME_LABELS member.

    Same polarity persisted (same-or-stronger) -> ``followed_through``;
    opposite polarity or an observed reversal -> ``contradicted``; a move
    between directional and neutral -> ``faded`` (the claim petered out).
    """
    if observed == _REVERSAL_DIRECTION:
        return "contradicted"
    before = _direction_polarity(claimed)
    after = _direction_polarity(observed)
    if before == after:
        return "followed_through"
    if {before, after} == {"positive", "negative"}:
        return "contradicted"
    return "faded"


def _state_outcome(claimed: str, observed: str) -> str:
    """Compare two persisted theme-pulse states -> an OUTCOME_LABELS member.

    Equal, or further along the SAME arc (rising ladder or deterioration
    arc) -> ``followed_through``; movement against the claimed arc, or a jump
    to the opposing arc -> ``contradicted``; a state outside both arcs
    (``Conflicted`` / ``Data insufficient``) is not comparable ->
    ``unresolved`` (honest, never guessed).
    """
    if claimed == observed:
        return "followed_through"
    if claimed in _RISING_STATE_LADDER and observed in _RISING_STATE_LADDER:
        return ("followed_through"
                if _RISING_STATE_LADDER[observed] > _RISING_STATE_LADDER[claimed]
                else "contradicted")
    if (claimed in _DETERIORATION_STATE_LADDER
            and observed in _DETERIORATION_STATE_LADDER):
        return ("followed_through"
                if _DETERIORATION_STATE_LADDER[observed]
                > _DETERIORATION_STATE_LADDER[claimed]
                else "contradicted")
    if claimed in _RISING_STATE_LADDER and observed in _DETERIORATION_STATE_LADDER:
        return "contradicted"
    if claimed in _DETERIORATION_STATE_LADDER and observed in _RISING_STATE_LADDER:
        return "contradicted"
    return "unresolved"


def _outcome_id(kind: str, subject_id: str, subject_run: str, tail: str) -> str:
    """Content-derived outcome id -- the idempotence key (never wall-clock)."""
    return "outcome.{0}.{1}.{2}.{3}".format(
        kind, _slug(subject_id), _slug(subject_run), _slug(tail))


def _signal_outcome(signal, run_id: str, next_run_id: str,
                    counterpart, now: str) -> OutcomeRecord:
    """One OutcomeRecord for one persisted signal claim vs the next run."""
    sid = getattr(signal, "signal_id", "")
    claimed = "direction_label '{0}'".format(signal.direction_label or "unspecified")
    scope = ", ".join(signal.affected_companies) or "no named companies"
    common = dict(
        subject_kind="signal", subject_id=sid, subject_run_id=run_id,
        subject_discipline=getattr(signal, "discipline", ""),
        claimed=claimed, created_at=now)
    if not next_run_id:
        return OutcomeRecord(
            outcome_id=_outcome_id("signal", sid, run_id, "unresolved"),
            outcome_label="unresolved",
            basis=("Signal '{0}' in run '{1}' claimed {2} (discipline '{3}', "
                   "{4}); no later run is persisted, so the outcome is "
                   "unresolved -- an honest state, not a guess.".format(
                       sid, run_id, claimed,
                       getattr(signal, "discipline", "") or "unspecified",
                       scope)),
            **common)
    if counterpart is None:
        return OutcomeRecord(
            outcome_id=_outcome_id("signal", sid, run_id, next_run_id),
            observed_run_id=next_run_id, observed="absent",
            outcome_label="faded",
            basis=("Signal '{0}' in run '{1}' claimed {2}; no signal for the "
                   "same subject (discipline '{3}', {4}) persisted in the next "
                   "run '{5}' -- the claim faded.".format(
                       sid, run_id, claimed,
                       getattr(signal, "discipline", "") or "unspecified",
                       scope, next_run_id)),
            **common)
    observed_direction = counterpart.direction_label or "unspecified"
    label = _direction_outcome(signal.direction_label, counterpart.direction_label)
    return OutcomeRecord(
        outcome_id=_outcome_id("signal", sid, run_id, next_run_id),
        observed_run_id=next_run_id,
        observed="direction_label '{0}' on signal '{1}'".format(
            observed_direction, counterpart.signal_id),
        outcome_label=label,
        basis=("Signal '{0}' in run '{1}' claimed {2}; run '{3}' persisted "
               "direction_label '{4}' on signal '{5}' for the same subject -- "
               "{6}.".format(sid, run_id, claimed, next_run_id,
                             observed_direction, counterpart.signal_id,
                             label.replace("_", " "))),
        **common)


def _pulse_outcome(pulse, run_id: str, next_run_id: str,
                   counterpart, now: str) -> OutcomeRecord:
    """One OutcomeRecord for one persisted theme-pulse claim vs the next run."""
    pid = getattr(pulse, "theme_pulse_id", "")
    theme = getattr(pulse, "theme_id", "") or getattr(pulse, "theme_name", "")
    claimed = "state '{0}'".format(pulse.state or "unspecified")
    common = dict(
        subject_kind="theme_pulse", subject_id=pid, subject_run_id=run_id,
        subject_theme_id=theme, claimed=claimed, created_at=now)
    if not next_run_id:
        return OutcomeRecord(
            outcome_id=_outcome_id("theme-pulse", pid, run_id, "unresolved"),
            outcome_label="unresolved",
            basis=("Theme pulse '{0}' (theme '{1}') in run '{2}' claimed {3}; "
                   "no later run is persisted, so the outcome is unresolved -- "
                   "an honest state, not a guess.".format(
                       pid, theme, run_id, claimed)),
            **common)
    if counterpart is None:
        return OutcomeRecord(
            outcome_id=_outcome_id("theme-pulse", pid, run_id, next_run_id),
            observed_run_id=next_run_id, observed="absent",
            outcome_label="faded",
            basis=("Theme pulse '{0}' (theme '{1}') in run '{2}' claimed {3}; "
                   "no pulse for the same theme persisted in the next run "
                   "'{4}' -- the claim faded.".format(
                       pid, theme, run_id, claimed, next_run_id)),
            **common)
    observed_state = counterpart.state or "unspecified"
    label = _state_outcome(pulse.state, counterpart.state)
    if label == "unresolved":
        return OutcomeRecord(
            outcome_id=_outcome_id("theme-pulse", pid, run_id, next_run_id),
            outcome_label="unresolved",
            basis=("Theme pulse '{0}' (theme '{1}') in run '{2}' claimed {3}; "
                   "the next run '{4}' persisted state '{5}' on pulse '{6}', "
                   "which is not comparable on either state arc -- the outcome "
                   "stays unresolved (honest, never guessed).".format(
                       pid, theme, run_id, claimed, next_run_id,
                       observed_state, counterpart.theme_pulse_id)),
            **common)
    return OutcomeRecord(
        outcome_id=_outcome_id("theme-pulse", pid, run_id, next_run_id),
        observed_run_id=next_run_id,
        observed="state '{0}' on theme pulse '{1}'".format(
            observed_state, counterpart.theme_pulse_id),
        outcome_label=label,
        basis=("Theme pulse '{0}' (theme '{1}') in run '{2}' claimed {3}; run "
               "'{4}' persisted state '{5}' on pulse '{6}' for the same theme "
               "-- {7}.".format(pid, theme, run_id, claimed, next_run_id,
                                observed_state, counterpart.theme_pulse_id,
                                label.replace("_", " "))),
        **common)


def track_outcomes(store_dir: str, *, now: str) -> Tuple[OutcomeRecord, ...]:
    """Pure read-and-compare: outcome records for every persisted claim.

    For each persisted run N, every signal / theme pulse of run N is compared
    against the SAME subject (discipline + companies / theme) in the NEXT
    persisted run N+1: persisted same-or-stronger -> ``followed_through``;
    opposite -> ``contradicted``; absent from the next run ->  ``faded``.
    Where NO later run exists the outcome is ``unresolved`` (honest, never a
    guess). Reads the 013B stores only; persists nothing; deterministic --
    subjects are visited in sorted id sequence per run.
    """
    if not str(now).strip():
        raise ValueError("track_outcomes requires an injected 'now' instant")
    run_ids = persisted_run_ids(store_dir)
    signal_store = SignalStore(store_dir)
    pulse_store = ThemePulseStore(store_dir)
    outcomes: List[OutcomeRecord] = []
    for index, run_id in enumerate(run_ids):
        next_run_id = run_ids[index + 1] if index + 1 < len(run_ids) else ""

        cur_signals = sorted(signal_store.query(run_id=run_id),
                             key=lambda s: s.signal_id)
        cur_pulses = sorted(pulse_store.query(run_id=run_id),
                            key=lambda p: p.theme_pulse_id)
        next_signal_by_key: Dict[object, object] = {}
        next_pulse_by_key: Dict[str, object] = {}
        if next_run_id:
            for sig in sorted(signal_store.query(run_id=next_run_id),
                              key=lambda s: s.signal_id):
                next_signal_by_key.setdefault(_signal_subject_key(sig), sig)
            for pul in sorted(pulse_store.query(run_id=next_run_id),
                              key=lambda p: p.theme_pulse_id):
                next_pulse_by_key.setdefault(_pulse_theme_key(pul), pul)

        for sig in cur_signals:
            outcomes.append(_signal_outcome(
                sig, run_id, next_run_id,
                next_signal_by_key.get(_signal_subject_key(sig)), now))
        for pul in cur_pulses:
            outcomes.append(_pulse_outcome(
                pul, run_id, next_run_id,
                next_pulse_by_key.get(_pulse_theme_key(pul)), now))
    return tuple(outcomes)


def record_outcomes(store_dir: str,
                    outcomes: Tuple[OutcomeRecord, ...]) -> Tuple[str, ...]:
    """Append only the NOT-yet-persisted outcomes; return the appended ids.

    The idempotence guard: outcome ids are content-derived, so a re-track
    appends nothing (the store stays byte-identical) and a later resolution
    of a previously ``unresolved`` subject appends a NEW record while the
    original ``unresolved`` line stays byte-unchanged.
    """
    store = OutcomeStore(store_dir)
    existing = {str(rec.get("record_id", "")) for rec in store.read_records()}
    appended: List[str] = []
    for outcome in outcomes:
        if outcome.outcome_id in existing:
            continue
        store.append(outcome, run_id=outcome.subject_run_id,
                     timestamp=outcome.created_at)
        existing.add(outcome.outcome_id)
        appended.append(outcome.outcome_id)
    return tuple(appended)


class OutcomeTracker:
    """The ``anubhava.outcome_tracker`` role: compare persisted runs, append outcomes.

    Composes the pure :func:`track_outcomes` with the idempotent
    :func:`record_outcomes`. It reads the 013B stores, appends to the outcome
    store ONLY, and never modifies any existing byte anywhere.
    """

    def __init__(self, store_dir: str) -> None:
        if not store_dir or not str(store_dir).strip():
            raise ValueError("OutcomeTracker requires a non-empty store_dir")
        self.store_dir = str(store_dir)

    def track(self, *, now: str) -> Tuple[OutcomeRecord, ...]:
        """Compute every outcome and append only the new ones; return all."""
        outcomes = track_outcomes(self.store_dir, now=now)
        record_outcomes(self.store_dir, outcomes)
        return outcomes

    def outcomes(self) -> Tuple[OutcomeRecord, ...]:
        """Every persisted outcome, in append sequence."""
        return OutcomeStore(self.store_dir).read_all()


# --------------------------------------------------------------------------- #
# 5. Roll-ups -- pure functions from outcomes to label+count records           #
# --------------------------------------------------------------------------- #
def _count_labels(outcomes) -> Dict[str, int]:
    counts = {"followed_through": 0, "contradicted": 0, "faded": 0,
              "unresolved": 0}
    for outcome in outcomes:
        counts[outcome.outcome_label] += 1
    return counts


def _reliability_label(followed: int, contradicted: int, faded: int) -> str:
    """Map hit / miss VOLUMES to a closed label (no ratio is ever stored).

    Below the ``min_resolved_outcomes`` threshold the label is
    ``insufficient_history`` -- no label pretends confidence. Otherwise the
    follow-through volume is compared against the contradicted + faded volume:
    more hits than misses -> ``improving``; fewer -> ``deteriorating``;
    equal -> ``stable``.
    """
    resolved = followed + contradicted + faded
    if resolved < LEARNING_THRESHOLDS["min_resolved_outcomes"]:
        return "insufficient_history"
    misses = contradicted + faded
    if followed > misses:
        return "improving"
    if followed < misses:
        return "deteriorating"
    return "stable"


def _window_of(outcomes) -> Tuple[str, str]:
    runs = [outcome.subject_run_id for outcome in outcomes]
    return (runs[0], runs[-1]) if runs else ("", "")


def _volume_basis(counts: Dict[str, int], window: Tuple[str, str],
                  label: str, scope: str) -> str:
    text = ("Across runs '{0}'..'{1}', {2}: {3} followed through, {4} "
            "contradicted, {5} faded, {6} unresolved (counts are volumes; no "
            "ratio is stored). Label: '{7}'.".format(
                window[0], window[1], scope, counts["followed_through"],
                counts["contradicted"], counts["faded"], counts["unresolved"],
                label))
    if label == "insufficient_history":
        text += (" Fewer than {0} resolved outcomes -- no label pretends "
                 "confidence.".format(
                     LEARNING_THRESHOLDS["min_resolved_outcomes"]))
    return text


def roll_signal_reliability(outcomes, *,
                            now: str) -> Tuple[SignalReliabilityRecord, ...]:
    """Roll signal outcomes into one per-discipline reliability record.

    Pure over its inputs: groups ``subject_kind == 'signal'`` outcomes by
    ``subject_discipline``, counts VOLUMES per outcome label, and assigns the
    closed reliability label (``insufficient_history`` below the threshold).
    Deterministic: disciplines are emitted in sorted sequence.
    """
    if not str(now).strip():
        raise ValueError("roll_signal_reliability requires an injected 'now'")
    grouped: Dict[str, List[OutcomeRecord]] = {}
    for outcome in outcomes:
        if outcome.subject_kind != "signal":
            continue
        grouped.setdefault(outcome.subject_discipline, []).append(outcome)
    records: List[SignalReliabilityRecord] = []
    for discipline in sorted(grouped):
        scoped = grouped[discipline]
        counts = _count_labels(scoped)
        window = _window_of(scoped)
        label = _reliability_label(counts["followed_through"],
                                   counts["contradicted"], counts["faded"])
        records.append(SignalReliabilityRecord(
            learning_id="learn.signal-reliability.{0}.{1}.{2}.f{3}-c{4}-fa{5}-u{6}".format(
                _slug(discipline or "unspecified"), _slug(window[0]),
                _slug(window[1]), counts["followed_through"],
                counts["contradicted"], counts["faded"], counts["unresolved"]),
            discipline=discipline, window=window,
            followed_through_count=counts["followed_through"],
            contradicted_count=counts["contradicted"],
            faded_count=counts["faded"],
            unresolved_count=counts["unresolved"],
            reliability_label=label,
            basis=_volume_basis(counts, window, label,
                                "discipline '{0}' signal claims".format(
                                    discipline or "unspecified")),
            created_at=now))
    return tuple(records)


def roll_theme_pulse_accuracy(outcomes, *,
                              now: str) -> Tuple[ThemePulseAccuracyRecord, ...]:
    """Roll theme-pulse outcomes into one per-theme accuracy record.

    ``transitions_observed`` is the RESOLVED outcome volume for the theme;
    ``transitions_followed_through`` / ``transitions_reversed`` are the
    follow-through / contradiction volumes. Same closed label + threshold
    discipline as every roll-up. Deterministic: themes in sorted sequence.
    """
    if not str(now).strip():
        raise ValueError("roll_theme_pulse_accuracy requires an injected 'now'")
    grouped: Dict[str, List[OutcomeRecord]] = {}
    for outcome in outcomes:
        if outcome.subject_kind != "theme_pulse":
            continue
        grouped.setdefault(outcome.subject_theme_id, []).append(outcome)
    records: List[ThemePulseAccuracyRecord] = []
    for theme_id in sorted(grouped):
        scoped = grouped[theme_id]
        counts = _count_labels(scoped)
        window = _window_of(scoped)
        resolved = (counts["followed_through"] + counts["contradicted"]
                    + counts["faded"])
        label = _reliability_label(counts["followed_through"],
                                   counts["contradicted"], counts["faded"])
        records.append(ThemePulseAccuracyRecord(
            learning_id="learn.theme-pulse-accuracy.{0}.{1}.{2}.o{3}-f{4}-r{5}".format(
                _slug(theme_id or "unspecified"), _slug(window[0]),
                _slug(window[1]), resolved, counts["followed_through"],
                counts["contradicted"]),
            theme_id=theme_id or "unspecified", window=window,
            transitions_observed=resolved,
            transitions_followed_through=counts["followed_through"],
            transitions_reversed=counts["contradicted"],
            accuracy_label=label,
            basis=_volume_basis(counts, window, label,
                                "theme '{0}' pulse claims".format(
                                    theme_id or "unspecified")),
            created_at=now))
    return tuple(records)


def roll_source_reliability(outcomes, signals_authority: Mapping[str, str], *,
                            now: str) -> Tuple[SourceReliabilityRecord, ...]:
    """Roll signal outcomes into per-source-tier (or per-adapter) reliability.

    ``signals_authority`` maps a signal id to its source-authority tier
    (``canonical`` / ``primary`` / ``convenience`` / ... / ``rumor``) or to an
    adapter id. A rumor tier whose claims repeatedly fail is labelled
    ``deteriorating`` -- and NEVER retroactively upgraded: this is a pure
    function; persisting its output appends NEW records only, and no past
    record is revised. Outcomes for signals absent from the mapping are
    skipped (unattributable, never guessed). Deterministic: groups in sorted
    sequence.
    """
    if not str(now).strip():
        raise ValueError("roll_source_reliability requires an injected 'now'")
    grouped: Dict[str, List[OutcomeRecord]] = {}
    for outcome in outcomes:
        if outcome.subject_kind != "signal":
            continue
        source = str(signals_authority.get(outcome.subject_id, "") or "")
        if not source.strip():
            continue
        grouped.setdefault(source, []).append(outcome)
    records: List[SourceReliabilityRecord] = []
    for source in sorted(grouped):
        scoped = grouped[source]
        counts = _count_labels(scoped)
        window = _window_of(scoped)
        label = _reliability_label(counts["followed_through"],
                                   counts["contradicted"], counts["faded"])
        is_tier = source in _labels.SOURCE_AUTHORITIES
        scope_text = ("'{0}'-tier sourced signal claims".format(source)
                      if is_tier
                      else "adapter '{0}' sourced signal claims".format(source))
        records.append(SourceReliabilityRecord(
            learning_id="learn.source-reliability.{0}.{1}.{2}.f{3}-c{4}-fa{5}-u{6}".format(
                _slug(source), _slug(window[0]), _slug(window[1]),
                counts["followed_through"], counts["contradicted"],
                counts["faded"], counts["unresolved"]),
            source_kind=source if is_tier else "",
            adapter_id="" if is_tier else source,
            window=window,
            followed_through_count=counts["followed_through"],
            contradicted_count=counts["contradicted"],
            faded_count=counts["faded"],
            unresolved_count=counts["unresolved"],
            reliability_label=label,
            basis=_volume_basis(counts, window, label, scope_text),
            created_at=now))
    return tuple(records)


def record_learning_rollups(store_dir: str, rollups) -> Tuple[str, ...]:
    """Append only the NOT-yet-persisted roll-up records; return appended ids.

    Ids are content-derived (scope + window + counts), so re-rolling the same
    outcomes appends nothing, and rolling NEW evidence appends a NEW record --
    every earlier line (including a rumor tier's ``deteriorating`` label)
    stays byte-unchanged forever: no retroactive upgrade is possible.
    """
    store = LearningStore(store_dir)
    existing = {str(rec.get("record_id", "")) for rec in store.read_records()}
    appended: List[str] = []
    for rollup in rollups:
        if rollup.learning_id in existing:
            continue
        store.append(rollup, timestamp=rollup.created_at)
        existing.add(rollup.learning_id)
        appended.append(rollup.learning_id)
    return tuple(appended)


# --------------------------------------------------------------------------- #
# 6. Reserved alert categories -- emitted only where an outcome implies them   #
# --------------------------------------------------------------------------- #
def emit_outcome_alerts(store_dir: str, outcomes, *,
                        now: str) -> Tuple[Alert, ...]:
    """Append the reserved learning alerts that drop naturally out of outcomes.

    * ``thesis_deteriorated`` -- a persisted theme-pulse claim was
      CONTRADICTED by the next persisted run (the outcome record is the
      evidence).
    * ``major_risk_emerged`` -- a persisted RISK-state theme claim
      (``Crowded`` / ``Exhausting`` / ``Breaking down``) FOLLOWED THROUGH:
      the risk state persisted, confirmed by a later run.

    ``new_opportunity_hypothesis`` stays reserved: no outcome comparison
    implies a new hypothesis, and fabricating one would be a guess.

    Observation only -- the alert names the outcome + both runs and points at
    the evidence; nothing here acts. Idempotent: alert ids derive from the
    outcome, so re-emitting appends nothing. Run this AFTER
    :func:`~reality_mesh.alerts.generate_alerts_for_run` for the observed run
    so the diff engine's own already-generated guard is unaffected.
    """
    if not str(now).strip():
        raise ValueError("emit_outcome_alerts requires an injected 'now'")
    store = AlertStore(store_dir)
    existing = {str(rec.get("record_id", "")) for rec in store.read_records()}
    emitted: List[Alert] = []
    for outcome in outcomes:
        if outcome.subject_kind != "theme_pulse":
            continue
        if outcome.outcome_label == "contradicted":
            category = "thesis_deteriorated"
            reason = ("Theme pulse '{0}' (theme '{1}') claimed {2} in run "
                      "'{3}', and run '{4}' contradicted it ({5}); evidence: "
                      "outcome record '{6}'.".format(
                          outcome.subject_id, outcome.subject_theme_id,
                          outcome.claimed, outcome.subject_run_id,
                          outcome.observed_run_id, outcome.observed,
                          outcome.outcome_id))
        elif (outcome.outcome_label == "followed_through"
              and any("'{0}'".format(state) in outcome.claimed
                      for state in RISK_CLAIM_STATES)):
            category = "major_risk_emerged"
            reason = ("Risk-state theme claim confirmed: theme pulse '{0}' "
                      "(theme '{1}') claimed {2} in run '{3}' and run '{4}' "
                      "persisted it ({5}); evidence: outcome record "
                      "'{6}'.".format(
                          outcome.subject_id, outcome.subject_theme_id,
                          outcome.claimed, outcome.subject_run_id,
                          outcome.observed_run_id, outcome.observed,
                          outcome.outcome_id))
        else:
            continue
        alert_id = "alert.{0}.{1}.{2}".format(
            outcome.observed_run_id, category, _slug(outcome.subject_id))
        if alert_id in existing:
            continue
        alert = Alert(
            alert_id=alert_id, run_id=outcome.observed_run_id,
            category=category, severity=CATEGORY_SEVERITY[category],
            human_readable_reason=reason,
            subject_themes=(outcome.subject_theme_id,)
            if outcome.subject_theme_id else (),
            subject_refs=(outcome.outcome_id, outcome.subject_id),
            evidence_refs=(outcome.outcome_id,),
            created_at=now)
        store.append(alert, timestamp=now)
        existing.add(alert_id)
        emitted.append(alert)
    return tuple(emitted)
