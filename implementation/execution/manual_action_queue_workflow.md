# Manual Action Queue — workflow

Realizes Execution's consumption of the **CIO Personalized Action Queue** (CIO-001) in manual mode.
The queue is the list of recommended actions the user works through, one at a time, under the
Execution gate. Execution **reads** queue items by version and never mutates them (EXEC-001 AR-1903).

## Source
Each queue item personalizes a Prometheus **Investment Action** (PROM-002: enter / hold / add /
trim / exit / avoid / wait / rotate), carrying its grounding. Re-ranking is CIO's job; the action
itself is Prometheus's. Execution presents and governs — it does not re-decide (EXEC-002 AR-2022).

## Queue item (fields)
| Field | Description |
|-------|-------------|
| `queue_item_id` | stable id |
| `investment_action_id` / `version` | the Prometheus Investment Action (PROM-002) |
| `cio_decision_record_id` | personalization grounding (CIO-001) |
| `action_type` | enter / hold / add / trim / exit / avoid / wait / rotate |
| `priority` | from CIO action prioritization |
| `grounding` | thesis / opportunity refs + the "why" (for display) |
| `timing` | timing-to-action (PROM-001) |
| `status` | pending / ticketed / confirmed / placed / recorded / reconciled / skipped |

## Workflow
1. Present pending items in priority order, each **with its grounding** (the "why").
2. The user selects an item to act on, or marks it **skip / wait** (a recorded non-action).
3. **Non-trade actions** (hold / avoid / wait) are recorded directly with reasoning — no ticket.
4. **Trade actions** (enter / add / trim / exit / rotate) generate a manual trade ticket
   (`manual_trade_ticket_schema.md`) and enter the checklist (`manual_execution_checklist.md`).
5. After placement and recording, the item advances to `reconciled` and leaves the queue.

## Boundary
Execution does not re-rank, re-decide, or alter queue items; it presents and governs only.
(EXEC-001 boundary; EXEC-002 AR-2022.)
