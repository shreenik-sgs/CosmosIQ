# Operator Guide — Learning & Feedback (Phase 017)

How to run the **learning loop** over your persisted Reality-Mesh stores: track outcomes,
journal a thesis so it becomes reviewable, and read the postmortem / red-team / timing /
expert-account / archetype reviews. Learning **observes** — it reads the persisted stores,
appends new records, and never edits a byte of history. Everything below is **operator-invoked**:
there is no daemon, no scheduler process, and nothing runs unless you run it.

Governance: `architecture/AGENT_MAP_012.md` §3.9 (Anubhava — Outcome Learning) ·
`docs/OPERATOR_GUIDE_013.md` (persistence/replay) · `docs/OPERATOR_GUIDE_015.md` (alerts) ·
`docs/OPERATOR_GUIDE_016.md` (the app, cockpits, diligence inputs).

---

## 1. The rules (they never bend)

- **Append-only; no history rewrite.** Every learning record is a NEW line in
  `outcome_store.jsonl` / `learning_store.jsonl` / `thesis_journal_store.jsonl`. A later
  resolution or re-review appends; the earlier line stays byte-unchanged forever.
- **No retroactive certainty.** No later observation → `unresolved`. A red-team warning with
  no matching later outcome → `unrealized`. Neither is ever guessed into an answer.
- **Labels + volume counts, not scores.** Reliability is `improving` / `stable` /
  `deteriorating` / `insufficient_history` plus counts. No ratio, percentage, or numeric
  metric field exists on any learning record (the store refuses such a key outright).
- **Unresolved / insufficient stays honest.** Below **3 resolved outcomes** (the 017 threshold,
  stored as data) every roll-up and review label reads `insufficient_history` (timing reads
  `unresolved`) — no label pretends confidence off a tiny sample.
- **Nothing here acts.** Learning produces records to read. There is no execution surface.

## 2. Track outcomes (run this first, after pulses have accumulated)

Outcome tracking compares each persisted claim (signal direction, theme-pulse state) in run N
against the same subject in run N+1 and appends one `OutcomeRecord` per claim:
`followed_through` / `contradicted` / `faded` / `unresolved`. It is a **one-shot operator
action** — run it whenever you want the learning layer to catch up (e.g. after your daily
pulse). Re-running is safe: ids are content-derived, so a re-track appends nothing.

```bash
PYTHONPATH=src python3 -c "
from reality_mesh import OutcomeTracker, emit_outcome_alerts
store = '<your persist dir>'; now = '2026-07-04T09:00:00Z'   # inject the instant yourself
outcomes = OutcomeTracker(store).track(now=now)
emit_outcome_alerts(store, outcomes, now=now)                # thesis_deteriorated / major_risk_emerged
print(len(outcomes), 'outcomes evaluated')"
```

Optional 017A roll-ups (per-discipline signal reliability, per-theme pulse accuracy,
per-source-tier reliability) are pure functions over those outcomes — see
`reality_mesh.learning`. Wiring tracking into the scheduled tick remains **deferred**; this
phase keeps it operator-invoked on purpose.

## 3. Journal a thesis (make it reviewable)

A postmortem reviews a **recorded** thesis run, not a memory of one. When the candidate
cockpit (OPERATOR_GUIDE_016 §3) shows a verdict you intend to stand behind, journal it —
quoting the engine's labels verbatim, labels and text only:

```bash
PYTHONPATH=src python3 -c "
from reality_mesh import journal_thesis
entry = journal_thesis('<your persist dir>',
    ticker='IREN',
    verdict_label='thesis_worthy',                  # quoted from the cockpit, verbatim
    timing_claimed='timing_not_confirmed',          # or 'timing_confirmed'
    recorded_at='2026-07-04T09:00:00Z',
    run_context='candidate cockpit render over diligence_inputs/IREN.json; theme physical-ai',
    invalidation_conditions=('Invalid if the physical-ai pulse reads state \'Breaking down\'',),
    monitoring_signals=('physical-ai breadth', 'IREN capacity announcements'),
    red_team_summary='Crowding risk in physical-ai; competition may erode IREN advantage')
print(entry.journal_id)"
```

Notes on the shape:
- `run_context`, `invalidation_conditions`, `monitoring_signals`, `red_team_summary` are the
  **matching surface**: reviews attach theme-pulse outcomes to the thesis only where the theme
  is explicitly named in this text, and signal outcomes only where the journaled ticker is
  among the signal's affected companies. Name your themes.
- Journaling the same ticker + `recorded_at` twice appends nothing; a fresh thesis run is a
  new entry. The cockpit MAY auto-journal in a later phase; today it is deliberate and manual.

## 4. Review (postmortem · red team · timing)

Run after tracking (§2). Each call appends **one** record to `learning_store.jsonl`
(idempotent — re-reviewing the same history leaves the store byte-identical) and returns it:

```bash
PYTHONPATH=src python3 -c "
from reality_mesh import review_thesis, review_red_team, review_timing
store, tid, now = '<your persist dir>', '<journal id from §3>', '2026-07-04T18:00:00Z'
pm = review_thesis(store, tid, now=now)
print(pm.postmortem_label); print(pm.basis)
rt = review_red_team(store, tid, now=now)
print(rt.review_label, len(rt.red_team_points_confirmed), 'confirmed')
tr = review_timing(store, tid, now=now)
print(tr.timing_label); print(tr.basis)"
```

How to read them:
- **Postmortem** — `thesis_held` / `thesis_weakened` / `thesis_broken` /
  `insufficient_history`, from outcome **volumes** (thresholds are data:
  `REVIEW_THRESHOLDS`). A journaled invalidation condition whose named state label was later
  persisted reads as *triggered* and the thesis is `thesis_broken` — that is what an
  invalidation condition means. Every `what_*` entry cites its `OutcomeRecord` id.
- **Red team** — each journaled point is `confirmed` **only** when a later persisted adverse
  outcome matches it by subject/theme (cited by id); otherwise `unrealized`. Unmatched is
  unmatched — the review never stretches a point onto an outcome it did not name.
- **Timing** — `early` (claimed confirmed, but adversity came first), `on_time`, `late`
  (claimed not-confirmed, yet follow-through was immediate), or `unresolved` (no resolved
  history, no follow-through, or under the threshold). The claim is judged against the
  persisted sequence only.

## 5. Expert-account reliability and archetypes

```bash
PYTHONPATH=src python3 -c "
from reality_mesh import roll_expert_reliability, roll_archetypes, append_experience_update
store, now = '<your persist dir>', '2026-07-04T18:00:00Z'
for r in roll_expert_reliability(store, now=now):
    print(r.account_handle, r.reliability_label, r.followed_through_count, r.contradicted_count)
for r in roll_archetypes(store, now=now):
    print(r.archetype_id, r.occurrences_count, r.archetype_label)
xp = append_experience_update(store, now=now)
print(xp.basis if xp else 'nothing to cite yet')"
```

- **Expert accounts** — a narrative signal's outcomes are attributed, via its cited source
  events, to the **social account** (`source_id`, e.g. an X handle) those events came from.
  Per account you get volume counts + the closed reliability label; under 3 resolved outcomes
  it reads `insufficient_history`. A loud account whose claims keep getting contradicted rolls
  up `deteriorating` — and is never retroactively upgraded; new evidence appends a new line.
- **Archetypes** — repeated persisted theme transitions (e.g. `theme_igniting_to_broadening`)
  become `ArchetypeUpdate` records with occurrence volumes. A pattern is *learned* only after
  it has recurred 3+ times; before that it is honestly `insufficient_history`.
- **Experience entry** — one dated note citing the persisted review record ids. Citation only;
  it adds no synthesis and is skipped entirely when there is nothing to cite.

## 6. What stays deferred

- **Auto-journaling** a thesis from the candidate cockpit (today: deliberate, manual §3).
- **Tick-wired outcome tracking** (today: the operator runs §2; the scheduled tick loop of
  OPERATOR_GUIDE_015 does not call learning).
- **Any UI surface** for reviews (a learning panel remains opt-in future work; default pages
  are byte-identical with or without this layer).
- **Anything that acts** on a review. A `deteriorating` account or a `thesis_broken`
  postmortem changes what you read, never what the system does.

## 7. Cross references
`docs/OPERATOR_GUIDE_013.md` (stores, append-only discipline) · `docs/OPERATOR_GUIDE_015.md`
(alert inbox — `thesis_deteriorated` / `major_risk_emerged` land there) ·
`docs/OPERATOR_GUIDE_016.md` (cockpits, diligence inputs) · `architecture/AGENT_MAP_012.md` §3.9.
