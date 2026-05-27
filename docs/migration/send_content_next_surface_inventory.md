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
- `POST /api/admin/hxc-dashboard/broadcast-tasks`

## New Frontend Assets

- `aicrm_next/frontend_compat/static/admin_console/send_content_composer.js`
- `aicrm_next/frontend_compat/static/admin_console/send_content_composer.css`
- `aicrm_next/frontend_compat/static/admin_console/material_picker.js`
- `aicrm_next/frontend_compat/static/admin_console/material_picker.css`
- `aicrm_next/frontend_compat/templates/admin_console/_automation_operation_orchestration_panel.html`
- `aicrm_next/frontend_compat/templates/admin_console/group_ops.html`
- `aicrm_next/frontend_compat/static/admin_console/group_ops.js`
- `aicrm_next/frontend_compat/templates/admin_console/channel_code_form.html`
- `aicrm_next/frontend_compat/static/admin_console/channel_admission_pages.js`

## Migrated Surfaces

- Automation operation send-content configuration is migrated to `AICRMSendContentComposer`.
- HXC dashboard broadcast is migrated to `AICRMSendContentComposer` plus Next-native `/api/admin/hxc-dashboard/broadcast-tasks`.
  - The HXC outer page owns `audience_filter`, `selected_customer_ids`, `sender_userid`, `source_id`, and `idempotency_key`.
  - The standard component owns only `content_text` plus image, miniprogram, and attachment library IDs.
  - The Next-native API creates an internal task with `dispatch_status=pending_external_dispatch`; it does not upload WeCom media or pretend a real send succeeded.
- Channel code center welcome copy and materials are migrated to `AICRMSendContentComposer`.
  - The outer channel page still owns channel name, channel code, channel type, owner, entry tag, and link/qrcode fields.
  - The standard component owns only welcome copy plus local image, miniprogram, and attachment IDs.
  - The short-term save adapter maps `content_text` to `welcome_message`, `image_library_ids` to `welcome_image_library_ids`, `miniprogram_library_ids` to `welcome_miniprogram_library_ids`, and `attachment_library_ids` to `welcome_attachment_library_ids`.
- 群运营计划标准编排动作: 已迁移到 `AICRMSendContentComposer`。
  - 外层页面仍负责第几天、时间、动作标题、排序、状态、节点/动作 id。
  - 标准组件负责标准话术、图片素材、小程序素材、附件/PDF 素材。
  - `content_package_json` 是标准组件的保存结构；legacy `node_attachments` / `attachments` 仅兼容旧数据和发送 fallback，不再作为运营输入项。
  - 本迁移不改变真实企微发送、media_id 解析或群消息下发链路。

## Explicit Non-Surfaces

This work does not add or rewrite:

- `wecom_ability_service/http/*`
- `wecom_ability_service/domains/*`
- `production_compat` routes
- legacy facade routes
- old Flask operation task routes
- legacy HXC broadcast backend routes such as `/api/admin/hxc-dashboard/broadcast`
- real WeCom send, upload, media resolution, or outbound task execution

## Ownership Boundary

`SendContentPackage` is the standard component's only backend contract. The component emits text and three local material ID arrays. The automation operation page owns strategy-level decisions: `content_mode`, selected profile template, default behavior rule, and `agent_code`.

HXC / funnel dashboard broadcast now has a Next-native task creation API. Real outbound dispatch, media upload, and media ID resolution remain separate explicit work and must not be hidden behind the old Flask broadcast route.

Campaign step and Sidebar integration are also left for the next frontend integration pass. Channel code center entry tags remain a separate outer-page picker and are not part of `SendContentPackage`.
