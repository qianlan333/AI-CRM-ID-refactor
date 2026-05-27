# HXC Next-Native Broadcast

HXC / funnel dashboard broadcast now uses a Next-native API:

- `POST /api/admin/hxc-dashboard/broadcast-tasks`

The API accepts a standard `SendContentPackage` plus HXC outer-page fields:

- `source_type=hxc_dashboard_broadcast`
- `source_id`
- `idempotency_key`
- `sender_userid`
- `audience_filter`
- `selected_customer_ids`
- `dry_run`

## Boundaries

The standard content component owns only:

- `content_text`
- `image_library_ids`
- `miniprogram_library_ids`
- `attachment_library_ids`

The HXC page owns audience filtering, selected customer IDs, sender selection, and idempotency. The API calls `NormalizeSendContentPackageCommand` with `require_body=true`, so empty HXC broadcasts are rejected.

## Side Effects

This PR does not upload WeCom media, resolve `media_id`, create old Flask broadcast records, or change the real WeCom dispatch chain. The Next-native API creates an internal HXC broadcast task with `dispatch_status=pending_external_dispatch` when PostgreSQL storage is available. If production storage or audience data is unavailable, it returns `status=production_unavailable` instead of pretending the send succeeded.

## Idempotency

`source_type + source_id + idempotency_key` is the idempotency key. Repeating the same request returns the existing task with `duplicate=true` and does not create a second task.

## Legacy Boundary

Do not use or revive old Flask `/api/admin/hxc-dashboard/broadcast` for new HXC broadcast work. Do not add new implementation under `wecom_ability_service/http/*`, `wecom_ability_service/domains/*`, `production_compat`, or legacy facade routes.
