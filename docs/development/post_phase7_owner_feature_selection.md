# Post-Phase 7 Owner Feature Selection

Status: post_phase7_owner_feature_selection.

This bundle is selection and planning-entry only:

- no business feature implementation
- no runtime route change
- no schema/migration
- no production_compat route
- no `wecom_ability_service` new business logic
- no direct legacy import
- no fallback removal
- no production_compat behavior change
- no legacy runtime deletion
- delete_ready false

## Intake Handoff

Post-Phase 7B PR #795 created the first new feature intake matrix. It kept the
selected feature pending owner selection and did not authorize implementation.

The intake candidates were:

- `hxc_next_native_broadcast_backend`
- `campaign_step_standard_send_content_migration`
- `material_picker_remaining_surface_migration`

These are candidates only. They are not implemented features.

## Owner Selected Feature

Selected feature:

- selected_feature_id: hxc_next_native_broadcast_backend

Selection reason:

- It connects most directly to the current standard send-content component work.
- PR #786 established that the HXC funnel dashboard frontend can generate a
  `content_package`, while the real broadcast backend is not yet Next-native.
- It gives a clear business closure path: move from "frontend can configure
  broadcast content" toward "a Next-native backend can receive, validate, and
  produce dry-run, preview, or task evidence for the broadcast intent".
- Real WeCom sending must remain default-off and must not be enabled in the
  first implementation PR.

## Selected Feature Details

- feature_id: hxc_next_native_broadcast_backend
- feature_name: HXC Next-native broadcast backend
- business_goal: let HXC funnel dashboard broadcast actions stop depending on
  the old Flask broadcast interface and enter the Next-native standard
  send-content backend path
- user_visible_value: operators can configure broadcast content in the HXC
  dashboard with the unified standard content component, then have a
  Next-native backend receive, validate, and generate dry-run, preview, or task
  evidence
- capability_owner: aicrm_next.send_content
- route_family: /api/admin/hxc-dashboard/broadcast*
- feature_category: internal_write + external_adapter_preparation
- external_side_effect: true only for future live send, false in first
  implementation
- data_schema_impact: likely none for the first implementation unless existing
  tables already support package or evidence persistence
- production_risk: medium
- requires_feature_flag: true
- requires_canary: true before live send
- requires_owner_approval: true
- rollback_requirement: disable the Next-native HXC broadcast backend and retain
  legacy fallback
- recommended_first_implementation_bundle:
  post_phase7_hxc_next_native_broadcast_backend_plan_bundle

## Implementation Boundary

The first implementation PR may only create a plan, contract, or disabled
backend skeleton. It must not enable live send.

Forbidden in the first implementation PR:

- real WeCom send
- old Flask broadcast call
- production_compat new route
- `wecom_ability_service` new business logic
- timer / automation execution
- batch send execution
- direct legacy import
- media live upload
- payment / OAuth / callback side effects

## Next PR Recommendation

- next: post_phase7_hxc_next_native_broadcast_backend_plan_bundle
- route_family: /api/admin/hxc-dashboard/broadcast*

## Codex Prompt For Next Stage

```text
You are working in qianlan333/AI-CRM after Phase 7 and Post-Phase 7A/B/C.

Read first:
- docs/development/post_phase7_new_feature_development_rules.md
- docs/development/post_phase7_first_new_feature_intake.md
- docs/development/post_phase7_owner_feature_selection.md
- docs/route_ownership/production_route_ownership_manifest.yaml

Task:
- create the HXC Next-native broadcast backend plan/contract bundle
- keep implementation disabled by default
- do not enable real WeCom send
- do not call the old Flask broadcast path
- do not add production_compat routes
- do not add wecom_ability_service business logic
- do not add direct legacy imports
- include checker/tests and full PR lifecycle
```
