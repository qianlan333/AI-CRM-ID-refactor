# Batch 2 Product Management Readonly Canary Plan

This plan prepares a staging or production-like canary for Batch 2 Product Management readonly. It does not change production routes, production proxy files, production product data, checkout routes, payment notify routes, WeChat Pay, or Alipay integrations.

## Summary

| field | value |
| --- | --- |
| batch name | `product_readonly` |
| production rollout | not approved |
| checkout/payment | excluded |
| external payment providers | fake / disabled |

## Execution Mode Options

| mode | allowed use | notes |
| --- | --- | --- |
| `staging_simulated` | AI-CRM Next TestClient or local staging evidence | No route owner changes. |
| `staging_proxy` | Staging proxy/router only | Requires rollback owner and staging operator signoff. |
| `header_allowlist` | One operator/session in staging | Route only requests with canary header. |
| `cookie_allowlist` | One operator/session in staging | Route only requests with canary cookie. |

## Included Readonly Routes

- `GET /admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products`
- `GET /api/admin/wechat-pay/products/{product_id}`
- `GET /p/{page_slug}`
- `GET /api/products/{page_slug}`

## Excluded Routes

- `POST /api/admin/wechat-pay/products`
- `PUT /api/admin/wechat-pay/products/{product_id}`
- `POST /api/admin/wechat-pay/products/{product_id}/enable`
- `POST /api/admin/wechat-pay/products/{product_id}/disable`
- `DELETE /api/admin/wechat-pay/products/{product_id}`
- `POST /api/checkout/wechat`
- `POST /api/checkout/alipay`
- `POST /api/wechat-pay/notify`
- `POST /api/alipay/notify`
- `GET /api/alipay/return` if it mutates state
- real WeChat Pay call
- real Alipay call

## Entry Criteria

| criterion | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| six parity pass | all `tools/compare_*_parity.py` reports |
| Commerce parity pass | `tools/compare_commerce_parity.py` |
| Product gray smoke pass | `tools/product_management_gray_smoke.py --next-testclient` |
| PNG screenshot baseline pass | `artifacts/frontend_screenshots/route_status.json` includes product admin and public product routes |
| Batch 1 rehearsal complete | Batch 1 Media readonly local/simulated evidence exists |
| no old production entrypoint dirty | `git status --short --untracked-files=all` review |
| no production config modified | deploy/production config status scan and side-effect report |

## Exit Criteria

- all readonly routes return 200
- forbidden placeholders remain absent through screenshot baseline
- side-effect safety flags are all false
- rollback dry-run is verified
- signoff draft is complete
- no checkout route appears in smoke route results
- no product write route appears in default canary route results

## No-Go Conditions

- any checkout execution
- any payment provider call
- any product write route included
- production config modified
- old system write endpoint called
- smoke blocker
- parity blocker
- missing rollback owner
- payment notify or payment return route executes by default

## Readiness Command

```bash
.venv/bin/python tools/check_batch_2_product_canary_readiness.py \
  --product-smoke-json /tmp/product_management_gray_smoke_batch_2.json \
  --commerce-parity-json /tmp/commerce_parity_batch_2_product.json \
  --output-md /tmp/batch_2_product_canary_readiness.md \
  --output-json /tmp/batch_2_product_canary_readiness.json
```

## Conclusion

Batch 2 readiness can only reach `canary_plan_ready` or `staging_simulated_canary_pass`. It is not `production_ready` and does not approve checkout, notify, WeChat Pay, or Alipay.
