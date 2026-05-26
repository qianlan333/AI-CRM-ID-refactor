# Post-Phase 7 New Feature Development Rules

Status: governance only. This bundle defines rules, templates, checker coverage,
and tests for future feature work. It does not implement a business feature.

## Current System State

Phase 7 final acceptance is complete. AI-CRM Next now has the architecture,
guardrails, cleanup evidence, and final acceptance records needed for post-Phase
7 development.

Fallback, production_compat, and legacy runtime remain retained. They exist for
compatibility and rollback only. New features must not rely on legacy fallback as
their primary path, and new features must not be implemented through
production_compat.

## Default Architecture Rules

All new features must prefer:

- `aicrm_next/*`
- Next native route, service, repository, and DTO boundaries
- explicit capability owner
- explicit route owner
- explicit tests
- explicit checker or guardrail
- explicit business continuity statement
- explicit rollback or degraded behavior

Forbidden by default:

- new `wecom_ability_service` business logic
- new legacy Flask page as a primary entry
- new production_compat fallback as the primary implementation
- new direct legacy import
- route without an owner
- route without tests
- external side effect without an explicit default-off gate

## Feature Categories

| Category | Default online | Feature flag | Canary | Owner approval | Rollback | production_compat allowed | fallback allowed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| internal_read / read-only | yes, if owned and tested | no | no | no | yes | no | compatibility only |
| internal_write / admin config | no | yes | yes | recommended | yes | no | rollback only |
| external_adapter / live external capability | no | yes | yes | yes | yes | no | rollback only |
| execution / timer / automation | no | yes | yes | yes | yes | no | no primary fallback |
| frontend_component / UI shell | yes, if Next native | case-by-case | case-by-case | no unless side effects | yes | no | legacy screen retained only |
| media / asset handling | no for live upload/publish | yes | yes | yes for live/public paths | yes | no | rollback only |
| payment / commerce | no | yes | yes | yes | yes | no | rollback only |
| OAuth / identity | no callback cutover by default | yes | yes | yes | yes | no | rollback only |
| WeCom / tags / callback / outbound | no outbound or callback cutover by default | yes | yes | yes | yes | no | rollback only |
| cleanup / retirement | no | n/a | n/a | yes | yes | no | n/a |

## New Feature PR Template

```markdown
## Summary
## Business value
## Capability owner
## Route family
## Architecture boundary
## Included stages
## Excluded stages
## Production behavior
## Fallback behavior
## production_compat behavior
## External side effects
## Data/schema impact
## Rollback
## Verification
## Risk
## Next step
## PR lifecycle
```

## Codex Development Prompt Template

```text
You are working in qianlan333/AI-CRM.

Before editing:
1. Read docs/route_ownership/production_route_ownership_manifest.yaml.
2. Read docs/development/post_phase7_new_feature_development_rules.md.
3. Choose the capability owner and route owner.

Rules:
- Do not implement the feature through legacy Flask, production_compat, or
  wecom_ability_service.
- Do not add direct legacy imports.
- Add focused tests and a checker or guardrail.
- Record business continuity and rollback/degraded behavior.
- Include full PR lifecycle.
- PR created does not count as complete; only merged into main counts.
```

## New Feature Admission Checks

The checker must verify:

- no new production_compat business route
- no new `wecom_ability_service` business route
- no new direct legacy import
- new route has owner
- new route has tests
- external side effect has a default-off gate
- timer or execution is default-off
- payment, OAuth, or WeCom callback has explicit approval gate
- frontend feature does not directly call a legacy API unless marked as a
  retained legacy screen

