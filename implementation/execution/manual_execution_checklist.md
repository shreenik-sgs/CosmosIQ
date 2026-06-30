# Manual Execution Checklist — the Actuation Gate, performed by the user

The manual realization of the **Actuation Gate** (EXEC-001 AR-1907/1908), **stale-action
revalidation** (EXEC-002 AR-2007/2008), and **confirmation↔preview binding** (EXEC-002 AR-2009).
The user completes this checklist **before** placing the trade. No item may be skipped; an
incomplete checklist means **do not place** (EXEC-001 AR-1909). The Gate is the **sole path** to a
trade — there is no shortcut around the checklist (EXEC-002 AR-2011).

## Pre-placement checklist
1. **Idempotency** — this ticket is not already placed (no duplicate). — AR-2001
2. **Action current** — the Investment Action version still matches the queue item. — AR-2007
3. **Preview fresh** — the Order Preview has not expired. — AR-2007/2009
4. **Confirmation binds preview** — order parameters unchanged since preview; if any changed,
   re-preview and re-confirm. — AR-2009/2010
5. **Market moved?** — price within the previewed tolerance; if not, return to preview. — AR-2007/2008
6. **Account checks** — sufficient buying power / margin / cash. — AR-2007
7. **Instrument tradable** — not halted / restricted. — AR-2007
8. **Market hours** — the venue is open (or the user accepts queuing). — AR-2007 / EXEC-001 AR-1917
9. **Not disabled** — execution is not in disable-execution / kill-switch state. — AR-2007/2020
10. **Risk acknowledged** — slippage / fill-risk warning reviewed. — EXEC-001 AR-1916
11. **Explicit confirmation** — the user confirms the **exact** previewed ticket. — AR-1910/2010

If anything material changed at any step, the ticket **returns to preview / confirmation rather
than placement** (EXEC-002 AR-2008).

## After the checklist
The user places the trade manually in the broker platform, then records the outcome
(`manual_fill_record_schema.md`). The completed checklist — items, answers, timestamps — is
appended to the audit trail (`execution_audit_trail_schema.md`).

## Emergency
A standing **disable-execution** toggle and **human override** (the user simply does not place) are
always available (EXEC-002 AR-2020). The kill switch in manual mode: stop placing, manually
cancel-all open orders, and record the emergency in the audit trail.
