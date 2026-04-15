# CRM Automation Workflow MCP Tools

## Available Tools

### `crm.automation.get_workflow_registry`

Use this to discover valid enum values before creating data.

Returns at least:

- `audiences`
- `segmentation_bases`
- `generation_modes`
- `node_trigger_modes`
- `workflow_statuses`

### `crm.automation.list_workflows`

Lists workflow bundles. Each bundle already includes:

- workflow metadata
- audiences
- workflow-level agent bindings
- nodes

Optional input:

```json
{
  "include_archived": false,
  "status": "draft"
}
```

### `crm.automation.get_workflow_nodes`

Required input:

```json
{
  "workflow_id": 12
}
```

### `crm.automation.create_workflow`

Minimum safe payload:

```json
{
  "workflow_name": "新客欢迎流",
  "workflow_code": "welcome_flow",
  "status": "draft",
  "segmentation_basis": "none",
  "generation_mode": "manual_layered",
  "audiences": ["operating"]
}
```

Allowed values:

- `status`: `draft`, `active`, `paused`
- `segmentation_basis`: `none`, `profile`, `behavior`
- `generation_mode`: `manual_layered`, `auto_layered_rewrite`, `personalized_single`
- `audiences`: `pending_questionnaire`, `operating`, `converted`

Notes:

- `profile_segment_template_id` is required only when `segmentation_basis = profile`.
- `agent_bindings` are required only for non-manual generation modes.

### `crm.automation.create_workflow_node`

Minimum safe payload for an immediate-on-entry text node:

```json
{
  "workflow_id": 12,
  "node_name": "欢迎首触达",
  "node_code": "welcome_touch_1",
  "target_audience_code": "operating",
  "trigger_mode": "audience_entered",
  "content_mode": "standard_direct",
  "standard_content_text": "欢迎加入，我们先带你完成第一步设置。"
}
```

Allowed values:

- `target_audience_code`: must belong to the workflow's audiences
- `trigger_mode`: `scheduled`, `audience_entered`
- `content_mode`: `standard_direct`, `manual_layered`, `standard_layered_rewrite`, `personalized_single`
- `segmentation_basis`: `none`, `profile`, `behavior`

Extra rules:

- If `trigger_mode = scheduled`, both `day_offset` and `send_time` are required.
- If `content_mode = standard_direct`, `standard_content_text` is required.
- If `content_mode = manual_layered`, `content_variants` are required.
- If `content_mode = standard_layered_rewrite` or `personalized_single`, valid `agent_bindings` are required.
