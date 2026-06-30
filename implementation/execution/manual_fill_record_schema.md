# Manual Fill Record — schema

The manual realization of **Fill = Observation** (EXEC-001 AR-1911) with **partial / multi-fill
aggregation** and **expiration** (EXEC-002 AR-2017/2019). The user records what actually happened
after placing the trade. Each fill is an **Observation of reality**, fed back up as evidence
(EXEC-001 AR-1913) — never as purpose. No new object: a fill is an Observation; the aggregate is a
derived view (EXEC-002 AR-2018/2021).

## Fill (one per execution event)
| Field | Description |
|-------|-------------|
| `fill_id` | stable id |
| `ticket_id` | the trade ticket placed |
| `fill_quantity` | quantity filled in this event |
| `fill_price` | price of this fill |
| `fill_time` | timestamp (from the broker) |
| `source` | manually entered / statement-confirmed |

## Aggregate (derived view over fills)
| Field | Description |
|-------|-------------|
| `cumulative_filled` | sum of `fill_quantity` |
| `remaining_quantity` | intended − `cumulative_filled` |
| `average_price` | quantity-weighted |
| `outcome` | working / partially_filled / filled / expired / cancelled / rejected / **indeterminate** |

## Outcomes (terminal, mutually exclusive)
- **filled** — cumulative = intended.
- **partially_filled** — 0 < cumulative < intended; remainder still working or cancelled.
- **expired** — time-in-force lapsed; **distinct** from cancel / reject / fail (EXEC-002 AR-2019).
- **cancelled / rejected** — recorded with reason (see `exception_failure_notes_schema.md`).
- **indeterminate** — outcome unknown (unsure it filled, platform glitch); resolved **only** by
  reconciliation against the broker statement (EXEC-002 AR-2004/2005), never assumed.

The aggregate updates **Position State** (PROM-002, derived) and is confirmed by reconciliation
(`position_reconciliation_workflow.md`).
