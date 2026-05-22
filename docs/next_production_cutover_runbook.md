# Next Production Cutover Runbook

## Preconditions

- GitHub deploy has completed successfully.
- Server `DATABASE_URL` is a real PostgreSQL URL.
- `AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE=1` is set, or production mode is detected through `DATABASE_URL` / environment.
- `AUTOMATION_INTERNAL_API_TOKEN` is configured before timer enablement.
- 5013 legacy callback fallback remains running.

## Verification Commands

```bash
python3 tools/check_next_production_runtime_gaps.py \
  --output-md /tmp/next_runtime_gaps.md \
  --output-json /tmp/next_runtime_gaps.json

python3 tools/check_next_timer_route_readiness.py \
  --output-md /tmp/next_timer_route_readiness.md \
  --output-json /tmp/next_timer_route_readiness.json

python3 tools/check_next_production_cutover_readiness.py \
  --output-md /tmp/next_cutover_readiness.md \
  --output-json /tmp/next_cutover_readiness.json
```

## Health Gate

Expected production health:

```json
{
  "database_mode": "postgres",
  "fixture_mode": false,
  "production_data_ready": true,
  "runtime_owner": "ai_crm_next"
}
```

If production reports fixture mode, stop and fix environment/config before continuing.

## Admin And API Smoke

Check these surfaces manually or with authenticated browser/API smoke:

- `/admin`
- `/admin/customers`
- `/admin/questionnaires`
- `/admin/wechat-pay/products`
- `/admin/image-library`
- `/admin/attachment-library`
- `/admin/miniprogram-library`
- `/admin/automation-conversion`
- `/api/customers`
- `/api/admin/questionnaires`
- `/api/admin/wechat-pay/products`
- `/api/admin/automation-conversion/overview`

## Timer Re-enable Gate

Only after `tools/check_next_timer_route_readiness.py` passes on the server:

```bash
sudo systemctl enable --now aicrm-reply-monitor-run-due.timer
sudo systemctl enable --now aicrm-reply-monitor-capture.timer
sudo systemctl enable --now aicrm-automation-jobs-run-due.timer
sudo systemctl enable --now aicrm-campaign-run-due.timer
```

Do not enable timers if token guard fails or any timer route returns 404.

## Callback Fallback

Do not remove the 5013 callback fallback in this phase. Keep the Nginx temporary callback split until Next callback has real observation evidence.

## Rollback

- Revert the GitHub PR if Next production route behavior regresses.
- Keep 5013 callback fallback running during rollback.
- Disable timers again if timer routes return non-diagnostic 5xx after enablement.
