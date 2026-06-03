# Cloud Orchestrator Campaigns Route Inventory

Legacy Exit group 18 moved Cloud Orchestrator campaign read/workspace surfaces to Next exact routes and then locked the read rollback closed. This group does not execute campaigns, does not run run-due, does not send WeCom messages, and does not run the automation runtime.

## Frontend API Backend Contract Matrix

| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | Repo/Read Model | 外部副作用 | 本组决策 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/cloud-orchestrator/campaigns` | `aicrm_next/frontend_compat/templates/admin_console/cloud_campaigns_workspace.html` | Campaign workspace page | page route | GET | `aicrm_next.cloud_orchestrator.api.admin_cloud_campaigns` | Template over Next read API | none | Next page route owns the workspace; not a production_compat shell | page 200, contains campaign read URLs |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | list campaign groups and rows | `/api/admin/cloud-orchestrator/campaigns?limit=5000` | GET | `aicrm_next.cloud_orchestrator.api.api_list_cloud_campaigns` | `ListCloudCampaignsQuery` / `CloudCampaignReadRepository.list_campaigns` | none | locked: Next exact read route; legacy rollback removed | API 200 or degraded empty, `route_owner=ai_crm_next` |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | open campaign drawer | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}` | GET | `aicrm_next.cloud_orchestrator.api.api_get_cloud_campaign` | `GetCloudCampaignQuery` / `campaign_overview` | none | locked: Next exact read route for overview, segments, status counts, embedded steps | API 200 for fixture, controlled 404 if missing |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | view members drawer | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members` | GET | `aicrm_next.cloud_orchestrator.api.api_list_cloud_campaign_members` | `ListCloudCampaignMembersQuery` / `list_members` | none | locked: Next exact read route for member rows; legacy rollback removed | API 200 for fixture, controlled 404 if missing |
| `/admin/cloud-orchestrator/campaigns` | API-only validation | list flattened steps | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps` | GET | `aicrm_next.cloud_orchestrator.api.api_list_cloud_campaign_steps` | `ListCloudCampaignStepsQuery` / `list_steps` | none | locked: Next exact read route; legacy rollback removed | API 200 for fixture, controlled 404 if missing |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | batch-start campaign group | `/api/admin/cloud-orchestrator/campaigns/batch-start` | POST | production_compat broad fallback | legacy command surface | potential real send/runtime if enabled downstream | out-of-scope; UI write controls are disabled by `CAMPAIGN_WRITE_DISABLED=true`; not deletion_locked | not executed |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | approve campaign | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve` | POST | production_compat broad fallback | legacy command surface | possible approval/start side effects | out-of-scope; UI guard blocks execution | not executed |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | start campaign | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/start` | POST | production_compat broad fallback | legacy command surface | real WeCom send may be scheduled by legacy runtime | out-of-scope; UI guard blocks execution | not executed |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | pause campaign | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/pause` | POST | production_compat broad fallback | legacy command surface | campaign lifecycle mutation | out-of-scope; UI guard blocks execution | not executed |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | reject campaign | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/reject` | POST | production_compat broad fallback | legacy command surface | campaign lifecycle mutation | out-of-scope; UI guard blocks execution | not executed |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | delete campaign | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}` | DELETE | production_compat broad fallback | legacy command surface | destructive storage mutation | out-of-scope; UI guard blocks execution | not executed |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` inline JS | create/edit/delete steps | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps*` | POST/PATCH/DELETE | production_compat broad fallback | legacy command surface | campaign step mutation | out-of-scope; edit controls are hidden while `CAMPAIGN_WRITE_DISABLED=true` | not executed |
| timer / job runner | no page caller in this group | run due campaign delivery | `/api/admin/cloud-orchestrator/campaigns/run-due` | POST | `aicrm_next.production_compat.api.api_cloud_campaigns_run_due` | legacy timer facade | real runtime/send risk, safe-mode guarded by legacy route | out-of-scope; no campaign execution in group 18 | not executed |
| timer / preview | no page caller in this group | preview due campaign delivery | `/api/admin/cloud-orchestrator/campaigns/run-due/preview` | POST | `aicrm_next.production_compat.api.api_cloud_campaigns_run_due_preview` | legacy timer facade | preview/noop path only | out-of-scope; retained for timer validation | not executed |

## Response Contract

Next campaign read JSON responses include:

- `ok`
- `items` / `campaigns` for list responses
- `campaign` for detail responses
- `members` / `rows` for member responses
- `steps` for step responses
- `count` and/or `total`
- `source_status=next_cloud_orchestrator_campaign_read`
- `route_owner=ai_crm_next`
- `fallback_used=false`
- `real_external_call_executed=false`
- `page_error` and `degraded=true` when production read storage is unavailable

## Side Effect Boundary

- No real WeCom send.
- No automation runtime.
- No campaign execute.
- No run-due execution.
- No real external storage.
- No payment/OpenClaw side effects.
- Media upload remains locked by the previous group and is not changed here.

## Decision Notes

Read/workspace GET routes are deletion_locked to Next exact read APIs with `legacy_fallback_allowed=false`. Campaign write, step mutation, batch-start, and run-due routes stay active/out-of-scope in production_compat and are not marked `deletion_locked` in this group.

## Deletion Closeout Status Matrix

| 页面入口 | 前端模板/JS | 动作 | API | Method | Handler | Closeout 状态 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/cloud-orchestrator/campaigns` | `cloud_campaigns_workspace.html` | Campaign workspace page | page route | GET | `aicrm_next.cloud_orchestrator.api.admin_cloud_campaigns` | locked: Next shell over Next read APIs; write controls disabled/out-of-scope | page 200, non-empty |
| `/admin/cloud-orchestrator/campaigns` | inline JS | list campaigns | `/api/admin/cloud-orchestrator/campaigns` | GET | `api_list_cloud_campaigns` | locked: Next read model only, legacy fallback removed | API 200, `fallback_used=false` |
| `/admin/cloud-orchestrator/campaigns` | inline JS | detail drawer | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}` | GET | `api_get_cloud_campaign` | locked: Next read model only, legacy fallback removed | API 200 for fixture |
| `/admin/cloud-orchestrator/campaigns` | inline JS | members drawer | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members` | GET | `api_list_cloud_campaign_members` | locked: Next read model only, legacy fallback removed | API 200 for fixture |
| `/admin/cloud-orchestrator/campaigns` | API-only validation | steps read | `/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps` | GET | `api_list_cloud_campaign_steps` | locked: Next read model only, legacy fallback removed | API 200 for fixture |
| `/admin/cloud-orchestrator/campaigns` | inline JS guarded by `CAMPAIGN_WRITE_DISABLED=true` | approve/start/pause/reject/delete/batch-start/step mutation | `/api/admin/cloud-orchestrator/campaigns*` | POST/PATCH/DELETE | production_compat broad write fallback | retained out-of-scope; pending Group 19/later runtime group; not deletion_locked | not executed |
| timer / job runner | no page caller in this group | run-due / preview | `/api/admin/cloud-orchestrator/campaigns/run-due*` | POST | production_compat timer fallback | retained out-of-scope; pending later runtime group; not deletion_locked | not executed |
