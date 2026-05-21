# D7 Slim Phase 2B Parity/Smoke Wrapper Report

## Scope

This change starts from `origin/main` after PR #507. It does not start D8, does
not add new D7 capability behavior, does not delete adapter boundary code, and
does not delete legacy fallback or D7 blocker coverage.

## Canonical Tool Layout

Root `tools/` is now the canonical source for all D7 parity and smoke tools.
`experiments/ai_crm_next/tools/` keeps command-compatible paths only as thin
wrappers through `_root_tool_wrapper.py`.

| Capability | Canonical parity tool | Canonical smoke tool | Experiments path |
| --- | --- | --- | --- |
| User Ops | `tools/compare_user_ops_parity.py` | `tools/user_ops_readonly_gray_smoke.py` | thin wrapper |
| Customer Read Model | `tools/compare_customer_read_model_parity.py` | `tools/customer_read_model_gray_smoke.py` | thin wrapper |
| Questionnaire | `tools/compare_questionnaire_parity.py` | `tools/questionnaire_readonly_gray_smoke.py` | thin wrapper |
| Automation | `tools/compare_automation_conversion_parity.py` | `tools/automation_readonly_gray_smoke.py` | thin wrapper |
| Commerce | `tools/compare_commerce_parity.py` | `tools/product_management_gray_smoke.py` | thin wrapper |
| Media | `tools/compare_media_library_parity.py` | `tools/media_library_gray_smoke.py` | thin wrapper |

## Wrapper Behavior

Each experiments wrapper:

- loads the matching root tool file by path;
- replaces the imported experiments module with the root module so monkeypatches
  target the canonical implementation;
- keeps the old CLI path executable by forwarding to the root `main()`.

## Test Assertion Changes

Former source-text checks against experiments tool files are now runtime safety
assertions:

- Product checks validate checkout/payment/external flags from the smoke report.
- User Ops checks validate write, WeCom dispatch, media upload, and deferred job
  flags from the smoke report.
- Questionnaire checks validate submit, OAuth, WeCom tag, and external webhook
  flags from the smoke report.
- Automation checks validate activation webhook, OpenClaw push, workflow runtime,
  WeCom dispatch, and external webhook flags from the smoke report.
- Experiments smoke tests assert the imported module resolves to root `tools/`
  and validate the same side-effect safety flags.

## Guard

`tests/test_d7_slim_cleanup.py` now checks that experiments parity/smoke tools
are short wrappers, not full duplicated implementations. The guard allows the
wrapper compatibility paths but rejects copied `run_smoke` or `run_compare`
logic under experiments.

## Safety

- Duplicate Next source remains absent.
- Root `aicrm_next/` remains the only Next production source.
- D7 adapter code, legacy fallback, D7 blocker matrix, readiness matrix, and
  adapter catalog are untouched.
- No production/deploy/nginx/systemd runtime configuration is changed.
- No real external call or write endpoint is executed.
