# Phase 7E Fallback Cleanup Readiness

## Summary

Phase 7E prepares fallback cleanup without removing any fallback. It defines route-specific evidence rules, excludes high-risk fallback families, and selects the first exact-route fallback cleanup canary candidate for a later PR.

## Scope

- Build fallback inventory categories from Phase 6 owner-switch evidence and Phase 7A/7C/7D cleanup planning.
- Require owner approval, rollback evidence, shadow compare evidence, and route ownership proof before any future fallback removal.
- Select one low-risk internal metadata route family for Phase 7G canary consideration.
- Keep all production fallback, production_compat behavior, runtime code, timers, outbound sends, callbacks, payment paths, migrations, deploy files, and `delete_ready` unchanged.

## Selected Candidate

The first exact-route fallback cleanup canary candidate is `task_groups_exact_route_fallback_cleanup_canary` for `/api/admin/automation-conversion/task-groups*`.

This is a readiness selection only. Phase 7E does not remove or disable the fallback.

## Exclusions

Payment, OAuth callback, WeCom callback, timer/run-due, outbound send, public questionnaire submit, wildcard fallback, and any route lacking rollback evidence are deferred.

## Next

The only allowed next bundle is `phase_7f_production_compat_cleanup_readiness_bundle`.
