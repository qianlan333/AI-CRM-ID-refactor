# Media Library Route Inventory

Scope: Legacy Exit group 16 validates the media library admin pages, API routes, storage adapter boundary, and route precedence on top of `origin/main` at PR #1006 (`acdac47d`). It does not remove legacy fallback code in this group, does not enable real external object storage, and does not execute real WeCom media upload.

Route precedence check:

- `aicrm_next.main.create_app()` currently registers `production_compat_router` before `media_library_router`, but `aicrm_next.production_compat.api` has no media-library exact route or broad `/api/admin/{path:path}` route that can catch media library requests.
- `media_library_router` is registered before `frontend_compat_router` and `production_compat_wildcard_router`.
- `tools/check_production_route_resolution.py` samples every media library API family plus the three admin pages; `tests/test_production_route_resolution.py` asserts they resolve to `aicrm_next.media_library.api` or `aicrm_next.frontend_compat.legacy_routes`, not production_compat.

Storage and side-effect boundary:

- Multipart image/attachment upload writes the media-library repository row and inline/local payload only. It does not call cloud storage or WeCom media upload.
- `from-url`, `from-base64`, and data-url upserts use guarded adapters only. Fake/staging adapters are allowed for tests and local smoke, but response metadata exposes `source_status`, adapter mode, idempotency keys, `fallback_used=false`, and `real_external_call_executed=false`.
- Remote source URLs are stored as references for fake/staging import metadata; thumbnail and variant read paths must not fetch remote URLs directly. If an image has only `source_url` and no local payload/variant, the route returns a controlled contract error instead of making an HTTP client call.
- Production real external storage and WeCom media upload remain `real_blocked` unless explicitly enabled by adapter flags. The API must not hide fake/staging adapter output as real production storage.
- Upload, import, and delete responses include a `side_effect_plan` or guarded adapter audit/idempotency metadata. Thumbnail and variant routes are binary responses with route-owner/fallback/real-call headers.
- Smoke payloads use a valid 1x1 PNG fixture for multipart upload. `from-base64` accepts both `data_base64` and compatible `data_url`; miniprogram create uses canonical `appid` and also accepts `app_id`.

## Frontend ↔ API ↔ Backend Contract Matrix

| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | Repo/Storage | 外部副作用 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/image-library` | `aicrm_next/frontend_compat/templates/admin_console/image_library.html` | list | `/api/admin/image-library?limit=80...` | GET | `list_images` | `ListMediaItemsQuery("image")` -> `MediaLibraryRepository.list_items` | none | `tests/test_media_library_next_contract.py` |
| `/admin/image-library` | `image_library.html` | facets | `/api/admin/image-library/facets` | GET | `list_image_facets` | `ListMediaFacetsQuery("image")` -> repo facets | none | `tests/test_media_library_next_contract.py` |
| `/admin/image-library` | `image_library.html` | detail modal preview from list metadata | `/api/admin/image-library/{image_id}` | GET | `get_image` | `GetMediaItemQuery("image")` -> repo item | none | `tests/test_media_library_next_contract.py`, `tests/test_media_library_variants.py` |
| `/admin/image-library` | `image_library.html` | create/update metadata | `/api/admin/image-library`, `/api/admin/image-library/{image_id}` | POST/PUT | `create_image`, `update_image` | `UpsertMediaItemCommand("image")` -> repo save | guarded adapter only if payload contains data URL; otherwise local row write | `tests/test_media_library_next_contract.py` |
| `/admin/image-library` | `image_library.html`, `static/admin_console/image_picker.js` | upload button / picker upload | `/api/admin/image-library/upload` | POST | `upload_image` | `UploadImageCommand` -> repo save inline/local payload | no cloud storage, no WeCom media upload; `side_effect_plan` returned | `tests/test_media_library_next_contract.py`, `tests/test_image_library_template.py`, `tests/test_image_upload_client_static.py` |
| `/admin/image-library` | API-only; no visible page button | import remote URL | `/api/admin/image-library/from-url` payload `{url,name}` | POST | `image_from_url` | `ImportImageFromUrlCommand` -> guarded cloud/wecom adapters + repo save | fake/staging adapter visible in tests; remote URL is not fetched; real external default blocked | `tests/test_media_library_next_contract.py`, `tests/test_media_library_no_real_external_calls.py` |
| `/admin/image-library` | API-only; used by tests and tooling | import base64 | `/api/admin/image-library/from-base64` payload `{data_base64,name}` or compatible `{data_url,name}` | POST | `image_from_base64` | `ImportImageFromBase64Command` -> guarded cloud/wecom adapters + repo save | fake/staging adapter visible in tests; real external default blocked | `tests/test_media_library_next_contract.py`, `tests/test_media_library_variants.py`, `tests/test_media_library_no_real_external_calls.py` |
| `/admin/image-library` | `image_library.html` | delete / force delete | `/api/admin/image-library/{image_id}` | DELETE | `delete_image` | `DeleteMediaItemCommand("image")` -> repo delete with reference guard | no external delete; returns `side_effect_plan`; force clears local references only | `tests/test_media_library_next_contract.py`, `tests/test_image_library_hard_delete.py` |
| `/admin/image-library` | `image_library.html`, `image_picker.js` | thumbnail fallback | `/api/admin/image-library/{image_id}/thumbnail?size=160/320/720` | GET | `get_image_thumbnail` | `GetImageThumbnailQuery` -> repo thumbnail/variant bytes | none; binary route-owner headers; no remote `source_url` HTTP fetch | `tests/test_media_library_next_contract.py`, `tests/test_media_library_variants.py`, `tests/test_media_library_no_real_external_calls.py` |
| `/admin/image-library` | `image_library.html`, `image_picker.js` | variant image URL | `/api/admin/image-library/{image_id}/variants/{variant_key}` | GET | `get_image_variant` | `GetImageVariantQuery` -> repo variant bytes | none; binary route-owner headers | `tests/test_media_library_next_contract.py`, `tests/test_media_library_variants.py` |
| `/admin/attachment-library` | `aicrm_next/frontend_compat/templates/admin_console/attachment_library.html` | list | `/api/admin/attachment-library?limit=300...` | GET | `list_attachments` | `ListMediaItemsQuery("attachment")` -> repo list | none | `tests/test_media_library_next_contract.py` |
| `/admin/attachment-library` | API-only on this page | create metadata | `/api/admin/attachment-library` | POST | `create_attachment` | `UpsertMediaItemCommand("attachment")` -> repo save | guarded adapter only if payload contains base64; otherwise local row write | `tests/test_media_library_next_contract.py` |
| `/admin/attachment-library` | `attachment_library.html`, `radar_link_form.html` | upload | `/api/admin/attachment-library/upload` | POST | `upload_attachment` | `UploadAttachmentCommand` -> repo save inline/local payload | no cloud storage, no WeCom media upload; `side_effect_plan` returned | `tests/test_media_library_next_contract.py` |
| `/admin/attachment-library` | `attachment_library.html` | detail from list card | `/api/admin/attachment-library/{attachment_id}` | GET | `get_attachment` | `GetMediaItemQuery("attachment")` -> repo item | none | `tests/test_media_library_next_contract.py` |
| `/admin/attachment-library` | `attachment_library.html` | update metadata / enabled | `/api/admin/attachment-library/{attachment_id}` | PUT | `update_attachment` | `UpsertMediaItemCommand("attachment")` -> repo save | local row write only unless data payload carries base64 | `tests/test_media_library_next_contract.py` |
| `/admin/attachment-library` | `attachment_library.html` | delete | `/api/admin/attachment-library/{attachment_id}` | DELETE | `delete_attachment` | `DeleteMediaItemCommand("attachment")` -> repo delete | no external delete; `side_effect_plan` returned | `tests/test_media_library_next_contract.py` |
| `/admin/miniprogram-library` | `aicrm_next/frontend_compat/templates/admin_console/miniprogram_library.html` | list | `/api/admin/miniprogram-library?enabled_only=false` | GET | `list_miniprograms` | `ListMediaItemsQuery("miniprogram")` -> repo list | none | `tests/test_media_library_next_contract.py`, `tests/test_miniprogram_library_template.py` |
| `/admin/miniprogram-library` | `miniprogram_library.html` | create | `/api/admin/miniprogram-library` payload canonical `{appid,page_path,title,thumb_image_id}`; compatible `{app_id,pagepath}` accepted | POST | `create_miniprogram` | `UpsertMediaItemCommand("miniprogram")` -> repo save | thumbnail resolve may use cache or guarded adapter; real production media upload blocked | `tests/test_media_library_next_contract.py`, `tests/test_miniprogram_library_template.py` |
| `/admin/miniprogram-library` | `miniprogram_library.html` | update metadata / thumb image reference / enabled | `/api/admin/miniprogram-library/{item_id}` payload canonical `{appid,page_path,thumb_image_id}`; compatible `{app_id,pagepath,thumb_media_id}` accepted | PUT | `update_miniprogram` | `UpsertMediaItemCommand("miniprogram")` -> repo save | local row write; `thumb_image_id` is the local image reference; `thumb_media_id` is preserved only as a WeCom media id cache and is not validated as a local image | `tests/test_media_library_next_contract.py`, `tests/test_miniprogram_library_template.py` |
| `/admin/miniprogram-library` | `miniprogram_library.html`, `admin_user_ops.html` | detail/list-selected item | `/api/admin/miniprogram-library/{item_id}` | GET | `get_miniprogram` | `GetMediaItemQuery("miniprogram")` -> repo item | none | `tests/test_media_library_next_contract.py` |
| `/admin/miniprogram-library` | `miniprogram_library.html` | delete | `/api/admin/miniprogram-library/{item_id}` | DELETE | `delete_miniprogram` | `DeleteMediaItemCommand("miniprogram")` -> repo delete | no external delete; `side_effect_plan` returned | `tests/test_media_library_next_contract.py` |
| `/admin/miniprogram-library` | `miniprogram_library.html`, `image_picker.js` | thumbnail image reference | `/api/admin/image-library?enabled_only=true&limit=80`, `/api/admin/image-library/{image_id}/thumbnail`, `/api/admin/image-library/upload` | GET/POST | `list_images`, `get_image_thumbnail`, `upload_image` | image repo + local upload | no real media upload from picker; miniprogram resolve remains guarded | `tests/test_media_library_next_contract.py`, `tests/test_image_upload_client_static.py` |
| `/admin/miniprogram-library` | `miniprogram_library.html` | thumb media resolve smoke | `/api/admin/miniprogram-library/{item_id}/test-resolve` | POST | `test_resolve_miniprogram` | `TestResolveMiniprogramThumbCommand` -> image repo/cache + guarded WeCom adapter | cache hit or SideEffectPlan/guarded adapter only; real production call blocked | `tests/test_media_library_next_contract.py` |

## Other Media Library Callers

| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | Repo/Storage | 外部副作用 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Cloud Orchestrator | `cloud_campaigns_workspace.html`, `cloud_plan_review.js`, `send_content_composer.js`, `material_picker.js` | material selector for configured content packages | `/api/admin/material-picker/items?type=...` | GET | `aicrm_next.send_content.api.list_material_picker_items` | `PostgresSendContentRepository` reads media library repo | none | `tests/test_next_send_content_frontend_contract.py`, `tests/test_send_content_next_native.py` |
| Cloud Orchestrator legacy upload bridge | production compat route | media upload fallback | `/api/admin/cloud-orchestrator/media/upload` | POST | `aicrm_next.production_compat.api` | legacy forward only | retained legacy bridge; out of group 16 execution scope | `tests/test_production_route_resolution.py` |
| Radar Links | `admin_console/radar_link_form.html` | pick/upload image or PDF material | `/api/admin/material-picker/items`, `/api/admin/image-library/upload`, `/api/admin/attachment-library/upload` | GET/POST | send-content picker + media upload handlers | media repo; radar PDF chunk flow for large PDFs | upload routes local-only; radar execute/storage outside this group | `tests/test_media_library_next_contract.py` plus radar link tests |
| Send Content | `static/admin_console/send_content_composer.js`, `material_picker.js` | image/miniprogram/attachment material selector | `/api/admin/material-picker/items` | GET | `list_material_picker_items` | send-content repo reads media library repo | none; send/execute outside this group | `tests/test_next_send_content_frontend_contract.py`, `tests/test_send_content_global_guardrails.py` |
| Questionnaire editor | grep result | media selector | none direct | n/a | n/a | no direct media-library route use found | none | grep inventory |
| Automation material selector | `automation_operation_orchestration_panel.js`, `send_content_composer.js`, `material_picker.js` | material selection inside operation content package | `/api/admin/material-picker/items` | GET | `list_material_picker_items` | send-content repo reads media library repo | none; automation runtime outside this group | `tests/test_next_send_content_frontend_contract.py` |
| Sidebar materials send | `static/sidebar_workbench/sidebar_workbench.js` | sidebar material list/send | `/api/sidebar/v2/materials`, `/api/sidebar/v2/materials/send` | GET/POST | customer read model / sidebar write | sidebar material view model, not direct media-library API | real send guarded by sidebar write route, outside this group | `tests/test_sidebar_v2_api.py` |
| Group Ops material selector | group ops plan UI via send-content composer | plan action material package | `/api/admin/material-picker/items` | GET | `list_material_picker_items` | send-content repo reads media library repo | send execution outside this group | `tests/test_group_ops_frontend_contract.py` |

## Response Contract

JSON API responses include or are compatible with:

- `ok`
- `items`, `total`, and `count` for list routes
- `source_status`
- `route_owner=ai_crm_next`
- `fallback_used=false`
- `real_external_call_executed=false`
- `storage_adapter_mode` / `adapter_mode`
- `side_effect_plan` for upload/delete/local command responses, or `adapter_result` with audit/idempotency details for guarded adapter imports

Binary thumbnail/variant responses include headers:

- `X-AICRM-Route-Owner=ai_crm_next`
- `X-AICRM-Fallback-Used=false`
- `X-AICRM-Real-External-Call-Executed=false`
- `X-AICRM-Storage-Adapter-Mode=<mode>`

## Out Of Scope

- Real external object storage enablement.
- Real WeCom media upload.
- Cloud Orchestrator execute.
- Sidebar material real send.
- Automation runtime.
- Payment/storage/OpenClaw real external calls.
- Public CDN optimization.
- Removing legacy fallback in this group.
