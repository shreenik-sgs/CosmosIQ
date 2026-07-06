"""Paper Recommendation Journal for the Reality Mesh (IMPLEMENTATION-022F).

Before any production recommendation is surfaced, EVERY recommendation is JOURNALED --
append-only -- so the system can later measure whether its recommendations improve over
time, count false positives / missed opportunities, calibrate signal families, and feed the
017 Learning & Feedback layer. This is a PAPER journal: it RECORDS what a
:class:`~reality_mesh.recommendation.CapitalRecommendation` said AT THE TIME; it is NOT
execution and it does not act.

HARD DISCIPLINE baked into the shape (mirrors the 013B stores + the 017 learning core):

* **Append-only; correction-not-mutation.** A journaled line, once written, is never edited
  or removed. There is NO update / delete API. A later outcome -- or a status change -- is a
  NEW line carrying the SAME ``journal_id``; the prior line stays byte-unchanged forever and
  the latest line for an id is the current knowledge (latest-wins per id). Every line carries
  a ``schema_version`` via the 013B envelope.
* **Does NOT imply execution.** There is NO field or token for a directive to act -- no
  routing affordance, no fill, no ticket. ``entry_reference_price`` is a REFERENCE data
  point ONLY: a labelled price context recorded "if available", clearly NOT an instruction to
  act, an entry directive, or a target. It is OPTIONAL -- absent it is ``None`` (a gap), never
  fabricated.
* **Labels + refs + counts, never a score.** There is NO numeric ``score`` / ``rank`` /
  ``rating`` field anywhere (enforced structurally by
  :func:`~reality_mesh.validation.assert_no_trade_fields`). ``subsequent_outcomes`` are
  labelled outcome REFS, never a numeric return; ``status`` is a CLOSED label. The 013B store
  guard would refuse a metric / credential key anyway.
* **Deterministic + offline.** Every id derives from ``(run_id, recommendation_id)``; every
  timestamp is an injected string (no wall clock). Persistence is one local append-only JSONL
  log. Re-journalling the same recommendation appends nothing (idempotent, byte-identical).

Deterministic, stdlib-only, Python 3.9. No network, no scheduler, no daemon on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Tuple

from .learning import OUTCOME_LABELS
from .recommendation import (
    RECOMMENDATION_DATA_QUALITY_STATES,
    RECOMMENDATION_LABELS,
    RECOMMENDATION_STATES,
    CapitalRecommendation,
)
from .stores import AppendOnlyStore
from .validation import assert_no_trade_fields

__all__ = [
    "JOURNAL_STATUSES",
    "JOURNAL_STATUS_OUTCOME",
    "SCHEMA_VERSION",
    "RecommendationJournalEntry",
    "RecommendationJournalStore",
    "journal_id_for",
    "journal_recommendation",
    "record_outcome",
    "journaled",
    "open_recommendations",
    "feed_learning",
]

# The journal's own record schema version (independent of the 013B envelope version).
SCHEMA_VERSION = "022F.1"

# The CLOSED status ladder a journaled recommendation may carry. ``open`` is the initial
# state; every other value is a settled disposition recorded by a LATER append (never a guess).
JOURNAL_STATUSES: Tuple[str, ...] = (
    "open",
    "invalidation_hit",
    "exit_watch_hit",
    "thesis_confirmed",
    "lapsed",
    "superseded",
)

# How a settled journal status maps to the 017 outcome vocabulary the Learning & Feedback
# roll-ups consume. Labels + counts only -- there is NO numeric metric in this mapping.
JOURNAL_STATUS_OUTCOME: Dict[str, str] = {
    "open": "unresolved",
    "invalidation_hit": "contradicted",
    "exit_watch_hit": "faded",
    "thesis_confirmed": "followed_through",
    "lapsed": "faded",
    "superseded": "unresolved",
}


def _forbid_floats(obj) -> None:
    """No float anywhere on a journal entry: the journal stores labels + refs, never a metric."""
    for f in fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, float):
            raise ValueError(
                "RecommendationJournalEntry.{0} is a float -- the journal stores labels + "
                "refs + counts only, never a numeric metric".format(f.name))
        if isinstance(value, tuple):
            for element in value:
                if isinstance(element, float):
                    raise ValueError(
                        "RecommendationJournalEntry.{0} contains a float -- the journal never "
                        "stores a numeric metric".format(f.name))


# --------------------------------------------------------------------------- #
# The typed journal entry                                                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RecommendationJournalEntry:
    """One append-only journaled recommendation: what a recommendation said AT THE TIME.

    Labels + refs + counts only. ``entry_reference_price`` is a REFERENCE price context (a
    labelled data point recorded "if available"), NEVER an instruction to act, an entry
    directive, or a target -- and it is OPTIONAL (``None`` when absent, a gap never fabricated).
    ``subsequent_outcomes`` grows -- via NEW appended lines with the SAME ``journal_id`` -- as
    later observations arrive; each element is a labelled outcome REF, never a numeric return.
    There is NO score / rank / rating field, and no directive-to-act field anywhere.
    """

    journal_id: str = ""                    # REQUIRED, deterministic ((run, recommendation) id)
    recommendation_id: str = ""             # REQUIRED -- the journaled recommendation
    run_id: str = ""                        # REQUIRED -- the run that produced it
    ticker: str = ""                        # REQUIRED
    recommendation_label: str = ""          # closed: RECOMMENDATION_LABELS ("" = unset)
    recommendation_state: str = ""          # closed: RECOMMENDATION_STATES
    published_at: str = ""                  # injected timestamp the recommendation was journaled
    entry_reference_price: Optional[str] = None   # a labelled REFERENCE, never a directive; None=gap
    time_horizon: str = ""                  # plain-English horizon label (never a number)
    thesis_summary: str = ""
    invalidation_condition: str = ""
    exit_watch_condition: str = ""
    source_refs: Tuple[str, ...] = field(default_factory=tuple)
    data_quality_state: str = ""            # the recommendation's recorded DQ verdict
    subsequent_outcomes: Tuple[str, ...] = field(default_factory=tuple)  # labelled outcome refs
    status: str = "open"                    # closed: JOURNAL_STATUSES
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        # -- required ids -- #
        for name in ("journal_id", "recommendation_id", "run_id", "ticker"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "RecommendationJournalEntry.{0} is required and must be non-empty".format(name))

        # -- closed vocabularies -- #
        if self.status not in JOURNAL_STATUSES:
            raise ValueError(
                "RecommendationJournalEntry.status {0!r} invalid (allowed: {1})".format(
                    self.status, list(JOURNAL_STATUSES)))
        if self.recommendation_state and self.recommendation_state not in RECOMMENDATION_STATES:
            raise ValueError(
                "RecommendationJournalEntry.recommendation_state {0!r} invalid (allowed: "
                "{1})".format(self.recommendation_state, list(RECOMMENDATION_STATES)))
        if self.recommendation_label and self.recommendation_label not in RECOMMENDATION_LABELS:
            raise ValueError(
                "RecommendationJournalEntry.recommendation_label {0!r} invalid (allowed: "
                "{1})".format(self.recommendation_label, list(RECOMMENDATION_LABELS)))
        if (self.data_quality_state
                and self.data_quality_state not in RECOMMENDATION_DATA_QUALITY_STATES):
            raise ValueError(
                "RecommendationJournalEntry.data_quality_state {0!r} invalid (allowed: "
                "{1})".format(self.data_quality_state,
                              list(RECOMMENDATION_DATA_QUALITY_STATES)))

        # -- entry_reference_price: a labelled REFERENCE or an honest gap (None), never a
        #    directive to act. If present it must be a label / number-rendered-as-text; a bare
        #    float is refused so it can never be mistaken for a computable instruction. -- #
        if self.entry_reference_price is not None and not isinstance(self.entry_reference_price, str):
            raise ValueError(
                "RecommendationJournalEntry.entry_reference_price must be a labelled string "
                "reference or None (a gap) -- it is a price CONTEXT, never a directive to act")

        # -- string-tuple + no-metric discipline -- #
        for name in ("source_refs", "subsequent_outcomes"):
            for element in getattr(self, name):
                if not isinstance(element, str):
                    raise ValueError(
                        "RecommendationJournalEntry.{0} must be a tuple of string refs -- the "
                        "journal records labelled refs, never a numeric return".format(name))
        _forbid_floats(self)

    @property
    def is_open(self) -> bool:
        return self.status == "open"


# --------------------------------------------------------------------------- #
# Deterministic id                                                              #
# --------------------------------------------------------------------------- #
def journal_id_for(run_id: str, recommendation_id: str) -> str:
    """A deterministic journal id from the run + recommendation (no wall clock, stable)."""
    return "recjournal:{0}:{1}".format(
        str(run_id or "").strip(), str(recommendation_id or "").strip())


# --------------------------------------------------------------------------- #
# The append-only store                                                         #
# --------------------------------------------------------------------------- #
class RecommendationJournalStore(AppendOnlyStore):
    """Append-only recommendation journal (``recommendation_journal.jsonl``).

    One line per journalling / outcome event. A later outcome (or status change) is a NEW line
    carrying the SAME ``journal_id`` -- the prior line stays byte-unchanged, and the LATEST
    line for an id is the current knowledge (latest-wins per id). Query axes: ``run_id`` /
    ``ticker`` / ``status`` / ``recommendation_state``. Composes the 013B base -- so it inherits
    the credential + trade/score key write refusal and the deterministic envelope, and it has
    NO update / delete affordance.
    """

    filename = "recommendation_journal.jsonl"
    record_cls = RecommendationJournalEntry
    id_field = "journal_id"
    timestamp_field = "published_at"
    ticker_fields = ("ticker",)


def _latest_by_id(store_dir: str) -> "Dict[str, RecommendationJournalEntry]":
    """journal_id -> the LATEST appended entry for that id (first-seen sequence preserved).

    The earlier lines stay byte-unchanged on disk; this is the read-side latest-wins view.
    """
    latest: Dict[str, RecommendationJournalEntry] = {}
    for entry in RecommendationJournalStore(store_dir).read_all():
        latest[entry.journal_id] = entry     # updating a key preserves its insertion index
    return latest


# --------------------------------------------------------------------------- #
# Journalling + outcome recording                                              #
# --------------------------------------------------------------------------- #
def journal_recommendation(store_dir: str, recommendation: CapitalRecommendation, *,
                           now: str,
                           entry_reference_price: Optional[str] = None
                           ) -> RecommendationJournalEntry:
    """Journal one recommendation append-only; return the entry.

    Records the recommendation's state + label + horizon + thesis + guardrail conditions +
    source refs + DQ verdict AT THE TIME. The journal id derives from
    ``(run_id, recommendation_id)`` so journalling the SAME recommendation twice appends
    nothing (the store stays byte-identical); a later observation is recorded via
    :func:`record_outcome`, never by re-writing this line. ``entry_reference_price`` is an
    OPTIONAL labelled reference (a price CONTEXT, not a directive to act); absent it is ``None``
    -- a gap, never fabricated.
    """
    if not str(now).strip():
        raise ValueError("journal_recommendation requires an injected 'now' instant")
    if not isinstance(recommendation, CapitalRecommendation):
        raise TypeError(
            "journal_recommendation expects a CapitalRecommendation, got {0}".format(
                type(recommendation).__name__))

    jid = journal_id_for(recommendation.run_id, recommendation.recommendation_id)
    entry = RecommendationJournalEntry(
        journal_id=jid,
        recommendation_id=recommendation.recommendation_id,
        run_id=recommendation.run_id,
        ticker=recommendation.ticker,
        recommendation_label=recommendation.recommendation_label,
        recommendation_state=recommendation.recommendation_state,
        published_at=str(now),
        entry_reference_price=entry_reference_price,
        time_horizon=recommendation.recommendation_time_horizon,
        thesis_summary=recommendation.key_thesis,
        invalidation_condition="; ".join(recommendation.invalidation_conditions),
        exit_watch_condition="; ".join(recommendation.exit_watch_conditions),
        source_refs=tuple(recommendation.source_provenance),
        data_quality_state=_dq_state_of(recommendation),
        subsequent_outcomes=(),
        status="open")

    store = RecommendationJournalStore(store_dir)
    existing = {str(rec.get("record_id", "")) for rec in store.read_records()}
    if entry.journal_id not in existing:
        store.append(entry, run_id=entry.run_id, timestamp=entry.published_at)
    else:
        # already journaled: return the latest knowledge, append nothing (byte-identical).
        return _latest_by_id(store_dir).get(entry.journal_id, entry)
    return entry


def _dq_state_of(recommendation: CapitalRecommendation) -> str:
    """The recommendation's recorded DQ verdict, iff it is a known closed state ("" otherwise).

    The recommendation carries its DQ as ``data_quality_ref``; where that is a recognised DQ
    state label it is journaled as the state, otherwise the state is left unset (a ref-only DQ
    is recorded through ``source_refs`` provenance, never invented as a state).
    """
    ref = str(getattr(recommendation, "data_quality_ref", "") or "").strip()
    return ref if ref in RECOMMENDATION_DATA_QUALITY_STATES else ""


def record_outcome(store_dir: str, recommendation_id: str, *, outcome_ref: str, now: str,
                   status: str = "") -> RecommendationJournalEntry:
    """Record a later observation for a journaled recommendation as a NEW append.

    Correction-not-mutation: appends a NEW line carrying the SAME ``journal_id`` that EXTENDS
    ``subsequent_outcomes`` with ``outcome_ref`` and (optionally) advances ``status`` -- the
    prior line stays byte-unchanged forever, and the latest line becomes the current knowledge.
    Idempotent: recording the same ``outcome_ref`` with no status change appends nothing (the
    store stays byte-identical). Requires the recommendation to have been journaled first.
    """
    if not str(now).strip():
        raise ValueError("record_outcome requires an injected 'now' instant")
    if not str(outcome_ref or "").strip():
        raise ValueError(
            "record_outcome requires a non-empty outcome_ref -- a labelled outcome reference, "
            "never a fabricated value")
    if status and status not in JOURNAL_STATUSES:
        raise ValueError(
            "record_outcome status {0!r} invalid (allowed: {1})".format(
                status, list(JOURNAL_STATUSES)))

    prior = _latest_entry_for_recommendation(store_dir, str(recommendation_id))
    if prior is None:
        raise ValueError(
            "no journaled recommendation {0!r} -- journal it first "
            "(journal_recommendation)".format(recommendation_id))

    new_status = status or prior.status
    if str(outcome_ref) in prior.subsequent_outcomes and new_status == prior.status:
        # nothing changes -> append nothing (idempotent, byte-identical).
        return prior
    new_outcomes = (prior.subsequent_outcomes + (str(outcome_ref),)
                    if str(outcome_ref) not in prior.subsequent_outcomes
                    else prior.subsequent_outcomes)

    entry = RecommendationJournalEntry(
        journal_id=prior.journal_id,
        recommendation_id=prior.recommendation_id,
        run_id=prior.run_id,
        ticker=prior.ticker,
        recommendation_label=prior.recommendation_label,
        recommendation_state=prior.recommendation_state,
        published_at=prior.published_at,       # the original publication instant is immutable
        entry_reference_price=prior.entry_reference_price,
        time_horizon=prior.time_horizon,
        thesis_summary=prior.thesis_summary,
        invalidation_condition=prior.invalidation_condition,
        exit_watch_condition=prior.exit_watch_condition,
        source_refs=prior.source_refs,
        data_quality_state=prior.data_quality_state,
        subsequent_outcomes=new_outcomes,
        status=new_status)
    RecommendationJournalStore(store_dir).append(
        entry, run_id=entry.run_id, timestamp=str(now))
    return entry


def _latest_entry_for_recommendation(store_dir: str, recommendation_id: str
                                     ) -> "Optional[RecommendationJournalEntry]":
    """The latest journaled entry for a recommendation id, or ``None`` if never journaled."""
    found: Optional[RecommendationJournalEntry] = None
    for entry in RecommendationJournalStore(store_dir).read_all():
        if entry.recommendation_id == recommendation_id:
            found = entry
    return found


# --------------------------------------------------------------------------- #
# Query helpers (latest-wins views)                                            #
# --------------------------------------------------------------------------- #
def journaled(store_dir: str, run_id: Optional[str] = None
              ) -> Tuple[RecommendationJournalEntry, ...]:
    """Every journaled recommendation (latest line per id), optionally scoped to one run."""
    entries = tuple(_latest_by_id(store_dir).values())
    if run_id is not None:
        entries = tuple(e for e in entries if e.run_id == run_id)
    return entries


def open_recommendations(store_dir: str) -> Tuple[RecommendationJournalEntry, ...]:
    """Every journaled recommendation whose LATEST line is still ``open``."""
    return tuple(e for e in _latest_by_id(store_dir).values() if e.status == "open")


# --------------------------------------------------------------------------- #
# The 017 Learning & Feedback hook -- labels + volume counts only              #
# --------------------------------------------------------------------------- #
def feed_learning(store_dir: str) -> Dict[str, int]:
    """Summarise the journal as the labels + VOLUME COUNTS the 017 learning core consumes.

    Maps each journaled recommendation's LATEST status onto the 017 outcome vocabulary
    (``JOURNAL_STATUS_OUTCOME``) and returns a VOLUME count per outcome label -- exactly the
    shape the 017 ``LearningStore`` reliability / accuracy roll-ups already digest (labels +
    counts, thresholds-as-data). There is NO numeric score here, and this NEVER rewrites
    learning.py: it shows only that the journal PRODUCES what 017 CONSUMES. Counts are volumes.
    """
    counts: Dict[str, int] = {label: 0 for label in sorted(OUTCOME_LABELS)}
    for entry in _latest_by_id(store_dir).values():
        counts[JOURNAL_STATUS_OUTCOME[entry.status]] += 1
    return counts


# --------------------------------------------------------------------------- #
# Construction-time guard: the entry carries NO trade / score field.            #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(RecommendationJournalEntry)
