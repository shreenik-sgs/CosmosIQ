# Manual Cancel / Replace Log — schema

The manual realization of **cancel / replace / modify as gated operations** and the **cancel/fill
race** (EXEC-002 AR-2014/2015/2016). The user performs the cancel or replace manually in the broker
platform; the system tracks it and reconciles the outcome. Cancel and replace are themselves
**gated actuations** — they pass the checklist too (AR-2014).

## Entry
| Field | Description |
|-------|-------------|
| `op_id` | stable id |
| `ticket_id` | the order being cancelled / replaced / modified |
| `op_type` | cancel / replace / modify |
| `requested_at` | when the user initiated it |
| `new_parameters` | for replace / modify (a new previewed ticket) |
| `outcome` | requested / acknowledged / rejected / **raced_with_fill** / indeterminate |
| `resolved_by` | reconciliation reference (broker statement) |

## Rules
- A **cancel/fill race** (the order fills while the user cancels) is resolved **only by
  reconciliation** against the broker's authoritative record; success is never assumed (AR-2016).
- A **replace / modify** creates a new previewed, re-confirmed ticket — confirmation↔preview binding
  still applies (AR-2009) — and the prior ticket's terminal state is reconciled.
- A **failed** cancel / replace is recorded and recovered by re-checking actual state via
  reconciliation (AR-2015).
- Every cancel / replace is appended to the audit trail (`execution_audit_trail_schema.md`).
