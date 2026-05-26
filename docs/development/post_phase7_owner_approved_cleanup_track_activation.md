# Post-Phase 7 Owner-Approved Cleanup Track Activation

Status: post_phase7_owner_approved_cleanup_track_activation.

This bundle activates the cleanup track only:

- feature selection paused
- no new feature development
- no business feature implementation
- no runtime route change
- no schema/migration
- no actual fallback removal
- no production_compat behavior change
- no wildcard production_compat cleanup
- no legacy runtime deletion
- delete_ready false

## Owner Request

The owner explicitly paused the post-Phase 7 new-feature path and requested an
owner-approved cleanup track for old-code retirement. This supersedes continuing
the HXC, Campaign, material-picker, or other new-feature selection path for now.

Post-Phase 7B PR #795 remains the intake baseline: it recorded candidates and
kept `selected_feature_status: pending_owner_selection` with
`implementation_authorized: false`. Post-Phase 7C PR #796 selected HXC as a
future feature candidate, but the owner now pauses that path before any feature
implementation starts.

## Cleanup Sequence

Cleanup must proceed by business path, not by broad folder deletion:

1. Confirm the route family no longer depends on old code.
2. Clean exact-route fallback.
3. Clean exact-route production_compat.
4. Recheck whether any legacy runtime is unreferenced.
5. Delete legacy runtime, template, or adapter only after route-specific
   evidence proves it is unused.
6. Record rollback, checker, tests, and evidence for every deletion.

## First Cleanup Candidates

- `task_groups_exact_route_fallback_cleanup`
- `task_groups_exact_route_production_compat_cleanup`
- `workflow_nodes_exact_route_fallback_cleanup`
- `workflow_nodes_exact_route_production_compat_cleanup`
- `dead_docs_checker_state_cleanup`
- `legacy_runtime_deletion_readiness_after_route_cleanup`

## Safety Boundary

This PR does not remove fallback, does not change production_compat behavior,
does not delete runtime, and does not set delete_ready. It only switches the
active state and guardrails to the owner-approved cleanup track.

High-risk paths remain excluded:

- Payment
- OAuth callback
- WeCom callback
- timer / run-due / automation execution
- outbound send
- public external submit
- wildcard production_compat cleanup

## Next PR Recommendation

- next: post_phase7_cleanup_task_groups_evidence_refresh_bundle
- route_family: /api/admin/automation-conversion/task-groups*
