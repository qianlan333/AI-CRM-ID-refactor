# Phase 4AF Action Templates Local Parity Harness

## Status

Phase 4AF adds a local fixture parity harness for `/api/admin/automation-conversion/action-templates*`.

- Local fixture parity harness.
- No production data.
- No production repository.
- No production route owner switch.
- No `production_compat` change.
- Legacy fallback retained.
- No external calls.
- No automation execution.
- `delete_ready`: false.

Current production behavior remains legacy `production_compat` fallback / `legacy_forward`. This PR does not change production ownership.

## Harness Matrix

The harness is `tools/run_phase4af_action_templates_local_parity.py`.

Read/list coverage:

- `GET /api/admin/automation-conversion/action-templates` returns `ok`.
- deterministic fixture seed exists.
- filters are accepted when supported.
- response includes `side_effect_safety`.
- response does not expose a route-level legacy facade owner header.

Create coverage:

- creates a `crm_local` template with an idempotency key.
- replays the same idempotency key with the same payload.
- rejects the same idempotency key with a different payload.
- rejects duplicate `template_code`.
- rejects missing `name` / `template_name`.
- rejects invalid `status`.
- rejects dangerous fields anywhere in the payload.
- emits an audit event.
- includes rollback payload.
- keeps side-effect safety values false.
- blocks fixture write success in production mode.

## Evidence Boundaries

This harness produces fixture/local evidence only.

- It is not production read parity.
- It is not production approval.
- It is not canary evidence.
- It is not route-switch readiness.
- It does not connect to production data.
- It does not call legacy Flask services.
- It does not call `wecom_ability_service` runtime.
- It does not call DeepSeek / LLM / external adapters.
- It does not call generate or from-workflow routes.
- It does not execute automation workflow.
- It does not send outbound messages.

## Repository Adapter Planning Gate

Phase 4AG may plan a production repository adapter only after this local parity harness passes.

- Production adapter must remain opt-in.
- Production route owner switch remains forbidden.
- Fallback removal remains forbidden.
- Production write canary remains forbidden.
- External calls remain forbidden.

## Business Continuity

本 PR 只实现 action-templates local fixture parity harness，不连接生产数据，不写生产，不启用 production repository as route owner，不切 production route owner，不删除 legacy fallback，不修改 production_compat，不影响当前自动化运营配置日常业务使用。production path 仍由 legacy fallback 保持。

## Phase 4AG Recommendation

Recommended next step:

- `production_repository_adapter_planning`

Phase 4AG can plan the action-templates production repository adapter, but it must not implement production repository behavior, switch production owner, enable external calls, remove fallback, or authorize production writes.
