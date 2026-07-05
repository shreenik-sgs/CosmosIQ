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
from typing import Any, Optional, Tuple

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
    generated_at: str = ""                  # injected timestamp (no wall-clock)
    reality_signal_refs: Tuple[str, ...] = field(default_factory=tuple)   # fused signals
    opportunity_hypothesis_ref: str = ""    # the Sphurana packet id
    investment_diligence_ref: str = ""      # the accepted engine's thesis id
    forward_scenario_state: str = ""        # closed: FORWARD_SCENARIO_STATES ("" = unset)
    trust_data_quality_state: str = ""      # closed: TRUST_DATA_QUALITY_STATES ("" = unset)
    candidate_state: str = "draft"          # closed: CANDIDATE_STATES
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
        """The required lineage pieces that are absent (empty tuple iff fully complete)."""
        missing = []
        if not self.reality_signal_refs:
            missing.append("reality_signal_refs")
        if not str(self.opportunity_hypothesis_ref or "").strip():
            missing.append("opportunity_hypothesis_ref")
        if not str(self.investment_diligence_ref or "").strip():
            missing.append("investment_diligence_ref")
        if self.trust_data_quality_state != "healthy":
            missing.append("trust_data_quality_state==healthy")
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


def assess_candidate_eligibility(
    *,
    ticker: str,
    run_id: str,
    reality_signal_refs: Tuple[str, ...] = (),
    opportunity_hypothesis_ref: str = "",
    investment_diligence_ref: str = "",
    forward_scenario_state: str = "",
    trust_data_quality_state: str = "",
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

    return CapitalCandidate(
        candidate_id=candidate_id_for(run_id, ticker),
        ticker=str(ticker or "").strip().upper(),
        run_id=str(run_id or "").strip(),
        generated_at=str(now),
        reality_signal_refs=signals,
        opportunity_hypothesis_ref=hyp,
        investment_diligence_ref=dil,
        forward_scenario_state=str(forward_scenario_state or "").strip(),
        trust_data_quality_state=dq,
        candidate_state=state,
        basis=why)


# --------------------------------------------------------------------------- #
# Construction-time guard: the contract may carry NO trade / score field.        #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(CapitalCandidate)
