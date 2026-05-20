# Automation Readonly Route Cutover Manifest

This manifest is for gray-release preparation only. A `gray_ready` value of `yes_readonly` means the route is eligible for readonly smoke and future readonly gray evaluation, not production cutover. Old Flask uses legacy route names for several readonly views; those are listed in `old_route_alias`.

| route | method | old_route_alias | old_owner | next_owner | route_type | side_effect_risk | current_next_status | gray_ready | data_requirement | rollback_route | smoke_command | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/automation-conversion` | GET | `/admin/automation-conversion` | old Flask `automation_conversion` admin page | Next frontend compat | page | read | partial_adapter | yes_readonly | legacy page renders | old Flask page route | `tools/automation_readonly_gray_smoke.py --next-testclient` | Old unauthenticated page can return `302 /login?next=/admin/automation-conversion`; record as `legacy_admin_auth_redirect`. |
| `/api/admin/automation-conversion/overview` | GET | `/api/admin/automation-conversion/dashboard` | old Flask dashboard API | Next `automation_engine` | api | read | parity_ready | yes_readonly | fixture or local test data | old Flask dashboard alias | `tools/automation_readonly_gray_smoke.py --next-testclient` | Same business area, different legacy shape; shape differences are legacy drift when Next contract passes. |
| `/api/admin/automation-conversion/pools` | GET | `/api/admin/automation-conversion/dashboard` | old Flask dashboard API | Next `automation_engine` | api | read | parity_ready | yes_readonly | six-pool state display | old Flask dashboard alias | `tools/automation_readonly_gray_smoke.py --next-testclient` | Old dashboard groups are not the same as Next pool projection. |
| `/api/admin/automation-conversion/members` | GET | `/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50` | old Flask segment-search API | Next `automation_engine` | api | read | parity_ready | yes_readonly | member list sample improves coverage | old Flask segment-search alias | `tools/automation_readonly_gray_smoke.py --next-testclient` | Uses old program `1`; no POST broadcast is executed. |
| `/api/admin/automation-conversion/members/{member_id}` | GET | `/api/admin/automation-conversion/member?external_contact_id={external_userid}` | old Flask member detail API | Next `automation_engine` | api | read | parity_ready | yes_after_sample | `member_id` from Next list and `external_userid` from old alias list | old Flask member detail alias | `tools/automation_readonly_gray_smoke.py --next-testclient` | Do not hardcode real member id or real external contact id. |
| `/api/admin/automation-conversion/execution-records` | GET | `/api/admin/automation-conversion/executions` | old Flask execution API | Next `automation_engine` | api | read | parity_ready | yes_readonly | execution record fixture/list data | old Flask executions alias | `tools/automation_readonly_gray_smoke.py --next-testclient` | Old execution batch shape differs from Next execution-record projection. |
| `/api/admin/automation-conversion/members/{member_id}/override-followup-type` | POST | not allowed | old Flask automation write service | Next `automation_engine` | api | write | fixture_partial | fake_next_only | explicit Next fake-write smoke only | keep old route active | `tools/automation_readonly_gray_smoke.py --next-testclient --include-fake-writes` | Not production gray-ready; never send to old Flask. |
| `/api/admin/automation-conversion/members/{member_id}/confirm-conversion` | POST | not allowed | old Flask automation write service | Next `automation_engine` | api | write | fixture_partial | fake_next_only | explicit Next fake-write smoke only | keep old route active | `tools/automation_readonly_gray_smoke.py --next-testclient --include-fake-writes` | Not production gray-ready; never send to old Flask. |
| `/api/admin/automation-conversion/members/{member_id}/enter-silent` | POST | not allowed | old Flask automation write service | Next `automation_engine` | api | write | fixture_partial | fake_next_only | explicit Next fake-write smoke only | keep old route active | `tools/automation_readonly_gray_smoke.py --next-testclient --include-fake-writes` | Not production gray-ready; never send to old Flask. |
| `/api/admin/automation-conversion/members/{member_id}/exit-marketing` | POST | not allowed | old Flask automation write service | Next `automation_engine` | api | write | fixture_partial | fake_next_only | explicit Next fake-write smoke only | keep old route active | `tools/automation_readonly_gray_smoke.py --next-testclient --include-fake-writes` | Not production gray-ready; never send to old Flask. |
| `/api/admin/automation-conversion/members/{member_id}/push-openclaw-context` | POST | not allowed | old Flask automation external push | Next fake OpenClaw boundary | api | external | fixture_partial | no_production | real OpenClaw adapter contract and audit required | keep old route active | not allowed | OpenClaw fake push is not production-ready and is excluded from gray smoke. |
| `/api/customer-automation/activation-webhook` | POST | not allowed | old Flask customer automation webhook | Next `automation_engine` fake boundary | api | external | fixture_partial | no_production | webhook idempotency/audit required | keep old route active | not allowed | Activation webhook is write/external and outside readonly gray. |
| workflow / agent runtime write routes | POST | not allowed | old Flask orchestration runtime | Next pending runtime | api | external | not_started | no_production | runtime phase 2 and external adapter validation required | keep old route active | not allowed | Real workflow/agent execution is outside this phase. |

## Old Route Mapping Diagnosis

2026-05-20 local old Flask route checks:

- `/admin/automation-conversion`: `302 /login?next=/admin/automation-conversion`, classified as `legacy_admin_auth_redirect`.
- `/api/admin/automation-conversion/overview`: `404`, no same-name legacy route; use `/api/admin/automation-conversion/dashboard` as readonly alias.
- `/api/admin/automation-conversion/pools`: `404`, no same-name legacy route; use `/api/admin/automation-conversion/dashboard` as readonly alias.
- `/api/admin/automation-conversion/members`: `404`, no same-name legacy route; use `/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50` as readonly alias.
- `/api/admin/automation-conversion/members/{member_id}`: no same-name legacy route; use `/api/admin/automation-conversion/member?external_contact_id={external_userid}` as readonly alias.
- `/api/admin/automation-conversion/execution-records`: `404`, no same-name legacy route; use `/api/admin/automation-conversion/executions` as readonly alias.

The alias routes support local readonly evidence after masked sample seeding, but their payload shapes are legacy-shaped and are expected to produce `legacy_missing_required_contract` warnings rather than blockers when AI-CRM Next satisfies the current contract.

## After-Sample Dual-Run Evidence

The masked local automation sample was seeded into `aicrm_old_flask_test` with `tools/seed_old_flask_automation_sample.py`. The follow-up dual smoke report is available at:

- `/tmp/automation_readonly_gray_smoke_dual_after_sample.md`
- `/tmp/automation_readonly_gray_smoke_dual_after_sample.json`

| next route | old route used | old status | next status | classification | notes |
| --- | --- | --- | --- | --- | --- |
| `/admin/automation-conversion` | `/admin/automation-conversion` | 302 | 200 | `legacy_admin_auth_redirect` | Old page redirects unauthenticated users to login; Next page route remains 200. |
| `/api/admin/automation-conversion/overview` | `/api/admin/automation-conversion/dashboard` | 200 | 200 | `old_route_alias_shape_drift` | Exact old Next-style route is 404; alias gives dashboard evidence. |
| `/api/admin/automation-conversion/pools` | `/api/admin/automation-conversion/dashboard` | 200 | 200 | `old_route_alias_shape_drift` | Old dashboard groups differ from Next pools contract. |
| `/api/admin/automation-conversion/members` | `/api/admin/automation-conversion/programs/1/members/segment-search?page=1&page_size=50` | 200 | 200 | `old_route_alias_shape_drift` | Old alias returned the masked member sample. |
| `/api/admin/automation-conversion/members/{member_id}` | `/api/admin/automation-conversion/member?external_contact_id=external_user_masked_automation_001` | 200 | 200 | `old_route_alias_shape_drift` | Old detail is sampled by `external_userid`; Next detail is sampled from the Next members list. |
| `/api/admin/automation-conversion/execution-records` | `/api/admin/automation-conversion/executions` | 200 | 200 | `old_route_alias_shape_drift` | Old execution batch shape differs from Next execution-record projection. |

The direct old routes named exactly like the Next contract still return 404 and remain classified as `legacy_missing_read_route` if queried directly. The smoke tool uses the documented aliases for old-vs-new readonly evidence without changing the Next API contract.
