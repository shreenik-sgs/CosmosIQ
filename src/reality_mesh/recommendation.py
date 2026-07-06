"""Typed CapitalRecommendation contract -- the model ABOVE CapitalCandidate (IMPLEMENTATION-022A).

A :class:`~reality_mesh.capital_candidate.CapitalCandidate` says only "this ticker has the full
evidence lineage a capital decision would require" -- it is *worth diligence*. A
:class:`CapitalRecommendation` sits one level ABOVE it: it is the typed object that appears in a
stock-pick report for **MANUAL REVIEW** -- "this passed the recommendation gates strongly enough
to be surfaced to a human". It is emphatically NOT a trade, NOT an order, and NOT a numeric
ranking:

* **Labels, not numbers.** There is NO numeric ``score`` / ``rank`` / ``rating`` /
  ``investability`` / ``alpha`` field anywhere, and NO ``buy`` / ``sell`` / ``order`` / ``submit``
  / ``broker`` / ``trade`` field. State + label are drawn from CLOSED vocabularies; a set of
  marketing-style ``FORBIDDEN_RECOMMENDATION_LABELS`` (Strong Buy / Buy Now / Alpha Score / ...)
  is REJECTED at construction -- any forbidden phrase appearing as a substring of the label raises.

* **``actionable_pick_manual_review`` is UNFORGEABLE at the type level** (mirrors the 019B
  ``CapitalCandidate.eligible`` invariant). Constructing that state REQUIRES the FULL ref set: an
  (eligible) ``capital_candidate_ref``, non-empty ``source_provenance``, an
  ``investment_diligence_ref``, a ``forward_scenario_ref``, a ``technical_timing_ref``, a
  ``portfolio_fit_ref``, a ``red_team_ref``, a ``data_quality_ref``, plus non-empty
  ``invalidation_conditions``, ``exit_watch_conditions`` and a ``sizing_guardrail``. Missing ANY
  piece -> ``ValueError``. (022A enforces the STRUCTURAL requirement; 022B adds the runtime gate
  logic -- the recommendation gates, thesis-killer resolution, DQ-acceptability.)

* **A ``blocked`` recommendation carries an EXACT reason.** ``state == "blocked"`` REQUIRES a
  non-empty ``blocked_reason`` -- nothing is hidden.

Execution stays MANUAL REVIEW: there is no buy/sell/order/submit affordance anywhere; the only
"execution" surface is a ``manual_execution_preview_ref`` -- a pointer to a human-review preview,
never an order. Deterministic (injected ``now`` + a run+ticker-derived id), stdlib-only,
Python 3.9, OFFLINE. No network / scheduler / broker on import; no wall-clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from .validation import assert_no_trade_fields


# --------------------------------------------------------------------------- #
# Closed vocabularies                                                           #
# --------------------------------------------------------------------------- #

# The recommendation state -- a CLOSED verdict about whether (and how strongly) a ticker should
# appear in a manual-review stock-pick report. ``actionable_pick_manual_review`` is the only
# "surface it to a human as a pick" state and is UNFORGEABLE (enforced in ``__post_init__``).
RECOMMENDATION_STATES: Tuple[str, ...] = (
    "not_recommended",
    "watch",
    "active_diligence",
    "prepare_entry",
    "actionable_pick_manual_review",
    "avoid",
    "deteriorating",
    "exit_review",
    "blocked",
)

# The CLOSED display-label vocabulary. Labels are qualitative -- never a score, rank, or rating.
# ``""`` (unset) is also permitted for the label-less states (``not_recommended``).
RECOMMENDATION_LABELS: Tuple[str, ...] = (
    "Watch",
    "Active Diligence",
    "Prepare Entry",
    "Actionable Pick — Manual Review",   # em-dash, U+2014
    "Avoid",
    "Exit Review",
    "Blocked",
)

# Marketing / trade-decision / numeric labels that are PERMANENTLY REJECTED. Any of these phrases
# appearing (case-insensitively) as a substring of a recommendation label raises ValueError -- a
# recommendation is a review label, never "buy now", a rank, or a score.
FORBIDDEN_RECOMMENDATION_LABELS: Tuple[str, ...] = (
    "Strong Buy",
    "Buy Now",
    "Sell Now",
    "Top Pick Rank #1",
    "Alpha Score",
    "Guaranteed Upside",
)

# The canonical state -> label pairing. A non-empty label MUST be the canonical one for its state
# (checked in ``__post_init__``); ``actionable_pick_manual_review`` and ``blocked`` additionally
# REQUIRE their exact label. ``not_recommended`` carries no positive label ("").
RECOMMENDATION_STATE_LABELS: Dict[str, str] = {
    "not_recommended": "",
    "watch": "Watch",
    "active_diligence": "Active Diligence",
    "prepare_entry": "Prepare Entry",
    "actionable_pick_manual_review": "Actionable Pick — Manual Review",
    "avoid": "Avoid",
    "deteriorating": "Exit Review",
    "exit_review": "Exit Review",
    "blocked": "Blocked",
}

# The states whose label is MANDATORY and must be exactly the canonical value.
_LABEL_REQUIRED_STATES: Tuple[str, ...] = ("actionable_pick_manual_review", "blocked")

# The producing run's data-quality state a recommendation may carry (informational; the runtime
# acceptability gate is 022B). ``blocked_by_policy`` never yields a recommendation at all.
RECOMMENDATION_DATA_QUALITY_STATES: Tuple[str, ...] = (
    "healthy", "explicitly_acceptable", "degraded", "failed")

# The publication lifecycle of a recommendation record (informational).
PUBLICATION_STATES: Tuple[str, ...] = ("draft", "published", "blocked", "superseded")

# The structural pieces an ``actionable_pick_manual_review`` recommendation MUST carry. Each maps
# to a human-readable name surfaced in the raised error / blocked_reason. Order is stable.
_ACTIONABLE_REQUIRED_REFS: Tuple[str, ...] = (
    "capital_candidate_ref",
    "source_provenance",
    "investment_diligence_ref",
    "forward_scenario_ref",
    "technical_timing_ref",
    "portfolio_fit_ref",
    "red_team_ref",
    "data_quality_ref",
    "invalidation_conditions",
    "exit_watch_conditions",
    "sizing_guardrail",
)


# --------------------------------------------------------------------------- #
# The typed contract                                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CapitalRecommendation:
    """A frozen, label-only stock-pick-for-MANUAL-REVIEW record sitting above a CapitalCandidate.

    ``actionable_pick_manual_review`` is UNFORGEABLE: it can only be constructed with the full ref
    set (an eligible ``capital_candidate_ref`` + ``source_provenance`` + ``investment_diligence_ref``
    + ``forward_scenario_ref`` + ``technical_timing_ref`` + ``portfolio_fit_ref`` + ``red_team_ref``
    + ``data_quality_ref`` + non-empty ``invalidation_conditions`` + ``exit_watch_conditions`` +
    ``sizing_guardrail``). Missing ANY piece raises ``ValueError``. A ``blocked`` recommendation
    REQUIRES an exact ``blocked_reason``. There is NO numeric / score / rank / rating / trade field
    anywhere; this is a review label, never a recommendation-to-act or a ranking.
    """

    recommendation_id: str = ""             # REQUIRED, deterministic (run + ticker derived)
    run_id: str = ""                        # REQUIRED -- the run that produced it
    generated_at: str = ""                  # injected timestamp (no wall-clock)
    mode: str = "pulse"                     # the producing run's mode
    candidate_id: str = ""                  # REQUIRED -- the underlying CapitalCandidate id
    ticker: str = ""                        # REQUIRED
    company_name: str = ""
    recommendation_state: str = "not_recommended"   # closed: RECOMMENDATION_STATES
    recommendation_label: str = ""          # closed: RECOMMENDATION_LABELS ("" = unset)
    recommendation_time_horizon: str = ""   # plain-English horizon label (never a number)

    # -- graph placement refs (the MAP the pick sits on) -- #
    theme_ref: str = ""
    mega_theme_ref: str = ""
    value_chain_ref: str = ""
    bottleneck_ref: str = ""

    # -- the evidence-lineage refs (what makes an actionable pick unforgeable) -- #
    capital_candidate_ref: str = ""         # an ELIGIBLE CapitalCandidate
    investment_diligence_ref: str = ""      # the accepted engine's thesis id
    forward_scenario_ref: str = ""          # the forward-scenario packet id
    portfolio_fit_ref: str = ""             # the portfolio-fit assessment id
    technical_timing_ref: str = ""          # the technical-timing / entry-inflection id
    red_team_ref: str = ""                  # the red-team review id (no unresolved thesis-killer)
    data_quality_ref: str = ""              # the DQ verdict (healthy / explicitly-acceptable)

    # -- provenance + human-readable narrative -- #
    source_provenance: Tuple[str, ...] = field(default_factory=tuple)
    evidence_summary: str = ""
    key_thesis: str = ""
    why_now: str = ""
    expected_catalysts: Tuple[str, ...] = field(default_factory=tuple)
    primary_risks: Tuple[str, ...] = field(default_factory=tuple)
    data_gaps: Tuple[str, ...] = field(default_factory=tuple)

    # -- the manual-review guardrails (labels / conditions, never numbers) -- #
    invalidation_conditions: Tuple[str, ...] = field(default_factory=tuple)
    exit_watch_conditions: Tuple[str, ...] = field(default_factory=tuple)
    sizing_guardrail: str = ""              # a qualitative sizing-range GUARDRAIL, never a number
    manual_execution_preview_ref: str = ""  # a pointer to a HUMAN-REVIEW preview, never an order

    publication_state: str = "draft"        # closed: PUBLICATION_STATES
    blocked_reason: str = ""                # REQUIRED when state == "blocked"

    def __post_init__(self) -> None:
        # -- required ids -- #
        for name in ("recommendation_id", "run_id", "candidate_id", "ticker"):
            value = getattr(self, name, "")
            if not isinstance(value, str) or value.strip() == "":
                raise ValueError(
                    "CapitalRecommendation.{0} is required and must be non-empty".format(name))

        # -- closed state vocab -- #
        if self.recommendation_state not in RECOMMENDATION_STATES:
            raise ValueError(
                "CapitalRecommendation.recommendation_state {0!r} invalid (allowed: {1})".format(
                    self.recommendation_state, list(RECOMMENDATION_STATES)))

        # -- publication + DQ vocabs (informational; "" = unset) -- #
        if self.publication_state and self.publication_state not in PUBLICATION_STATES:
            raise ValueError(
                "CapitalRecommendation.publication_state {0!r} invalid (allowed: {1})".format(
                    self.publication_state, list(PUBLICATION_STATES)))

        # -- the label: closed vocab + NEVER a forbidden (trade/score/rank) phrase -- #
        self._validate_label()

        # -- state <-> label consistency -- #
        self._validate_state_label_pairing()

        # -- the unforgeable-actionable invariant -- #
        if self.recommendation_state == "actionable_pick_manual_review":
            missing = self.missing_actionable_requirements()
            if missing:
                raise ValueError(
                    "CapitalRecommendation cannot be 'actionable_pick_manual_review' without the "
                    "full ref set -- missing {0}. An actionable manual-review pick REQUIRES an "
                    "eligible capital_candidate_ref + source_provenance + investment_diligence_ref "
                    "+ forward_scenario_ref + technical_timing_ref + portfolio_fit_ref + "
                    "red_team_ref + data_quality_ref + invalidation_conditions + "
                    "exit_watch_conditions + sizing_guardrail.".format(", ".join(missing)))

        # -- a blocked recommendation carries an EXACT reason -- #
        if self.recommendation_state == "blocked":
            if not str(self.blocked_reason or "").strip():
                raise ValueError(
                    "CapitalRecommendation.blocked_reason is required and must be non-empty when "
                    "recommendation_state == 'blocked' -- a block always names its exact reason")

    # -- validation helpers --------------------------------------------------- #
    def _validate_label(self) -> None:
        label = self.recommendation_label
        if label:
            # a forbidden marketing/trade/score phrase appearing anywhere in the label is fatal.
            low = label.lower()
            for phrase in FORBIDDEN_RECOMMENDATION_LABELS:
                if phrase.lower() in low:
                    raise ValueError(
                        "CapitalRecommendation.recommendation_label {0!r} contains forbidden "
                        "phrase {1!r} -- a recommendation is a review label, never a buy/sell/"
                        "rank/score directive".format(label, phrase))
            if label not in RECOMMENDATION_LABELS:
                raise ValueError(
                    "CapitalRecommendation.recommendation_label {0!r} invalid (allowed: {1})".format(
                        label, list(RECOMMENDATION_LABELS)))

    def _validate_state_label_pairing(self) -> None:
        expected = RECOMMENDATION_STATE_LABELS.get(self.recommendation_state, "")
        label = self.recommendation_label
        if self.recommendation_state in _LABEL_REQUIRED_STATES:
            # actionable / blocked: the exact canonical label is MANDATORY.
            if label != expected:
                raise ValueError(
                    "CapitalRecommendation.recommendation_state {0!r} requires "
                    "recommendation_label {1!r} (got {2!r})".format(
                        self.recommendation_state, expected, label))
        elif label and label != expected:
            # any other state: an empty label is allowed, but a present one must be consistent.
            raise ValueError(
                "CapitalRecommendation state/label mismatch: state {0!r} pairs with label {1!r}, "
                "not {2!r}".format(self.recommendation_state, expected, label))

    # -- actionable-requirement introspection --------------------------------- #
    def missing_actionable_requirements(self) -> Tuple[str, ...]:
        """The required actionable pieces that are absent (empty tuple iff fully complete)."""
        missing = []
        # scalar refs -- each must be a non-empty string.
        for name in ("capital_candidate_ref", "investment_diligence_ref", "forward_scenario_ref",
                     "technical_timing_ref", "portfolio_fit_ref", "red_team_ref",
                     "data_quality_ref", "sizing_guardrail"):
            if not str(getattr(self, name, "") or "").strip():
                missing.append(name)
        # tuple requirements -- each must be non-empty.
        for name in ("source_provenance", "invalidation_conditions", "exit_watch_conditions"):
            if not tuple(getattr(self, name, ()) or ()):
                missing.append(name)
        # return in the canonical order.
        return tuple(n for n in _ACTIONABLE_REQUIRED_REFS if n in set(missing))

    @property
    def is_actionable_pick(self) -> bool:
        return self.recommendation_state == "actionable_pick_manual_review"

    @property
    def is_blocked(self) -> bool:
        return self.recommendation_state == "blocked"


# The recommendation contract (for registry / test introspection). Trade/score-clean.
CAPITAL_RECOMMENDATION_MODELS = (CapitalRecommendation,)


# --------------------------------------------------------------------------- #
# Deterministic id                                                              #
# --------------------------------------------------------------------------- #
def recommendation_id_for(run_id: str, ticker: str) -> str:
    """A deterministic recommendation id from the run + ticker (no wall-clock, order-stable)."""
    return "rec:{0}:{1}".format(str(run_id or "").strip(), str(ticker or "").strip().upper())


# --------------------------------------------------------------------------- #
# Optional honest assembler (022B builds the real gate). NEVER forges actionable. #
# --------------------------------------------------------------------------- #
def assess_recommendation(
    *,
    ticker: str,
    run_id: str,
    intended_state: str,
    now: str,
    candidate_id: str = "",
    company_name: str = "",
    recommendation_label: str = "",
    recommendation_time_horizon: str = "",
    mode: str = "pulse",
    theme_ref: str = "",
    mega_theme_ref: str = "",
    value_chain_ref: str = "",
    bottleneck_ref: str = "",
    capital_candidate_ref: str = "",
    investment_diligence_ref: str = "",
    forward_scenario_ref: str = "",
    portfolio_fit_ref: str = "",
    technical_timing_ref: str = "",
    red_team_ref: str = "",
    data_quality_ref: str = "",
    source_provenance: Tuple[str, ...] = (),
    evidence_summary: str = "",
    key_thesis: str = "",
    why_now: str = "",
    expected_catalysts: Tuple[str, ...] = (),
    primary_risks: Tuple[str, ...] = (),
    data_gaps: Tuple[str, ...] = (),
    invalidation_conditions: Tuple[str, ...] = (),
    exit_watch_conditions: Tuple[str, ...] = (),
    sizing_guardrail: str = "",
    manual_execution_preview_ref: str = "",
) -> CapitalRecommendation:
    """Build a :class:`CapitalRecommendation` HONESTLY from what is present.

    This is the MODEL-slice assembler -- it does NOT implement the 022B recommendation gates
    (thesis-killer resolution, technical timing, portfolio fit are their own slices). Its one job
    is to guarantee that ``actionable_pick_manual_review`` is NEVER reached without the full ref
    set: if ``intended_state`` is actionable but any required piece is missing, it DOWNGRADES to a
    ``blocked`` recommendation whose ``blocked_reason`` names EXACTLY what is missing -- it never
    fabricates a ref to reach actionable. ``now`` is injected; the id is derived deterministically.
    """
    rec_id = recommendation_id_for(run_id, ticker)
    symbol = str(ticker or "").strip().upper()
    provenance = tuple(str(p) for p in (source_provenance or ()) if str(p or "").strip())

    common = dict(
        recommendation_id=rec_id, run_id=str(run_id or "").strip(), generated_at=str(now),
        mode=str(mode or "").strip() or "pulse", candidate_id=str(candidate_id or "").strip(),
        ticker=symbol, company_name=company_name,
        recommendation_time_horizon=recommendation_time_horizon,
        theme_ref=theme_ref, mega_theme_ref=mega_theme_ref, value_chain_ref=value_chain_ref,
        bottleneck_ref=bottleneck_ref, capital_candidate_ref=capital_candidate_ref,
        investment_diligence_ref=investment_diligence_ref, forward_scenario_ref=forward_scenario_ref,
        portfolio_fit_ref=portfolio_fit_ref, technical_timing_ref=technical_timing_ref,
        red_team_ref=red_team_ref, data_quality_ref=data_quality_ref,
        source_provenance=provenance, evidence_summary=evidence_summary, key_thesis=key_thesis,
        why_now=why_now, expected_catalysts=tuple(expected_catalysts or ()),
        primary_risks=tuple(primary_risks or ()), data_gaps=tuple(data_gaps or ()),
        invalidation_conditions=tuple(invalidation_conditions or ()),
        exit_watch_conditions=tuple(exit_watch_conditions or ()),
        sizing_guardrail=sizing_guardrail,
        manual_execution_preview_ref=manual_execution_preview_ref)

    if intended_state == "actionable_pick_manual_review":
        # probe the requirements WITHOUT constructing an actionable record (which would raise).
        probe = CapitalRecommendation(
            recommendation_state="prepare_entry",
            recommendation_label=RECOMMENDATION_STATE_LABELS["prepare_entry"], **common)
        missing = probe.missing_actionable_requirements()
        if missing:
            reason = (
                "cannot reach actionable_pick_manual_review: missing {0} -- an actionable "
                "manual-review pick requires the full ref set".format(", ".join(missing)))
            return CapitalRecommendation(
                recommendation_state="blocked",
                recommendation_label=RECOMMENDATION_STATE_LABELS["blocked"],
                publication_state="blocked", blocked_reason=reason, **common)
        return CapitalRecommendation(
            recommendation_state="actionable_pick_manual_review",
            recommendation_label=RECOMMENDATION_STATE_LABELS["actionable_pick_manual_review"],
            publication_state="published", **common)

    label = recommendation_label or RECOMMENDATION_STATE_LABELS.get(intended_state, "")
    return CapitalRecommendation(
        recommendation_state=intended_state, recommendation_label=label, **common)


# --------------------------------------------------------------------------- #
# Construction-time guard: the contract may carry NO trade / score field.        #
# --------------------------------------------------------------------------- #
assert_no_trade_fields(CapitalRecommendation)
