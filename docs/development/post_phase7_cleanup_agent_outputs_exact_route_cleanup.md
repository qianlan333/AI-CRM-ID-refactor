# Post-Phase 7 Agent-Outputs Exact-Route Cleanup

## Status

- status: `post_phase7_cleanup_agent_outputs_exact_route_cleanup`
- route family: `/api/admin/automation-conversion/agent-outputs*`
- selected exact route: `/api/admin/automation-conversion/agent-outputs`
- owner standing approval: granted by qianlan
- runtime deletion: not authorized
- wildcard cleanup: not authorized
- delete_ready: false

## Cleanup Result

This PR removes only the exact production_compat decorator for `/api/admin/automation-conversion/agent-outputs`.

The wildcard production_compat entry `/api/admin/automation-conversion/agent-outputs/{path:path}` remains retained because export/detail subpath behavior still needs separate route-specific proof before any broader cleanup.

## Evidence

- Next-native exact route exists: `GET /api/admin/automation-conversion/agent-outputs`
- Existing route tests cover the Next-native list route and production repository unavailable payload.
- Agent-output side-effect safety remains false for live external calls, timer execution, outbound send, run execution, export/download, and writes.
- Manifest/backlog notes record this exact-entry cleanup while keeping the route family guarded.

## Production Behavior

Only the selected exact list route changes owner from production_compat forwarding to the existing Next-native implementation. Subpaths remain production_compat guarded.

## Non-goals

This PR does not delete runtime code, does not remove wildcard routing, does not remove agent-output subpath fallback, does not touch payment/OAuth/WeCom/public-submit/timer/outbound paths, and does not enable global delete readiness.

## Rollback

Rollback is `git revert <this-cleanup-merge-commit>`, restoring the single exact production_compat decorator.

## Next

Run `post_phase7_cleanup_legacy_runtime_recheck_bundle`. Runtime deletion remains blocked unless the follow-up recheck proves no production_compat, fallback, import, manifest, test, or runtime references for a selected slice.
