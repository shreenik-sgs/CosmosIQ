"""Diff-based alert generation + append-only alert inbox (IMPLEMENTATION-015C).

Alerts OBSERVE -- they never act. An :class:`Alert` is a frozen record that names a state
CHANGE between two persisted pulse runs and points at the evidence; a human reads it and
decides what (if anything) to do next. There is NO action field of any kind on an alert, no
affordance to act from one, and nothing here starts, loops, waits, or reaches a network.

The discipline (ADR-CANDIDATE-015; ARCHITECTURE_CONTRACT_012 stays in force):

* **Diff-based and deterministic.** :func:`generate_alerts_for_run` compares THIS run's
  persisted signals / theme pulses / findings / data-quality records (the 013B stores)
  against the PREVIOUS persisted run's. A state CHANGE alerts; sameness stays quiet -- an
  unchanged reality produces ZERO alerts. Same stores + same injected ``now`` -> the same
  alerts with the same ids, byte for byte.
* **First run is a baseline.** With no previous run there is nothing to compare: the result
  carries one visible baseline note and NO alerts -- never a flood restating the first run.
* **Closed vocabularies.** ``category`` is one of :data:`ALERT_CATEGORIES` and ``severity``
  one of :data:`ALERT_SEVERITIES` -- labels, never scores. ``human_readable_reason`` is
  REQUIRED: plain English naming the evidence (ids, states, runs), never a bare code.
* **Append-only inbox.** :class:`AlertStore` composes the 013B
  :class:`~reality_mesh.stores.AppendOnlyStore`: no update, no delete, no in-place change.
  Acknowledging an alert appends a NEW :class:`AlertAcknowledgment` record that REFERENCES
  the alert_id (:func:`acknowledge_alert`); the original alert line is byte-unchanged
  forever.

Deterministic, stdlib-only, Python 3.9, OFFLINE: every timestamp is an injected ISO-8601
string (the wall clock is never read), ids derive from run + category + subject, and all
persistence is local append-only JSONL.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

from .stores import (
    AppendOnlyStore,
    DataQualityStore,
    FindingStore,
    RunStore,
    SignalStore,
    ThemePulseStore,
)

__all__ = [
    "ALERT_CATEGORIES",
    "ALERT_SEVERITIES",
    "CATEGORY_SEVERITY",
    "Alert",
    "AlertAcknowledgment",
    "AlertStore",
    "AlertAcknowledgmentStore",
    "AlertGenerationResult",
    "previous_persisted_run_id",
    "diff_persisted_runs",
    "generate_alerts_for_run",
    "record_failed_pulse_alert",
    "acknowledge_alert",
    "acknowledged_alert_ids",
    "alerts_with_status",
    "unacknowledged_alerts",
    "acknowledged_alerts",
]

# The CLOSED alert-category vocabulary (a new category requires a spec change, never a
# free-text value). Every category names an OBSERVED state change -- none names an action.
ALERT_CATEGORIES: FrozenSet[str] = frozenset({
    "market_regime_changed",
    "sector_rotation_detected",
    "theme_pulse_changed",
    "filing_dilution_risk",
    "social_narrative_spike",
    "crowding_warning",
    "source_data_quality_failure",
    "thesis_deteriorated",
    "new_opportunity_hypothesis",
    "major_risk_emerged",
})

# The CLOSED severity vocabulary -- labels on a human-attention ladder, never scores.
ALERT_SEVERITIES: FrozenSet[str] = frozenset({"info", "notice", "warning", "critical"})

# The default severity LABEL per category (a label mapping, not a weighting).
CATEGORY_SEVERITY: Mapping[str, str] = {
    "market_regime_changed": "warning",
    "sector_rotation_detected": "notice",
    "theme_pulse_changed": "notice",
    "filing_dilution_risk": "warning",
    "social_narrative_spike": "notice",
    "crowding_warning": "warning",
    "source_data_quality_failure": "critical",
    "thesis_deteriorated": "warning",
    "new_opportunity_hypothesis": "info",
    "major_risk_emerged": "critical",
}

# Theme-pulse states whose ARRIVAL upgrades a theme_pulse_changed alert to ``warning``.
_DETERIORATING_THEME_STATES = frozenset({"Breaking down", "Exhausting"})

# Elevated narrative labels: a social/narrative signal reaching one of these where the
# previous run's counterpart had none is a velocity spike (weak-signal tier -- says so).
_SPIKE_URGENCIES = frozenset({"elevated", "high", "immediate"})
_SPIKE_MAGNITUDES = frozenset({"major", "extreme"})

# Crowding labels that fire a crowding_warning when newly reached.
_CROWDING_FIRED = frozenset({"major", "extreme"})

# Data-quality statuses that count as failing (gate verdict or run diagnostic).
_FAILING_DQ_STATUSES = frozenset({"fail", "failed"})


# --------------------------------------------------------------------------- #
# 1. Alert + AlertAcknowledgment -- frozen observation records                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Alert:
    """One frozen observation of a state change. It names evidence; it never acts.

    ``human_readable_reason`` is REQUIRED plain English naming the evidence (what changed,
    from what to what, between which runs). There is NO action field: nothing on an alert
    can start, place, or change anything anywhere.
    """

    alert_id: str = ""
    run_id: str = ""
    category: str = ""                      # closed: ALERT_CATEGORIES
    severity: str = "info"                  # closed: ALERT_SEVERITIES (a label, not a score)
    human_readable_reason: str = ""         # REQUIRED plain English naming the evidence
    subject_tickers: Tuple[str, ...] = field(default_factory=tuple)
    subject_themes: Tuple[str, ...] = field(default_factory=tuple)
    subject_refs: Tuple[str, ...] = field(default_factory=tuple)   # signal / pulse / finding ids
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    created_at: str = ""                    # injected timestamp (no wall clock)
    acknowledged: bool = False              # read-model flag; persisted alerts stay False

    def __post_init__(self) -> None:
        for name in ("alert_id", "run_id", "created_at"):
            value = getattr(self, name)
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "Alert.{0} is required and must be non-empty".format(name))
        if self.category not in ALERT_CATEGORIES:
            raise ValueError(
                "Alert.category {0!r} invalid (closed vocabulary: {1})".format(
                    self.category, sorted(ALERT_CATEGORIES)))
        if self.severity not in ALERT_SEVERITIES:
            raise ValueError(
                "Alert.severity {0!r} invalid (closed vocabulary: {1})".format(
                    self.severity, sorted(ALERT_SEVERITIES)))
        if not isinstance(self.human_readable_reason, str) \
                or self.human_readable_reason.strip() == "":
            raise ValueError(
                "Alert.human_readable_reason is REQUIRED: plain English naming the "
                "evidence -- an alert without a reason is refused")
        if not isinstance(self.acknowledged, bool):
            raise ValueError("Alert.acknowledged must be a bool")
        for name in ("subject_tickers", "subject_themes", "subject_refs", "evidence_refs"):
            object.__setattr__(self, name, tuple(getattr(self, name)))


@dataclass(frozen=True)
class AlertAcknowledgment:
    """One append-only acknowledgment: a NEW record REFERENCING an alert_id.

    Acknowledging never touches the alert's own line -- the original stays byte-unchanged;
    this record is the only thing that marks it read.
    """

    ack_id: str = ""
    alert_id: str = ""                      # the alert this acknowledges (a reference)
    acknowledged_by: str = "operator"
    at: str = ""                            # injected timestamp
    note: str = ""

    def __post_init__(self) -> None:
        for name in ("ack_id", "alert_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "AlertAcknowledgment.{0} is required and must be non-empty".format(name))


# --------------------------------------------------------------------------- #
# 2. The append-only alert inbox stores (013B pattern)                          #
# --------------------------------------------------------------------------- #
class AlertStore(AppendOnlyStore):
    """The alert inbox: one JSONL line per alert, append-only, never edited.

    Query axes: ``run_id`` / ``category`` / ``severity`` (+ ``ticker`` over subject_tickers,
    ``theme`` over subject_themes). Acknowledgment lives in the SEPARATE
    :class:`AlertAcknowledgmentStore` -- an alert line is never rewritten.
    """

    filename = "alert_store.jsonl"
    record_cls = Alert
    id_field = "alert_id"
    timestamp_field = "created_at"
    ticker_fields = ("subject_tickers",)
    theme_fields = ("subject_themes",)


class AlertAcknowledgmentStore(AppendOnlyStore):
    """Acknowledgment records: NEW lines referencing alert ids (never a mutation)."""

    filename = "alert_ack_store.jsonl"
    record_cls = AlertAcknowledgment
    id_field = "ack_id"
    timestamp_field = "at"


def acknowledge_alert(store_dir: str, alert_id: str, *, at: str,
                      acknowledged_by: str = "operator", note: str = "") -> str:
    """Acknowledge one alert by APPENDING a new record referencing it; return the ack_id.

    The alert's own stored line stays byte-unchanged forever. An unknown alert_id is
    refused (``ValueError``) -- an acknowledgment must reference a real alert.
    """
    if not str(alert_id).strip():
        raise ValueError("acknowledge_alert requires a non-empty alert_id")
    known = {a.alert_id for a in AlertStore(store_dir).read_all()}
    if alert_id not in known:
        raise ValueError(
            "unknown alert_id {0!r} -- nothing to acknowledge (known alerts: {1})".format(
                alert_id, sorted(known) if known else "none"))
    ack_store = AlertAcknowledgmentStore(store_dir)
    prior = sum(1 for a in ack_store.read_all() if a.alert_id == alert_id)
    ack = AlertAcknowledgment(
        ack_id="ack.{0}.{1:03d}".format(alert_id, prior + 1),
        alert_id=alert_id, acknowledged_by=acknowledged_by, at=at, note=note)
    return ack_store.append(ack, timestamp=at)


def acknowledged_alert_ids(store_dir: str) -> FrozenSet[str]:
    """The set of alert ids that carry at least one acknowledgment record."""
    return frozenset(a.alert_id for a in AlertAcknowledgmentStore(store_dir).read_all())


def alerts_with_status(store_dir: str) -> Tuple[Alert, ...]:
    """Every stored alert (append sequence) with ``acknowledged`` joined from the ack store.

    A read-model only: the joined flag comes from :class:`AlertAcknowledgmentStore`
    references; the stored alert lines themselves are untouched and still carry ``False``.
    """
    acked = acknowledged_alert_ids(store_dir)
    return tuple(
        replace(alert, acknowledged=alert.alert_id in acked)
        for alert in AlertStore(store_dir).read_all())


def unacknowledged_alerts(store_dir: str) -> Tuple[Alert, ...]:
    """Alerts with NO acknowledgment record yet (the open inbox)."""
    return tuple(a for a in alerts_with_status(store_dir) if not a.acknowledged)


def acknowledged_alerts(store_dir: str) -> Tuple[Alert, ...]:
    """Alerts that carry at least one acknowledgment record."""
    return tuple(a for a in alerts_with_status(store_dir) if a.acknowledged)


# --------------------------------------------------------------------------- #
# 3. The diff engine -- previous run vs this run; a CHANGE alerts               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AlertGenerationResult:
    """What one alert-generation pass observed (alerts + honest notes)."""

    run_id: str = ""
    previous_run_id: str = ""               # "" on the baseline (first) run
    baseline: bool = False
    alerts: Tuple[Alert, ...] = field(default_factory=tuple)
    notes: Tuple[str, ...] = field(default_factory=tuple)


def previous_persisted_run_id(store_dir: str, run_id: str) -> str:
    """The distinct run persisted immediately before ``run_id`` ("" if none exists).

    Distinct run ids are read from the RunStore spine in append sequence (a superseding
    correction line for the same run does not count twice). A ``run_id`` that never
    persisted (e.g. a failed pulse) compares against the LATEST persisted run.
    """
    seen: List[str] = []
    for record in RunStore(store_dir).read_records():
        rid = str(record.get("run_id", "") or "")
        if rid and rid not in seen:
            seen.append(rid)
    if run_id in seen:
        index = seen.index(run_id)
        return seen[index - 1] if index > 0 else ""
    return seen[-1] if seen else ""


def _slug(text: str) -> str:
    """A deterministic id-safe token: lowercase alnum, runs of anything else -> '-'."""
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


def _mk_alert(run_id: str, category: str, subject: str, reason: str, now: str, *,
              severity: str = "", tickers: Tuple[str, ...] = (),
              themes: Tuple[str, ...] = (), refs: Tuple[str, ...] = (),
              evidence: Tuple[str, ...] = ()) -> Alert:
    return Alert(
        alert_id="alert.{0}.{1}.{2}".format(run_id, category, _slug(subject)),
        run_id=run_id, category=category,
        severity=severity or CATEGORY_SEVERITY[category],
        human_readable_reason=reason,
        subject_tickers=tuple(tickers), subject_themes=tuple(themes),
        subject_refs=tuple(refs), evidence_refs=tuple(evidence),
        created_at=now)


def _by_id(records, id_name: str) -> Dict[str, object]:
    return {getattr(r, id_name, ""): r for r in records if getattr(r, id_name, "")}


def _theme_of(pulse) -> str:
    return getattr(pulse, "theme_name", "") or getattr(pulse, "theme_id", "")


def _diff_theme_pulses(prev, cur, run_id, prev_id, now) -> List[Alert]:
    alerts: List[Alert] = []
    prev_map = _by_id(prev, "theme_pulse_id")
    cur_map = _by_id(cur, "theme_pulse_id")
    for key in sorted(cur_map):
        if key not in prev_map:
            continue                        # a newly-scoped theme is coverage, not a change
        before, after = prev_map[key], cur_map[key]
        theme = _theme_of(after)
        if before.state != after.state:
            severity = ("warning" if after.state in _DETERIORATING_THEME_STATES
                        else CATEGORY_SEVERITY["theme_pulse_changed"])
            alerts.append(_mk_alert(
                run_id, "theme_pulse_changed", key,
                "Theme pulse for '{0}' changed state from '{1}' to '{2}' between run "
                "{3} and run {4}; evidence: theme pulse record '{5}'.".format(
                    theme, before.state, after.state, prev_id, run_id, key),
                now, severity=severity, themes=(getattr(after, "theme_id", "") or theme,),
                refs=(key,), evidence=(key,) + tuple(after.evidence_refs)))
        if (after.crowding_label in _CROWDING_FIRED
                and before.crowding_label not in _CROWDING_FIRED):
            alerts.append(_mk_alert(
                run_id, "crowding_warning", key,
                "Crowding for theme '{0}' reached '{1}' in run {2} (it was '{3}' in run "
                "{4}); evidence: theme pulse record '{5}'.".format(
                    theme, after.crowding_label, run_id,
                    before.crowding_label or "unrecorded", prev_id, key),
                now, themes=(getattr(after, "theme_id", "") or theme,),
                refs=(key,), evidence=(key,)))
    return alerts


def _diff_signals(prev, cur, run_id, prev_id, now) -> List[Alert]:
    alerts: List[Alert] = []
    prev_map = _by_id(prev, "signal_id")
    cur_map = _by_id(cur, "signal_id")
    for key in sorted(cur_map):
        after = cur_map[key]
        before = prev_map.get(key)
        discipline = getattr(after, "discipline", "")
        companies = tuple(getattr(after, "affected_companies", ()) or ())
        themes = tuple(getattr(after, "affected_themes", ()) or ())
        if discipline == "market_regime":
            if before is not None and before.direction_label != after.direction_label:
                alerts.append(_mk_alert(
                    run_id, "market_regime_changed", key,
                    "Market regime direction flipped from '{0}' to '{1}' between run {2} "
                    "and run {3}; evidence: signal '{4}'.".format(
                        before.direction_label, after.direction_label, prev_id,
                        run_id, key),
                    now, tickers=companies, themes=themes, refs=(key,), evidence=(key,)))
        elif discipline == "sector_rotation":
            if before is None:
                alerts.append(_mk_alert(
                    run_id, "sector_rotation_detected", key,
                    "A new sector rotation signal '{0}' ('{1}', sectors: {2}) appeared in "
                    "run {3}; it was not present in run {4}.".format(
                        key, after.direction_label,
                        ", ".join(getattr(after, "affected_sectors", ()) or ()) or "none "
                        "named", run_id, prev_id),
                    now, tickers=companies, themes=themes, refs=(key,), evidence=(key,)))
            elif before.direction_label != after.direction_label:
                alerts.append(_mk_alert(
                    run_id, "sector_rotation_detected", key,
                    "Sector rotation signal '{0}' changed direction from '{1}' to '{2}' "
                    "between run {3} and run {4}.".format(
                        key, before.direction_label, after.direction_label, prev_id,
                        run_id),
                    now, tickers=companies, themes=themes, refs=(key,), evidence=(key,)))
        elif discipline == "narrative":
            spiking = (after.urgency_label in _SPIKE_URGENCIES
                       or after.magnitude_label in _SPIKE_MAGNITUDES)
            was_spiking = before is not None and (
                before.urgency_label in _SPIKE_URGENCIES
                or before.magnitude_label in _SPIKE_MAGNITUDES)
            if spiking and not was_spiking:
                previously = ("urgency '{0}' / magnitude '{1}' in run {2}".format(
                    before.urgency_label, before.magnitude_label, prev_id)
                    if before is not None else "absent in run {0}".format(prev_id))
                alerts.append(_mk_alert(
                    run_id, "social_narrative_spike", key,
                    "Social narrative velocity spiked: signal '{0}' reached urgency '{1}' "
                    "/ magnitude '{2}' in run {3} (previously {4}). Weak / social "
                    "evidence -- requires corroboration by non-social sources.".format(
                        key, after.urgency_label, after.magnitude_label, run_id,
                        previously),
                    now, tickers=companies, themes=themes, refs=(key,), evidence=(key,)))
    return alerts


def _diff_dilution_findings(prev, cur, run_id, prev_id, now) -> List[Alert]:
    alerts: List[Alert] = []
    prev_ids = {getattr(f, "finding_id", "") for f in prev
                if "dilution" in str(getattr(f, "finding_type", "")).lower()}
    for finding in sorted(
            (f for f in cur if "dilution" in str(getattr(f, "finding_type", "")).lower()),
            key=lambda f: getattr(f, "finding_id", "")):
        fid = getattr(finding, "finding_id", "")
        if fid in prev_ids:
            continue
        companies = tuple(getattr(finding, "affected_companies", ()) or ())
        named = " for {0}".format(", ".join(companies)) if companies else ""
        alerts.append(_mk_alert(
            run_id, "filing_dilution_risk", fid,
            "A new dilution-related filing finding '{0}' ({1}){2} appeared in run {3}; "
            "it was not present in run {4}.".format(
                fid, getattr(finding, "finding_type", ""), named, run_id, prev_id),
            now, tickers=companies,
            themes=tuple(getattr(finding, "affected_themes", ()) or ()),
            refs=(fid,), evidence=(fid,) + tuple(getattr(finding, "evidence_refs", ()))))
    return alerts


def _failing_dq(records) -> Dict[str, object]:
    """Failing data-quality records keyed by CATEGORY (dq ids embed the run id)."""
    return {r.category: r for r in records if r.status in _FAILING_DQ_STATUSES}


def _diff_data_quality(prev, cur, run_id, prev_id, now) -> List[Alert]:
    alerts: List[Alert] = []
    prev_failing = _failing_dq(prev)
    cur_failing = _failing_dq(cur)
    for category in sorted(cur_failing):
        if category in prev_failing:
            continue                        # still failing, already alerted -- quiet
        record = cur_failing[category]
        alerts.append(_mk_alert(
            run_id, "source_data_quality_failure", category,
            "Data-quality check '{0}' is failing in run {1} (status '{2}') and was not "
            "failing in run {3}: {4}".format(
                category, run_id, record.status, prev_id,
                record.summary or "no summary recorded"),
            now, refs=(record.dq_id,), evidence=(record.dq_id,)))
    return alerts


def diff_persisted_runs(store_dir: str, previous_id: str, current_id: str, *,
                        now: str) -> Tuple[Alert, ...]:
    """Pure read-and-compare: the alerts implied by ``previous_id`` -> ``current_id``.

    Reads the 013B stores only; persists nothing. Deterministic: subjects are visited in
    sorted id sequence, so the same stores yield the same alerts in the same sequence.
    """
    if not str(previous_id).strip() or not str(current_id).strip():
        raise ValueError("diff_persisted_runs requires both run ids (baseline handling "
                         "lives in generate_alerts_for_run)")
    signal_store = SignalStore(store_dir)
    pulse_store = ThemePulseStore(store_dir)
    finding_store = FindingStore(store_dir)
    dq_store = DataQualityStore(store_dir)
    alerts: List[Alert] = []
    alerts.extend(_diff_theme_pulses(
        pulse_store.query(run_id=previous_id), pulse_store.query(run_id=current_id),
        current_id, previous_id, now))
    alerts.extend(_diff_signals(
        signal_store.query(run_id=previous_id), signal_store.query(run_id=current_id),
        current_id, previous_id, now))
    alerts.extend(_diff_dilution_findings(
        finding_store.query(run_id=previous_id), finding_store.query(run_id=current_id),
        current_id, previous_id, now))
    alerts.extend(_diff_data_quality(
        dq_store.query(run_id=previous_id), dq_store.query(run_id=current_id),
        current_id, previous_id, now))
    return tuple(alerts)


def generate_alerts_for_run(store_dir: str, run_id: str, *, now: str) -> AlertGenerationResult:
    """Observe ``run_id`` against the previous persisted run and append any alerts.

    * First persisted run (no previous) -> a BASELINE note and zero alerts (never a flood).
    * No state change -> zero alerts (quiet is the honest answer).
    * Already generated for this run -> the existing alerts are returned untouched
      (append-only: re-observing a run never writes duplicates).
    """
    if not str(run_id).strip():
        raise ValueError("generate_alerts_for_run requires a non-empty run_id")
    if not str(now).strip():
        raise ValueError("generate_alerts_for_run requires an injected 'now' instant")
    store = AlertStore(store_dir)
    existing = store.query(run_id=run_id)
    previous_id = previous_persisted_run_id(store_dir, run_id)
    if existing:
        return AlertGenerationResult(
            run_id=run_id, previous_run_id=previous_id, baseline=False,
            alerts=tuple(existing),
            notes=("alerts for run {0} were already recorded ({1} alert(s)); the "
                   "append-only inbox was left untouched".format(run_id, len(existing)),))
    if not previous_id:
        return AlertGenerationResult(
            run_id=run_id, previous_run_id="", baseline=True, alerts=(),
            notes=("baseline: run {0} is the first persisted run -- nothing to compare "
                   "yet; state-change alerts begin with the next run".format(run_id),))
    alerts = diff_persisted_runs(store_dir, previous_id, run_id, now=now)
    for alert in alerts:
        store.append(alert, timestamp=now)
    if alerts:
        notes = ("{0} state change(s) observed between run {1} and run {2} -- alert(s) "
                 "appended to the inbox".format(len(alerts), previous_id, run_id),)
    else:
        notes = ("no state change between run {0} and run {1} -- no alert (quiet is the "
                 "honest answer)".format(previous_id, run_id),)
    return AlertGenerationResult(
        run_id=run_id, previous_run_id=previous_id, baseline=False,
        alerts=alerts, notes=notes)


def record_failed_pulse_alert(store_dir: str, run_id: str, *, policy_id: str,
                              message: str, now: str) -> Optional[Alert]:
    """Append ONE source_data_quality_failure alert for a failed scheduled pulse.

    A failed pulse persists no run to diff, but the failure itself is a state change worth
    a human's eyes: one alert names the policy, the run id, and the failure message.
    Idempotent per run: if this run's failure was already alerted, nothing is appended.
    """
    if not str(run_id).strip():
        raise ValueError("record_failed_pulse_alert requires a non-empty run_id")
    store = AlertStore(store_dir)
    if store.query(run_id=run_id):
        return None
    alert = _mk_alert(
        run_id, "source_data_quality_failure", "scheduled-pulse",
        "Scheduled pulse for policy '{0}' (run {1}) FAILED: {2}. Nothing was persisted "
        "for this run; the failure is recorded in the health stores, never papered "
        "over.".format(policy_id, run_id, message),
        now, refs=("dq.{0}.orchestration".format(run_id),),
        evidence=("dq.{0}.orchestration".format(run_id),))
    store.append(alert, timestamp=now)
    return alert
