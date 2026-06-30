# Manual Trade Ticket — schema

The manual realization of the **Order** (EXEC-001) in its pre-actuation form (Order Intent +
Order Preview). One ticket per intended trade action; it is the operational record the user
reviews, confirms, and places manually. The `Order` remains the only operational object — the
ticket is its manual instance (EXEC-001 AR-1904; EXEC-002 AR-2021, no new object).

## Identity & idempotency
| Field | Description |
|-------|-------------|
| `ticket_id` | stable, unique; the **idempotency key** (EXEC-002 AR-2002) |
| `queue_item_id` | source action (`manual_action_queue_workflow.md`) |
| `investment_action_id` / `version` | Prometheus Investment Action (PROM-002) |
| `cio_decision_record_id` | personalization grounding (CIO-001) |

A ticket is created **at most once** per `(investment_action_id, version)`; a repeat request
resolves to the same ticket, never a duplicate (EXEC-002 AR-2001).

## Order parameters (the previewed order)
| Field | Description |
|-------|-------------|
| `action_type` | enter / add / trim / exit / rotate |
| `instrument` | symbol / identifier |
| `side` | buy / sell |
| `quantity` | intended quantity |
| `order_type` | market / limit / stop / stop-limit |
| `limit_price` / `stop_price` | as applicable |
| `time_in_force` | day / GTC / … |
| `account` | which account |
| `estimated_cost` | preview estimate |
| `risk_warning` | slippage / fill-risk note (EXEC-001 AR-1916) |
| `venue` | broker / venue (informational; manual) |

## Allocation & quantity derivation
| Field | Description |
|-------|-------------|
| `intended_allocation` | the capital this ticket should deploy, in account currency — from the **Capital Allocation Recommendation** (PROM-001), personalized by CIO |

- `instrument` comes from the **Security / Instrument Mapping** (PROM-001) carried on the Investment Action — it is **not** chosen in Execution.
- `quantity` MAY be derived as `intended_allocation ÷ preview price`, subject to **rounding rules** (whole shares / lot size / option-contract multiple), so deployed capital approximates `intended_allocation`. The derivation and its rounding are recorded so reconciliation can compare intended vs actual capital.

## Preview & confirmation binding
| Field | Description |
|-------|-------------|
| `preview_hash` | hash of the order parameters shown to the user |
| `preview_timestamp` | when previewed (freshness / staleness) |
| `confirmation` | bound to `preview_hash` (EXEC-002 AR-2009/2010) |

Any change to instrument, side, quantity, order_type, limit/stop price, time_in_force, account,
estimated_cost, risk_warning, or venue **invalidates the confirmation** and requires a fresh
preview and confirmation (EXEC-002 AR-2009).

## Placement (recorded when the user places the order)
| Field | Description |
|-------|-------------|
| `broker_order_id` | the order identifier the broker returns when the user places the order manually — the key for reconciling against the broker record (EXEC-002 AR-2012, links 4–5) |
| `placed_at` | timestamp at which the user placed the order |

Both are empty until the user places the order, and are **required before reconciliation links 4–5 can be walked**.

## State
`draft → previewed → confirmed → placed (by the user) → recorded → reconciled`; or
`expired` / `cancelled` / `rejected` / **`indeterminate`** (EXEC-002 AR-2004). Position State is
**derived** from ticket + fills (PROM-002), not stored on the ticket.

## Grounding (for replay/audit)
`thesis_id/version`, `opportunity_id/version`, `worldview_version`, `profile_version` — bound so
the ticket is replayable (EXEC-001 AR-1919). **Replay reconstructs the ticket; it never re-places
it** (EXEC-002 AR-2003).
