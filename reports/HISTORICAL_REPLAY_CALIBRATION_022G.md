# Historical Replay Calibration — IMPLEMENTATION-022G

Filled from an ACTUAL execution of `reality_mesh.replay_calibration.run_replay_calibration` over the seeded illustrative cases. Every field below is read back from the produced `ReplayCalibrationResult` records — never from memory or assumption.

> HONESTY: this calibrates the recommendation **LOGIC** on ILLUSTRATIVE, clearly-labelled **synthetic** scenarios. It is **NOT** a validated historical alpha backtest with real returns. There is no ground-truth labelled multi-bagger/failure market data here, no real ticker is claimed to have been "caught", and no return or outcome is fabricated. The SAME 022B recommendation gates are applied to every case, UNCHANGED — never tuned to hindsight.

| Field | Value |
|-------|-------|
| Prepared at (injected) | `2026-07-06T00:00:00Z` |
| Gate engine | `recommendation_gates.evaluate_recommendation` (022B, 15 hard gates, UNCHANGED) |
| Cases | 5 illustrative synthetic scenarios (one per scenario kind) |
| Mode | REPLAY — every record marked `replay_mode=True`, isolated from live |

## The four calibration questions

**1. Does the layer AVOID obvious bad recommendations?** YES — no weak / social-only / insufficient / deteriorating case reached `actionable_pick_manual_review`.

**2. Does it BLOCK weak candidates?** YES — the hype/weak case produced `blocked` and the insufficient-data case produced `blocked` (both via the real gates, honestly blocked with an exact reason).

**3. Does it SURFACE a strong candidate with complete evidence?** YES — the strong-beneficiary case with genuinely complete evidence reached `actionable_pick_manual_review` through the real 022B gates (all 15 passed; no special-casing).

**4. Does it FLAG a deteriorating thesis?** YES — the deteriorating case raised an unresolved red-team thesis-killer, which the gates BLOCKED (`gate_state=blocked`); the calibration surfaces that as the conservative review verdict `exit_review`.

## Per-case outcome

| Case | Scenario | Expectation (CHECK-only) | 022B gate_state | Calibration verdict | Deterioration flagged | Matched? |
|------|----------|--------------------------|-----------------|---------------------|-----------------------|----------|
| ILLUSTRATIVE — strong beneficiary, complete evidence (synthetic SYNTH-A) | `strong_beneficiary_complete_evidence` | `actionable` | `actionable_pick_manual_review` | `actionable_pick_manual_review` | NO | YES |
| ILLUSTRATIVE — hype with weak evidence (synthetic SYNTH-B) | `hype_weak_evidence` | `block` | `blocked` | `blocked` | NO | YES |
| ILLUSTRATIVE — deteriorating thesis, red-team thesis-killer (synthetic SYNTH-C) | `deteriorating_thesis` | `flag_deterioration` | `blocked` | `exit_review` | YES | YES |
| ILLUSTRATIVE — social/rumor-only narrative (synthetic SYNTH-D) | `social_only_noise` | `watch` | `watch` | `watch` | NO | YES |
| ILLUSTRATIVE — insufficient data, no eligible candidate (synthetic SYNTH-E) | `insufficient_data` | `block` | `blocked` | `blocked` | NO | YES |

## Calibration summary (labels + volume counts — feeds 017 learning; no score)

| Label | Count |
|-------|-------|
| `cases_total` | 5 |
| `matched_expectation` | 5 |
| `unmatched_expectation` | 0 |
| `actionable` | 1 |
| `active_diligence` | 0 |
| `watch` | 1 |
| `blocked` | 3 |
| `exit_review` | 1 |
| `flagged_deterioration` | 1 |

## Honesty caveats (stated plainly)

- **Illustrative synthetic scenarios.** Every case is a clearly-labelled synthetic scenario (`SYNTH-A`…`SYNTH-E`) that exercises one branch of the recommendation LOGIC. None is a real company.
- **NOT a validated backtest.** This is not a historical alpha backtest and carries no real returns or outcomes. There is no ground-truth labelled market data here; no numeric score / rank is produced anywhere.
- **Not hindsight-optimized.** The SAME 022B gates are applied to every case, unchanged. A case with incomplete evidence is honestly blocked / downgraded — that is the correct conservative result, not a miss to "fix".
- **Replay-mode, isolated from live.** Every record is marked `replay_mode=True` and persisted to its own append-only log (`replay_calibration.jsonl`); a replay verdict can never appear as a live recommendation, and the calibration mutates no source record.
- **Social-only caps at watch.** The social/rumor-only case — otherwise fully evidenced — produced `watch`: a social/rumor basis is monitored, never surfaced as actionable.

## Recommended 022G verdict

The recommendation LOGIC behaved conservatively on every illustrative case (5/5 matched the conservative expectation): it surfaced only the complete-evidence strong case, blocked the weak and insufficient cases, capped the social-only case at watch, and flagged the deteriorating thesis. This validates the LOGIC on synthetic scenarios ONLY — a real validated backtest with ground-truth returns remains an outstanding, separate item.

Verdict: **logic calibration PASSED (illustrative)**.
