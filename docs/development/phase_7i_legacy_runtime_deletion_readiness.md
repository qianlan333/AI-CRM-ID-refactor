# Phase 7I Legacy Runtime Deletion Readiness

Status: readiness only. This bundle does not delete legacy runtime, Flask routes,
templates, production fallback, or production_compat entries.

## Summary

Phase 7I inventories legacy runtime deletion readiness after the Phase 7G and
Phase 7H canaries. The selected task-groups fallback removal canary remains
blocked, and the matching production_compat cleanup canary remains blocked. That
means no runtime module can be safely deleted in this bundle.

## Scope

- Legacy runtime usage inventory.
- Route ownership usage matrix.
- Fallback usage matrix.
- Production_compat usage matrix.
- Test usage matrix.
- Import graph summary.
- Delete candidate matrix.
- Unsafe and deferred candidate matrix.
- First runtime cleanup candidate selection.
- Checker, tests, and phase state.

## Runtime Usage Inventory

| Area | Current usage | Phase 7I classification |
| --- | --- | --- |
| `wecom_ability_service` runtime modules | Still imported by explicit legacy runner and fallback surfaces | unsafe_to_delete |
| Legacy Flask routes/templates | Still required by retained fallback and production_compat forwards | unsafe_to_delete |
| `aicrm_next/production_compat` route forwards | Still active and wildcard/exact cleanup is blocked | deferred_until_production_compat_cleanup |
| `aicrm_next/integration_gateway` references | Boundary references remain intentional after Phase 7B | needs_more_evidence |
| Tests referencing legacy modules | Still used for compatibility and checker evidence | needs_more_evidence |
| Route ownership manifest entries | Many route families still record production_compat or legacy fallback ownership | deferred_until_fallback_removed |

## Candidate Matrix

| Candidate | Category | Evidence requirement | Decision |
| --- | --- | --- | --- |
| `task_groups_legacy_runtime_modules` | deferred_until_fallback_removed | Phase 7G fallback removal must execute and rollback evidence must exist | not safe for deletion |
| `task_groups_production_compat_forward` | deferred_until_production_compat_cleanup | Phase 7H exact-route production_compat cleanup must execute | not safe for deletion |
| `wecom_ability_service_live_callback_runtime` | deferred_due_to_external_side_effect | WeCom callback ownership and live callback evidence | unsafe_to_delete |
| `payment_runtime_modules` | deferred_due_to_external_side_effect | Payment owner approval, sandbox evidence, rollback | unsafe_to_delete |
| `oauth_callback_runtime` | deferred_due_to_external_side_effect | OAuth callback route ownership and rollback evidence | unsafe_to_delete |
| `media_upload_runtime` | needs_more_evidence | Upload ownership evidence and no public publish regression | not selected |
| `timer_execution_runtime` | deferred_due_to_external_side_effect | Timer/run-due execution approval | unsafe_to_delete |
| `public_questionnaire_submit_runtime` | deferred_due_to_external_side_effect | Public submit ownership and no production-write regression | unsafe_to_delete |

## First Runtime Cleanup Candidate Selection

No runtime cleanup candidate is selected for deletion. The recommended next
bundle is a blocker acceptance package that records the retained fallback and
production_compat blockers before any runtime deletion work.

## Safety

- legacy runtime deletion authorized: false
- fallback removal authorized: false
- production_compat behavior change authorized: false
- destructive migration authorized: false
- delete_ready: false

## Rollback

Rollback is a normal git revert of this readiness-only package. Since no runtime
code changes, route changes, production_compat changes, or fallback removals are
included, production behavior is unchanged.

