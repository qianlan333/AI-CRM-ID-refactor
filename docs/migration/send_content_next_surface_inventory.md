# Send Content Next Surface Inventory

## New Next-Native Surfaces

- `POST /api/admin/send-content/validate`
- `POST /api/admin/send-content/preview`
- `GET /api/admin/material-picker/items`
- `GET /api/admin/automation-conversion/tasks/{task_id}`
- `PUT /api/admin/automation-conversion/tasks/{task_id}`
- `PUT /api/admin/automation-conversion/tasks/{task_id}/send-strategy`
- `PUT /api/admin/automation-conversion/tasks/{task_id}/send-content/unified`
- `PUT /api/admin/automation-conversion/tasks/{task_id}/send-content/profile-segments/{segment_key}`
- `PUT /api/admin/automation-conversion/tasks/{task_id}/send-content/behavior-segments/{segment_key}`
- `PUT /api/admin/automation-conversion/tasks/{task_id}/send-content/agent-materials`
- `GET /api/admin/automation-conversion/behavior-segment-rules`

## Explicit Non-Surfaces

This work does not add or rewrite:

- `wecom_ability_service/http/*`
- `wecom_ability_service/domains/*`
- `production_compat` routes
- legacy facade routes
- old Flask operation task routes
- HXC broadcast backend routes such as `/api/admin/hxc-dashboard/broadcast`
- real WeCom send, upload, media resolution, or outbound task execution

## Ownership Boundary

`SendContentPackage` is the standard component's only backend contract. The component emits text and three local material ID arrays. The automation operation page owns strategy-level decisions: `content_mode`, selected profile template, default behavior rule, and `agent_code`.

HXC / funnel dashboard broadcast remains out of scope for this phase. If a Next-native HXC broadcast backend is needed later, it should be implemented in a separate PR with explicit outbound safety gates.

