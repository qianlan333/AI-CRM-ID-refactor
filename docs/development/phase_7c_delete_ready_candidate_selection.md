# Phase 7C Delete Ready Candidate Selection

## Status

- status: phase_7c_delete_ready_candidate_selection
- bundle_type: phase_7c_delete_ready_candidate_selection_bundle
- cleanup_family: delete_ready_candidate_selection
- production behavior changed: false
- production_compat behavior changed: false
- fallback removed: false
- legacy runtime deleted: false
- delete_ready authorized: false

## Scope

Phase 7C selects and classifies cleanup candidates. It does not delete files, remove runtime fallback, change production_compat behavior, change route ownership, execute timers, send outbound traffic, or authorize `delete_ready`.

## Candidate Matrix

The matrix separates no-runtime docs/tooling cleanup from exact-route fallback cleanup, production_compat manifest cleanup, legacy runtime deletion, and unsafe/deferred candidates. Every candidate records evidence requirements, rollback strategy, owner approval requirement, and whether it is a delete_ready candidate. All runtime delete authorizations remain false.

## Suggested Phase 7D Candidate

The first Phase 7D candidate should be no-runtime docs/tooling/state cleanup or a legacy import checker baseline follow-up now that Phase 7B reduced direct import blockers to zero. It must not remove production fallback, change production_compat behavior, delete legacy runtime, or set `delete_ready: true`.

## Non-Goals

This bundle does not remove fallback, change production_compat behavior, delete runtime code, change deploy/nginx/systemd config, run destructive migrations, alter payment/OAuth/WeCom callback behavior, execute timers, run automation, or send outbound traffic.
