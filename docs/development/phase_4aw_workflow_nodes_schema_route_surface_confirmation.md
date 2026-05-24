# Phase 4AW Workflow Nodes Schema / Route Surface Confirmation

## Status

Phase 4AW confirms the legacy route surface and schema references for `/api/admin/automation-conversion/workflow-nodes*`.

This package is documentation, checker, test, and state only. It does not implement runtime code, connect to staging or production databases, write production data, change `production_compat`, switch route ownership, remove the legacy fallback, execute workflow nodes, run timers, send outbound messages, or enable external calls.

## Route Surface

The current production route owner remains `aicrm_next.production_compat` with legacy forwarding behavior.

- `/api/admin/automation-conversion/workflow-nodes/{path:path}` remains registered through the legacy automation workspace route.
- Methods remain inherited from `_ALL_METHODS`: GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD.
- No new route is added and no existing business route is removed or modified.

## Schema Surface

The primary metadata table for this route family is `automation_workflow_node`.

Required columns confirmed from `wecom_ability_service/schema_postgres.sql`:

- `id`
- `workflow_id`
- `node_code`
- `node_name`
- `target_audience_code`
- `trigger_mode`
- `day_offset`
- `send_time`
- `timezone`
- `position_index`
- `enabled`
- `created_at`
- `updated_at`

Required indexes confirmed:

- `uq_automation_workflow_node_code`
- `idx_automation_workflow_node_position`
- `idx_automation_workflow_node_schedule`

Related tables remain deferred until a later owner-approved scope:

- `automation_workflow_node_content`
- `automation_workflow_node_content_variant`
- `automation_workflow_node_transition`
- `automation_workflow_execution`
- `automation_workflow_execution_item`
- `automation_frequency_budget`

## Boundary

Phase 4AW is a schema and route confirmation package for workflow-node metadata only. It prepares the next fixture/native contract planning step without authorizing runtime implementation.

Deferred:

- workflow activation
- workflow execution
- node transition runtime behavior
- timer execution
- outbound send
- real external calls
- update/delete route expansion
- production repository route enablement
- production route ownership switch
- production write
- fallback removal

## Business Continuity

Current production traffic remains on the legacy `production_compat` fallback path. This package does not alter the automation operations page/API behavior, does not connect to production data, and does not affect daily automation configuration usage.

## Next Step

Phase 4AX may plan the workflow-nodes fixture/native metadata contract. It must remain planning-only unless the owner explicitly authorizes runtime implementation in a later package.
