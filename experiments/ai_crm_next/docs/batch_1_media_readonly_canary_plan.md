# Batch 1 Media Library Readonly Canary Plan

This plan prepares a staging or production-like canary for Batch 1. It does not change production routes, production proxy files, production data, cloud storage, or WeCom media integrations.

## Canary Scope

Included readonly routes:

- `GET /admin/image-library`
- `GET /api/admin/image-library`
- `GET /admin/attachment-library`
- `GET /api/admin/attachment-library`
- `GET /admin/miniprogram-library`
- `GET /api/admin/miniprogram-library`

Excluded routes:

- `POST /api/admin/image-library`
- `POST /api/admin/image-library/from-url`
- `POST /api/admin/image-library/from-base64`
- `PUT /api/admin/image-library/{image_id}`
- `DELETE /api/admin/image-library/{image_id}`
- attachment write routes
- miniprogram write routes
- cloud upload
- WeCom media upload

## Canary Mode Options

| mode | allowed use | notes |
| --- | --- | --- |
| `dry_run` | Local evidence and report aggregation | No route owner changes. |
| `staging_shadow` | Staging-only shadow checks | Compare route behavior without production traffic. |
| `header_allowlist` | One operator/session in staging | Route only requests with the canary header. |
| `cookie_allowlist` | One operator/session in staging | Route only requests with the canary cookie. |
| `percentage=0` | Template only | Do not enable percentage rollout in this phase. |

## Recommended First Canary

- mode: `staging_shadow` or `header_allowlist`
- audience: 1 operator / 1 session
- scope: readonly routes only
- writes: disabled
- external adapters: disabled / fake
- rollback owner: old Flask

## Entry Criteria

| criterion | required evidence |
| --- | --- |
| ordinary pytest pass | `.venv/bin/python -m pytest -q` |
| six parity pass | all `tools/compare_*_parity.py` reports |
| Media parity pass | `tools/compare_media_library_parity.py` |
| Media gray smoke pass | `tools/media_library_gray_smoke.py --next-testclient` |
| PNG screenshot baseline pass | `artifacts/frontend_screenshots/route_status.json` |
| Batch 1 rehearsal report GO | `tools/run_gray_rehearsal_batch.py --batch media_readonly` |
| no old production entrypoint dirty | `git status --short --untracked-files=all` review |
| no production config modified | status scan and side-effect report |

## Exit Criteria

- all included smoke routes return 200
- forbidden placeholder checks remain clean through the screenshot baseline
- side-effect safety flags are all false
- rollback dry-run is verified
- signoff template is complete
- no write route appears in canary route results

## No-Go Conditions

- any write route is included
- any external upload is attempted
- production config is modified
- old service write endpoint is called
- smoke blocker exists
- parity blocker exists
- rollback owner is missing
- cloud storage or WeCom media is enabled

## Readiness Command

```bash
.venv/bin/python tools/check_batch_1_media_canary_readiness.py \
  --media-smoke-json /tmp/media_gray_smoke_after_canary_plan.json \
  --media-parity-json /tmp/media_parity_after_canary_plan.json \
  --batch-rehearsal-json /tmp/gray_rehearsal_batch_1_media_readonly_audit.json \
  --output-md /tmp/batch_1_media_canary_readiness.md \
  --output-json /tmp/batch_1_media_canary_readiness.json
```

## Conclusion

Batch 1 canary status is `canary_plan_ready` only after the readiness checker passes. This is not `production_ready`.
