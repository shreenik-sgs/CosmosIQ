"""Learning & Feedback reviews for the Reality Mesh (IMPLEMENTATION-017B).

The review layer over the 017A outcome core: thesis postmortems, red-team
reviews, timing reviews, expert-account reliability, archetype learning, and
the experience-layer update. Reviews COMPOSE the 017A records and stores --
they read persisted outcomes and append NEW records; they never act, never
edit history, and never fabricate certainty:

* **A review reviews a RECORDED thesis run.** The operator journals a thesis
  into the append-only :class:`ThesisJournalStore` (labels + text only); every
  review cites that journal entry by id plus the persisted
  :class:`~reality_mesh.learning.OutcomeRecord` ids it compared it against.
* **Append-only; NO rewriting history.** Every review is a NEW line appended
  to the 017A :class:`~reality_mesh.learning.LearningStore`; the journal
  entry, the outcome lines, and every upstream store line stay byte-unchanged
  forever. A later re-review with the same history appends nothing
  (content-derived ids); a re-review over NEW history appends a NEW record.
* **No retroactive certainty.** A red-team point is ``confirmed`` ONLY where
  a later persisted adverse outcome explicitly matches its warning by subject
  / theme; an unmatched point stays ``unrealized`` -- unmatched is unmatched,
  never guessed. A timing review with no resolved history reads
  ``unresolved``; a roll-up under the 017A resolved-outcome threshold reads
  ``insufficient_history`` -- no label pretends confidence.
* **Labels + volume counts, never a metric.** Every field is a string, a
  string tuple, or a volume count; no ratio / percentage / numeric field is
  ever stored (enforced at construction AND by the 013B store guard).
* **Thresholds as data.** :data:`REVIEW_THRESHOLDS` carries the volumes that
  separate ``thesis_held`` / ``thesis_weakened`` / ``thesis_broken`` and
  re-uses the 017A ``min_resolved_outcomes`` floor.

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no daemon.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, fields
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

from . import labels as _labels
from . import learning as _learning
from .learning import (
    LEARNING_THRESHOLDS,
    RELIABILITY_LABELS,
    LearningStore,
    OutcomeRecord,
    OutcomeStore,
    persisted_run_ids,
    record_learning_rollups,
    _count_labels,
    _forbid_metric_values,
    _reliability_label,
    _require_counts,
    _require_label,
    _require_text,
    _require_window,
    _slug,
    _volume_basis,
    _window_of,
)
from .stores import AppendOnlyStore, EventStore, SignalStore
from .validation import assert_no_trade_fields

__all__ = [
    "JOURNAL_VERDICTS",
    "TIMING_CLAIMS",
    "POSTMORTEM_LABELS",
    "TIMING_LABELS",
    "REVIEW_THRESHOLDS",
    "REVIEW_RECORDS",
    "ThesisJournalEntry",
    "ThesisJournalStore",
    "journal_thesis",
    "ThesisPostmortem",
    "RedTeamReview",
    "TimingReview",
    "ExpertAccountReliabilityRecord",
    "ArchetypeUpdate",
    "ExperienceLayerUpdate",
    "review_thesis",
    "review_red_team",
    "review_timing",
    "roll_expert_reliability",
    "roll_archetypes",
    "append_experience_update",
]

# --------------------------------------------------------------------------- #
# Closed vocabularies + thresholds-as-data                                     #
# --------------------------------------------------------------------------- #

# The Nivesha investability vocabulary a journaled thesis carries, verbatim
# (prometheus/investment_thesis.py). CLOSED -- a journal entry quotes the
# engine's label; it never invents a new verdict spelling.
JOURNAL_VERDICTS: FrozenSet[str] = frozenset(
    {"not_investable", "watch", "thesis_worthy", "thesis_worthy_timing_confirmed"})

# What the journaled thesis claimed about timing AT THE TIME (labels only).
TIMING_CLAIMS: FrozenSet[str] = frozenset(
    {"timing_confirmed", "timing_not_confirmed"})

# What a postmortem / red-team review concluded. CLOSED -- and
# ``insufficient_history`` is mandatory below the resolved-outcome floor.
POSTMORTEM_LABELS: FrozenSet[str] = frozenset(
    {"thesis_held", "thesis_weakened", "thesis_broken", "insufficient_history"})

# What a timing review concluded. ``unresolved`` is the honest state when the
# persisted history cannot answer the timing question -- never a guess.
TIMING_LABELS: FrozenSet[str] = frozenset(
    {"early", "on_time", "late", "unresolved"})

# Thresholds live as DATA. The resolved-outcome floor is the 017A threshold
# (below it every review label reads insufficient_history / unresolved); the
# volume lines between held / weakened / broken are named here, not buried.
REVIEW_THRESHOLDS: Mapping[str, int] = {
    "min_resolved_outcomes": LEARNING_THRESHOLDS["min_resolved_outcomes"],
    "weakened_min_contradicted": 1,
    "broken_min_contradicted": 2,
    "weakened_min_confirmed_points": 1,
    "broken_min_confirmed_points": 2,
}

_ADVERSE_OUTCOME_LABELS: FrozenSet[str] = frozenset({"contradicted", "faded"})


# --------------------------------------------------------------------------- #
# Shared text helpers (deterministic, honest matching -- never fuzzy)          #
# --------------------------------------------------------------------------- #
def _norm(text) -> str:
    """Case / hyphen / underscore-insensitive token (mirrors theme matching)."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _quoted(text: str) -> str:
    """The first single-quoted token in a persisted claim/observation string."""
    parts = str(text or "").split("'")
    return parts[1] if len(parts) >= 2 else ""


def _mentions_word(text: str, word: str) -> bool:
    """True iff ``word`` appears as a whole word in ``text`` (case-insensitive).

    Whole-word only: an explicit mention, never a substring coincidence.
    """
    if not str(word).strip():
        return False
    return re.search(
        r"\b{0}\b".format(re.escape(str(word).lower())), str(text).lower()) is not None


def _require_now(now: str, who: str) -> None:
    if not str(now).strip():
        raise ValueError("{0} requires an injected 'now' instant".format(who))


def _require_str_tuple(obj, names: Tuple[str, ...]) -> None:
    for name in names:
        value = getattr(obj, name)
        coerced = tuple(value)
        for element in coerced:
            if not isinstance(element, str):
                raise ValueError(
                    "{0}.{1} must be a tuple of strings -- reviews are "
                    "citations + labels only".format(type(obj).__name__, name))
        object.__setattr__(obj, name, coerced)


# --------------------------------------------------------------------------- #
# 1. The thesis journal -- the operator RECORDS a thesis to make it reviewable #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ThesisJournalEntry:
    """One journaled thesis run: what was concluded, quoted AT THE TIME.

    Labels + text only -- the entry quotes the engine's verdict label, the
    invalidation conditions, the monitoring signals, and the red-team summary
    as recorded; no numeric field exists here. The entry is the fixed point a
    later postmortem / red-team / timing review cites; it is never edited.
    """

    journal_id: str = ""
    ticker: str = ""
    run_context: str = ""                   # which run / render produced the thesis
    verdict_label: str = ""                 # closed: JOURNAL_VERDICTS (quoted verbatim)
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    monitoring_signals: Tuple[str, ...] = field(default_factory=tuple)
    red_team_summary: str = ""              # the red team's points, as recorded
    timing_claimed: str = ""                # closed: TIMING_CLAIMS
    recorded_at: str = ""                   # injected timestamp (no wall clock)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("journal_id", "ticker", "recorded_at"))
        _require_label(self, "verdict_label", JOURNAL_VERDICTS)
        _require_label(self, "timing_claimed", TIMING_CLAIMS)
        _require_str_tuple(self, ("invalidation_conditions", "monitoring_signals"))
        for name in ("journal_id", "ticker", "run_context", "verdict_label",
                     "red_team_summary", "timing_claimed", "recorded_at"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(
                    "ThesisJournalEntry.{0} must be a string".format(name))
        _forbid_metric_values(self)


class ThesisJournalStore(AppendOnlyStore):
    """Append-only thesis journal (``thesis_journal_store.jsonl``).

    One line per journaled thesis run. Query axes: ``ticker`` /
    ``verdict_label`` / ``time_window``. Never updated, never rewritten -- a
    fresh thesis run for the same ticker is a NEW line.
    """

    filename = "thesis_journal_store.jsonl"
    record_cls = ThesisJournalEntry
    id_field = "journal_id"
    timestamp_field = "recorded_at"
    ticker_fields = ("ticker",)


def journal_thesis(store_dir: str, *, ticker: str, verdict_label: str,
                   timing_claimed: str, recorded_at: str, run_context: str = "",
                   invalidation_conditions: Tuple[str, ...] = (),
                   monitoring_signals: Tuple[str, ...] = (),
                   red_team_summary: str = "") -> ThesisJournalEntry:
    """Journal one thesis run so it becomes REVIEWABLE; return the entry.

    The journal id derives from ticker + recorded_at, so journaling the same
    thesis run twice appends nothing (the store stays byte-identical) while a
    later thesis run for the same ticker (a new ``recorded_at``) is a NEW
    line. Labels + text only; the engines' numeric internals are never
    journaled.
    """
    entry = ThesisJournalEntry(
        journal_id="thesis.{0}.{1}".format(
            _slug(ticker), _slug(recorded_at)),
        ticker=str(ticker).strip().upper(),
        run_context=run_context,
        verdict_label=verdict_label,
        invalidation_conditions=tuple(invalidation_conditions),
        monitoring_signals=tuple(monitoring_signals),
        red_team_summary=red_team_summary,
        timing_claimed=timing_claimed,
        recorded_at=recorded_at)
    store = ThesisJournalStore(store_dir)
    existing = {str(rec.get("record_id", "")) for rec in store.read_records()}
    if entry.journal_id not in existing:
        store.append(entry, timestamp=entry.recorded_at)
    return entry


def _journal_entry(store_dir: str, thesis_id: str) -> ThesisJournalEntry:
    """The journaled entry for ``thesis_id`` -- absent is an error, not a guess."""
    for entry in ThesisJournalStore(store_dir).read_all():
        if entry.journal_id == thesis_id:
            return entry
    raise ValueError(
        "no journaled thesis {0!r} -- a review reviews a RECORDED thesis run; "
        "journal it first (journal_thesis)".format(thesis_id))


# --------------------------------------------------------------------------- #
# 2. Frozen review records -- citations + labels + volume counts only          #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ThesisPostmortem:
    """What the persisted history showed about one journaled thesis.

    Every ``what_*`` entry cites the :class:`OutcomeRecord` id it rests on;
    ``invalidation_conditions_triggered`` names the journaled condition AND
    the outcome whose later persisted state label matched it (labels only).
    """

    learning_id: str = ""
    thesis_ref: str = ""                    # the journal entry, by id
    window: Tuple[str, str] = ("", "")      # (first_run_id, last_run_id)
    what_followed_through: Tuple[str, ...] = field(default_factory=tuple)
    what_contradicted: Tuple[str, ...] = field(default_factory=tuple)
    what_faded: Tuple[str, ...] = field(default_factory=tuple)
    invalidation_conditions_triggered: Tuple[str, ...] = field(default_factory=tuple)
    postmortem_label: str = ""              # closed: POSTMORTEM_LABELS
    basis: str = ""                         # plain English citing thesis + runs
    created_at: str = ""                    # injected timestamp

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "thesis_ref", "basis", "created_at"))
        _require_label(self, "postmortem_label", POSTMORTEM_LABELS)
        _require_window(self)
        _require_str_tuple(self, ("what_followed_through", "what_contradicted",
                                  "what_faded",
                                  "invalidation_conditions_triggered"))
        _forbid_metric_values(self)


@dataclass(frozen=True)
class RedTeamReview:
    """Which journaled red-team points a later persisted outcome confirmed.

    A point is ``confirmed`` ONLY where a later persisted ADVERSE outcome
    explicitly matches its warning by subject / theme (the entry cites the
    outcome id); an unmatched point stays ``unrealized`` -- never guessed.
    """

    learning_id: str = ""
    thesis_ref: str = ""
    window: Tuple[str, str] = ("", "")
    red_team_points_confirmed: Tuple[str, ...] = field(default_factory=tuple)
    red_team_points_unrealized: Tuple[str, ...] = field(default_factory=tuple)
    review_label: str = ""                  # closed: POSTMORTEM_LABELS
    basis: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "thesis_ref", "basis", "created_at"))
        _require_label(self, "review_label", POSTMORTEM_LABELS)
        _require_window(self)
        _require_str_tuple(self, ("red_team_points_confirmed",
                                  "red_team_points_unrealized"))
        _forbid_metric_values(self)


@dataclass(frozen=True)
class TimingReview:
    """What happened AFTER the journaled timing claim, in persisted run sequence.

    ``what_happened_next`` cites the resolved outcome ids in sequence;
    ``timing_label`` compares the claim to that sequence. Where the history
    cannot answer (no resolved outcomes, no follow-through, or a sample under
    the resolved floor) the label is ``unresolved`` -- honest, never a guess.
    """

    learning_id: str = ""
    thesis_ref: str = ""
    window: Tuple[str, str] = ("", "")
    timing_claimed: str = ""                # closed: TIMING_CLAIMS
    what_happened_next: Tuple[str, ...] = field(default_factory=tuple)
    timing_label: str = ""                  # closed: TIMING_LABELS
    basis: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "thesis_ref", "basis", "created_at"))
        _require_label(self, "timing_claimed", TIMING_CLAIMS)
        _require_label(self, "timing_label", TIMING_LABELS)
        _require_window(self)
        _require_str_tuple(self, ("what_happened_next",))
        _forbid_metric_values(self)


@dataclass(frozen=True)
class ExpertAccountReliabilityRecord:
    """Per-account social-source reliability: outcome VOLUMES + a closed label.

    Composes the 017A source-tier learning down to the single account: every
    counted outcome evaluates a signal whose cited source events (evidence
    refs) originate from this account. Counts are volumes; no ratio is ever
    stored, and a past record is never retroactively upgraded -- new evidence
    appends a NEW line.
    """

    learning_id: str = ""
    account_handle: str = ""                # the event source_id (e.g. an X handle)
    account_kind: str = ""                  # the event source_type (x / reddit / ...)
    window: Tuple[str, str] = ("", "")
    followed_through_count: int = 0         # volume count
    contradicted_count: int = 0             # volume count
    faded_count: int = 0                    # volume count
    unresolved_count: int = 0               # volume count
    reliability_label: str = ""             # closed: RELIABILITY_LABELS (017A)
    basis: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "account_handle", "basis",
                             "created_at"))
        _require_label(self, "reliability_label", RELIABILITY_LABELS)
        _require_counts(self, ("followed_through_count", "contradicted_count",
                               "faded_count", "unresolved_count"))
        _require_window(self)
        _forbid_metric_values(self)


@dataclass(frozen=True)
class ArchetypeUpdate:
    """One learned state-arc archetype: a repeated persisted theme transition.

    ``archetype_id`` names the claimed-state -> observed-state arc (e.g.
    ``theme_igniting_to_broadening``); the counts are VOLUMES of persisted
    occurrences, and the label reads ``insufficient_history`` until the arc
    has recurred at least the 017A resolved floor -- a pattern is learned,
    never asserted off a tiny sample.
    """

    learning_id: str = ""
    archetype_id: str = ""
    window: Tuple[str, str] = ("", "")
    occurrences_count: int = 0              # volume count (resolved outcomes)
    followed_through_count: int = 0         # volume count
    reversed_count: int = 0                 # volume count (contradicted)
    archetype_label: str = ""               # closed: RELIABILITY_LABELS (017A)
    basis: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "archetype_id", "basis",
                             "created_at"))
        _require_label(self, "archetype_label", RELIABILITY_LABELS)
        _require_counts(self, ("occurrences_count", "followed_through_count",
                               "reversed_count"))
        _require_window(self)
        _forbid_metric_values(self)


@dataclass(frozen=True)
class ExperienceLayerUpdate:
    """A dated append-only note tying review records into one experience entry.

    Citation ONLY: the entry names the persisted review record ids and adds
    no synthesis beyond that citation. At least one citation is required --
    an empty experience entry is refused, never fabricated.
    """

    learning_id: str = ""
    entry_date: str = ""                    # the injected review instant
    cited_record_ids: Tuple[str, ...] = field(default_factory=tuple)
    basis: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        _require_text(self, ("learning_id", "entry_date", "basis", "created_at"))
        _require_str_tuple(self, ("cited_record_ids",))
        if not self.cited_record_ids:
            raise ValueError(
                "ExperienceLayerUpdate requires at least one cited record id "
                "-- an experience entry is citation only, never fabricated")
        _forbid_metric_values(self)


# The six 017B review records (for registry / test introspection).
REVIEW_RECORDS = (
    ThesisJournalEntry,
    ThesisPostmortem,
    RedTeamReview,
    TimingReview,
    ExpertAccountReliabilityRecord,
    ArchetypeUpdate,
    ExperienceLayerUpdate,
)

# Register the review roll-up shapes with the 017A LearningStore so a mixed
# learning log reconstructs every line to its own frozen class. ADDITIVE
# registration only -- the 017A shapes and their behaviour are untouched.
_REVIEW_ROLLUP_SHAPES = {
    "ThesisPostmortem": ThesisPostmortem,
    "RedTeamReview": RedTeamReview,
    "TimingReview": TimingReview,
    "ExpertAccountReliabilityRecord": ExpertAccountReliabilityRecord,
    "ArchetypeUpdate": ArchetypeUpdate,
    "ExperienceLayerUpdate": ExperienceLayerUpdate,
}
_SHAPES_REGISTERED = _learning._ROLLUP_CLASS_BY_NAME.update(_REVIEW_ROLLUP_SHAPES)


# --------------------------------------------------------------------------- #
# 3. Reading the persisted outcome history (composing 017A -- no re-derivation)#
# --------------------------------------------------------------------------- #
def _current_outcomes(store_dir: str) -> Tuple[OutcomeRecord, ...]:
    """The persisted outcomes, one per subject claim, in persisted run sequence.

    The 017A store keeps an earlier ``unresolved`` line byte-unchanged when a
    later run resolves the same claim; for REVIEW reading, the latest appended
    record per (kind, subject, run) is the current knowledge -- the earlier
    line is superseded by citation, never by mutation.
    """
    latest: Dict[Tuple[str, str, str], Tuple[int, OutcomeRecord]] = {}
    for index, outcome in enumerate(OutcomeStore(store_dir).read_all()):
        key = (outcome.subject_kind, outcome.subject_id, outcome.subject_run_id)
        latest[key] = (index, outcome)
    run_order = {rid: i for i, rid in enumerate(persisted_run_ids(store_dir))}
    ordered = sorted(
        latest.values(),
        key=lambda pair: (run_order.get(pair[1].subject_run_id, len(run_order)),
                          pair[0]))
    return tuple(outcome for _, outcome in ordered)


def _signal_companies_index(store_dir: str) -> Dict[str, Tuple[str, ...]]:
    """signal_id -> its affected companies (uppercased), from the 013B store."""
    index: Dict[str, Tuple[str, ...]] = {}
    for signal in SignalStore(store_dir).read_all():
        index.setdefault(
            signal.signal_id,
            tuple(str(c).strip().upper() for c in signal.affected_companies))
    return index


def _thesis_scope(store_dir: str, entry: ThesisJournalEntry
                  ) -> Tuple[OutcomeRecord, ...]:
    """The persisted outcomes a journaled thesis is accountable to.

    Explicit matching only: a signal outcome is in scope iff the journaled
    ticker is among the subject signal's affected companies; a theme-pulse
    outcome is in scope iff its theme token appears in the journal's own text
    (context / conditions / monitoring signals / red-team summary). Nothing
    outside an explicit mention is pulled in.
    """
    corpus = _norm(" ".join(
        (entry.run_context, entry.red_team_summary)
        + entry.invalidation_conditions + entry.monitoring_signals))
    ticker = entry.ticker.strip().upper()
    companies = _signal_companies_index(store_dir)
    matched: List[OutcomeRecord] = []
    for outcome in _current_outcomes(store_dir):
        if outcome.subject_kind == "signal":
            if ticker in companies.get(outcome.subject_id, ()):
                matched.append(outcome)
        elif outcome.subject_kind == "theme_pulse":
            token = _norm(outcome.subject_theme_id)
            if token and token in corpus:
                matched.append(outcome)
    return tuple(matched)


def _cite(outcome: OutcomeRecord) -> str:
    """One review entry line citing the outcome record id + both runs."""
    if outcome.outcome_label == "unresolved":
        return ("outcome '{0}': run '{1}' claimed {2}; no later observation is "
                "persisted".format(outcome.outcome_id, outcome.subject_run_id,
                                   outcome.claimed))
    return ("outcome '{0}': run '{1}' claimed {2}; run '{3}' persisted "
            "{4}".format(outcome.outcome_id, outcome.subject_run_id,
                         outcome.claimed, outcome.observed_run_id,
                         outcome.observed or "'absent'"))


# --------------------------------------------------------------------------- #
# 4. review_thesis -- the postmortem                                           #
# --------------------------------------------------------------------------- #
def _postmortem_label(counts: Dict[str, int], triggered_volume: int) -> str:
    """Map outcome VOLUMES (+ triggered conditions) to a closed postmortem label."""
    resolved = (counts["followed_through"] + counts["contradicted"]
                + counts["faded"])
    if resolved < REVIEW_THRESHOLDS["min_resolved_outcomes"]:
        return "insufficient_history"
    if (triggered_volume > 0
            or counts["contradicted"] >= REVIEW_THRESHOLDS["broken_min_contradicted"]):
        return "thesis_broken"
    if (counts["contradicted"] >= REVIEW_THRESHOLDS["weakened_min_contradicted"]
            or counts["faded"] > counts["followed_through"]):
        return "thesis_weakened"
    return "thesis_held"


def review_thesis(store_dir: str, thesis_id: str, *, now: str) -> ThesisPostmortem:
    """Postmortem one journaled thesis against the persisted outcome history.

    Reads the journal + the 017A outcome store; appends ONE new postmortem to
    the learning store (idempotent -- the id derives from the thesis and the
    history reviewed, so a re-review over the same history appends nothing).
    """
    _require_now(now, "review_thesis")
    entry = _journal_entry(store_dir, thesis_id)
    scoped = _thesis_scope(store_dir, entry)
    counts = _count_labels(scoped)
    window = _window_of(scoped)

    triggered: List[str] = []
    for condition in entry.invalidation_conditions:
        for outcome in scoped:
            observed_token = _quoted(outcome.observed)
            if outcome.outcome_label == "unresolved" or not observed_token:
                continue
            if _mentions_word(condition, observed_token):
                triggered.append(
                    "{0} -- triggered by outcome '{1}': run '{2}' persisted "
                    "{3}".format(condition, outcome.outcome_id,
                                 outcome.observed_run_id, outcome.observed))
                break

    label = _postmortem_label(counts, len(triggered))
    record = ThesisPostmortem(
        learning_id="learn.thesis-postmortem.{0}.{1}.{2}.f{3}-c{4}-fa{5}-u{6}-t{7}".format(
            _slug(entry.journal_id), _slug(window[0]), _slug(window[1]),
            counts["followed_through"], counts["contradicted"],
            counts["faded"], counts["unresolved"], len(triggered)),
        thesis_ref=entry.journal_id,
        window=window,
        what_followed_through=tuple(
            _cite(o) for o in scoped if o.outcome_label == "followed_through"),
        what_contradicted=tuple(
            _cite(o) for o in scoped if o.outcome_label == "contradicted"),
        what_faded=tuple(_cite(o) for o in scoped if o.outcome_label == "faded"),
        invalidation_conditions_triggered=tuple(triggered),
        postmortem_label=label,
        basis=(_volume_basis(counts, window, label,
                             "thesis '{0}' (ticker {1}) subjects".format(
                                 entry.journal_id, entry.ticker))
               + " {0} journaled invalidation condition(s) triggered.".format(
                   len(triggered))),
        created_at=now)
    record_learning_rollups(store_dir, (record,))
    return record


# --------------------------------------------------------------------------- #
# 5. review_red_team -- confirmed vs unrealized, never guessed                 #
# --------------------------------------------------------------------------- #
def _red_team_points(summary: str) -> Tuple[str, ...]:
    """The journaled red-team points: the summary split on ';' / newlines."""
    raw: List[str] = []
    for line in str(summary or "").replace(";", "\n").splitlines():
        line = line.strip()
        if line:
            raw.append(line)
    return tuple(raw)


def _point_matches(point: str, outcome: OutcomeRecord,
                   companies: Dict[str, Tuple[str, ...]]) -> bool:
    """True iff the ADVERSE outcome explicitly matches the point's subject/theme."""
    if outcome.subject_kind == "theme_pulse":
        token = _norm(outcome.subject_theme_id)
        return bool(token) and token in _norm(point)
    for ticker in companies.get(outcome.subject_id, ()):
        if _mentions_word(point, ticker):
            return True
    return False


def _confirmed_label(counts: Dict[str, int], confirmed_volume: int) -> str:
    resolved = (counts["followed_through"] + counts["contradicted"]
                + counts["faded"])
    if resolved < REVIEW_THRESHOLDS["min_resolved_outcomes"]:
        return "insufficient_history"
    if confirmed_volume >= REVIEW_THRESHOLDS["broken_min_confirmed_points"]:
        return "thesis_broken"
    if confirmed_volume >= REVIEW_THRESHOLDS["weakened_min_confirmed_points"]:
        return "thesis_weakened"
    return "thesis_held"


def review_red_team(store_dir: str, thesis_id: str, *, now: str) -> RedTeamReview:
    """Review the journaled red-team points against later persisted outcomes.

    A point is ``confirmed`` ONLY where a later persisted ADVERSE outcome
    (contradicted / faded) explicitly matches its warning by subject / theme;
    the confirming outcome is cited by id. An unmatched point stays
    ``unrealized`` -- unmatched is unmatched, never guessed. Appends ONE
    review (idempotent by content-derived id).
    """
    _require_now(now, "review_red_team")
    entry = _journal_entry(store_dir, thesis_id)
    scoped = _thesis_scope(store_dir, entry)
    counts = _count_labels(scoped)
    window = _window_of(scoped)
    companies = _signal_companies_index(store_dir)
    adverse = tuple(o for o in scoped
                    if o.outcome_label in _ADVERSE_OUTCOME_LABELS)

    confirmed: List[str] = []
    unrealized: List[str] = []
    for point in _red_team_points(entry.red_team_summary):
        match: Optional[OutcomeRecord] = None
        for outcome in adverse:
            if _point_matches(point, outcome, companies):
                match = outcome
                break
        if match is not None:
            confirmed.append(
                "{0} -- confirmed by outcome '{1}': run '{2}' persisted "
                "{3}".format(point, match.outcome_id, match.observed_run_id,
                             match.observed or "'absent'"))
        else:
            unrealized.append(
                "{0} -- unrealized: no later persisted outcome matches this "
                "warning (unmatched stays unmatched, never guessed)".format(point))

    label = _confirmed_label(counts, len(confirmed))
    record = RedTeamReview(
        learning_id="learn.red-team-review.{0}.{1}.{2}.p{3}-conf{4}".format(
            _slug(entry.journal_id), _slug(window[0]), _slug(window[1]),
            len(confirmed) + len(unrealized), len(confirmed)),
        thesis_ref=entry.journal_id,
        window=window,
        red_team_points_confirmed=tuple(confirmed),
        red_team_points_unrealized=tuple(unrealized),
        review_label=label,
        basis=("Red-team review of thesis '{0}' across runs '{1}'..'{2}': "
               "{3} journaled point(s), {4} confirmed by a later persisted "
               "adverse outcome, {5} unrealized (counts are volumes; no ratio "
               "is stored). Label: '{6}'.".format(
                   entry.journal_id, window[0], window[1],
                   len(confirmed) + len(unrealized), len(confirmed),
                   len(unrealized), label)
               + (" Fewer than {0} resolved outcomes -- no label pretends "
                  "confidence.".format(REVIEW_THRESHOLDS["min_resolved_outcomes"])
                  if label == "insufficient_history" else "")),
        created_at=now)
    record_learning_rollups(store_dir, (record,))
    return record


# --------------------------------------------------------------------------- #
# 6. review_timing -- early / on_time / late / unresolved, honestly            #
# --------------------------------------------------------------------------- #
def _timing_label(claimed: str, resolved: Tuple[OutcomeRecord, ...]) -> Tuple[str, str]:
    """(timing label, plain-English why) from the resolved sequence."""
    if len(resolved) < REVIEW_THRESHOLDS["min_resolved_outcomes"]:
        return ("unresolved",
                "fewer than {0} resolved outcomes are persisted -- the timing "
                "question cannot be answered yet, and no answer is "
                "guessed".format(REVIEW_THRESHOLDS["min_resolved_outcomes"]))
    followed = [o for o in resolved if o.outcome_label == "followed_through"]
    if not followed:
        return ("unresolved",
                "no persisted outcome followed through, so the thesis claim "
                "itself did not develop -- timing is unresolved, not judged")
    first = resolved[0]
    if claimed == "timing_confirmed":
        if first.outcome_label == "followed_through":
            return ("on_time",
                    "timing was claimed confirmed and the first resolved "
                    "outcome ('{0}') followed through".format(first.outcome_id))
        return ("early",
                "timing was claimed confirmed but the first resolved outcome "
                "('{0}') went against the claim before follow-through arrived "
                "('{1}')".format(first.outcome_id, followed[0].outcome_id))
    if first.outcome_label == "followed_through":
        return ("late",
                "timing was NOT claimed confirmed, yet the first resolved "
                "outcome ('{0}') already followed through -- the development "
                "preceded the confirmation".format(first.outcome_id))
    return ("on_time",
            "timing was NOT claimed confirmed and follow-through arrived only "
            "later ('{0}') -- waiting matched the persisted "
            "sequence".format(followed[0].outcome_id))


def review_timing(store_dir: str, thesis_id: str, *, now: str) -> TimingReview:
    """Review the journaled timing claim against what happened next.

    ``what_happened_next`` cites the resolved outcomes in persisted run
    sequence; the label compares the claim to that sequence and reads
    ``unresolved`` wherever the history cannot answer. Appends ONE review
    (idempotent by content-derived id).
    """
    _require_now(now, "review_timing")
    entry = _journal_entry(store_dir, thesis_id)
    scoped = _thesis_scope(store_dir, entry)
    window = _window_of(scoped)
    resolved = tuple(o for o in scoped if o.outcome_label != "unresolved")
    label, why = _timing_label(entry.timing_claimed, resolved)
    record = TimingReview(
        learning_id="learn.timing-review.{0}.{1}.{2}.r{3}-{4}".format(
            _slug(entry.journal_id), _slug(window[0]), _slug(window[1]),
            len(resolved), _slug(label)),
        thesis_ref=entry.journal_id,
        window=window,
        timing_claimed=entry.timing_claimed,
        what_happened_next=tuple(_cite(o) for o in resolved),
        timing_label=label,
        basis=("Timing review of thesis '{0}' across runs '{1}'..'{2}': the "
               "journal claimed '{3}'; {4} resolved outcome(s) followed. "
               "Label: '{5}' -- {6}.".format(
                   entry.journal_id, window[0], window[1],
                   entry.timing_claimed, len(resolved), label, why)),
        created_at=now)
    record_learning_rollups(store_dir, (record,))
    return record


# --------------------------------------------------------------------------- #
# 7. roll_expert_reliability -- per-account social-source learning             #
# --------------------------------------------------------------------------- #
def _social_event_accounts(store_dir: str) -> Dict[str, Tuple[str, str]]:
    """event_id -> (account handle, account kind) for SOCIAL events only.

    An event is attributed iff it is a social / rumor-tier source AND names a
    ``source_id`` handle; anything else is skipped -- unattributable is
    unattributable, never guessed.
    """
    accounts: Dict[str, Tuple[str, str]] = {}
    for event in EventStore(store_dir).read_all():
        handle = str(getattr(event, "source_id", "") or "").strip()
        if not handle:
            continue
        source_type = getattr(event, "source_type", "")
        if (_labels.is_social_source(source_type=source_type,
                                     discipline=getattr(event, "discipline", ""))
                or _labels.is_social_source_type(source_type)
                or getattr(event, "source_authority", "") == "rumor"):
            accounts.setdefault(event.event_id, (handle, source_type))
    return accounts


def roll_expert_reliability(store_dir: str, *,
                            now: str) -> Tuple[ExpertAccountReliabilityRecord, ...]:
    """Roll per-account reliability from persisted narrative-signal outcomes.

    Every signal outcome is attributed -- via the subject signal's cited
    source events / evidence refs -- to the SOCIAL account(s) whose events it
    rests on; each account's outcomes are counted as VOLUMES and labelled with
    the 017A closed ladder (``insufficient_history`` under 3 resolved).
    Appends the new records (idempotent by content-derived ids) and returns
    every rolled record. Deterministic: accounts in sorted sequence.
    """
    _require_now(now, "roll_expert_reliability")
    accounts = _social_event_accounts(store_dir)
    signal_events: Dict[str, Tuple[str, ...]] = {}
    for signal in SignalStore(store_dir).read_all():
        refs = tuple(signal.source_events) + tuple(signal.evidence_refs)
        signal_events.setdefault(signal.signal_id, refs)

    grouped: Dict[Tuple[str, str], List[OutcomeRecord]] = {}
    for outcome in _current_outcomes(store_dir):
        if outcome.subject_kind != "signal":
            continue
        seen: List[Tuple[str, str]] = []
        for ref in signal_events.get(outcome.subject_id, ()):
            account = accounts.get(ref)
            if account is not None and account not in seen:
                seen.append(account)
        for account in seen:
            grouped.setdefault(account, []).append(outcome)

    records: List[ExpertAccountReliabilityRecord] = []
    for handle, kind in sorted(grouped):
        scoped = grouped[(handle, kind)]
        counts = _count_labels(scoped)
        window = _window_of(scoped)
        label = _reliability_label(counts["followed_through"],
                                   counts["contradicted"], counts["faded"])
        records.append(ExpertAccountReliabilityRecord(
            learning_id="learn.expert-account.{0}.{1}.{2}.f{3}-c{4}-fa{5}-u{6}".format(
                _slug(handle), _slug(window[0]), _slug(window[1]),
                counts["followed_through"], counts["contradicted"],
                counts["faded"], counts["unresolved"]),
            account_handle=handle,
            account_kind=kind,
            window=window,
            followed_through_count=counts["followed_through"],
            contradicted_count=counts["contradicted"],
            faded_count=counts["faded"],
            unresolved_count=counts["unresolved"],
            reliability_label=label,
            basis=_volume_basis(counts, window, label,
                                "account '{0}' ({1}) sourced signal claims".format(
                                    handle, kind or "unspecified kind")),
            created_at=now))
    record_learning_rollups(store_dir, records)
    return tuple(records)


# --------------------------------------------------------------------------- #
# 8. roll_archetypes -- repeated state-arc transitions become archetypes       #
# --------------------------------------------------------------------------- #
def roll_archetypes(store_dir: str, *, now: str) -> Tuple[ArchetypeUpdate, ...]:
    """Roll repeated theme state-arc transitions into archetype records.

    Groups the RESOLVED theme-pulse outcomes by their persisted transition
    (claimed state -> observed state); each recurring arc becomes an
    :class:`ArchetypeUpdate` named for the transition (e.g.
    ``theme_igniting_to_broadening``) with VOLUME counts and the 017A closed
    label -- ``insufficient_history`` until the arc has recurred at least 3
    times. Appends the new records (idempotent) and returns every rolled one.
    """
    _require_now(now, "roll_archetypes")
    grouped: Dict[str, List[OutcomeRecord]] = {}
    for outcome in _current_outcomes(store_dir):
        if outcome.subject_kind != "theme_pulse":
            continue
        if outcome.outcome_label == "unresolved":
            continue
        claimed = _quoted(outcome.claimed)
        if not claimed:
            continue
        observed = _quoted(outcome.observed) or "absent"
        archetype_id = "theme_{0}_to_{1}".format(
            _slug(claimed).replace("-", "_"), _slug(observed).replace("-", "_"))
        grouped.setdefault(archetype_id, []).append(outcome)

    records: List[ArchetypeUpdate] = []
    for archetype_id in sorted(grouped):
        scoped = grouped[archetype_id]
        counts = _count_labels(scoped)
        window = _window_of(scoped)
        label = _reliability_label(counts["followed_through"],
                                   counts["contradicted"], counts["faded"])
        first = scoped[0]
        records.append(ArchetypeUpdate(
            learning_id="learn.archetype.{0}.{1}.{2}.o{3}-f{4}-r{5}".format(
                _slug(archetype_id), _slug(window[0]), _slug(window[1]),
                len(scoped), counts["followed_through"], counts["contradicted"]),
            archetype_id=archetype_id,
            window=window,
            occurrences_count=len(scoped),
            followed_through_count=counts["followed_through"],
            reversed_count=counts["contradicted"],
            archetype_label=label,
            basis=("Archetype '{0}': across runs '{1}'..'{2}' the persisted "
                   "transition {3} -> {4} recurred {5} time(s): {6} followed "
                   "through, {7} reversed (counts are volumes; no ratio is "
                   "stored). Label: '{8}'.".format(
                       archetype_id, window[0], window[1], first.claimed,
                       first.observed or "'absent'", len(scoped),
                       counts["followed_through"], counts["contradicted"],
                       label)
                   + (" Fewer than {0} resolved occurrences -- no pattern is "
                      "asserted off a tiny sample.".format(
                          REVIEW_THRESHOLDS["min_resolved_outcomes"])
                      if label == "insufficient_history" else "")),
            created_at=now))
    record_learning_rollups(store_dir, records)
    return tuple(records)


# --------------------------------------------------------------------------- #
# 9. append_experience_update -- one dated entry, citations only               #
# --------------------------------------------------------------------------- #
_EXPERIENCE_CITABLE_TYPES = frozenset(
    {"ThesisPostmortem", "RedTeamReview", "TimingReview",
     "ExpertAccountReliabilityRecord", "ArchetypeUpdate"})


def append_experience_update(store_dir: str, *,
                             now: str) -> Optional[ExperienceLayerUpdate]:
    """Tie every persisted review record into ONE dated experience entry.

    Cites the persisted postmortem / red-team / timing / expert-account /
    archetype record ids -- and NOTHING else: no synthesis beyond citation.
    With no review records persisted, returns ``None`` and appends nothing
    (an empty experience entry would be a fabrication). Idempotent: the id
    derives from the cited set, so re-appending over the same records leaves
    the store byte-identical, and new review records yield a NEW entry.
    """
    _require_now(now, "append_experience_update")
    cited: List[str] = []
    for envelope in LearningStore(store_dir).read_records():
        if str(envelope.get("record_type", "")) in _EXPERIENCE_CITABLE_TYPES:
            rid = str(envelope.get("record_id", ""))
            if rid and rid not in cited:
                cited.append(rid)
    if not cited:
        return None
    digest = hashlib.sha256("\n".join(cited).encode("utf-8")).hexdigest()[:12]
    record = ExperienceLayerUpdate(
        learning_id="learn.experience.{0}".format(digest),
        entry_date=now,
        cited_record_ids=tuple(cited),
        basis=("Experience entry: cites {0} persisted review record(s) -- {1}. "
               "Citation only; no synthesis beyond the records named.".format(
                   len(cited),
                   ", ".join("'{0}'".format(rid) for rid in cited))),
        created_at=now)
    record_learning_rollups(store_dir, (record,))
    return record
