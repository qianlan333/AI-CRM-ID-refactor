# Public Product / Pay Route Inventory

Legacy Exit Group 27 closes the public product and pay landing rollback for `/p/*`, `/pay/*`, and `/api/products/*`.

## Frontend <-> API <-> Backend Contract Matrix

| 入口 | 调用方 | 动作 | Route | Method | Handler | Backend | 外部副作用 | Closeout 状态 | Smoke |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 商品详情页 | QR/share/sidebar product_url | render product display | `/p/{product_or_slug}` | GET/HEAD | `aicrm_next.public_product.api.public_product_page` | `CommerceRepository.get_product_by_slug/get_product_by_code` + `preview_product` | none; `payment_request_executed=false`; `order_create_executed=false` | `legacy_fallback_allowed=false`; `deletion_locked`; `replacement_status=locked` | 200 or controlled 404, never 500 |
| 支付落地页 | legacy `/pay/<product_code>` link | render blocked pay landing | `/pay/{product_or_slug}` | GET/HEAD | `aicrm_next.public_product.api.public_pay_landing` | same product projection | medium risk, but `real_blocked`; no order create; no provider call | `legacy_fallback_allowed=false`; `deletion_locked`; `replacement_status=locked` | 200 or controlled 404, no payment request |
| Product API detail | public frontend / legacy share clients | read product contract | `/api/products/{path}` | GET/HEAD | `aicrm_next.public_product.api.public_product_api` | product projection | none for detail/list | `legacy_fallback_allowed=false`; `deletion_locked`; `replacement_status=locked` | 200 known, 404 unknown |
| Product API list | diagnostics/public readers | read active product list | `/api/products/list` | GET/HEAD | `public_product_api` | `list_products` filtered to enabled display projection | none | locked | 200 contract |
| checkout-like child path | old clients or probes | block payment action | `/api/products/{path containing checkout/payment/order}` | GET/HEAD | `public_product_api` | no repository write | blocked; `payment_request_executed=false`; `order_create_executed=false` | locked | 410 controlled |
| write-like product path | old clients or probes | block write/payment action | `/api/products/{path}` | POST/PUT/PATCH/DELETE | `public_product_api_blocked_write` | none | blocked; no order create; no provider call | locked | 410 controlled |
| unknown child path | bad URL/manual probes | controlled not found | `/api/products/{unknown}` | GET/HEAD | `public_product_api` | product lookup only | none | locked | 404 controlled |
| production_compat exact rollback | legacy fallback | removed | `/p/*`, `/pay/*`, `/api/products/*` | all | removed from `router` | none | production_compat rollback removed | grep clean |
| production_compat wildcard rollback | broad fallback | removed | `/p/*`, `/pay/*`, `/api/products/*` | all | removed from `wildcard_router` | none | wildcard_router rollback removed | grep clean |
| payment/admin/h5/checkout/orders/provider | out-of-scope | later groups own payment APIs | `/api/admin/wechat-pay/*`, `/api/admin/alipay/*`, `/api/h5/wechat-pay/*`, `/api/h5/alipay/*`, `/api/orders/*`, `/api/checkout/*`, `/api/wechat-pay/*`, `/api/alipay/*` | all | later group owners unchanged | guarded/blocked by separate groups | checkout/orders locked in group 28; public provider notify/return locked in group 29; admin/h5 remain out-of-scope | smoke admin/h5 still reach retained family |

## Boundary Decisions

- `/p/{path}` is a public product/detail landing path used by share URLs and sidebar product links.
- `/pay/{path}` is treated as a public pay landing, not an executable checkout route in this group.
- `/api/products/{path}` is read/display contract only; payment/action paths are blocked.
- Known child APIs in this group: detail by slug/code, list, blocked checkout/payment/order child path, unknown path.
- Lead channel and completion redirect fields may be present in the product projection but this group does not execute redirects, channel admission, payment, order creation, webhook, or callback behavior.
- Do not process real payment, real order create, real WeChat Pay, real Alipay, or payment webhook in this group.
- Do not change payment/admin/h5/checkout/orders/provider wildcard ownership in this group; later groups 28 and 29 close checkout/orders and public provider notify/return, while admin/h5 remain out-of-scope.
