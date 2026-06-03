# WeCom Tag Write Route Inventory

Status: Group 13 closeout deletion_locked

This inventory covers the WeCom Tag CRUD and sync surfaces moved to Next CommandBus after the WeCom Tag Read legacy deletion was locked. Read routes stay `deletion_locked`; this closeout deletes the production_compat rollback for write/sync and locks exact write routes to Next CommandBus only.

## Frontend API Backend Contract Matrix

| Page entry | Frontend JS | Action | API | Method | Handler | Command | Registry | Manifest | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/wecom-tags` | `config_wecom_tags.html`; `wecom_tag_management.js` | 页面加载 | `/admin/wecom-tags`; read `/api/admin/wecom/tags`; read `/api/admin/wecom/tag-groups` | GET | `frontend_compat.legacy_routes`; `list_admin_wecom_tags_read_model`; `list_admin_wecom_tag_groups_read_model` | none | read routes `deletion_locked`; write closeout unaffected | read routes `next_exact` | page 200; not blank |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | create tag | `/api/admin/wecom/tags` | POST | `create_admin_wecom_tag_command` | `CreateWeComTagCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, `source_status=next_command`, `adapter_mode=real_blocked` |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | update tag | `/api/admin/wecom/tags/{tag_id}` | PUT or PATCH | `mutate_admin_wecom_tag_command` | `UpdateWeComTagCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, `fallback_used=false` |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | delete tag | `/api/admin/wecom/tags/{tag_id}` | DELETE | `mutate_admin_wecom_tag_command` | `DeleteWeComTagCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, `real_external_call_executed=false` |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | create group | `/api/admin/wecom/tag-groups` | POST | `create_admin_wecom_tag_group_command` | `CreateWeComTagGroupCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, `adapter_mode=real_blocked` |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | update group | `/api/admin/wecom/tag-groups/{group_id}` | PUT or PATCH | `mutate_admin_wecom_tag_group_command` | `UpdateWeComTagGroupCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, `fallback_used=false` |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | delete group | `/api/admin/wecom/tag-groups/{group_id}` | DELETE | `mutate_admin_wecom_tag_group_command` | `DeleteWeComTagGroupCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, no compatibility facade |
| `/admin/wecom-tags` | `wecom_tag_management.js` with generated `Idempotency-Key` | sync | `/api/admin/wecom/tags/sync` | POST | `sync_admin_wecom_tags_command` | `SyncWeComTagCatalogCommand` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | `next_command`, `legacy_fallback_allowed=false`, `deletion_locked` | 200, `sync_executed=false`, `local_only=true` |

No actual `/api/admin/wecom/tag-groups/sync` route exists in the current codebase, so it is not added as a Group 13 surface.

## Runtime Ownership

| Route | Methods | Registry runtime_owner | Manifest production_behavior | Rollback |
| --- | --- | --- | --- | --- |
| `/api/admin/wecom/tags` | POST, OPTIONS | `next_command` | `next_command` | production_compat rollback removed; `legacy_fallback_allowed=false` |
| `/api/admin/wecom/tags/{tag_id}` | PUT, PATCH, DELETE, OPTIONS | `next_command` | `next_command` | production_compat rollback removed; `legacy_fallback_allowed=false` |
| `/api/admin/wecom/tags/sync` | POST, OPTIONS | `next_command` | `next_command` | production_compat rollback removed; `legacy_fallback_allowed=false` |
| `/api/admin/wecom/tags/sync-due` | POST, OPTIONS | `next_command` | `next_command` | production_compat rollback removed; `legacy_fallback_allowed=false` |
| `/api/admin/wecom/tag-groups` | POST, OPTIONS | `next_command` | `next_command` | production_compat rollback removed; `legacy_fallback_allowed=false` |
| `/api/admin/wecom/tag-groups/{group_id}` | PUT, PATCH, DELETE, OPTIONS | `next_command` | `next_command` | production_compat rollback removed; `legacy_fallback_allowed=false` |
| `/api/admin/wecom/tags*` | POST, PUT, PATCH, DELETE, OPTIONS | `next_native` | `guarded_preview` | auxiliary out-of-scope Next subpaths only; no production_compat fallback |
| `/api/admin/wecom/tag-groups*` | POST, PUT, PATCH, DELETE, OPTIONS | `next_native` | `guarded_preview` | auxiliary out-of-scope Next subpaths only; no production_compat fallback |

Lifecycle for exact write routes is `delete_status=deletion_locked` and `replacement_status=locked`. The production_compat decorators for `/api/admin/wecom/tags`, `/api/admin/wecom/tags/{path:path}`, `/api/admin/wecom/tag-groups`, and `/api/admin/wecom/tag-groups/{path:path}` have been removed. The wildcard inventory rows now document auxiliary Next-owned out-of-scope surfaces, not legacy rollback.

## Backend Boundary

`aicrm_next/customer_tags/api.py` exposes `write_router` and registers exact write routes before `production_compat_router` in `aicrm_next/main.py`.

`aicrm_next/production_compat/api.py` no longer registers WeCom tag read/write/sync exact or family fallback routes.

`aicrm_next/customer_tags/commands.py` defines the write command shapes. `aicrm_next/customer_tags/admin_write.py` owns CommandBus dispatch, validation, idempotency, audit recording, production blocking, and response shape. `aicrm_next/customer_tags/write_repo.py` owns `WeComTagWriteRepository`, the local projection write fixture repository used by the blocked command path.

`aicrm_next/customer_tags/commands.py` defines the write command shapes. `aicrm_next/customer_tags/admin_write.py` owns CommandBus dispatch, validation, idempotency, audit recording, production blocking, and response shape. `aicrm_next/customer_tags/write_repo.py` owns the local projection write fixture repository.

Every successful command response must include `route_owner=ai_crm_next`, `source_status=next_command`, `fallback_used=false`, `real_external_call_executed=false`, `local_only=true`, and a `side_effect_plan` with `adapter_mode=real_blocked`.

## Guardrails

Real WeCom create/update/delete/sync is not executed in this group. The command layer records a `SideEffectPlan` and returns `sync_executed=false` for sync commands. Production data mode returns `production_unavailable` instead of fixture writes.

Frontend writes use `Idempotency-Key`; duplicate keys return the existing CommandBus result instead of creating duplicate audit/projection events.

Rollback would require restoring the removed production_compat decorators from a prior commit and changing registry/manifest lifecycle back to validating. The default rollback path should keep real WeCom execution blocked unless a separate live-adapter approval is granted.
