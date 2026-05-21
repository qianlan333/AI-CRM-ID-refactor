# D8.1 Planning Closeout

Date: 2026-05-22

Status: readiness acceptance for D8.0/D8.1 planning only.

This closeout starts from `origin/main` after PR #512. It does not start D8.2 runtime enforcement, does not create a `legacy_flask/` archive package, does not add a runtime lockdown guard, and does not change application runtime behavior.

## Acceptance Summary

| Check | Result | Evidence |
| --- | --- | --- |
| D8.0 planning docs/checker/tests present | pass | `docs/d8_legacy_flask_shell_retirement_plan.md`, dependency inventory, allowed fallback matrix, `tools/check_d8_legacy_shell_retirement_readiness.py`, and `tests/test_d8_legacy_shell_retirement_readiness.py` exist. |
| D8.1 planning docs/checker/tests present | pass | `docs/d8_1_legacy_fallback_route_lockdown_plan.md`, route matrix, `tools/check_d8_1_legacy_fallback_route_lockdown.py`, and `tests/test_d8_1_legacy_fallback_route_lockdown.py` exist. |
| D8.2-D8.5 not restored | pass | No D8.2-D8.5 docs, tools, tests, runtime package, or enforcement files were added by this closeout. |
| No archive package | pass | `legacy_flask/` is absent. |
| No runtime lockdown shim | pass | `wecom_ability_service/legacy_lockdown.py` is absent. |
| Runtime behavior unchanged | pass | `app.py --help` still reports AI-CRM Next as default runtime with explicit legacy fallback commands. |
| Legacy fallback import works | pass | `from legacy_flask_app import main` succeeds. |
| Default runtime remains Next | pass | `app.py` remains the default AI-CRM Next entry. |
| D8 delete gate unmet | pass | D8.0 plan still requires D7 real external replacement evidence, production observation, no legacy route hits, rollback independence, Next-only deploy/systemd path, and human signoff. |
| Forbidden readiness/status markers absent | pass | D8 docs were scanned by targeted tests; the forbidden readiness/status marker strings are absent. |

## Verification Results

| Command | Result |
| --- | --- |
| `bash scripts/check_no_duplicate_next_source.sh` | PASS |
| `python3 tools/check_d8_legacy_shell_retirement_readiness.py --output-md /tmp/d8_legacy_shell_readiness.md --output-json /tmp/d8_legacy_shell_readiness.json` | PASS |
| `python3 tools/check_d8_1_legacy_fallback_route_lockdown.py --output-md /tmp/d8_1_legacy_fallback_route_lockdown.md --output-json /tmp/d8_1_legacy_fallback_route_lockdown.json` | PASS |
| `python3 -m pytest -q tests/test_d8_*.py` | 16 passed |
| `scripts/run_tests.sh` | 720 passed, 888 skipped |
| `cd experiments/ai_crm_next && .venv/bin/python -m pytest -q` | 394 passed, 3 skipped |
| `python3 app.py --help` | PASS |
| `python3 legacy_flask_app.py --help` | PASS |
| `from legacy_flask_app import main` smoke | PASS |

## Closeout Decision

D8.0/D8.1 planning is accepted as planning/readiness-only. The next phase must not be treated as approved runtime enforcement. Any D8.2 work requires a separate branch, explicit scope, and a fresh safety review.

## Safety

- No production/deploy/nginx/systemd config changes.
- No real traffic cutover.
- No real external service calls.
- No write endpoints executed.
- No legacy shell or fallback deletion.
- No D8.2-D8.5 or D9 work.
