# Operator Guide 020E — Alert Delivery Channels

IMPLEMENTATION-020E adds the **first alert-delivery path**: a delivery **abstraction**, an
in-app **inbox/file** channel (the safe default), and an **email** channel that in tests uses an
injected transport / dry-run and never touches the network.

A delivered alert is a **notification of an observation** — it is never an instruction to act.
CosmosIQ **observes; it never trades.** Execution stays **Manual Review Only** and there is no
broker connection anywhere in this system.

## The abstraction

`src/reality_mesh/alert_delivery.py`:

- **`AlertDeliveryChannel`** (ABC) — `deliver(alert, *, mode, now) -> AlertDeliveryResult`, plus
  `channel_id` and `is_external`.
  - **`InboxChannel`** — the safe default. Marks the alert delivered to the in-app inbox.
    Always allowed, in every mode. Reaches no network.
  - **`EmailChannel(transport=None, *, sender_present=None, dry_run=True)`** — the first external
    channel. `smtplib` is imported **only inside `_send`** (never at module top). A `transport`
    callable is injectable so tests never hit the wire; `dry_run` (default) renders the message
    without sending. The email credential is a **presence label only** — read lazily, never
    stored or echoed.
- **`AlertDeliveryPolicy`** — the per-mode channel rules + the high-severity gate.
- **`AlertDeliveryResult`** (frozen) — one sanitized attempt: `alert_id`, `channel`, `status`,
  `mode`, `attempted_at`, `detail_sanitized`, `retry_count`. Never a secret, never a trade word.
- **`AlertDeliveryStore`** (`alert_delivery_store.jsonl`) — every attempt persisted
  **append-only**. Re-delivering appends a new line; prior lines are byte-unchanged.
- **`deliver_alert(alert, *, policy, mode, channels, store_dir, now)`** — applies the policy,
  delivers via the allowed channels, persists each result, returns the tuple.

## Delivery statuses (closed vocabulary)

`not_delivered`, `delivered`, `suppressed_by_mode`, `suppressed_by_policy`, `failed_retryable`,
`failed_permanent`.

## Per-mode policy

| Mode | In-app inbox | External (email) |
|------|--------------|------------------|
| `OFF` | delivered | **suppressed_by_mode** — no continuous delivery |
| `MANUAL` | delivered | **suppressed_by_mode** — manual-run alerts stay in the inbox only |
| `SHADOW_24X7` | delivered (marked Shadow Mode) | **suppressed_by_mode** unless `shadow_delivery_enabled` is set; a shadow message is always clearly labelled Shadow Mode |
| `PRODUCTION_24X7` | delivered | **suppressed_by_policy** until the Phase-020F activation gate passes (020F is not built yet, so production external delivery stays suppressed) |

The safe default policy (`AlertDeliveryPolicy.default()`) has `shadow_delivery_enabled=False` and
`production_activated=False`: **no external delivery at all**.

## Severity model + high-severity gating

The delivery-side severity ladder is `{info, watch, review_required, critical}` (the 015C alert
record vocabulary stays frozen; the incoming severity is mapped onto this ladder for display and
gating). A **`critical`** delivery requires **all** of:

- a healthy / approved DQ state,
- **non-speculative** authority (not a social / rumor category),
- a `run_id` (provenance of the producing run),
- at least one evidence reference.

An unsupported `critical` is **capped to `review_required`**. A social/rumor-only **or** DQ-failed
input can therefore **never** be delivered as a critical production action — only a lower-severity
narrative/crowding watch.

## Forbidden language

No delivered alert (inbox or email subject/body) may contain buy/sell/order/submit/auto-trade/
auto-rebalance/broker-submit/"strong buy"/"guaranteed upside" language. The 020D
`FORBIDDEN_ALERT_PHRASES` set is swept over the subject and body (scrub + a construction guard).

## Email configuration (presence-only)

The real SMTP path reads these environment variables **lazily inside `_send`**, as presence
labels only — a value is never stored, logged, or echoed:

- `COSMOSIQ_ALERT_EMAIL_SENDER` — the sender credential (presence-only).
- `COSMOSIQ_ALERT_EMAIL_HOST` — the SMTP host.
- `COSMOSIQ_ALERT_EMAIL_RECIPIENT` — the recipient.

A missing sender credential yields a labelled `not_delivered` result (no value echoed) — a
visible gap, never a crash, never a fabricated send.

### Disable / unsubscribe

To stop email alerts, set delivery to **inbox-only** in operator settings, or **unset**
`COSMOSIQ_ALERT_EMAIL_SENDER`. The default configuration is inbox-only.

## Safety invariants (permanent)

- No network on import — `smtplib` is imported only inside the email send method; tests inject a
  transport or use dry-run; the real SMTP path is never exercised offline.
- All delivery attempts are persisted **append-only**; no secret appears in delivered content,
  logs, or stored results.
- Delivery is notification only — nothing here places, orders, or changes anything. Execution
  stays Manual Review Only; there is no broker connection.
