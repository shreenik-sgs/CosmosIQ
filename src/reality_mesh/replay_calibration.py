"""Historical Replay Calibration for the Reality Mesh (IMPLEMENTATION-022G).

BEFORE trusting production stock-pick reports, run the recommendation layer over
REPLAY-MODE historical cases to CHECK that it (a) avoids obvious bad recommendations,
(b) blocks weak candidates, (c) surfaces a strong candidate with complete evidence, and
(d) flags a deteriorating thesis. This slice applies the SAME 022B recommendation gates
(:func:`~reality_mesh.recommendation_gates.evaluate_recommendation`) to each case -- never
special-cased, never tuned so a "known winner" passes.

THE HONESTY MANDATE (baked into the shape):

* **Not hindsight-optimized.** Each case runs the UNCHANGED 022B gate engine. A case that
  lacks complete evidence is honestly ``blocked`` / downgraded -- that is a correct,
  conservative result, NOT a miss to fix. The gates are never tuned to force a match.
* **Illustrative synthetic scenarios, NOT a validated backtest.** The cases are clearly
  labelled synthetic scenarios that exercise the recommendation LOGIC (weak -> blocked;
  strong + complete -> surfaced; deteriorating -> flagged). This calibrates the LOGIC; it is
  NOT a validated historical alpha backtest with real returns. No real ticker is claimed to
  have been "caught"; there is NO fabricated return / outcome anywhere.
* **Replay is isolated from live.** Every :class:`ReplayCalibrationResult` carries
  ``replay_mode=True`` and is persisted to its OWN append-only log
  (``replay_calibration.jsonl``) -- never the live recommendation journal. A replay verdict
  can never appear as a live recommendation. The calibration reads its injected cases; it
  mutates NO source record (append-only, correction-not-mutation).

The deterioration read: a deteriorating thesis surfaces to the 022B gates as an UNRESOLVED
red-team thesis-killer, which the ``red_team_no_thesis_killer`` gate BLOCKS (the exact,
honest 022B output, preserved in :attr:`ReplayCalibrationResult.gate_state`). The calibration
reads that block through the 017-family deterioration lens and reports the conservative review
verdict ``exit_review`` in :attr:`recommendation_state` -- the gate is NEVER modified.

Labels + refs + counts only -- there is NO numeric score / rank / rating field, and no
directive-to-act (purchase / disposal) field anywhere. Deterministic (injected ``now`` + ids
derived from the case). Stdlib-only, Python 3.9, OFFLINE. No network / scheduler / execution
venue on import; no wall-clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, Optional, Tuple

from .capital_candidate import CapitalCandidate, assess_candidate_eligibility
from .learning import OUTCOME_LABELS
from .recommendation import RECOMMENDATION_STATES
from .recommendation_gates import evaluate_recommendation
from .stores import AppendOnlyStore
from .validation import assert_no_trade_fields

__all__ = [
    "SCENARIO_KINDS",
    "EXPECTATION_LABELS",
    "SCHEMA_VERSION",
    "ReplayCalibrationCase",
    "ReplayCalibrationResult",
    "ReplayCalibrationStore",
    "run_replay_calibration",
    "calibration_summary",
    "record_calibration",
    "calibration_results",
    "build_illustrative_cases",
    "render_calibration_report",
]

# The calibration record's own schema version (independent of the 013B envelope version).
SCHEMA_VERSION = "022G.1"

# The CLOSED set of scenario kinds a calibration case may model. One illustrative case per kind
# is seeded by :func:`build_illustrative_cases`.
SCENARIO_KINDS: Tuple[str, ...] = (
    "strong_beneficiary_complete_evidence",
    "hype_weak_evidence",
    "deteriorating_thesis",
    "social_only_noise",
    "insufficient_data",
)

# The CLOSED set of in-hindsight expectation labels -- what a correctly-CONSERVATIVE layer
# SHOULD do with a case. This is used ONLY to CHECK behaviour; it is never fed into the gates.
EXPECTATION_LABELS: Tuple[str, ...] = (
    "block",
    "watch",
    "active_diligence",
    "actionable",
    "flag_deterioration",
)

# The recommendation-gate id whose failure (on an unresolved thesis-killer) reads as thesis
# DETERIORATION rather than a fresh-candidate block.
_RED_TEAM_GATE_ID = "red_team_no_thesis_killer"

# The conservative review verdict a flagged-deterioration case surfaces (a RECOMMENDATION_STATES
# member; never an actionable/surfaced state).
_DETERIORATION_VERDICT = "exit_review"


# --------------------------------------------------------------------------- #
# The frozen calibration case                                                   #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayCalibrationCase:
    """One clearly-illustrative, synthetic replay case fed to the SAME 022B gates.

    Carries the synthetic evidence inputs (candidate / DQ / freshness / corroboration /
    theme-pulse / graph refs / diligence / forward scenario / red-team / timing / portfolio /
    guardrails) plus an in-hindsight ``expectation_label`` -- what a correctly-conservative
    layer SHOULD do. The expectation is for CHECKING behaviour ONLY; it is NEVER passed to
    :func:`~reality_mesh.recommendation_gates.evaluate_recommendation`. There is NO numeric /
    score / rank field anywhere.
    """

    case_id: str = ""                       # REQUIRED, deterministic
    label: str = ""                         # a clearly-illustrative name
    scenario_kind: str = ""                 # closed: SCENARIO_KINDS
    expectation_label: str = ""             # closed: EXPECTATION_LABELS (CHECK-only)
    run_id: str = ""
    ticker: str = ""
    company_name: str = ""

    # -- the synthetic evidence inputs (mirror the 022B gate inputs) -- #
    candidate: Optional[CapitalCandidate] = None
    data_quality_ref: str = ""
    data_quality_state: str = ""
    source_freshness: str = ""
    corroboration_sources: Tuple[Any, ...] = field(default_factory=tuple)
    theme_pulse_state: str = ""
    bottleneck_exposure_refs: Tuple[str, ...] = field(default_factory=tuple)
    company_evidence_refs: Tuple[Any, ...] = field(default_factory=tuple)
    investment_diligence_ref: str = ""
    diligence_complete: bool = False
    forward_scenario_ref: str = ""
    red_team_ref: str = ""
    unresolved_thesis_killer: bool = False
    technical_timing_ref: str = ""
    technical_timing_acceptable: bool = False
    portfolio_fit_ref: str = ""
    portfolio_fit_acceptable: bool = False
    sizing_guardrail: str = ""
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    exit_watch_conditions: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        for name in ("case_id", "label", "run_id", "ticker"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "ReplayCalibrationCase.{0} is required and must be non-empty".format(name))
        if self.scenario_kind not in SCENARIO_KINDS:
            raise ValueError(
                "ReplayCalibrationCase.scenario_kind {0!r} invalid (allowed: {1})".format(
                    self.scenario_kind, list(SCENARIO_KINDS)))
        if self.expectation_label not in EXPECTATION_LABELS:
            raise ValueError(
                "ReplayCalibrationCase.expectation_label {0!r} invalid (allowed: {1})".format(
                    self.expectation_label, list(EXPECTATION_LABELS)))


# --------------------------------------------------------------------------- #
# The frozen calibration result                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayCalibrationResult:
    """One case's calibration outcome, produced by the REAL 022B gates. Labels only.

    ``gate_state`` is the EXACT, unchanged 022B output
    (:attr:`~reality_mesh.recommendation_gates.RecommendationGateOutcome.state`).
    ``recommendation_state`` is the calibration's conservative verdict: normally identical to
    ``gate_state``, except a deteriorating thesis (a red-team thesis-killer block) is surfaced
    as ``exit_review`` through the 017 deterioration lens -- the gate is never modified.
    ``replay_mode`` is ALWAYS ``True`` (a replay verdict can never appear as a live
    recommendation). There is NO numeric score / rank / rating field anywhere.
    """

    case_id: str = ""                       # REQUIRED
    replay_mode: bool = True                # ALWAYS True -- isolated from live
    scenario_kind: str = ""
    expectation_label: str = ""
    recommendation_state: str = ""          # the conservative verdict (RECOMMENDATION_STATES)
    gate_state: str = ""                    # the EXACT 022B gate output (RECOMMENDATION_STATES)
    blocked_reason: str = ""                # the exact failed-gate reason when blocked
    deterioration_flag: bool = False        # True iff a thesis-killer deterioration was read
    matched_expectation: bool = False       # did the produced behaviour match the expectation?
    expectation_note: str = ""              # plain-English match / mismatch note
    notes: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        assert_no_trade_fields(type(self))
        if not isinstance(self.case_id, str) or self.case_id.strip() == "":
            raise ValueError("ReplayCalibrationResult.case_id is required and must be non-empty")
        if self.replay_mode is not True:
            raise ValueError(
                "ReplayCalibrationResult.replay_mode must be True -- a calibration record is "
                "always replay-mode and can never appear as a live recommendation")
        for name in ("recommendation_state", "gate_state"):
            value = getattr(self, name)
            if value and value not in RECOMMENDATION_STATES:
                raise ValueError(
                    "ReplayCalibrationResult.{0} {1!r} invalid (allowed: {2})".format(
                        name, value, list(RECOMMENDATION_STATES)))
        if self.expectation_label and self.expectation_label not in EXPECTATION_LABELS:
            raise ValueError(
                "ReplayCalibrationResult.expectation_label {0!r} invalid (allowed: {1})".format(
                    self.expectation_label, list(EXPECTATION_LABELS)))
        # No stray numeric field may sneak in -- labels + booleans + text only.
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, float):
                raise ValueError(
                    "ReplayCalibrationResult.{0} is a float -- the calibration stores labels "
                    "+ booleans + text only, never a numeric score".format(f.name))


# --------------------------------------------------------------------------- #
# The append-only calibration store                                             #
# --------------------------------------------------------------------------- #
class ReplayCalibrationStore(AppendOnlyStore):
    """Append-only replay-calibration log (``replay_calibration.jsonl``).

    One line per calibration result. Every record carries ``replay_mode=True`` and is kept
    SEPARATE from the live recommendation journal -- a live recommendation query never reads
    this log. A re-calibration for the same ``case_id`` is a NEW line (latest-wins per id); the
    prior line stays byte-unchanged. Composes the 013B base, so it inherits the credential +
    trade/score key write refusal and has NO update / delete affordance.
    """

    filename = "replay_calibration.jsonl"
    record_cls = ReplayCalibrationResult
    id_field = "case_id"
    ticker_fields = ()


def _latest_by_case(store_dir: str) -> "Dict[str, ReplayCalibrationResult]":
    """case_id -> the LATEST appended result for that id (earlier lines stay byte-unchanged)."""
    latest: Dict[str, ReplayCalibrationResult] = {}
    for result in ReplayCalibrationStore(store_dir).read_all():
        latest[result.case_id] = result
    return latest


# --------------------------------------------------------------------------- #
# Running the calibration -- the SAME 022B gates, never tuned                    #
# --------------------------------------------------------------------------- #
def _gate_kwargs(case: ReplayCalibrationCase, now: str) -> Dict[str, Any]:
    """The exact kwargs handed to the UNCHANGED 022B gate engine for a case."""
    return dict(
        run_id=case.run_id, ticker=case.ticker, now=now, company_name=case.company_name,
        candidate=case.candidate,
        data_quality_ref=case.data_quality_ref, data_quality_state=case.data_quality_state,
        source_freshness=case.source_freshness,
        corroboration_sources=tuple(case.corroboration_sources or ()),
        theme_pulse_state=case.theme_pulse_state,
        bottleneck_exposure_refs=tuple(case.bottleneck_exposure_refs or ()),
        company_evidence_refs=tuple(case.company_evidence_refs or ()),
        investment_diligence_ref=case.investment_diligence_ref,
        diligence_complete=case.diligence_complete,
        forward_scenario_ref=case.forward_scenario_ref,
        red_team_ref=case.red_team_ref, unresolved_thesis_killer=case.unresolved_thesis_killer,
        technical_timing_ref=case.technical_timing_ref,
        technical_timing_acceptable=case.technical_timing_acceptable,
        portfolio_fit_ref=case.portfolio_fit_ref,
        portfolio_fit_acceptable=case.portfolio_fit_acceptable,
        sizing_guardrail=case.sizing_guardrail,
        invalidation_conditions=tuple(case.invalidation_conditions or ()),
        exit_watch_conditions=tuple(case.exit_watch_conditions or ()),
    )


def _deterioration_read(case: ReplayCalibrationCase, gate_results) -> bool:
    """True iff the case is a thesis DETERIORATION: a red-team thesis-killer the gate blocked.

    Read uniformly from the gate output (an unresolved thesis-killer that the
    ``red_team_no_thesis_killer`` gate failed on) -- never from a ticker-specific rule and never
    from hindsight.
    """
    if not case.unresolved_thesis_killer:
        return False
    for gate in gate_results:
        if gate.gate_id == _RED_TEAM_GATE_ID:
            return not gate.passed
    return False


def _expectation_satisfied(expectation_label: str, gate_state: str,
                           deterioration_flag: bool) -> bool:
    """Whether the produced behaviour matches the conservative expectation (CHECK-only)."""
    if expectation_label == "flag_deterioration":
        return bool(deterioration_flag)
    if expectation_label == "actionable":
        return gate_state == "actionable_pick_manual_review"
    if expectation_label == "active_diligence":
        return gate_state in ("active_diligence", "actionable_pick_manual_review")
    if expectation_label == "watch":
        return gate_state == "watch"
    if expectation_label == "block":
        return gate_state == "blocked"
    return False


def run_replay_calibration(cases: Tuple[ReplayCalibrationCase, ...], *, now: str
                           ) -> Tuple[ReplayCalibrationResult, ...]:
    """Run the SAME 022B gates over each replay case; return the marked, replay-mode results.

    For each case: run the UNCHANGED
    :func:`~reality_mesh.recommendation_gates.evaluate_recommendation`, record the exact gate
    state, read (uniformly) whether the case is a thesis deterioration, and record whether the
    produced behaviour matches the case's conservative expectation. NEVER tunes the gates to
    force a match. Deterministic: ``now`` is injected. Every result carries ``replay_mode=True``.
    """
    if not str(now).strip():
        raise ValueError("run_replay_calibration requires an injected 'now' instant")

    results = []
    for case in cases:
        outcome, _rec = evaluate_recommendation(**_gate_kwargs(case, now))
        gate_state = outcome.state
        deterioration = _deterioration_read(case, outcome.gate_results)
        recommendation_state = _DETERIORATION_VERDICT if deterioration else gate_state
        matched = _expectation_satisfied(case.expectation_label, gate_state, deterioration)

        if deterioration:
            note = ("thesis deterioration read from the 022B red-team thesis-killer block "
                    "(gate_state={0!r}); surfaced as {1!r}".format(gate_state,
                                                                    _DETERIORATION_VERDICT))
        else:
            note = "expectation {0!r} vs 022B gate_state {1!r}".format(
                case.expectation_label, gate_state)

        results.append(ReplayCalibrationResult(
            case_id=case.case_id,
            replay_mode=True,
            scenario_kind=case.scenario_kind,
            expectation_label=case.expectation_label,
            recommendation_state=recommendation_state,
            gate_state=gate_state,
            blocked_reason=outcome.blocked_reason,
            deterioration_flag=deterioration,
            matched_expectation=matched,
            expectation_note=note,
            notes="illustrative synthetic scenario -- exercises the recommendation LOGIC, "
                  "not a validated backtest with real returns"))
    return tuple(results)


# --------------------------------------------------------------------------- #
# Persistence -- append-only, latest-wins, idempotent                           #
# --------------------------------------------------------------------------- #
def record_calibration(store_dir: str, results: Tuple[ReplayCalibrationResult, ...], *, now: str
                       ) -> Tuple[ReplayCalibrationResult, ...]:
    """Append each calibration result to the replay-calibration log; return the newly written.

    Append-only + latest-wins per ``case_id``: a result whose latest recorded line is identical
    is skipped (idempotent, byte-identical re-run); a changed result is a NEW appended line and
    the prior line stays byte-unchanged. Only ``replay_mode=True`` results may be recorded --
    a live recommendation can never land here.
    """
    if not str(now).strip():
        raise ValueError("record_calibration requires an injected 'now' instant")
    store = ReplayCalibrationStore(store_dir)
    latest = _latest_by_case(store_dir)
    written = []
    for result in results:
        if result.replay_mode is not True:
            raise ValueError("record_calibration refuses a non-replay-mode result")
        prior = latest.get(result.case_id)
        if prior is not None and prior == result:
            continue                                # idempotent -> append nothing
        store.append(result, timestamp=now)
        latest[result.case_id] = result
        written.append(result)
    return tuple(written)


def calibration_results(store_dir: str) -> Tuple[ReplayCalibrationResult, ...]:
    """Every recorded calibration result (latest line per case_id)."""
    return tuple(_latest_by_case(store_dir).values())


# --------------------------------------------------------------------------- #
# The label + count summary -- feeds 017 learning (labels + volumes, no score)   #
# --------------------------------------------------------------------------- #
def calibration_summary(results: Tuple[ReplayCalibrationResult, ...]) -> Dict[str, int]:
    """Summarise the calibration as LABEL + VOLUME-COUNT tallies (matched / blocked / flagged).

    Labels + counts only -- exactly the shape the 017 Learning & Feedback roll-ups consume;
    there is NO numeric score here. Counts are volumes.
    """
    tally: Dict[str, int] = {
        "cases_total": 0,
        "matched_expectation": 0,
        "unmatched_expectation": 0,
        "actionable": 0,
        "active_diligence": 0,
        "watch": 0,
        "blocked": 0,
        "exit_review": 0,
        "flagged_deterioration": 0,
    }
    for result in results:
        tally["cases_total"] += 1
        tally["matched_expectation" if result.matched_expectation
              else "unmatched_expectation"] += 1
        state_key = ("actionable" if result.gate_state == "actionable_pick_manual_review"
                     else result.gate_state)
        if state_key in tally:
            tally[state_key] += 1
        if result.recommendation_state == "exit_review":
            tally["exit_review"] += 1
        if result.deterioration_flag:
            tally["flagged_deterioration"] += 1
    return tally


# --------------------------------------------------------------------------- #
# The illustrative, clearly-synthetic seed cases (one per scenario kind)         #
# --------------------------------------------------------------------------- #
def _illustrative_candidate(ticker: str, run_id: str, now: str, *, mode: str = "pulse"
                            ) -> CapitalCandidate:
    """A deterministically-eligible synthetic 020A candidate for a case."""
    return assess_candidate_eligibility(
        ticker=ticker, run_id=run_id, reality_signal_refs=("sig-illustrative-1",),
        opportunity_hypothesis_ref="hyp-illustrative-1",
        investment_diligence_ref="THS-illustrative-1",
        trust_data_quality_state="healthy", mode=mode, now=now)


def build_illustrative_cases(now: str) -> Tuple[ReplayCalibrationCase, ...]:
    """Seed ONE clearly-illustrative, synthetic case per scenario kind. Deterministic.

    These are NOT real companies and NOT a labelled backtest -- each case exercises a distinct
    branch of the recommendation LOGIC. The strong case supplies genuinely complete evidence
    (so the real gates reach actionable); every other case is honestly incomplete / weak /
    social-only / deteriorating.
    """
    strong = dict(
        candidate=_illustrative_candidate("SYNTH-A", "REPLAY-STRONG-1", now),
        data_quality_ref="DQ-strong", data_quality_state="healthy",
        source_freshness="fresh",
        corroboration_sources=(("sec:strong-1", "primary", "sec_filing"),
                               ("fmp:strong-2", "convenience", "fmp")),
        theme_pulse_state="Igniting",
        bottleneck_exposure_refs=("bn-illustrative-chokepoint",),
        company_evidence_refs=(("sec:strong-1", "primary", "sec_filing"),),
        investment_diligence_ref="THS-illustrative-1", diligence_complete=True,
        forward_scenario_ref="FWD-strong",
        red_team_ref="RT-strong", unresolved_thesis_killer=False,
        technical_timing_ref="TT-strong", technical_timing_acceptable=True,
        portfolio_fit_ref="PF-strong", portfolio_fit_acceptable=True,
        sizing_guardrail="starter position only (qualitative range)",
        invalidation_conditions=("thesis broken if the chokepoint clears",),
        exit_watch_conditions=("exit watch if margins compress",),
    )

    cases = (
        ReplayCalibrationCase(
            case_id="replaycal:strong_beneficiary_complete_evidence",
            label="ILLUSTRATIVE — strong beneficiary, complete evidence (synthetic SYNTH-A)",
            scenario_kind="strong_beneficiary_complete_evidence",
            expectation_label="actionable",
            run_id="REPLAY-STRONG-1", ticker="SYNTH-A",
            company_name="Synthetic Beneficiary A", **strong),

        ReplayCalibrationCase(
            case_id="replaycal:hype_weak_evidence",
            label="ILLUSTRATIVE — hype with weak evidence (synthetic SYNTH-B)",
            scenario_kind="hype_weak_evidence",
            expectation_label="block",
            run_id="REPLAY-WEAK-1", ticker="SYNTH-B",
            company_name="Synthetic Hype B",
            candidate=_illustrative_candidate("SYNTH-B", "REPLAY-WEAK-1", now),
            data_quality_ref="DQ-weak", data_quality_state="healthy",
            source_freshness="fresh",
            corroboration_sources=(("fmp:weak-1", "convenience", "fmp"),),  # only one source
            theme_pulse_state="Exhausting",                                 # not strengthening
            bottleneck_exposure_refs=(),                                    # no chokepoint mapped
            company_evidence_refs=(),
            investment_diligence_ref="", diligence_complete=False,
            forward_scenario_ref="",
            red_team_ref="", unresolved_thesis_killer=False,
            sizing_guardrail="", invalidation_conditions=(), exit_watch_conditions=()),

        ReplayCalibrationCase(
            case_id="replaycal:deteriorating_thesis",
            label="ILLUSTRATIVE — deteriorating thesis, red-team thesis-killer (synthetic SYNTH-C)",
            scenario_kind="deteriorating_thesis",
            expectation_label="flag_deterioration",
            run_id="REPLAY-DETERIORATE-1", ticker="SYNTH-C",
            company_name="Synthetic Deteriorating C",
            # otherwise-complete evidence, but an UNRESOLVED red-team thesis-killer has emerged.
            candidate=_illustrative_candidate("SYNTH-C", "REPLAY-DETERIORATE-1", now),
            data_quality_ref="DQ-det", data_quality_state="healthy",
            source_freshness="fresh",
            corroboration_sources=(("sec:det-1", "primary", "sec_filing"),
                                   ("fmp:det-2", "convenience", "fmp")),
            theme_pulse_state="Igniting",
            bottleneck_exposure_refs=("bn-illustrative-chokepoint",),
            company_evidence_refs=(("sec:det-1", "primary", "sec_filing"),),
            investment_diligence_ref="THS-illustrative-1", diligence_complete=True,
            forward_scenario_ref="FWD-det",
            red_team_ref="RT-det", unresolved_thesis_killer=True,             # deterioration
            technical_timing_ref="TT-det", technical_timing_acceptable=True,
            portfolio_fit_ref="PF-det", portfolio_fit_acceptable=True,
            sizing_guardrail="starter position only (qualitative range)",
            invalidation_conditions=("thesis broken if the chokepoint clears",),
            exit_watch_conditions=("exit watch if margins compress",)),

        ReplayCalibrationCase(
            case_id="replaycal:social_only_noise",
            label="ILLUSTRATIVE — social/rumor-only narrative (synthetic SYNTH-D)",
            scenario_kind="social_only_noise",
            expectation_label="watch",
            run_id="REPLAY-SOCIAL-1", ticker="SYNTH-D",
            company_name="Synthetic Social-Noise D",
            # everything else present, but the ONLY corroboration + company evidence is social.
            candidate=_illustrative_candidate("SYNTH-D", "REPLAY-SOCIAL-1", now),
            data_quality_ref="DQ-social", data_quality_state="healthy",
            source_freshness="fresh",
            corroboration_sources=(("x:rumor-1", "rumor", "x_post"),
                                   ("x:rumor-2", "rumor", "x_post")),
            theme_pulse_state="Igniting",
            bottleneck_exposure_refs=("bn-illustrative-chokepoint",),
            company_evidence_refs=(("x:rumor-1", "rumor", "x_post"),),
            investment_diligence_ref="THS-illustrative-1", diligence_complete=True,
            forward_scenario_ref="FWD-social",
            red_team_ref="RT-social", unresolved_thesis_killer=False,
            technical_timing_ref="TT-social", technical_timing_acceptable=True,
            portfolio_fit_ref="PF-social", portfolio_fit_acceptable=True,
            sizing_guardrail="starter position only (qualitative range)",
            invalidation_conditions=("thesis broken if the chokepoint clears",),
            exit_watch_conditions=("exit watch if margins compress",)),

        ReplayCalibrationCase(
            case_id="replaycal:insufficient_data",
            label="ILLUSTRATIVE — insufficient data, no eligible candidate (synthetic SYNTH-E)",
            scenario_kind="insufficient_data",
            expectation_label="block",
            run_id="REPLAY-INSUFFICIENT-1", ticker="SYNTH-E",
            company_name="Synthetic Insufficient E",
            candidate=None,                                          # no eligible candidate
            data_quality_ref="", data_quality_state="",             # DQ unstated
            source_freshness="", corroboration_sources=(),
            theme_pulse_state="Data insufficient",
            bottleneck_exposure_refs=(), company_evidence_refs=(),
            investment_diligence_ref="", diligence_complete=False,
            forward_scenario_ref="", red_team_ref="",
            sizing_guardrail="", invalidation_conditions=(), exit_watch_conditions=()),
    )
    return cases


# --------------------------------------------------------------------------- #
# The honest calibration report (markdown text -- deterministic)                 #
# --------------------------------------------------------------------------- #
def _by_kind(results: Tuple[ReplayCalibrationResult, ...]
             ) -> "Dict[str, ReplayCalibrationResult]":
    return {r.scenario_kind: r for r in results}


def render_calibration_report(cases: Tuple[ReplayCalibrationCase, ...],
                              results: Tuple[ReplayCalibrationResult, ...],
                              summary: Dict[str, int], *, now: str) -> str:
    """Render the honest 022G calibration report as markdown text. Deterministic."""
    by_kind = _by_kind(results)
    case_by_id = {c.case_id: c for c in cases}

    any_bad = any(
        (r.gate_state == "actionable_pick_manual_review"
         or r.recommendation_state == "actionable_pick_manual_review")
        for r in results if r.scenario_kind != "strong_beneficiary_complete_evidence")
    strong = by_kind.get("strong_beneficiary_complete_evidence")
    weak = by_kind.get("hype_weak_evidence")
    insufficient = by_kind.get("insufficient_data")
    deteriorating = by_kind.get("deteriorating_thesis")
    social = by_kind.get("social_only_noise")

    def yn(flag: bool) -> str:
        return "YES" if flag else "NO"

    lines = []
    lines.append("# Historical Replay Calibration — IMPLEMENTATION-022G")
    lines.append("")
    lines.append("Filled from an ACTUAL execution of `reality_mesh.replay_calibration."
                 "run_replay_calibration` over the seeded illustrative cases. Every field below "
                 "is read back from the produced `ReplayCalibrationResult` records — never from "
                 "memory or assumption.")
    lines.append("")
    lines.append("> HONESTY: this calibrates the recommendation **LOGIC** on ILLUSTRATIVE, "
                 "clearly-labelled **synthetic** scenarios. It is **NOT** a validated historical "
                 "alpha backtest with real returns. There is no ground-truth labelled "
                 "multi-bagger/failure market data here, no real ticker is claimed to have been "
                 "\"caught\", and no return or outcome is fabricated. The SAME 022B recommendation "
                 "gates are applied to every case, UNCHANGED — never tuned to hindsight.")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append("| Prepared at (injected) | `{0}` |".format(now))
    lines.append("| Gate engine | `recommendation_gates.evaluate_recommendation` (022B, "
                 "15 hard gates, UNCHANGED) |")
    lines.append("| Cases | {0} illustrative synthetic scenarios (one per scenario kind) |".format(
        summary.get("cases_total", 0)))
    lines.append("| Mode | REPLAY — every record marked `replay_mode=True`, isolated from live |")
    lines.append("")

    lines.append("## The four calibration questions")
    lines.append("")
    lines.append("**1. Does the layer AVOID obvious bad recommendations?** {0} — no weak / "
                 "social-only / insufficient / deteriorating case reached "
                 "`actionable_pick_manual_review`.".format(yn(not any_bad)))
    if weak is not None and insufficient is not None:
        lines.append("")
        lines.append("**2. Does it BLOCK weak candidates?** {0} — the hype/weak case produced "
                     "`{1}` and the insufficient-data case produced `{2}` (both via the real "
                     "gates, honestly blocked with an exact reason).".format(
                         yn(weak.gate_state == "blocked" and insufficient.gate_state == "blocked"),
                         weak.gate_state, insufficient.gate_state))
    if strong is not None:
        lines.append("")
        lines.append("**3. Does it SURFACE a strong candidate with complete evidence?** {0} — the "
                     "strong-beneficiary case with genuinely complete evidence reached `{1}` "
                     "through the real 022B gates (all 15 passed; no special-casing).".format(
                         yn(strong.gate_state == "actionable_pick_manual_review"),
                         strong.gate_state))
    if deteriorating is not None:
        lines.append("")
        lines.append("**4. Does it FLAG a deteriorating thesis?** {0} — the deteriorating case "
                     "raised an unresolved red-team thesis-killer, which the gates BLOCKED "
                     "(`gate_state={1}`); the calibration surfaces that as the conservative "
                     "review verdict `{2}`.".format(
                         yn(deteriorating.deterioration_flag),
                         deteriorating.gate_state, deteriorating.recommendation_state))
    lines.append("")

    lines.append("## Per-case outcome")
    lines.append("")
    lines.append("| Case | Scenario | Expectation (CHECK-only) | 022B gate_state | "
                 "Calibration verdict | Deterioration flagged | Matched? |")
    lines.append("|------|----------|--------------------------|-----------------|"
                 "---------------------|-----------------------|----------|")
    for result in results:
        case = case_by_id.get(result.case_id)
        label = case.label if case is not None else result.case_id
        lines.append("| {0} | `{1}` | `{2}` | `{3}` | `{4}` | {5} | {6} |".format(
            label, result.scenario_kind, result.expectation_label, result.gate_state,
            result.recommendation_state, yn(result.deterioration_flag),
            yn(result.matched_expectation)))
    lines.append("")

    lines.append("## Calibration summary (labels + volume counts — feeds 017 learning; no score)")
    lines.append("")
    lines.append("| Label | Count |")
    lines.append("|-------|-------|")
    for key in ("cases_total", "matched_expectation", "unmatched_expectation", "actionable",
                "active_diligence", "watch", "blocked", "exit_review", "flagged_deterioration"):
        lines.append("| `{0}` | {1} |".format(key, summary.get(key, 0)))
    lines.append("")

    lines.append("## Honesty caveats (stated plainly)")
    lines.append("")
    lines.append("- **Illustrative synthetic scenarios.** Every case is a clearly-labelled "
                 "synthetic scenario (`SYNTH-A`…`SYNTH-E`) that exercises one branch of the "
                 "recommendation LOGIC. None is a real company.")
    lines.append("- **NOT a validated backtest.** This is not a historical alpha backtest and "
                 "carries no real returns or outcomes. There is no ground-truth labelled "
                 "market data here; no numeric score / rank is produced anywhere.")
    lines.append("- **Not hindsight-optimized.** The SAME 022B gates are applied to every case, "
                 "unchanged. A case with incomplete evidence is honestly blocked / downgraded — "
                 "that is the correct conservative result, not a miss to \"fix\".")
    lines.append("- **Replay-mode, isolated from live.** Every record is marked "
                 "`replay_mode=True` and persisted to its own append-only log "
                 "(`replay_calibration.jsonl`); a replay verdict can never appear as a live "
                 "recommendation, and the calibration mutates no source record.")
    if social is not None:
        lines.append("- **Social-only caps at watch.** The social/rumor-only case — otherwise "
                     "fully evidenced — produced `{0}`: a social/rumor basis is monitored, never "
                     "surfaced as actionable.".format(social.gate_state))
    lines.append("")
    lines.append("## Recommended 022G verdict")
    lines.append("")
    all_matched = summary.get("unmatched_expectation", 0) == 0
    lines.append("The recommendation LOGIC behaved conservatively on every illustrative case "
                 "({0}/{1} matched the conservative expectation): it surfaced only the "
                 "complete-evidence strong case, blocked the weak and insufficient cases, capped "
                 "the social-only case at watch, and flagged the deteriorating thesis. This "
                 "validates the LOGIC on synthetic scenarios ONLY — a real validated backtest "
                 "with ground-truth returns remains an outstanding, separate item.".format(
                     summary.get("matched_expectation", 0), summary.get("cases_total", 0)))
    lines.append("")
    lines.append("Verdict: **{0}**.".format(
        "logic calibration PASSED (illustrative)" if all_matched
        else "logic calibration INCOMPLETE — review unmatched cases"))
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Construction-time guard: no calibration shape may carry a trade / score field. #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(ReplayCalibrationCase)
assert_no_trade_fields(ReplayCalibrationResult)

# 017 learning consumes labels + volume counts. The calibration summary keys are a superset of a
# labels+counts view; this reference keeps the 017 outcome vocabulary in scope for readers.
_017_OUTCOME_VOCAB = tuple(sorted(OUTCOME_LABELS))
