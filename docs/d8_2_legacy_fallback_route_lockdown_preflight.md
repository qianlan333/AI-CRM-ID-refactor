# D8.2 Legacy Fallback Route Lockdown Preflight

Date: 2026-05-22

Status: preflight only.

This preflight checks whether D8.2 legacy fallback route lockdown enforcement is ready to implement. It does not create runtime enforcement, does not create a `legacy_flask/` archive package, does not add `wecom_ability_service/legacy_lockdown.py`, and does not change `app.py` or `legacy_flask_app.py` behavior.

## Inputs

| Input | Purpose |
| --- | --- |
| `docs/d8_legacy_flask_shell_retirement_plan.md` | Confirms D8.0 remains planning/readiness only and keeps the shell deletion gate blocked. |
| `docs/d8_legacy_shell_allowed_fallback_matrix.md` | Documents fallback surfaces that must remain allowed while blockers exist. |
| `docs/d8_1_legacy_fallback_route_lockdown_plan.md` | Confirms D8.1 remains planning-only and does not register runtime enforcement. |
| `docs/d8_1_legacy_fallback_route_matrix.md` | Provides the D8.1 docs matrix for future route/fallback lockdown planning. |
| `docs/legacy_delete_batches.md` | Provides D1-D6 retired readonly route status. |
| `app.py`, `legacy_flask_app.py` | Confirm default runtime and explicit fallback usage. |

## Preflight Findings

| Check | Current result | Readiness impact |
| --- | --- | --- |
| D8.0/D8.1 planning package present | present | Satisfied. |
| D8.1 matrix covers D1-D6 retired readonly routes | not fully covered | D8.2 enforcement is not ready. The matrix currently focuses on high-risk fallback categories and must add explicit D1-D6 readonly entries before enforcement. |
| Allowed fallback matrix covers high-risk fallback categories | mostly covered | Operational diagnostics fallback is not explicit enough and should be added before enforcement. |
| Retired readonly and allowed fallback routes conflict | no conflict found in this preflight | Satisfied for planning; future enforcement still needs route-level review. |
| Default runtime remains AI-CRM Next | yes | Satisfied. |
| Legacy fallback remains explicit only | yes | Satisfied. |
| Legacy fallback runner help/import | works | Satisfied. |
| `legacy_flask/` package | absent | Satisfied. |
| `wecom_ability_service/legacy_lockdown.py` runtime guard | absent | Satisfied. |
| D8 forbidden readiness/status marker strings | absent | Satisfied. |
| production/deploy/nginx/systemd config changes | none in this branch | Satisfied. |

## Readiness Decision

D8.2 runtime enforcement is not ready to implement from the current D8.1 matrix. The next safe step is to update planning coverage for D1-D6 retired readonly routes and operational diagnostics fallback, then rerun this preflight.

No runtime work is approved by this report.

## Safety

- No `legacy_flask/` package creation.
- No runtime lockdown guard.
- No `app.py` or `legacy_flask_app.py` behavior change.
- No `wecom_ability_service` move.
- No legacy shell or fallback deletion.
- No D8.3-D8.5 or D9 work.
- No production/deploy/nginx/systemd config changes.
- No real external calls.
- No write endpoint execution.
