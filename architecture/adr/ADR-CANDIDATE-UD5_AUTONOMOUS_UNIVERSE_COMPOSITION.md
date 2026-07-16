# ADR-CANDIDATE-UD5 — Autonomous Universe Composition: the Engine Composes Its Own Universe

Status: **RETIRED — ACCEPTED as ADR-0011** (`ARCHITECTURE_DECISIONS.md`). This candidate is kept for
its rationale and open questions; the binding decision is ADR-0011, which additionally bounds the
universe by real chokepoint occupancy (open question 3, settled by the architect) and holds that
membership is never a claim about return.
Date: proposed during UNIVERSE-DISCOVERY UD-5 · Supersedes: none · Related: ADR-0010
(cognition–actuation boundary), ADR-0001 (specification is the single source of truth),
UD-1 (`reality_mesh/universe_discovery.py`), UD-3 (`reality_mesh/accepted_universe.py`),
UD-4 (`reality_mesh/dynamic_universe.py`).

> This is a **candidate** for architect review. It does not modify the frozen ADR register and
> does not increment the next-ADR number. If accepted, it should be entered as a formal ADR with
> the next available number (currently ADR-0011) and this candidate retired.

## Context

CosmosIQ was built to find what is worth watching. UD-4 says so without hedging: it is *"the slice
that ENDS hand-curation."* Yet the universe the system actually watches today is eight tickers and
three themes, typed by a human into a launchd argument vector:

```
--live-watchlist NVDA,AVGO,COHR,LITE,VRT,OKLO,IREN,AAOI
--live-themes    physical-ai,ai-accelerators,optics
```

The discovery machinery exists and works. Run live against real credentials, `discover_via_fmp_screener`
returns fifty grounded candidates from a sector query, and `discover_via_sec_fulltext` returns nineteen
from a theme phrase — each carrying a real `sec:fts/<accession>` or `fmp:screener/<sector>` reference,
and each honestly reporting the hits it could not map rather than guessing a ticker. The engine can see.

It simply has nowhere to put what it sees. Three gaps separate the capability from the product:

1. **Discovery is unreachable and unpersisted.** UD-1's producers return in-memory dataclasses. No CLI
   invokes them; no store records them. Nothing in `cosmosiq_service`, `cosmosiq_pulse`, or
   `cosmosiq_app` calls them. Discovery is a library function waiting for a caller that was never
   written.
2. **The universe store has never existed.** `accepted_universe.jsonl` is absent from every store in
   the repository. `accepted_watchlist(store_dir)` therefore returns `()`, and — correctly, by UD-4's
   own honesty rule — *never* falls back to a seed. The dynamic universe has never once been populated.
3. **Acceptance refuses to run unattended.** `accept_universe_entry` requires an `accepted_by` human
   name and states: *"the engine NEVER auto-accepts and NEVER auto-fills a field."*

The third gap is the load-bearing one, and it is the reason this is an architectural decision rather
than a defect report. The first two are unwritten code. The third is a rule.

**That rule is presently defined nowhere but a docstring.** It appears in no specification file, no
architecture contract, and no ADR. Under ADR-0001 — *"Architecture is never defined in code"* — a
constraint of this weight living only in `accepted_universe.py` is already drift. Whatever is decided
here, the decision belongs in the register.

### The category error

ADR-0010 drew the one threshold this system treats as absolute, and drew it with care:

> **What can be undone may be done freely; what cannot be undone must be gated.**
>
> *Every act so far — to observe, to model, to hypothesize, to assess, to recommend, to personalize —
> is reversible. A belief can be revised, a judgment withdrawn, a recommendation replayed and remade,
> and the world is none the wiser. Thought leaves no mark.*

Ask what kind of act it is to admit a ticker into the universe.

It places no capital. It sends no order. It touches no venue. It changes nothing outside the
repository, and the world does not learn of it. The store that holds it is append-only with
`correction_of`, so a later record can supersede it and the reasoning stands corrected at no cost but
the correcting. Admitting a ticker is a **belief about what merits attention** — and by ADR-0010's own
account, a belief is exactly the thing that may be revised freely, because it leaves no mark.

The human gate on `accept_universe_entry` is an actuation-grade gate applied to a cognitive act. It
is the discipline ADR-0010 reserved for irreversible deeds, spent on a reversible thought. The result
is not additional safety — it is a system that cannot use the sight it was built to have, while the
mark it was protecting against was never at risk.

This candidate holds that the gate is in the wrong place, and that ADR-0010 is not being overturned
here but applied correctly for the first time.

### What the gate was right about

One thing the current design protects is genuinely worth protecting, and it must survive intact.

`accepted_by` is an **attestation**. It records *who judged this worth watching*. The reason
`accept_universe_entry` refuses to run unattended is not really that acceptance is dangerous — it is
that an unattended acceptance would have to write *somebody's name* into a decision they never made.
That is not caution about capital; it is a refusal to forge a signature. It is the same principle
behind the PL-2 operator-attestation work: a record of a human judgment must correspond to a human
judgment.

Automating the decision is safe. Automating the *signature* is not. The distinction is the whole of
this decision.

## Decision

**Universe composition is cognition. The engine SHALL compose its own universe, and SHALL attribute
its own judgments to itself.**

**1. The engine MAY accept autonomously.** An evidence-grounded candidate MAY enter the accepted
universe without a human in the loop. Universe membership is a reversible belief and is governed as
cognition, not as actuation.

**2. The evidence gate is untouched.** Only a candidate GROUNDED against a real source (SEC / FMP)
may be accepted. An ungrounded candidate, an unverified suggestion, or a hit with no ticker mapping
is REFUSED — as it is today. Autonomy removes the human from the decision; it removes nothing from
the evidence. **No fabrication, no fixture-as-real, no guessed ticker.** What could not be accepted
by a human on the evidence SHALL NOT be accepted by the engine on the same evidence.

**3. Attribution SHALL be truthful.** `accepted_by` SHALL name the principal that actually decided.
An engine acceptance SHALL be attributed to the engine and the policy under which it acted — never
to a person. The system SHALL NOT write a human's name into a decision that human did not make.
Machine and human acceptances SHALL remain distinguishable in the store for all time, so that any
reader can ask *who judged this* and receive a true answer.

**4. Reversibility SHALL be preserved and is the operator's standing power.** Every engine
acceptance remains correctable: the operator MAY reject or supersede any entry via `correction_of`,
and a human correction SHALL outrank an engine acceptance. The operator's authority moves from
*gatekeeper of every entry* to *editor of the whole*, which is the authority appropriate to a
reversible act at scale.

**5. The actuation boundary is reaffirmed, not weakened.** A ticker in the universe is not a
position. Nothing here permits capital to move. Every irreversible action continues to pass the
ADR-0010 gate in full. This decision widens what the system may *think about*; it widens nothing
about what it may *do*.

**6. Direction is not curation.** Discovery is steered by a mandate — a sector, a theme, a phrase
— and a mandate is not a watchlist. Naming *silicon photonics* as worth investigating states an
interest and leaves the engine to find who matters; naming *LITE, COHR, AAOI* states the answer and
leaves the engine nothing to find. The former is legitimate architectural input and SHALL be
specified rather than passed as a deployment argument. The latter is the practice this decision
ends. **A hardcoded ticker list SHALL NOT be a supported means of setting the universe.**

## Consequences

- The launchd deployment stops carrying `--live-watchlist`. The service resolves its scope from the
  accepted universe (`--live-accepted-watchlist`).
- Discovery gains a caller: a persisted, invokable path from producers to the accepted universe,
  runnable on a tick.
- `accept_universe_entry` gains a truthful machine principal. It does **not** lose its grounding
  validation.
- The store becomes mixed-provenance. Every reader — cockpit included — must be able to show whether
  a ticker was admitted by the engine or by a person, and under what policy.
- The universe becomes larger and more volatile than eight hand-typed names. Governing it becomes a
  matter of the mandate and the correction record, not of the argument vector.
- A rule that lived only in a docstring becomes an architectural decision, closing an ADR-0001 drift.

## Open questions for the architect

1. **Where does the mandate live?** Sectors/themes must be specified somewhere — `config/`, the
   specification, or a store. Today `--live-themes` is a deployment argument, which §6 says it should
   not be.
2. **What is the machine principal's form?** A reserved `accepted_by` value, or a new explicit field
   (e.g. `accepted_by_kind: engine | operator`)? A new field is cleaner and unambiguous, but changes
   the record schema.
3. **What bounds an autonomous sweep?** Fifty candidates from one sector query is a large jump from
   eight. Per-tick caps, a review queue, or unbounded?
4. **Does an engine acceptance need a confidence floor** beyond "grounded" — or is grounded the bar,
   as it is for humans today?
5. **Retirement:** may the engine also *reject* — dropping a ticker that no longer merits attention —
   or is removal reserved to the operator?
