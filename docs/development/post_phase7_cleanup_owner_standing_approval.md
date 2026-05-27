# Post-Phase 7 Cleanup Owner Standing Approval

## Status

- status: `post_phase7_cleanup_owner_standing_approval`
- owner: qianlan
- approval source: chat owner standing approval on 2026-05-27
- scope: route-by-route cleanup of replaced and unused low/medium-risk legacy fallback code
- global delete_ready: false
- broad runtime deletion authorized: false

## Approved Route Families

This standing approval covers normal low/medium-risk exact-route cleanup when replacement evidence is complete for:

- `/api/admin/automation-conversion/task-groups*`
- `/api/admin/automation-conversion/workflow-nodes*`
- `/api/admin/automation-conversion/tasks*`
- `/api/admin/automation-conversion/workflows*`
- `/api/admin/automation-conversion/agents*`
- `/api/admin/automation-conversion/agent-outputs*`
- `/api/admin/automation-conversion/agent-runs*`
- `/api/admin/automation-conversion/action-templates*`
- `/api/admin/automation-conversion/profile-segment-templates*`
- other internal admin routes proven equivalent by checker/tests

## Required Gates

Codex may delete a production_compat or fallback entry only after the exact route surface has Next-native replacement, checker/tests pass, manifest/backlog evidence is updated, rollback is documented, and unrelated routes are retained.

## Non-goals

This approval does not authorize deleting `wecom_ability_service/`, deleting `legacy_flask_app.py`, deleting `wildcard_router`, broad fallback removal, high-risk payment/OAuth/WeCom/public-submit/timer/outbound cleanup, live external side effects, or setting global `delete_ready: true`.

Runtime deletion may only be proposed after a recheck proves there are no production_compat, fallback, import, manifest, test, or runtime references for the selected slice.
