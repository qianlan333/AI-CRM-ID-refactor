# WeCom Tag Write Route Inventory

Status: Group 13 validating

This inventory covers the WeCom Tag CRUD and sync surfaces moved to Next CommandBus after the WeCom Tag Read legacy deletion was locked. Read routes stay `deletion_locked`; this group keeps production_compat rollback for write/sync while the exact write routes resolve to Next first.

## Frontend API Backend Contract Matrix

| Frontend surface | User action | Next API | Method | Command | Repository | Side effect |
| --- | --- | --- | --- | --- | --- | --- |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 新增标签 | `/api/admin/wecom/tags` | POST | `CreateWeComTagCommand` | `WeComTagWriteRepository.create_tag` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `real_external_call_executed=false` |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 编辑标签 | `/api/admin/wecom/tags/{tag_id}` | PUT or PATCH | `UpdateWeComTagCommand` | `WeComTagWriteRepository.update_tag` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `real_external_call_executed=false` |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 删除标签 | `/api/admin/wecom/tags/{tag_id}` | DELETE | `DeleteWeComTagCommand` | `WeComTagWriteRepository.delete_tag` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `real_external_call_executed=false` |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 新增标签组 | `/api/admin/wecom/tag-groups` | POST | `CreateWeComTagGroupCommand` | `WeComTagWriteRepository.create_group` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `real_external_call_executed=false` |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 编辑标签组 | `/api/admin/wecom/tag-groups/{group_id}` | PUT or PATCH | `UpdateWeComTagGroupCommand` | `WeComTagWriteRepository.update_group` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `real_external_call_executed=false` |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 删除标签组 | `/api/admin/wecom/tag-groups/{group_id}` | DELETE | `DeleteWeComTagGroupCommand` | `WeComTagWriteRepository.delete_group` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `real_external_call_executed=false` |
| `/admin/wecom-tags` via `config_wecom_tags.html` and `wecom_tag_management.js` | 同步企微标签 | `/api/admin/wecom/tags/sync` | POST | `SyncWeComTagCatalogCommand` | `WeComTagWriteRepository.sync_catalog` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `sync_executed=false` |
| Historical due-sync entrypoint | 同步企微标签 | `/api/admin/wecom/tags/sync-due` | POST | `SyncWeComTagCatalogCommand` | `WeComTagWriteRepository.sync_catalog` | `SideEffectPlan` only, `adapter_mode=real_blocked`, `sync_executed=false` |

No actual `/api/admin/wecom/tag-groups/sync` route exists in the current codebase, so it is not added as a Group 13 surface.

## Runtime Ownership

| Route | Methods | Registry runtime_owner | Manifest production_behavior | Rollback |
| --- | --- | --- | --- | --- |
| `/api/admin/wecom/tags` | POST, OPTIONS | `next_command` | `next_command` | `legacy_fallback_allowed=true`, `legacy_source=production_compat` |
| `/api/admin/wecom/tags/{tag_id}` | PUT, PATCH, DELETE, OPTIONS | `next_command` | `next_command` | `legacy_fallback_allowed=true`, `legacy_source=production_compat` |
| `/api/admin/wecom/tags/sync` | POST, OPTIONS | `next_command` | `next_command` | `legacy_fallback_allowed=true`, `legacy_source=production_compat` |
| `/api/admin/wecom/tags/sync-due` | POST, OPTIONS | `next_command` | `next_command` | `legacy_fallback_allowed=true`, `legacy_source=production_compat` |
| `/api/admin/wecom/tag-groups` | POST, OPTIONS | `next_command` | `next_command` | `legacy_fallback_allowed=true`, `legacy_source=production_compat` |
| `/api/admin/wecom/tag-groups/{group_id}` | PUT, PATCH, DELETE, OPTIONS | `next_command` | `next_command` | `legacy_fallback_allowed=true`, `legacy_source=production_compat` |
| `/api/admin/wecom/tags*` | POST, PUT, PATCH, DELETE, OPTIONS | `production_compat` | `legacy_forward` | retained rollback family for fake-stub write, live mark/unmark, and other subpaths |
| `/api/admin/wecom/tag-groups*` | POST, PUT, PATCH, DELETE, OPTIONS | `production_compat` | `legacy_forward` | retained rollback family for other tag-group subpaths |

Lifecycle for exact write routes is `delete_status=next_primary_with_legacy_rollback` and `replacement_status=validating`. The retained wildcard rollback families stay `delete_status=active` and `replacement_status=validating`.

## Backend Boundary

`aicrm_next/customer_tags/api.py` exposes `write_router` and registers exact write routes before `production_compat_router` in `aicrm_next/main.py`.

`aicrm_next/customer_tags/commands.py` defines the write command shapes. `aicrm_next/customer_tags/admin_write.py` owns CommandBus dispatch, validation, idempotency, audit recording, production blocking, and response shape. `aicrm_next/customer_tags/write_repo.py` owns the local projection write fixture repository.

Every successful command response must include `route_owner=ai_crm_next`, `source_status=next_command`, `fallback_used=false`, `real_external_call_executed=false`, `local_only=true`, and a `side_effect_plan` with `adapter_mode=real_blocked`.

## Guardrails

Real WeCom create/update/delete/sync is not executed in this group. The command layer records a `SideEffectPlan` and returns `sync_executed=false` for sync commands. Production data mode returns `production_unavailable` instead of fixture writes.

Frontend writes use `Idempotency-Key`; duplicate keys return the existing CommandBus result instead of creating duplicate audit/projection events.

The retained rollback is registry/manifest-only for the exact routes and still available through production_compat family records. Rollback means removing the Next write router registration or changing route order back to production_compat first; it does not require deleting the Group 13 command modules.
