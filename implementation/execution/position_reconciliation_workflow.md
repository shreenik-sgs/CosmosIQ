# Position Reconciliation — workflow

The manual realization of **full-chain reconciliation** (EXEC-002 AR-2012/2013) and **indeterminate
resolution** (AR-2005). Reconciliation is the authority that converts recorded action into trusted
state; an **indeterminate** outcome is resolved *only* here, against the broker statement — never by
assumption.

## The chain (reconcile each link; surface any divergence)
1. intended action  ↔  Order Intent (the ticket)
2. Order Intent  ↔  Order Preview (parameters unchanged)
3. Order Preview  ↔  User Confirmation (bound)
4. User Confirmation  ↔  what the user placed
5. what the user placed  ↔  **broker acknowledgment** (the broker statement)
6. broker acknowledgment  ↔  fills recorded
7. fills  ↔  resulting position
8. resulting position  ↔  expected position (from the action)
9. execution outcome  ↔  Personal CIO / Prometheus records

## Procedure
1. Pull the **broker statement** — the authoritative record.
2. Walk the chain; mark each link `reconciled` or **`divergent`**.
3. Any divergence is recorded as an **Observation** and **halts dependent actuation** until
   resolved (AR-2013): do not place follow-on actions on an unreconciled position.
4. Resolve any **indeterminate** ticket by matching it to the statement (filled? not? partial?).
5. Update **Position State** (PROM-002) from the reconciled truth; append to the audit trail.

## Cadence
At minimum after every placement, and at end of session. Divergences and indeterminate resolutions
are first-class **Observations** that flow up as evidence (EXEC-001 AR-1913) — the system learns
from the gap between intended and actual.
