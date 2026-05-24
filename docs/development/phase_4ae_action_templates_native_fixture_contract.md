# Phase 4AE Action Templates Native Fixture Contract

## Status

Phase 4AE implements the Next native fixture/local contract for `/api/admin/automation-conversion/action-templates*`.

- Fixture/local Next native contract implementation.
- No production route owner switch.
- No production repository.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not change production ownership.

## Scope

In scope:

- `GET /api/admin/automation-conversion/action-templates`
- `POST /api/admin/automation-conversion/action-templates`
- Fixture/local in-memory repository only.
- CRM-local bounded metadata create only.

Out of scope:

- `POST /api/admin/automation-conversion/action-templates/generate`
- `POST /api/admin/automation-conversion/action-templates/from-workflow`
- Detail route.
- Update route.
- Delete route.
- Options/catalog route.
- DeepSeek / LLM adapter.
- Workflow execution.
- Outbound send.
- Timer.
- WeCom / OpenClaw / MCP.
- Customer pool state change.
- Production repository.
- Route owner switch.
- Fallback removal.
- `production_compat` change.

## Contract

### List

Request query:

- `template_source`
- `category`
- `keyword`
- `include_archived`
- `limit`
- `offset`

Response shape:

- `ok`
- `source_status`
- `route_owner`
- `items`
- `templates`
- `total`
- `count`
- `filters`
- `side_effect_safety`

### Create

Request body:

- `name` / `template_name`: required.
- `code` / `template_code`: optional; generated from name if omitted.
- `template_source`: must be `crm_local` for create.
- `category`
- `description`
- `status`: `active` or `archived`.
- `default_config`: JSON object.
- `ui_schema`: JSON object.
- `workflow_blueprint`: JSON object, metadata only.
- `node_blueprints`: JSON list, metadata only.
- `operator` / `created_by`.
- `idempotency_key`: required.

Response shape:

- `template`
- `audit_event`
- `rollback_payload`
- `idempotent_replay`
- `side_effect_safety`

Validation rejects dangerous fields anywhere in payload:

- `run_due`
- `execute`
- `execution`
- `send`
- `wecom`
- `openclaw`
- `mcp`
- `timer`
- `workflow_activation`
- `customer_pool_state_change`
- `outbound_task`
- `agent_runtime_execution`
- `deepseek`
- `llm`

### Idempotency

The fixture/local repository stores an idempotency record scoped by route family, operation, operator, and idempotency key.

- Same key and same request hash replays the stored response without creating another row.
- Same key and different request hash returns an idempotency conflict.

### Duplicate Protection

`template_code` must be unique inside the fixture/local repository. Duplicate codes are rejected.

### Audit And Rollback

Create emits a redacted audit event containing:

- before snapshot.
- after snapshot.
- request payload.
- validation result.
- rollback payload.
- side-effect safety evidence.

Rollback payload is metadata evidence only. This PR does not implement rollback execution.

### Side-Effect Safety

Every response includes safety values showing that no real external call, automation execution, outbound send, WeCom call, OpenClaw call, MCP call, LLM call, timer, or customer pool state change occurred.

### Production Guard

If `AICRM_NEXT_ENV=production` and this Next route is reached unexpectedly:

- `POST` returns degraded `503` / `production_repository_not_enabled`.
- Fixture/local repository success is blocked.
- Production path remains legacy fallback.

This PR does not modify `aicrm_next/main.py` or `aicrm_next/production_compat/api.py`.

## Business Continuity

本 PR 只实现 action-templates Next native fixture/local contract，不连接生产数据，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。production path 仍由 legacy fallback 保持。

## Phase 4AF Recommendation

Recommended next step:

- `local_parity_harness_or_repository_adapter_planning`

Phase 4AF may do local parity harness / repository adapter planning. It must not switch production owner, enable external calls, remove fallback, or authorize production writes.
