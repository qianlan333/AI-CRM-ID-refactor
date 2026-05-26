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

## New Frontend Assets

- `aicrm_next/frontend_compat/static/admin_console/send_content_composer.js`
- `aicrm_next/frontend_compat/static/admin_console/send_content_composer.css`
- `aicrm_next/frontend_compat/static/admin_console/material_picker.js`
- `aicrm_next/frontend_compat/static/admin_console/material_picker.css`
- `aicrm_next/frontend_compat/templates/admin_console/_automation_operation_orchestration_panel.html`

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

Campaign step and Sidebar integration are also left for the next frontend integration pass. This PR provides the standard component and automation operation page integration only.
