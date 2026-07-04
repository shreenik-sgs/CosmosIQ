# ADR-CANDIDATE-015 — Scheduled Pulse Unlock: a Data + Pure-Tick Cadence Core, Never a Daemon

Status: **CANDIDATE** — accepted-by-authorization (the master production authorization unlocks
Phase 015), pending formal entry in the ADR register `ARCHITECTURE_DECISIONS.md`
Date: proposed during Phase 015 · Supersedes: none · Related: ADR-0010 (cognition–actuation
boundary), ARCHITECTURE_CONTRACT_012 §G, SPEC-013 §D, RUNTIME_CONTRACT_013,
ADR-CANDIDATE-011 (evidence-layer discipline).

> This is a **candidate** for architect review. It does not modify the frozen ADR register and
> does not increment the next-ADR number. If accepted, it should be entered as a formal ADR with
> the next available number and this candidate retired.

## Context

From Phase 012 through Phase 014 a scheduler was **explicitly forbidden**
(ARCHITECTURE_CONTRACT_012 §G: "No scheduler, background job, automated refresh, streaming, or
automated trading"). Every pulse was manual/on-demand; the reserved `scheduled` / `streaming`
trigger types are rejected at construction in `reality_mesh.runtime.PulseRun`; repo-wide AST
guards ban scheduler/daemon/loop module imports across `reality_mesh`; and the
`scheduler_broker_trading_guardrail` data-quality gate re-asserts this on every run.

That prohibition was deliberate sequencing, not a permanent ban. SPEC-013 §D scheduled the
unlock: **Phase 015 — Scheduled pulse / alerting (ONLY after 013 + 014; requires a new ADR)**.
Phases 013 and 014 are now complete: the runtime records, append-only persistence, deterministic
replay, observability roll-ups, and the eleven data-quality gates all exist and are
test-enforced. The **master production authorization** therefore unlocks a scheduler in
Phase 015 — and only in Phase 015, only under the discipline below.

The risk being managed is the classic one: a scheduler is the first component that *acts without
a human present*. Left undisciplined it becomes an always-on daemon, and an always-on daemon
adjacent to an execution layer is the road to automated trading. This ADR-candidate fixes the
boundary before any scheduled run exists.

## Decision

**The scheduler is unlocked for Phase 015 as frozen data plus a pure `tick` decision function
(`reality_mesh.scheduler`), driven only by an explicitly-started runner — never a daemon, never
auto-started, and never connected to execution.**

Specifically:

- **Data + tick core (015A, this slice).** `CadencePolicy`, `MarketHoursCalendar`,
  `ScheduleState`, and `PulseSchedule` are frozen dataclasses; `due_policies(schedule, now)`
  is a pure function of an injected `now` that computes *what is due*. It runs nothing.
  Nothing starts on import; there is no thread, no event loop, no `while True`, no sleeping,
  no process, and no such module import (the existing repo-wide AST guards remain in force
  over `reality_mesh.scheduler` unchanged).
- **Explicit-start runner only (015B).** Anything that *acts* on `due_policies` must be a
  separately-started, operator-invoked runner — started by a human command, never on import,
  never as a side effect. Only when that runner exists (015B) is the reserved `scheduled`
  trigger type in `reality_mesh.runtime` unlocked, via its own reviewed change; this slice does
  not touch `runtime.py`.
- **Operator controls are first-class.** `pause` / `resume` (per policy and global
  `paused_all`), a global `max_runs_per_hour` throttle, and deterministic exponential failure
  backoff (`now + min(2**failures * interval, 24h)`, no jitter, no randomness) are part of the
  core, not an afterthought. Every state transition returns a NEW frozen object —
  append-style, never mutation.
- **Deterministic.** Injected ISO timestamps everywhere; the wall clock is never read; there is
  no randomness anywhere in the cadence path. Same inputs → same due-set, byte-for-byte.
- **Alerts observe; they never execute.** Alert generation/review (later 015 slices) may only
  *surface* regime change, rotation, theme-pulse change, filing risk, narrative spikes,
  crowding warnings, and data-quality failures. An alert can never place, size, or suggest an
  order. Execution stays a **manual preview only** (Kriya).
- **Still forbidden, unchanged:** auto-buy, auto-sell, broker execution, automated trading, and
  portfolio auto-rebalancing remain forbidden and separately approval-gated (Phase 020+ with
  its own explicit approval + ADR). Phase 015 does not move that boundary by a millimeter.

## Consequences

**Positive**
- Cadence becomes reviewable **data** (the SPEC-013 §D cadence bands ship as
  `DEFAULT_CADENCE_POLICIES`), not behavior hidden in a loop.
- The decision ("what is due now?") is testable offline and deterministically, independent of
  any runner; the 013 replay/observability/gate machinery applies to scheduled runs exactly as
  to manual ones.
- The execution boundary (ADR-0010) is untouched; the scheduler cannot reference execution at
  all (test-asserted).

**Negative / accepted costs**
- Nothing runs by itself after 015A: an operator (or the future 015B runner) must call the
  tick and act on it. That inconvenience is the safety property.
- Backoff without jitter can synchronize retries across policies; accepted, because
  determinism outranks retry-smoothing in this system.

**Enforcement**
- `reality_mesh.scheduler` imports no scheduler/daemon/network/broker module (existing AST
  guards + `tests/test_reality_mesh_scheduler.py`).
- No `while True` / sleep / thread / event-loop construct in the module (test-asserted).
- No execution/trade token in the module source (test-asserted).
- `PulseRun.trigger_type` still rejects `scheduled` / `streaming` until 015B unlocks it under
  review.
- Demo and default pulse surfaces remain byte-identical (untouched paths, test-asserted).

## Alternatives considered

1. **A background daemon/thread with `sleep` loops** — rejected: violates the AST guards, makes
   behavior untestable and non-deterministic, and normalizes always-on operation before the
   alerting/learning layers exist.
2. **OS-level job scheduling (external timer services) now** — rejected for 015A: pushes cadence
   policy outside the reviewed, replayable core; may be revisited for 015B/C as the *explicit
   starter* of the runner, never as the decision-maker.
3. **Keep the scheduler forbidden indefinitely** — rejected: SPEC-013 §D sequenced the unlock
   deliberately; regime-change and filing-risk alerting has real value, and the 013 gates now
   exist precisely to keep a scheduled pulse honest.
4. **Unlock the `scheduled` trigger type in this slice** — rejected: the vocabulary unlock
   belongs with the runner that actually records scheduled runs (015B), keeping this slice
   purely decisional.

## Review note

On acceptance, enter as the next formal ADR (increment the register), cross-reference SPEC-013
§D and ARCHITECTURE_CONTRACT_012 §G, and retire this candidate file.
