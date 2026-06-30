"""Stage J -- Technical inflection (Nivesha timing).

Reads the chart ONLY as a timing flag -- it creates no order and recommends no
trade. A clean setup is a stacked, up-sloping EMA structure (9 > 20 > 50 > 200)
breaking out of a contracted base on expanding volume, outperforming the market.
Failed breakouts and dilution overhang penalise the setup. ``technical_confirmation``
is the gate Nivesha hands to the repricing trigger; it is a TIMING signal, never
an instruction to act.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._common import clamp

_DILUTION_OVERHANG = {"none": 0.0, "low": 0.0, "moderate": 0.10, "high": 0.25}

# A base is "long enough" to matter once it has built for at least this many days.
MIN_BASE_DAYS = 30
VOLUME_CONFIRM_MULT = 1.20
TECHNICAL_CONFIRM_SCORE = 0.60


@dataclass(frozen=True)
class TechnicalInflectionResult:
    ema_stack_status: str = "not_stacked"
    trend_alignment: bool = False
    compression_breakout_status: str = "none"
    breakout: bool = False
    volume_confirmation: bool = False
    relative_strength_confirmation: bool = False
    failed_breakout_risk: bool = False
    dilution_overhang_penalty: float = 0.0
    technical_setup_score: float = 0.0
    timing_quality: str = "poor"
    technical_confirmation: bool = False
    notes: tuple = ()


def analyze_technical_inflection(candidate) -> TechnicalInflectionResult:
    c = candidate
    if c is None:
        return TechnicalInflectionResult()

    have_emas = None not in (c.ema9, c.ema20, c.ema50, c.ema200)
    stacked = bool(have_emas and c.ema9 > c.ema20 > c.ema50 > c.ema200)
    ema_status = "stacked_up" if stacked else "not_stacked"
    trend_alignment = bool(stacked and c.ema_slopes_up)

    base_long_enough = (c.base_duration_days is not None
                        and c.base_duration_days >= MIN_BASE_DAYS)
    breakout = bool(base_long_enough and c.volatility_contracting and c.price_above_breakout)
    if breakout:
        compression_status = "breakout_confirmed"
    elif base_long_enough and c.volatility_contracting:
        compression_status = "coiling"
    else:
        compression_status = "none"

    volume_confirmation = bool(
        c.volume_recent is not None and c.volume_avg is not None
        and c.volume_recent >= VOLUME_CONFIRM_MULT * c.volume_avg
    )
    rs_confirmation = bool(c.relative_strength is not None and c.relative_strength > 0)

    failed_breakout_risk = not bool(c.price_above_breakout)
    if c.invalidation_level is not None and c.current_price is not None:
        if c.current_price < c.invalidation_level:
            failed_breakout_risk = True

    overhang = _DILUTION_OVERHANG.get(c.dilution_risk, 0.0)
    overhang += 0.05 * (int(c.shelf_registration) + int(c.atm_facility))
    overhang = clamp(overhang, 0.0, 0.5)

    score = clamp(
        0.30 * (1.0 if stacked else 0.0)
        + 0.20 * (1.0 if trend_alignment else 0.0)
        + 0.20 * (1.0 if breakout else 0.0)
        + 0.20 * (1.0 if volume_confirmation else 0.0)
        + 0.10 * (1.0 if rs_confirmation else 0.0)
        - overhang
    )

    if failed_breakout_risk:
        timing = "failed_breakout_risk"
    elif score >= 0.80:
        timing = "high"
    elif score >= TECHNICAL_CONFIRM_SCORE:
        timing = "constructive"
    else:
        timing = "poor"

    technical_confirmation = bool(score >= TECHNICAL_CONFIRM_SCORE and stacked
                                  and volume_confirmation and not failed_breakout_risk)

    notes = []
    if not stacked:
        notes.append("EMAs are not stacked 9>20>50>200")
    if not volume_confirmation:
        notes.append("volume does not confirm (recent < 1.2x average)")
    if failed_breakout_risk:
        notes.append("price is not above the breakout / invalidation level")
    if overhang > 0:
        notes.append("dilution overhang weighs on the setup")

    return TechnicalInflectionResult(
        ema_stack_status=ema_status,
        trend_alignment=trend_alignment,
        compression_breakout_status=compression_status,
        breakout=breakout,
        volume_confirmation=volume_confirmation,
        relative_strength_confirmation=rs_confirmation,
        failed_breakout_risk=failed_breakout_risk,
        dilution_overhang_penalty=round(overhang, 4),
        technical_setup_score=round(score, 4),
        timing_quality=timing,
        technical_confirmation=technical_confirmation,
        notes=tuple(notes),
    )
