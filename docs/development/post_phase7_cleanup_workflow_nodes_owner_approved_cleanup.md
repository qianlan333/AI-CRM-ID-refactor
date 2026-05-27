# Post-Phase 7 Workflow-Nodes Owner-Approved Cleanup

## Status

- status: post_phase7_cleanup_workflow_nodes_owner_approved_cleanup
- route family: `/api/admin/automation-conversion/workflow-nodes*`
- owner approval: granted by qianlan from chat_owner_confirmation_2026-05-27
- rollback owner: qianlan
- selected cleanup: remove only the workflow-nodes production_compat entry
- runtime deletion: not authorized
- wildcard cleanup outside workflow-nodes: not authorized
- delete_ready: false

## Replacement Routes

The selected fallback was removed only after the Next-native route surface was present for the workflow-nodes family:

- `GET /api/admin/automation-conversion/workflow-nodes`
- `POST /api/admin/automation-conversion/workflow-nodes`
- `GET /api/admin/automation-conversion/workflows/{workflow_id}/nodes`
- `POST /api/admin/automation-conversion/workflows/{workflow_id}/nodes`
- `PUT /api/admin/automation-conversion/workflow-nodes/{node_id}`
- `DELETE /api/admin/automation-conversion/workflow-nodes/{node_id}`

Delete is implemented as safe archive/tombstone behavior. It does not hard-delete legacy runtime files and does not trigger workflow execution, timers, outbound sends, WeCom calls, OpenClaw/MCP calls, payment/OAuth behavior, or public-submit behavior.

## Selected Deletion

Only this selected production_compat decorator was removed:

```python
@router.api_route("/api/admin/automation-conversion/workflow-nodes/{path:path}", methods=_ALL_METHODS)
```

Unrelated production_compat routes, `wildcard_router`, legacy runtime files, payment/OAuth/WeCom/public-submit/timer/outbound behavior, and all rollback paths remain retained.

## Business Continuity

- selected exact route only: true
- unrelated production_compat routes retained: true
- legacy runtime retained: true
- production repository unavailable payload retained: true
- fallback broad cleanup executed: false
- wildcard cleanup executed: false
- runtime deletion executed: false
- delete_ready: false

## Rollback

Rollback is `git revert <this-cleanup-merge-commit>`, which restores the selected decorator and leaves the Next-native replacement in place for comparison.

## Next Bundle

If this PR merges, the next bundle is `post_phase7_cleanup_legacy_runtime_recheck_bundle`. Runtime deletion remains blocked until that recheck proves no fallback, production_compat, manifest, test, or import references remain.
