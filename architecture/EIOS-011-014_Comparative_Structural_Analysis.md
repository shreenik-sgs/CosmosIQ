# Comparative Structural Analysis — EIOS-011 … EIOS-014

**Status:** evidence document for the deferred review **ARB-012 — Intelligence Discipline
Architecture** · **Date:** 2026-06-30 · **Book:** v5.5

**This is evidence-gathering, not a redesign.** It compares the four domain intelligence
chapters authored so far to determine how strong the recurring pattern is. It changes nothing,
proposes no abstraction, and keeps ARB-012 deferred. The decision of whether to introduce an
"Intelligence Discipline" abstraction belongs to ARB-012, not here.

Chapters compared: **EIOS-011 Technology · EIOS-012 Economic · EIOS-013 Supply Network ·
EIOS-014 Capital** Intelligence.

---

## 1. The section skeleton is identical, position-for-position

Every one of the four chapters has the **same 19 `###` sections in the same order**. Only the
domain name and the five assessment sections (positions 6–10) vary.

| # | EIOS-011 | EIOS-012 | EIOS-013 | EIOS-014 | Invariant? |
|---|---|---|---|---|---|
| 1 | Purpose | Purpose | Purpose | Purpose | ✅ template |
| 2 | Conformance | Conformance | Conformance | Conformance | ✅ identical (000–010 + ADR-0008) |
| 3 | Conformance to the RI Contract | " | " | " | ✅ identical |
| 4 | Technology Domain Scope | Economic … | Supply Network … | Capital … | ✅ template |
| 5 | Grounding in Scientific Understanding | " | " | " | ✅ template |
| 6 | Technology Emergence | Economic Transition | Supply Structure | Capital Structure | ⬛ domain |
| 7 | Technology Readiness | Value Network | Supply Constraint | Capital Cycle | ⬛ domain |
| 8 | Technology Convergence | Capital Flow | Supply Fragility | Capital Concentration | ⬛ domain |
| 9 | Technology Constraint | Economic Constraint | Supply Transition | Capital Constraint | ⬛ domain |
| 10 | Technology Evolution | Economic Readiness & Timing | Supply Readiness & Timing | Capital Readiness & Timing | ⬛ domain |
| 11 | Cross-Domain … Influence | " | " | " | ✅ template |
| 12 | … Intelligence Products | " | " | " | ✅ template (compositions) |
| 13 | Continuous … Understanding | " | " | " | ✅ template |
| 14 | Purpose-Free … Intelligence | " | " | " | ✅ template (Capital +strict) |
| 15 | Handoff | Handoff | Handoff | Handoff | ✅ identical |
| 16–19 | Architectural Rules / Requirements Introduced / Future Dependencies / Cross References | " | " | " | ✅ structural tail |

**14 of 19 sections are invariant template; only 5 (positions 6–10) are domain-specific.**
≈74% of the chapter is template by section count.

## 2. The rule and requirement structure is parallel

Each chapter carries **exactly 14 Architectural Rules and 15 Requirements**, in parallel slots:

**Architectural Rules** (AR-`NN`01 … AR-`NN`14):
- `01` form Assessments about the domain, conforming to the RI contract
- `02` reference (not redefine) the Intelligence Assessment; introduce no new objects
- `03` ground in the worldview + Experience Layer; do not recompute
- `04–08` **domain assessment rules** (the variable five)
- `09` cross-domain influence via the Intelligence Graph
- `10` Products are compositions, no independent identity
- `11` purpose-free — understanding only
- `12` continuously evolving understanding
- `13` provide to the Intelligence Portfolio and Genesis; ground but never form opportunities
- `14` implementation independent

→ **9 of 14 rules are invariant** (`01–03`, `09–14`); 5 are domain assessment rules.

**Requirements** (REQ-`XX`-001 … 015) follow the identical pattern: 10 invariant slots
(001–004, 010–015) + 5 domain assessment slots (005–009).

## 3. Even the "variable" five have structure

Across the four domains, the five assessment slots are not arbitrary:

| Assessment theme | 011 | 012 | 013 | 014 | Coverage |
|---|---|---|---|---|---|
| **Constraint** | ✅ | ✅ | ✅ | ✅ | **universal** |
| **Readiness / Timing** | ✅ | ✅ | ✅ | ✅ | **universal** |
| Structure / Transition | (Evolution) | Transition | Structure + Transition | Structure | common |
| Domain-unique | Emergence, Convergence, Evolution | Value Network, Capital Flow | Fragility | Cycle, Concentration | domain |

**Two of the five assessment slots (Constraint, Readiness/Timing) are universal**; the rest are
structural or domain-unique. So even the variable core has a partial invariant.

## 4. Other recurring invariants
- **Conformance base is identical:** every domain engine conforms to EIOS-000…010 (the shared
  Reality Intelligence base), explicitly **not** to its sibling domain engines.
- **Grounding, not recomputation:** every chapter grounds in the worldview + Experience Layer
  assessments (ERS/RM/CRI/CAS/HAS/TTI, evolution analyses) and recomputes nothing.
- **One canonical object:** none introduces a new reasoning object; all produce Intelligence
  Assessments and compose them into (non-canonical) Products.
- **Per-discipline requirement namespace:** REQ-TI / REQ-EI / REQ-SN / REQ-CP — one namespace
  per domain engine, registered uniformly.
- **Purpose-free spine:** all four hold the understanding-only boundary; Capital states it with
  extra strictness (closest to investment).

## 5. Anomalies / open boundary questions (for ARB-012 to weigh)
- **Economic ↔ Capital overlap on "capital."** EIOS-012 has a *Capital Flow Assessment*; EIOS-014
  is a whole capital domain. Authored boundary: Capital Intelligence assesses the capital domain
  in its own right; Economic Intelligence assesses capital movement within economic understanding;
  they cross-influence. ARB-012 should confirm this boundary holds for a general discipline model.
- **Is the assessment count fixed at five?** It is five in all four, but that may be coincidence;
  a discipline abstraction would need to decide whether the count/shape is fixed or open.
- **Are Constraint and Readiness/Timing mandatory** for every discipline, or merely common so far?
- **Namespace scheme:** REQ-CP was chosen over REQ-CI to avoid colliding with the
  Constitutional-Invariant `CI` namespace — a discipline abstraction should specify a collision-safe
  naming rule for future disciplines (Energy, Healthcare, Defense, …).

## 6. Evidence verdict (not a decision)

**The recurring pattern is strong and consistent.** Across four independent domains:
- ~74% of sections are identical template (14/19),
- ~64% of rules are invariant (9/14),
- ~67% of requirements are invariant (10/15),
- the conformance base, grounding discipline, canonical-object usage, composition model,
  cross-domain mechanism, purpose-free boundary, and handoff are **the same in all four**,
- and even the variable core shares two universal assessment themes.

This is exactly the signature the ARB-012 hypothesis predicted: the domain engines look like
**instances of one template** — a candidate **Intelligence Discipline** — differing only in
domain scope, grounding sources, and a small assessment set.

## 7. What this implies — for ARB-012, deferred
If ARB-012 later confirms the abstraction, the natural shape (to be decided *there*, not here)
would be: an **Intelligence Discipline** defined once (likely in Reality Intelligence / EIOS-010),
which each domain chapter *instantiates* by supplying (a) its domain scope, (b) its grounding
sources, and (c) its assessment set — inheriting the entire invariant spine. New disciplines
(Energy, Healthcare, Defense) would then be added as instances, with no new reasoning objects and
no architectural change.

**That remains a hypothesis.** This document only establishes that the evidence now exists and is
strong. Per standing direction:
- ARB-012 stays **deferred**.
- EIOS-010 and ADR-0008 are **unchanged**.
- No abstraction is introduced now; authoring of further domain chapters (if any) continues in the
  current concrete style until ARB-012 is run.
