# Manual Execution — implementation artifacts

The first implementation artifacts for EIOS. They realize the **Execution** layer
(Part VII — `specification/07_Execution/`: EXEC-001, EXEC-002) in its **manual-only** actuation
mode (Architecture Book v9.2, EXEC-001 §"The Actuator").

These are hand-authored implementation design documents — **not** generated from the Book. They
must remain faithful to the architecture and never relax a safeguard: a human actuator satisfies
the same Actuation Gate an automated one would.

## Boundary
- **Prometheus and CIO recommend** actions (what / how much / when).
- **Execution prepares and governs** the manual action — ticket, preview, checklist, revalidation,
  confirmation, idempotent marking, reconciliation, audit.
- **The user places the trade manually** in the broker platform (the user is the *actuator*).
- **The system records, reconciles, audits, and learns** — fills/exceptions flow back up as
  Observations (EXEC-001 AR-1913).
- **The system never submits orders to a broker** in this mode (EXEC-001 §"The Actuator").

Broker adapters / automated submission are **deferred indefinitely** and not in the current roadmap.

## Artifacts
| File | Realizes (EXEC) |
|------|-----------------|
| `manual_action_queue_workflow.md` | CIO Personalized Action Queue consumption |
| `manual_trade_ticket_schema.md` | Order · Order Intent · Order Preview |
| `manual_execution_checklist.md` | Actuation Gate · stale-action revalidation · confirmation↔preview binding |
| `manual_fill_record_schema.md` | Fill = Observation · partial/multi-fill · expiration |
| `manual_cancel_replace_log.md` | cancel/replace/modify · cancel/fill race |
| `position_reconciliation_workflow.md` | full-chain reconciliation · indeterminate state |
| `execution_audit_trail_schema.md` | audit trail · replay (reconstruct, never re-actuate) |
| `exception_failure_notes_schema.md` | Exception/Failure = Observation |

## MVP workflow
1. Show the recommended action **with its grounding** (thesis / opportunity / why).
2. Generate the manual trade ticket.
3. Show the checklist / stale-action validation.
4. Require user confirmation (bound to the exact ticket).
5. **User manually places the trade in the broker.**
6. User records the fill / outcome (incl. partial / exception).
7. System reconciles position and stores the audit trail.
8. Recorded outcome flows back up as Observation — *learn from what happened*.

## Definition of Done (first activation)
This is where the project's full Definition of Done first applies end-to-end:
spec (Part VII) → ticket → checklist → confirmation → record → reconcile → audit/replay.
