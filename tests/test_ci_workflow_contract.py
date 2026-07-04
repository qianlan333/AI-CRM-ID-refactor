from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ci_runs_full_regression_and_scoped_postgres_gates_on_pr_and_main() -> None:
    source = _source(CI_WORKFLOW)

    assert "pull_request:" in source
    assert "push:" in source
    assert "python-tests:" in source
    assert "    env:\n      DATABASE_URL: postgresql://test:test@localhost:5432/test" not in source
    assert "Run architecture gates" in source
    assert "Run architecture gates\n        env:\n          DATABASE_URL: postgresql://test:test@localhost:5432/test" in source
    assert "bash scripts/ci/run_architecture_gates.sh" in source
    assert "Run PostgreSQL P0 regression slice" in source
    assert "tests/test_order_reconciliation_worker.py" in source
    assert "tests/test_identity_resolution_backfill_worker.py" in source
    assert "tests/test_channels_api_production_guard.py" in source
    assert "tests/test_admin_routes_require_auth.py::test_admin_api_routes_require_session_when_enforced" in source
    assert "Run PostgreSQL P0 regression slice\n        env:\n          DATABASE_URL: postgresql://test:test@localhost:5432/test" in source
    assert "Run full pytest regression (PG-only)" not in source
    assert "Run full pytest regression\n        run: python -m pytest tests/ -n auto" in source
    assert "python -m pytest tests/ -n auto" in source
    assert "tests/test_broadcast_jobs_service.py" not in source
    assert "Run PR smoke tests" not in source
    assert "Run main smoke tests" not in source


def test_ci_runs_frontend_typecheck_build_and_tests() -> None:
    source = _source(CI_WORKFLOW)

    assert "frontend-check:" in source
    assert "npm ci" in source
    assert "npm run typecheck" in source
    assert "npm run build:frontend" in source
    assert "git diff --exit-code" in source
    assert "npm run test:frontend" in source


def test_deploy_waits_for_successful_ci_on_main() -> None:
    source = _source(DEPLOY_WORKFLOW)

    assert "workflow_run:" in source
    assert 'workflows: ["CI"]' in source
    assert "types: [completed]" in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "github.event.workflow_run.head_branch == 'main'" in source
    assert "push:" not in source


def test_architecture_gate_script_runs_alembic_revision_guard() -> None:
    script = _source(ROOT / "scripts" / "ci" / "run_architecture_gates.sh")

    assert "tools/check_route_ownership_manifest.py" in script
    assert "tools/check_architecture_boundaries.py" in script
    assert "tools/check_external_effects_boundary.py" in script
    assert "tools/check_db_access_boundary.py" in script
    assert "tools/check_background_job_contract.py" in script
    assert "tools/check_data_table_lifecycle.py" in script
    assert "tests/test_alembic_revision_chain.py" in script
