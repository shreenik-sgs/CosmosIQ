# Exception / Failure Notes — schema

The manual realization of **Exception / Failure = Observation** (EXEC-001 AR-1912; EXEC-002). When
something goes wrong — a rejection, a platform error, a missed or ambiguous fill, an unexpected
outcome — the user records it as an Observation. **No failure is silently discarded** (AR-1912);
every one is preserved, auditable, and flows up as evidence.

## Entry
| Field | Description |
|-------|-------------|
| `note_id` | stable id |
| `ticket_id` | the ticket involved (if any) |
| `occurred_at` | when |
| `category` | rejection / platform_error / missed_fill / ambiguous_outcome / constraint_block / other |
| `description` | what happened, in the user's words |
| `resulting_state` | e.g. indeterminate / rejected / cancelled |
| `follow_up` | reconciliation reference / corrective action |

## Rules
- Every exception or failure is an **Observation of reality** and flows up as evidence (EXEC-001
  AR-1913); it never flows up as purpose.
- An **`ambiguous_outcome`** sets the ticket **indeterminate** until reconciled (EXEC-002 AR-2004/2005).
- Exceptions are never edited away; they are part of the permanent audit trail.
- Patterns across exceptions are inputs the cognitive layers may learn from — the
  *learn from what happened* loop.
