# Route Inventory Consolidation Inventory

Generated: 2026-06-29T02:36:17Z

This report is generated from `docs/architecture/route_ownership_manifest.yml`
and `docs/architecture/*route_inventory.md` by
`tools/report_route_inventory_consolidation.py`. It does not delete, move,
or deprecate any route inventory file.

## Current Sources

- Canonical manifest: `docs/architecture/route_ownership_manifest.yml`
- Manifest contract: `docs/architecture/route_ownership_manifest.md`
- Manifest checker: `tools/check_route_ownership_manifest.py`
- Manifest regression test: `tests/test_route_ownership_manifest.py`

The manifest currently covers 550 FastAPI routes.
The hand-written inventory set currently contains 24 `*_route_inventory.md` files.

## Classification Summary

- `mostly_manifest_derivable`: 5
- `needs_manual_review`: 2
- `retain_closeout_evidence`: 17

## Inventory Details

### mostly_manifest_derivable

| Inventory | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |
| --- | ---: | ---: | ---: | ---: | --- |
| `docs/architecture/cloud_orchestrator_media_upload_route_inventory.md` | 4 | 4 | 0 | 3 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/architecture/cloud_orchestrator_run_due_route_inventory.md` | 2 | 2 | 0 | 1 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/architecture/sidebar_jssdk_route_inventory.md` | 2 | 2 | 0 | 0 | Exact routes match manifest and can be compared with generated route rows. |
| `docs/architecture/sidebar_write_route_inventory.md` | 9 | 9 | 0 | 2 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |
| `docs/architecture/user_ops_route_inventory.md` | 13 | 13 | 0 | 6 | Exact routes match manifest; preserve linked test evidence until a generated table proves parity. |

### retain_closeout_evidence

| Inventory | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |
| --- | ---: | ---: | ---: | ---: | --- |
| `docs/architecture/admin_auth_login_route_inventory.md` | 8 | 5 | 3 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/auth_wecom_route_inventory.md` | 9 | 7 | 2 | 7 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/checkout_orders_route_inventory.md` | 21 | 8 | 8 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/cloud_orchestrator_campaign_write_route_inventory.md` | 18 | 11 | 1 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/cloud_orchestrator_campaigns_route_inventory.md` | 16 | 12 | 3 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/hxc_dashboard_route_inventory.md` | 13 | 10 | 1 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/media_library_route_inventory.md` | 31 | 21 | 4 | 12 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/messages_route_inventory.md` | 12 | 10 | 1 | 4 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/provider_payment_notify_route_inventory.md` | 15 | 5 | 6 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/public_product_pay_route_inventory.md` | 19 | 0 | 11 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_admin_read_route_inventory.md` | 17 | 14 | 2 | 3 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_admin_write_route_inventory.md` | 10 | 8 | 2 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_h5_submit_route_inventory.md` | 5 | 4 | 1 | 5 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/questionnaire_oauth_route_inventory.md` | 7 | 3 | 3 | 6 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/sidebar_readonly_route_inventory.md` | 16 | 14 | 2 | 1 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/wecom_tag_read_route_inventory.md` | 18 | 10 | 2 | 6 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |
| `docs/architecture/wecom_tag_write_route_inventory.md` | 12 | 7 | 4 | 0 | Contains wildcard/family refs or route refs not exactly covered by the manifest. |

### needs_manual_review

| Inventory | Routes | Exact manifest matches | Wildcard/family refs | Test refs | Reason |
| --- | ---: | ---: | ---: | ---: | --- |
| `docs/architecture/customer_automation_webhook_route_inventory.md` | 0 | 0 | 0 | 0 | No route-like backtick paths were extracted. |
| `docs/architecture/wecom_tag_live_mutation_route_inventory.md` | 0 | 0 | 0 | 4 | No route-like backtick paths were extracted. |

## Recommended Order

1. Keep all existing route inventory tests in place.
2. Use this report to compare generated route/method/owner rows against the
   hand-written route inventory files.
3. Archive only rows proven redundant; keep closeout evidence sections under
   `docs/reports/evidence/` or a future `docs/archive/route_inventory/`.
4. Only after a second PR proves parity, replace hand-written route tables with
   generated output.

## Non-Goals

- Do not delete route inventory docs in this batch.
- Do not delete `tests/test_*_route_inventory.py`.
- Do not change route ownership manifest semantics.
- Do not change FastAPI router registration or route behavior.
