# D7 Slim Phase 2A Checker Helper Report

## Scope

This PR starts from `origin/main` after PR #505. It only extracts mechanical
helper code for the D7.5-D7.7 contract checkers. It does not add D7 capability
behavior, does not start D8, does not delete fallback code, and does not
wrapperize parity or smoke tools.

## Helper Added

`tools/d7_contract_check_common.py` now owns shared checker primitives:

- project-root resolution and root `sys.path` setup
- project-relative path and text reading
- required-file collection
- adapter class/method presence checks
- temporary environment cleanup and restoration around mode checks
- repeated disabled/production-guard mode probing
- fake-operation result shape, idempotency, audit, and side-effect safety checks
- docs marker scanning
- JSON report writing and Markdown line writing

## Checkers Updated

| Checker | Shared logic moved | Capability-specific logic kept local |
| --- | --- | --- |
| `tools/check_d7_5_automation_adapter_contract.py` | path/read, adapter method scan, mode-guard loop, fake result safety, docs scan, missing-file collection, report writers | Automation write, activation, OpenClaw webhook, workflow runtime, agent runtime sample calls; automation application-boundary source checks; automation smoke/parity checks |
| `tools/check_d7_6_customer_sync_adapter_contract.py` | path/read, adapter method and contract scan, mode-guard loop, fake result safety, docs scan, missing-file collection, report writers | Archive, contacts, identity, and projection sample calls; customer/identity source-boundary checks; customer smoke/parity checks |
| `tools/check_d7_7_mcp_openclaw_adapter_contract.py` | path/read, required-file collection, adapter method and contract scan, mode-guard loop, fake result safety, docs scan, report writers | MCP, customer context, automation context, OpenClaw bridge, compatibility sample calls; dispatch/application source checks; OpenClaw service gate; customer and automation context smoke/parity checks |

## Guard Added

`tests/test_d7_slim_cleanup.py` now verifies that:

- `tools/d7_contract_check_common.py` exists and exposes the expected mechanical primitives.
- D7.5-D7.7 checkers import the helper.
- D7.5-D7.7 checkers still keep local sample calls and capability-specific safety strings.

## Safety Notes

- D7.1-D7.4 checkers are untouched.
- D7 implementation reports are untouched.
- D7 adapter boundary code is untouched.
- Legacy fallback code is untouched.
- Duplicate Next source under experiments remains absent.
- No production/deploy/nginx/systemd runtime configuration is changed.
- No real external call or write endpoint is executed by this change.

