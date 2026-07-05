"""Typed CapitalCandidate contract + a HARD eligibility gate (IMPLEMENTATION-019B).

Closes the one substantive pre-019-closeout gap an audit found: until now a "capital
candidate" was only a cockpit VIEW, not a typed object that CANNOT exist without full
evidence lineage. This module makes eligibility **unforgeable at the type level**.

A :class:`CapitalCandidate` is an *eligibility + lineage record* -- NEVER a recommendation,
a ranking, or a trade. It carries labels + refs only:

* there is NO numeric ``score`` / ``rank`` / ``rating`` / ``investability`` / ``sizing``
  field anywhere on it, and NO ``buy`` / ``sell`` / ``order`` / ``broker`` / ``trade`` /
  ``execution`` field -- a candidate says only "this ticker has, or has not, the full
  evidence lineage a capital decision would require", never "act";
* a candidate is INELIGIBLE unless it carries CURRENT-RUN provenance (the run that produced
  it, the fused reality signals, the Sphurana opportunity-hypothesis packet) AND diligence
  (the accepted engine's thesis output) AND the producing run's data quality is ``healthy``.
  Constructing a ``candidate_state == "eligible"`` object without that full ref set raises
  ``ValueError`` -- no candidate is ever "eligible" without the full lineage.

:func:`assess_candidate_eligibility` computes the honest ``candidate_state`` from what is
actually present -- it NEVER fabricates a ref to reach ``eligible``. Missing provenance ->
``ineligible_missing_provenance``; missing diligence -> ``ineligible_missing_diligence``; a
failed-DQ producing run -> ``ineligible_dq_failed``; a non-healthy (degraded / unstated) DQ
-> ``ineligible_stale``; a full, healthy lineage -> ``eligible``.

Deterministic (injected ``now`` + a candidate id derived deterministically from the run +
ticker), stdlib-only, Python 3.9, OFFLINE. No network / scheduler / broker on import.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from .gates import DataQualityGateRunner
from .stores import AppendOnlyStore, DataQualityStore, RunStore, SignalStore
from .validation import assert_no_trade_fields


# --------------------------------------------------------------------------- #
# Closed vocabularies                                                           #
# --------------------------------------------------------------------------- #

# The candidate state -- an eligibility verdict, never a score. ``eligible`` is only
# constructible with the full lineage (enforced in ``__post_init__``).
CANDIDATE_STATES: Tuple[str, ...] = (
    "eligible",
    "ineligible_missing_provenance",
    "ineligible_missing_diligence",
    "ineligible_dq_failed",
    "ineligible_stale",
    "draft",
)

# The four ineligible verdicts (every non-eligible, non-draft state), for callers.
INELIGIBLE_STATES: Tuple[str, ...] = tuple(
    s for s in CANDIDATE_STATES if s.startswith("ineligible_"))

# The forward-scenario sidecar's presence label (the diligence/forward side).
FORWARD_SCENARIO_STATES: Tuple[str, ...] = ("present", "absent", "insufficient")

# The producing run's data-quality status a candidate may carry (a subset of RUN_STATUSES;
# a ``blocked_by_policy`` run never yields a candidate at all). ``healthy`` is the only DQ
# state under which a candidate can be ``eligible``.
TRUST_DATA_QUALITY_STATES: Tuple[str, ...] = ("healthy", "degraded", "failed")


# --------------------------------------------------------------------------- #
# The typed contract                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CapitalCandidate:
    """A frozen eligibility + lineage record for a ticker under one current run.

    ``eligible`` is UNFORGEABLE: a candidate can only be ``eligible`` when it carries
    non-empty ``reality_signal_refs``, an ``opportunity_hypothesis_ref``, an
    ``investment_diligence_ref``, AND ``trust_data_quality_state == "healthy"``. Constructing
    an ``eligible`` candidate that is missing any of those raises ``ValueError`` -- eligibility
    cannot exist without the full evidence lineage. There is NO numeric / score / rank / trade
    field anywhere; this is an eligibility record, never a recommendation or a ranking.
    """

    candidate_id: str = ""                  # REQUIRED, deterministic (run + ticker derived)
    ticker: str = ""                        # REQUIRED
    run_id: str = ""                        # REQUIRED -- the current run that produced it
    mode: str = "pulse"                     # REQUIRED for eligible -- the producing run's mode
    generated_at: str = ""                  # injected timestamp (no wall-clock)
    reality_signal_refs: Tuple[str, ...] = field(default_factory=tuple)   # fused signals
    opportunity_hypothesis_ref: str = ""    # the Sphurana packet id
    investment_diligence_ref: str = ""      # the accepted engine's thesis id
    forward_scenario_state: str = ""        # closed: FORWARD_SCENARIO_STATES ("" = unset)
    trust_data_quality_state: str = ""      # closed: TRUST_DATA_QUALITY_STATES ("" = unset)
    candidate_state: str = "draft"          # closed: CANDIDATE_STATES
    source_provenance: Tuple[str, ...] = field(default_factory=tuple)     # source refs / summary
    basis: str = ""                         # plain-English lineage citing the refs

    def __post_init__(self) -> None:
        for name in ("candidate_id", "ticker", "run_id"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "CapitalCandidate.{0} is required and must be non-empty".format(name))
        if self.candidate_state not in CANDIDATE_STATES:
            raise ValueError(
                "CapitalCandidate.candidate_state {0!r} invalid (allowed: {1})".format(
                    self.candidate_state, list(CANDIDATE_STATES)))
        if self.forward_scenario_state and self.forward_scenario_state not in \
                FORWARD_SCENARIO_STATES:
            raise ValueError(
                "CapitalCandidate.forward_scenario_state {0!r} invalid (allowed: {1})".format(
                    self.forward_scenario_state, list(FORWARD_SCENARIO_STATES)))
        if self.trust_data_quality_state and self.trust_data_quality_state not in \
                TRUST_DATA_QUALITY_STATES:
            raise ValueError(
                "CapitalCandidate.trust_data_quality_state {0!r} invalid (allowed: {1})".format(
                    self.trust_data_quality_state, list(TRUST_DATA_QUALITY_STATES)))

        # --- the unforgeable-eligibility invariant --------------------------- #
        # An ``eligible`` candidate is IMPOSSIBLE without the full lineage: the fused signals,
        # the opportunity-hypothesis packet, the diligence thesis, AND a healthy producing run.
        if self.candidate_state == "eligible":
            missing = self.missing_lineage()
            if missing:
                raise ValueError(
                    "CapitalCandidate cannot be 'eligible' without full lineage -- missing {0}. "
                    "Eligibility requires current-run provenance (reality_signal_refs + "
                    "opportunity_hypothesis_ref) AND diligence (investment_diligence_ref) AND a "
                    "healthy producing run (trust_data_quality_state == 'healthy').".format(
                        ", ".join(missing)))

    # -- lineage introspection ------------------------------------------------ #
    def missing_lineage(self) -> Tuple[str, ...]:
        """The required lineage pieces that are absent (empty tuple iff fully complete).

        Eligibility requires -- on top of the 019B ref set + a healthy producing run -- a
        non-empty ``run_id`` and a non-empty ``mode`` (the active run that produced it): a
        published-eligible candidate always carries WHICH run + mode generated it.
        """
        missing = []
        if not self.reality_signal_refs:
            missing.append("reality_signal_refs")
        if not str(self.opportunity_hypothesis_ref or "").strip():
            missing.append("opportunity_hypothesis_ref")
        if not str(self.investment_diligence_ref or "").strip():
            missing.append("investment_diligence_ref")
        if self.trust_data_quality_state != "healthy":
            missing.append("trust_data_quality_state==healthy")
        if not str(self.run_id or "").strip():
            missing.append("run_id")
        if not str(self.mode or "").strip():
            missing.append("mode")
        return tuple(missing)

    @property
    def is_eligible(self) -> bool:
        return self.candidate_state == "eligible"


# The candidate contract (for registry / test introspection).
CAPITAL_CANDIDATE_MODELS = (CapitalCandidate,)


# --------------------------------------------------------------------------- #
# Deterministic id + eligibility assessment                                     #
# --------------------------------------------------------------------------- #
def candidate_id_for(run_id: str, ticker: str) -> str:
    """A deterministic candidate id from the run + ticker (no wall-clock, order-stable)."""
    return "cc:{0}:{1}".format(str(run_id or "").strip(), str(ticker or "").strip().upper())


def _provenance_summary(run_id: str, mode: str, signals: Tuple[str, ...], hyp: str,
                        dil: str, forward_state: str, dq: str) -> Tuple[str, ...]:
    """A deterministic, order-stable source-provenance summary (refs + labels, never a value).

    Assembled from the current run's identity + the lineage refs actually present, so a
    published candidate always carries WHERE its evidence came from -- never a fabricated ref.
    """
    parts = ["run:{0}".format(run_id), "mode:{0}".format(mode)]
    parts += ["signal:{0}".format(s) for s in signals]
    if hyp:
        parts.append("hypothesis:{0}".format(hyp))
    if dil:
        parts.append("diligence:{0}".format(dil))
    parts.append("forward:{0}".format(forward_state or "absent"))
    parts.append("dq:{0}".format(dq or "unstated"))
    return tuple(parts)


def assess_candidate_eligibility(
    *,
    ticker: str,
    run_id: str,
    reality_signal_refs: Tuple[str, ...] = (),
    opportunity_hypothesis_ref: str = "",
    investment_diligence_ref: str = "",
    forward_scenario_state: str = "",
    trust_data_quality_state: str = "",
    mode: str = "pulse",
    source_provenance: Tuple[str, ...] = (),
    now: str,
) -> CapitalCandidate:
    """Build a :class:`CapitalCandidate` whose ``candidate_state`` reflects what is PRESENT.

    Computes the honest state from the lineage actually supplied -- it NEVER fabricates a ref
    to reach ``eligible``:

    * missing fused signals OR the opportunity-hypothesis packet -> ``ineligible_missing_provenance``;
    * present provenance but no diligence thesis ref -> ``ineligible_missing_diligence``;
    * a producing run whose DQ is ``failed`` -> ``ineligible_dq_failed``;
    * a producing run whose DQ is not ``healthy`` (degraded / unstated) -> ``ineligible_stale``;
    * full provenance + diligence + a ``healthy`` producing run -> ``eligible``.

    ``now`` is injected (the timestamp is never read from a clock); the candidate id is derived
    deterministically from ``run_id`` + ``ticker``. Returns the frozen record.
    """
    signals = tuple(r for r in (reality_signal_refs or ()) if str(r or "").strip())
    hyp = str(opportunity_hypothesis_ref or "").strip()
    dil = str(investment_diligence_ref or "").strip()
    dq = str(trust_data_quality_state or "").strip()
    run = str(run_id or "").strip()
    run_mode = str(mode or "").strip()
    fwd = str(forward_scenario_state or "").strip()

    if not signals or not hyp:
        state = "ineligible_missing_provenance"
        why = ("no current-run provenance: {0} -- a candidate without the fused reality "
               "signals AND the opportunity-hypothesis packet can never be eligible".format(
                   "; ".join(filter(None, [
                       "" if signals else "reality_signal_refs absent",
                       "" if hyp else "opportunity_hypothesis_ref absent"]))))
    elif not dil:
        state = "ineligible_missing_diligence"
        why = ("provenance present (signals {0}, hypothesis {1}) but NO diligence reference -- "
               "the accepted engine's thesis output is required; ineligible until diligence is "
               "attached".format(len(signals), hyp))
    elif dq == "failed":
        state = "ineligible_dq_failed"
        why = ("full lineage present but the producing run's data quality is FAILED -- a "
               "candidate is never eligible off a failed-DQ run")
    elif dq != "healthy":
        state = "ineligible_stale"
        why = ("full lineage present but the producing run's data quality is {0!r} (not "
               "healthy) -- ineligible until a healthy current run confirms it".format(
                   dq or "unstated"))
    else:
        state = "eligible"
        why = ("eligible: current-run provenance (run {0}, signals {1}, hypothesis {2}) AND "
               "diligence (thesis {3}) AND a healthy producing run -- full evidence lineage "
               "present".format(run_id, len(signals), hyp, dil))

    provenance = tuple(str(p) for p in (source_provenance or ()) if str(p or "").strip()) \
        or _provenance_summary(run, run_mode, signals, hyp, dil, fwd, dq)

    return CapitalCandidate(
        candidate_id=candidate_id_for(run_id, ticker),
        ticker=str(ticker or "").strip().upper(),
        run_id=run,
        mode=run_mode,
        generated_at=str(now),
        reality_signal_refs=signals,
        opportunity_hypothesis_ref=hyp,
        investment_diligence_ref=dil,
        forward_scenario_state=fwd,
        trust_data_quality_state=dq,
        candidate_state=state,
        source_provenance=provenance,
        basis=why)


# --------------------------------------------------------------------------- #
# APPEND-ONLY publication store (IMPLEMENTATION-020A)                            #
# --------------------------------------------------------------------------- #
class CapitalCandidateStore(AppendOnlyStore):
    """The append-only publication log of :class:`CapitalCandidate` records.

    Composes the 013B :class:`~reality_mesh.stores.AppendOnlyStore`, inheriting every hard
    guarantee: no update / delete, the replay envelope, the credential-key + trade/score-key
    refusal, and deterministic ``sort_keys`` JSONL. PUBLICATION IS APPEND-ONLY: a published
    candidate is a NEW store line; a BLOCKED candidate is persisted too (with its exact reason
    -- nothing is hidden); re-publishing an unchanged candidate is IDEMPOTENT by its
    content-derived id -- an identical record is never written twice, and the prior line is
    byte-unchanged forever.
    """

    filename = "capital_candidate_store.jsonl"
    record_cls = CapitalCandidate
    id_field = "candidate_id"
    timestamp_field = "generated_at"
    ticker_fields = ("ticker",)

    def publish(self, candidate: CapitalCandidate) -> str:
        """Append ONE candidate append-only; idempotent when byte-identical already present.

        Returns the candidate's stable, content-derived id. If an EQUAL record (every field,
        incl. its state, basis, provenance and generated_at) is already persisted, nothing is
        written and the prior line stays byte-unchanged -- re-publish is a no-op.
        """
        if candidate in self.read_all():
            return candidate.candidate_id
        return self.append(candidate)


def _latest_by_id(candidates: Tuple[CapitalCandidate, ...]) -> Tuple[CapitalCandidate, ...]:
    """Distinct candidates keyed on their content-derived id, LATEST (superseding) line wins."""
    by_id: Dict[str, CapitalCandidate] = {}
    order = []
    for cand in candidates:
        if cand.candidate_id not in by_id:
            order.append(cand.candidate_id)
        by_id[cand.candidate_id] = cand
    return tuple(by_id[cid] for cid in order)


def published_candidates(store_dir: str, run_id: Optional[str] = None
                         ) -> Tuple[CapitalCandidate, ...]:
    """Every published candidate (latest line per id), optionally scoped to one ``run_id``."""
    store = CapitalCandidateStore(store_dir)
    records = store.query(run_id=run_id) if run_id else store.read_all()
    return _latest_by_id(tuple(records))


def eligible_candidates(store_dir: str, run_id: Optional[str] = None
                        ) -> Tuple[CapitalCandidate, ...]:
    """The published candidates whose current state is ``eligible``."""
    return tuple(c for c in published_candidates(store_dir, run_id) if c.is_eligible)


def blocked_candidates(store_dir: str, run_id: Optional[str] = None
                       ) -> Tuple[CapitalCandidate, ...]:
    """The published candidates whose current state is one of the ``ineligible_*`` verdicts."""
    return tuple(c for c in published_candidates(store_dir, run_id)
                 if c.candidate_state in INELIGIBLE_STATES)


def _run_trust_dq_state(store_dir: str, run: Any) -> str:
    """The producing run's Trust / Data-Quality state, mapped onto TRUST_DATA_QUALITY_STATES.

    Read from the run's persisted gate-overall DQ record (falling back to the run's own
    ``data_quality_status``): ``healthy`` / ``degraded`` / ``failed`` pass through; a
    ``blocked_by_policy`` run is treated as ``failed`` (its candidate can never be eligible);
    anything else is an honestly-unstated ("") DQ.
    """
    overall = ""
    for record in DataQualityStore(store_dir).query(run_id=run.run_id):
        if record.category == "gate_overall":
            overall = record.status
    raw = overall or str(getattr(run, "data_quality_status", "") or "")
    if raw in TRUST_DATA_QUALITY_STATES:
        return raw
    if raw == "blocked_by_policy":
        return "failed"
    return ""


def publish_candidates_for_run(
    store_dir: str,
    run_id: str,
    *,
    tickers: Optional[Tuple[str, ...]] = None,
    now: str,
    mode: str = "pulse",
    diligence_by_ticker: Optional[Dict[str, Any]] = None,
) -> Tuple[CapitalCandidate, ...]:
    """Publish (assess -> construct -> persist -> gate -> state) every ticker in a run's scope.

    THE OFFICIAL PUBLISH PATH. For each ticker in scope (``tickers`` when given, else the run's
    persisted watchlist):

    1. gather that ticker's fused ``RealitySignal`` refs from the run (:class:`SignalStore`),
       the operator-supplied ``OpportunityHypothesis`` + ``InvestmentDiligence`` refs (+ a
       forward-scenario status) from ``diligence_by_ticker``, and the run's Trust / Data-Quality
       state from its persisted DQ records;
    2. :func:`assess_candidate_eligibility` -> the honest ``candidate_state`` (it NEVER fabricates
       a ref to reach eligible: a missing forward scenario is a rendered GAP -- ``absent`` -- not
       a block, so a candidate with the other refs stays eligible);
    3. PERSIST the record append-only (content-derived id, idempotent) -- an eligible candidate
       lands ONLY with full provenance; a candidate missing any required ref lands as
       ``ineligible_*`` WITH the exact reason (nothing is hidden);
    4. run :meth:`DataQualityGateRunner.run` over the published set (reusing the 019B gate) as a
       verification pass -- a forged-eligible candidate would roll the run to ``blocked_by_policy``.

    ``diligence_by_ticker`` maps a ticker (upper- or as-typed) to a dict carrying any of
    ``opportunity_hypothesis_ref`` / ``investment_diligence_ref`` / ``forward_scenario_state``.
    Deterministic (injected ``now`` + content-derived ids); offline. Returns the published set.
    """
    if not str(run_id or "").strip():
        raise ValueError("publish_candidates_for_run requires a non-empty run_id")
    runs = RunStore(store_dir).query(run_id=run_id)
    if not runs:
        raise ValueError(
            "no persisted run with run_id {0!r} -- a candidate needs a CURRENT run that "
            "produced it".format(run_id))
    run = runs[-1]
    scope = tuple(tickers) if tickers else tuple(getattr(run, "watchlist", ()) or ())
    dq_state = _run_trust_dq_state(store_dir, run)
    diligence = dict(diligence_by_ticker or {})
    signal_store = SignalStore(store_dir)
    store = CapitalCandidateStore(store_dir)

    published: list = []
    for ticker in scope:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            continue
        signal_ids = tuple(sorted(
            s.signal_id for s in signal_store.query(run_id=run.run_id, ticker=symbol)))
        dil_spec = dict(diligence.get(symbol) or diligence.get(str(ticker)) or {})
        hyp_ref = str(dil_spec.get("opportunity_hypothesis_ref", "") or "")
        dil_ref = str(dil_spec.get("investment_diligence_ref", "") or "")
        forward_state = str(dil_spec.get("forward_scenario_state", "") or "absent")
        candidate = assess_candidate_eligibility(
            ticker=symbol, run_id=run.run_id,
            reality_signal_refs=signal_ids,
            opportunity_hypothesis_ref=hyp_ref,
            investment_diligence_ref=dil_ref,
            forward_scenario_state=forward_state,
            trust_data_quality_state=dq_state,
            mode=mode, now=now)
        store.publish(candidate)
        published.append(candidate)

    # Verification pass: reuse the 019B gate. A properly-eligible set passes; a forged one would
    # roll to blocked_by_policy (the construction invariant already makes that unreachable here).
    DataQualityGateRunner().run(candidates=tuple(published))
    return tuple(published)


# --------------------------------------------------------------------------- #
# Construction-time guard: the contract may carry NO trade / score field.        #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(CapitalCandidate)
