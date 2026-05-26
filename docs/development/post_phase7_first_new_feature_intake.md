# Post-Phase 7 First New Feature Intake

Status: post_phase7_first_new_feature_intake.

This bundle is intake only:

- no runtime change
- no business feature implementation
- no production_compat route
- no `wecom_ability_service` new business logic
- no direct legacy import
- no fallback removal
- no production_compat behavior change
- no legacy runtime deletion
- delete_ready false

## Phase 7 / Post-Phase 7A Handoff

Phase 7 is complete. Fallback, production_compat, and legacy runtime are
retained. delete_ready remains false. Future cleanup requires separate owner
approval and route-specific evidence.

Post-Phase 7A established that new feature development must use Next-native
owners, must not use production_compat as the primary path, must not add new
`wecom_ability_service` business routes, must not add direct legacy imports, and
must include owner, tests, checker, rollback, and business continuity evidence.

## Intake Purpose

This PR establishes the first standard intake table for future feature work. It
records candidate sources, capability owner, route family, feature category, risk
level, external side-effect status, feature flag/canary/rollback requirements,
the likely first implementation bundle, and the Codex prompt shape for the next
stage.

This PR does not select or implement a feature. Owner selection is required
before a business implementation plan can start.

## Feature Intake Matrix

Candidate sources for later owner selection:

- user requested feature
- product backlog feature
- existing Next-native send content continuation
- automation conversion UI improvement
- HXC Next-native broadcast backend
- campaign step standard component migration
- admin_user_ops material picker migration
- workflow_nodes material picker migration
- owner-approved cleanup track

| feature_id | feature_name | business_goal | user_visible_value | capability_owner | route_family | feature_category | external_side_effect | data_schema_impact | production_risk | requires_feature_flag | requires_canary | requires_owner_approval | rollback_requirement | recommended_first_implementation_bundle | blocked_reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hxc_next_native_broadcast_backend | HXC Next-native broadcast backend / standard send content continuation | Move broadcast backend intake toward Next-native ownership while keeping real send default-off | Operators get a governed path toward standard send-content backend parity | aicrm_next.automation_engine | /api/admin/send-content* | external_adapter | yes, outbound send risk | none in intake | high | true | true | true | keep existing fallback/legacy path; disable new send path by default | post_phase7_hxc_broadcast_backend_plan_bundle | owner_selection_required |
| campaign_step_standard_send_content_migration | Campaign Step standard send content component migration | Continue standard send-content UI migration where legacy picker logic remains | Campaign steps can eventually share the standard content component | aicrm_next.frontend_compat | /admin/automation-conversion/campaign* | frontend_component | no by intake; future send path must stay gated | none in intake | medium | false unless paired with send behavior | true for rollout | true | revert UI integration; retain existing legacy screen behavior | post_phase7_campaign_step_component_plan_bundle | owner_selection_required |
| material_picker_remaining_surface_migration | Remaining material picker surface migration | Replace remaining direct miniprogram-library fetch surfaces with Next-native picker/options | Admin users get consistent material selection UX | aicrm_next.frontend_compat | admin_user_ops / workflow_nodes material picker surfaces | frontend_component | no | none in intake | medium | false | true | true | revert component migration; retain legacy screen only if explicitly marked | post_phase7_material_picker_migration_plan_bundle | owner_selection_required |
| owner_approved_cleanup_track | Owner-approved cleanup track | Separate future cleanup from feature work | Cleanup happens only with explicit approval and evidence | selected_by_owner | selected_by_owner | cleanup | no by default | none in intake | high | n/a | n/a | true | restore retained fallback/production_compat/runtime state | post_phase7_owner_approved_cleanup_plan_bundle | not_selected_for_feature_intake |

## Default First Candidate Recommendation

First priority recommendation: `hxc_next_native_broadcast_backend`.

Reason: the standard send-content frontend work has moved forward, while real
broadcast backend ownership still needs Next-native intake. Any real sending
must remain default-off and owner-approved.

Second priority recommendation:
`campaign_step_standard_send_content_migration`.

Reason: the prior standard send-content work left Campaign Step picker and
attachment logic as a follow-up candidate. It is suitable as a frontend
component migration intake, not as a send execution change.

Third priority recommendation:
`material_picker_remaining_surface_migration`.

Reason: remaining surfaces still need intake before migrating away from direct
legacy material-library fetches toward `AICRMMaterialPicker` or a Next-native
options API.

These are intake recommendations only. Real implementation requires owner
confirmation. This PR implements none of the candidates.

## Selected First Feature

- selected_feature_status: pending_owner_selection
- selected_feature_id: none
- implementation_authorized: false
- owner_selection_required: true

## Next PR Recommendation

Because no owner selected a feature in this task:

- next: post_phase7_owner_feature_selection_bundle

## Codex Prompt For Next Stage

```text
You are working in qianlan333/AI-CRM after Phase 7 and Post-Phase 7A.

Read first:
- docs/development/post_phase7_new_feature_development_rules.md
- docs/development/post_phase7_first_new_feature_intake.md
- docs/route_ownership/production_route_ownership_manifest.yaml
- docs/development/legacy_replacement_backlog.yaml

Task:
- select exactly one owner-approved feature candidate
- record capability owner and route family
- do not implement business runtime
- do not add production_compat routes
- do not add wecom_ability_service business logic
- do not add direct legacy imports
- keep fallback, production_compat, legacy runtime retained
- produce a plan/checker/test bundle with full PR lifecycle
```
