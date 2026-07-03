# WeChat Pay Order Identity Repair

## Purpose

Paid H5 orders can be created without `external_userid` when the buyer enters
from a public product/payment link without sidebar `ctx`. The order still keeps
WeChat identity fields such as `unionid` or `payer_openid`, and the repair job
backfills `wechat_pay_orders.external_userid` from existing CRM identity tables.

## Runtime Contract

- Route: `POST /api/admin/jobs/order-identity-repair/run`
- Auth: `CRON_SECRET` bearer token, or the standard admin action token.
- Recommended schedule: hourly.
- Default batch size: 100 orders.
- Retry limit: each missing order is attempted at most 3 times.
- External calls: none. The job only reads local identity tables and updates
  `wechat_pay_orders` plus `wechat_pay_order_identity_repair`.

## Manual Dry Run

```bash
curl -sS -X POST "https://www.youcangogogo.com/api/admin/jobs/order-identity-repair/run" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":true,"limit":100,"max_attempts":3}'
```

## Manual Execute

```bash
curl -sS -X POST "https://www.youcangogogo.com/api/admin/jobs/order-identity-repair/run" \
  -H "Authorization: Bearer ${CRON_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":false,"limit":100,"max_attempts":3}'
```

## Rollback

Stop the hourly caller first. The data write is conservative: it only updates
orders whose `external_userid` is still empty. If a repair result must be
reverted, clear the specific order's `external_userid` and mark its
`wechat_pay_order_identity_repair` row as `skipped` with an operator note in
`detail_json`.
