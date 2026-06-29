# Route Inventory Consolidation Inventory

Generated on 2026-06-29 as a cleanup planning artifact. This document does not
delete, move, or deprecate any route inventory file. It records which hand-written
`docs/architecture/*route_inventory.md` files are mostly reproducible from the
canonical route ownership manifest, and which files still carry closeout evidence
that should not be auto-generated yet.

## Current Sources

- Canonical manifest: `docs/architecture/route_ownership_manifest.yml`
- Manifest contract: `docs/architecture/route_ownership_manifest.md`
- Manifest checker: `tools/check_route_ownership_manifest.py`
- Manifest regression test: `tests/test_route_ownership_manifest.py`

The manifest currently covers 550 FastAPI routes. Static mounts are excluded by
the manifest contract. The hand-written inventory set currently contains 24
`*_route_inventory.md` files under `docs/architecture/`.

## Classification

### Mostly Manifest-Derivable

These inventories are primarily route/method/owner matrices. Their structural
columns could be generated from `route_ownership_manifest.yml`, while retaining a
short human-authored note for side-effect or closeout nuance:

| Inventory | Extracted routes | Exact manifest matches | Notes |
| --- | ---: | ---: | --- |
| `admin_auth_login_route_inventory.md` | 8 | 5 | Keep WeCom SSO gated-real note. |
| `cloud_orchestrator_campaign_write_route_inventory.md` | 18 | 11 | Keep CommandBus and SideEffectPlan notes. |
| `cloud_orchestrator_campaigns_route_inventory.md` | 16 | 12 | Split read/workspace rows from write controls later. |
| `cloud_orchestrator_run_due_route_inventory.md` | 2 | 2 | Good generator candidate. |
| `hxc_dashboard_route_inventory.md` | 13 | 10 | Keep explicit no-real-WeCom directory sync evidence. |
| `questionnaire_admin_write_route_inventory.md` | 10 | 8 | Keep write safety and export-preview notes. |
| `questionnaire_h5_submit_route_inventory.md` | 5 | 4 | Keep public submit no-real-side-effect evidence. |
| `sidebar_jssdk_route_inventory.md` | 2 | 2 | Keep explicit real-enabled gate note. |
| `sidebar_readonly_route_inventory.md` | 16 | 14 | Good generator candidate after route family grouping. |
| `sidebar_write_route_inventory.md` | 9 | 9 | Good generator candidate with SideEffectPlan annotations. |
| `user_ops_route_inventory.md` | 13 | 13 | Good generator candidate. |

### Retain As Closeout Evidence For Now

These inventories include wildcard deletion history, legacy rollback rationale,
external-effect boundaries, caller matrices, or historical test references. Keep
them as durable closeout evidence until a generator can preserve those fields:

| Inventory | Extracted routes | Exact manifest matches | Why keep |
| --- | ---: | ---: | --- |
| `auth_wecom_route_inventory.md` | 9 | 7 | Wildcard retirement and OAuth gating evidence. |
| `checkout_orders_route_inventory.md` | 21 | 8 | Public checkout/order wildcard and payment boundary notes. |
| `cloud_orchestrator_media_upload_route_inventory.md` | 4 | 4 | Approved WeCom media upload boundary and route precedence notes. |
| `media_library_route_inventory.md` | 31 | 21 | Broad caller/test evidence and storage boundary notes. |
| `messages_route_inventory.md` | 12 | 10 | Deprecated/blocked exact response evidence. |
| `provider_payment_notify_route_inventory.md` | 15 | 5 | Provider callback fake/real-blocked contract. |
| `questionnaire_admin_read_route_inventory.md` | 17 | 14 | Read migration evidence plus out-of-scope OAuth/H5 notes. |
| `questionnaire_oauth_route_inventory.md` | 7 | 3 | OAuth state/security boundary and historical wildcard context. |
| `wecom_tag_read_route_inventory.md` | 18 | 10 | Sync/read split and live-gate context. |
| `wecom_tag_write_route_inventory.md` | 12 | 7 | CRUD/sync/write boundary and rollback closeout evidence. |

### Needs Manual Review Before Any Generator

These files do not map cleanly to extracted backtick route paths and should be
reviewed before any archive or generator work:

| Inventory | Reason |
| --- | --- |
| `customer_automation_webhook_route_inventory.md` | No route-like backtick paths extracted; likely narrative evidence. |
| `public_product_pay_route_inventory.md` | Many route family/wildcard references; exact route normalization needs manual review. |
| `wecom_tag_live_mutation_route_inventory.md` | Caller matrix is command/effect oriented and not a pure route list. |

## Recommended Order

1. Keep all existing route inventory tests in place.
2. Build a report-only generator that emits route/method/owner rows from
   `route_ownership_manifest.yml` without changing existing docs.
3. Compare generated rows against the mostly manifest-derivable files above.
4. Archive only the rows proven redundant; keep closeout evidence sections under
   `docs/reports/evidence/` or a future `docs/archive/route_inventory/`.
5. Only after a second PR proves parity, replace hand-written route tables with
   generated output.

## Non-Goals

- Do not delete route inventory docs in this batch.
- Do not delete `tests/test_*_route_inventory.py`.
- Do not change route ownership manifest semantics.
- Do not change FastAPI router registration or route behavior.
