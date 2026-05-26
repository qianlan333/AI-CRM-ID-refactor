# Phase 7F Production Compat Cleanup Readiness

## Summary

Phase 7F prepares production_compat cleanup without changing production_compat behavior. It records exact-route candidates, excludes wildcard and high-risk route families, and selects a first exact-route production_compat cleanup canary candidate for a later PR.

## Scope

- Build production_compat cleanup inventory from Phase 6H, Phase 6I, and Phase 7E readiness evidence.
- Require shadow compare evidence, rollback evidence, and route ownership proof before any future production_compat behavior change.
- Select `/api/admin/automation-conversion/task-groups*` as the first exact-route production_compat cleanup candidate because it matches the Phase 7E fallback candidate.
- Keep wildcard production_compat, fallback behavior, runtime code, timers, outbound sends, callbacks, payment paths, migrations, deploy files, and `delete_ready` unchanged.

## Selected Candidate

The first exact-route production_compat cleanup canary candidate is `task_groups_exact_route_production_compat_cleanup_canary` for `/api/admin/automation-conversion/task-groups*`.

This is a readiness selection only. Phase 7F does not change production_compat behavior.

## Exclusions

Wildcard production_compat, payment, OAuth callback, WeCom callback, timer/run-due, outbound send, public external submit, and any route lacking shadow compare plus rollback evidence are deferred.

## Next

The only allowed next bundle is `phase_7g_first_exact_route_fallback_removal_canary_bundle`.
