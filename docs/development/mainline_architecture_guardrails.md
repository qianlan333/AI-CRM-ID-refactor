# Mainline Architecture Guardrails

## Business Impact

This report gives each post-merge mainline a readable health snapshot before the
team continues deployment or migrates more business capability to AI-CRM Next.
It helps spot fixture leakage, route ownership drift, timer risk, external-call
risk, and legacy fallback removal risk before those become sales, operations, or
customer-facing incidents.

## Checker

Run:

```bash
.venv/bin/python tools/check_mainline_architecture_guardrails.py \
  --output-md /tmp/mainline_architecture_guardrails.md \
  --output-json /tmp/mainline_architecture_guardrails.json
```

The checker aggregates:

- Architecture skill compliance
- Architecture doc consistency
- Route ownership manifest
- Production route resolution
- Repository provider hardening
- Admin read model boundary
- Admin real data binding
- Production runtime gaps
- Timer route readiness

## Safety Defaults

- `safe_to_enable_timers` is false unless timer readiness passes and audited
  server canary evidence is present.
- `safe_to_enable_real_external_calls` is always false in this local checker.
- `safe_to_remove_legacy_fallback` is always false in this local checker.
- Local checker output is not production canary evidence.

## Blocking Rules

- `architecture_skill_compliance` failure is a blocker.
- `repository_provider_hardening` failure is a blocker.
- Missing `production_route_resolution` output is a blocker.
- Non-empty `shadowed_exact_routes` is a blocker.
- Critical checker failures are reported as blockers; timer readiness failures
  stay warnings unless a future server-side verifier supplies audited evidence.

## Non-Goals

This checker does not modify runtime, routes, deploy config, timers, external
calls, or legacy fallback behavior.
