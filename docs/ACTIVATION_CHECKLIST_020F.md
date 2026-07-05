# Production 24×7 Activation Checklist — IMPLEMENTATION-020F

The formal, evidence-based checklist that decides whether CosmosIQ may be operated as production
24×7. Generate the evaluated form with:

```
python3 -m cosmosiq_ops prod-check --work-dir DIR --now <ISO-8601>
```

**Rule (unforgiving):**

```
production_mode_allowed = (no item is fail)
                      AND (no BLOCKING item is manual_review_required or fail)
                      AND operator_approval is a valid recorded approval
```

Every item below is **blocking**. Three items **cannot be machine-verified OFFLINE** and remain
`manual_review_required` until an operator satisfies them: `live_source_health`,
`operator_shadow_validation`, `operator_signoff`. So an honest OFFLINE evaluation refuses full
production and lands at **shadow 24×7 only** — the correct, safe default.

## Item fields

- **id** — stable check id.
- **section** — one of the 11 sections.
- **description** — what the item verifies.
- **status** — `pass` | `fail` | `not_applicable` | `manual_review_required`.
- **evidence_path** — where the supporting evidence lives.
- **blocking** — whether the item forbids production while unmet (all 020F items are blocking).
- **notes** — the machine result detail or the manual-review reason.

## The 11 sections and their items

| # | Section | id | Kind | Blocking |
|---|---|---|---|---|
| 1 | Build/Test | `suite_or_ci_gate` | machine | yes |
| 2 | Mode Configuration | `mode_state_machine` | machine | yes |
| 2 | Mode Configuration | `no_auto_promotion` | machine | yes |
| 3 | Source Configuration | `sec_adapter_offline_smoke` | machine | yes |
| 3 | Source Configuration | `live_source_health` | **manual** | yes |
| 4 | Scheduler/Service | `scheduler_dry_run` | machine | yes |
| 4 | Scheduler/Service | `service_wrapper_health` | machine | yes |
| 5 | Persistence/Replay | `replay_deterministic` | machine | yes |
| 6 | Trust/Data Quality | `dq_gate_pass` | machine | yes |
| 7 | Candidate Eligibility | `candidate_publication` | machine | yes |
| 8 | Alert Safety | `alert_safety_policy` | machine | yes |
| 9 | UI/Operator Surfaces | `no_trade_control` | machine | yes |
| 9 | UI/Operator Surfaces | `no_hidden_score` | machine | yes |
| 9 | UI/Operator Surfaces | `fixture_leakage` | machine | yes |
| 9 | UI/Operator Surfaces | `demo_byte_identical` | machine | yes |
| 9 | UI/Operator Surfaces | `operator_shadow_validation` | **manual** | yes |
| 10 | Security/Secrets | `secret_scan` | machine | yes |
| 11 | Runbook/Rollback | `rollback_docs` | machine | yes |
| 11 | Runbook/Rollback | `operator_signoff` | **manual** | yes |

## Sign-off template (record for the human approval)

```
approved_by:   <operator identity>
approved_at:   <ISO-8601 instant>
target_mode:   production_24x7
statement:     I have reviewed the completed shadow-validation run, confirmed live source
               health, and read the prod-check report. I approve PRODUCTION_24X7 activation.
```

Only with a valid recorded approval **and** every blocking item satisfied does
`production_mode_allowed` become `true` and `SHADOW_24X7 → PRODUCTION_24X7` promotion succeed.
