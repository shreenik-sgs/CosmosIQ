"""DiligenceInputs -- the MANUAL, hand-fed evidence the alpha gauntlet consumes.

IMPORTANT: every field here is supplied BY HAND for the MVP. Nothing in this
module (or anywhere downstream of it) fetches prices, financials, ownership, or
chart data autonomously. ``CandidateInput`` is a researcher's structured note on
one company in the opportunity's value chain; ``DiligenceInputs`` bundles the
candidates for one Opportunity Hypothesis plus a few theme-level overrides.

These objects are frozen dataclasses: the gauntlet reads them and never mutates
them. They carry NO investment verdict -- they are raw structured facts from
which Nivesha (Prometheus) REASONS a gated Investment Thesis. There is no
autonomous data acquisition here; that is deliberately out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class CandidateInput:
    """A hand-fed structured note on one company in the value chain.

    All fields are optional (MVP, manually supplied). Numbers are absolute, in
    whatever consistent unit the researcher recorded; margins/ratios are
    fractions in 0..1; ``relative_strength`` is a signed number where > 0 means
    outperforming the benchmark.
    """

    name: str = ""
    ticker: str = ""
    value_chain_role: str = ""
    tier: int = 0
    # --- valuation / capitalisation ---
    current_price: Optional[float] = None
    shares_outstanding: Optional[float] = None
    # --- fundamentals ---
    revenue: Optional[float] = None
    prior_revenue: Optional[float] = None
    gross_margin: Optional[float] = None
    prior_gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    ebitda: Optional[float] = None
    fcf: Optional[float] = None
    backlog: Optional[float] = None
    guidance: Optional[str] = None  # {"raise", "inline", "cut"}
    capex: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None
    # --- capital-structure / dilution ---
    dilution_risk: str = "none"  # {"none", "low", "moderate", "high"}
    shelf_registration: bool = False
    atm_facility: bool = False
    convertible_debt: bool = False
    # --- ownership / recognition ---
    institutional_ownership: Optional[float] = None  # 0..1
    analyst_coverage: Optional[int] = None
    short_interest: Optional[float] = None  # 0..1
    float_shares: Optional[float] = None
    # --- valuation framing ---
    valuation_multiple: Optional[float] = None
    valuation_reflects_story: bool = False
    bear_price: Optional[float] = None
    base_price: Optional[float] = None
    bull_price: Optional[float] = None
    extreme_bull_price: Optional[float] = None
    # --- technical / chart ---
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    ema_slopes_up: bool = False
    relative_strength: Optional[float] = None  # > 0 => outperforming
    vwap: Optional[float] = None
    breakout_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    price_above_breakout: bool = False
    base_duration_days: Optional[int] = None
    volatility_contracting: bool = False
    volume_recent: Optional[float] = None
    volume_avg: Optional[float] = None


@dataclass(frozen=True)
class DiligenceInputs:
    """The bundle of hand-fed candidates for one Opportunity Hypothesis.

    MANUAL MVP INPUTS -- not autonomous fetching. ``candidates`` is the set of
    companies the researcher wants the gauntlet to score against the opportunity.
    The probability fields override the default bear/base/bull weighting used in
    the asymmetry stage.
    """

    domain: str = ""
    candidates: Tuple[CandidateInput, ...] = field(default_factory=tuple)
    # theme-level overrides (all optional, manual)
    bear_probability: Optional[float] = None
    base_probability: Optional[float] = None
    bull_probability: Optional[float] = None
    catalyst_timing_window: Optional[str] = None
    notes: str = ""

    def scenario_probabilities(self) -> Tuple[float, float, float]:
        """Return (bear, base, bull) probabilities, defaulting to .25/.5/.25."""
        if (self.bear_probability is not None
                and self.base_probability is not None
                and self.bull_probability is not None):
            return (float(self.bear_probability), float(self.base_probability),
                    float(self.bull_probability))
        return (0.25, 0.5, 0.25)
