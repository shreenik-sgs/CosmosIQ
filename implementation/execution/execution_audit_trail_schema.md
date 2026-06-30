# Execution Audit Trail — schema

The manual realization of **audit trail + replay** (EXEC-001 AR-1919; EXEC-002 AR-2024). An
append-only log of everything that happened in the manual execution process, sufficient to
**reconstruct** any ticket and the whole session exactly. **Replay reconstructs; it never
re-actuates** (EXEC-002 AR-2003/2024).

## Entry (append-only)
| Field | Description |
|-------|-------------|
| `entry_id` | monotonic / stable |
| `timestamp` | when |
| `ticket_id` | the ticket (if any) |
| `event_type` | see below |
| `actor` | user / system |
| `payload` | event detail (parameters, checklist answers, fill, divergence, …) |
| `grounding_versions` | investment_action, thesis, opportunity, worldview, profile versions |

## event_type (at least)
- `queue_item_presented` · `ticket_created` · `previewed` · `checklist_completed` · `confirmed`
- **`placed_by_user`** · `fill_recorded` · `partial_fill` · `expired` · `cancelled` · `rejected`
- `cancel_requested` · `replace_requested` · `indeterminate_marked` · `reconciled` · `divergence_found`
- `disabled` · `override` · `emergency_invoked`

## Invariants
- **Append-only**: entries are never edited or deleted; operational history is never rewritten
  (AR-2024).
- Every ticket state transition has a corresponding entry.
- The trail is sufficient to **replay the session deterministically** — reconstruct, never re-place.
- Emergency-control invocations (disable, override, kill, cancel-all) are **always** recorded
  (EXEC-002 AR-2020).
