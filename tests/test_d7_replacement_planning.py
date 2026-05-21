from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN = REPO_ROOT / "docs" / "d7_write_external_replacement_plan.md"
CATALOG = REPO_ROOT / "docs" / "d7_adapter_contract_catalog.md"
READINESS = REPO_ROOT / "docs" / "d7_capability_readiness_matrix.md"
BLOCKERS = REPO_ROOT / "docs" / "d7_write_external_blocker_matrix.md"
CHECKER_PATH = REPO_ROOT / "tools" / "check_d7_replacement_planning.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_d7_replacement_planning", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _docs_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (PLAN, CATALOG, READINESS, BLOCKERS))


def test_d7_master_plan_exists_and_batches_exist() -> None:
    assert PLAN.exists()
    text = PLAN.read_text(encoding="utf-8")
    for batch in ("D7.1", "D7.2", "D7.3", "D7.4", "D7.5", "D7.6", "D7.7"):
        assert batch in text


def test_adapter_contract_catalog_exists_and_required_adapters_all_covered() -> None:
    checker = _load_checker()
    assert CATALOG.exists()
    text = CATALOG.read_text(encoding="utf-8")
    for adapter in checker.REQUIRED_ADAPTERS:
        assert adapter in text


def test_capability_readiness_matrix_exists_and_required_capabilities_all_covered() -> None:
    checker = _load_checker()
    assert READINESS.exists()
    text = READINESS.read_text(encoding="utf-8")
    for capability in checker.REQUIRED_CAPABILITIES:
        assert capability in text


def test_d7_docs_have_no_forbidden_status_markers() -> None:
    text = _docs_text()
    assert "production_ready" not in text
    assert "production_approved" not in text
    assert "delete_ready" not in text


def test_production_mode_requires_explicit_env_flag_for_every_external_adapter() -> None:
    checker = _load_checker()
    rows = checker.parse_markdown_table(CATALOG)
    adapters = {row["adapter_name"]: row for row in rows if row.get("adapter_name")}
    for adapter in checker.REQUIRED_ADAPTERS:
        assert adapter in adapters
        assert "AICRM_NEXT_ENABLE_" in adapters[adapter]["production_enable_env_flags"]


def test_external_adapters_require_idempotency_audit_timeout_and_retry() -> None:
    checker = _load_checker()
    rows = checker.parse_markdown_table(CATALOG)
    for row in rows:
        if not row.get("adapter_name"):
            continue
        assert row["idempotency_key"]
        assert row["audit_log_required"] == "yes"
        assert row["timeout_policy"]
        assert row["retry_policy"]
        assert row["rollback_behavior"]


def test_checker_runs_and_returns_ok() -> None:
    checker = _load_checker()
    report = checker.build_report(BLOCKERS, PLAN, CATALOG, READINESS)
    assert report["ok"], report
    assert report["missing_capabilities"] == []
    assert report["missing_adapters"] == []
    assert report["forbidden_status_markers"] == []


def test_d7_docs_do_not_claim_real_external_calls_executed() -> None:
    text = _docs_text().lower()
    for claim in (
        "real external call executed",
        "real traffic cutover executed",
        "production canary executed",
        "production outbound enabled",
    ):
        assert claim not in text


def test_app_py_default_remains_next() -> None:
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source
    assert "Run AI-CRM Next FastAPI app (default runtime)." in source


def test_legacy_fallback_still_exists() -> None:
    assert (REPO_ROOT / "legacy_flask_app.py").exists()


def test_aicrm_next_has_no_old_backend_imports() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in source
        assert "openclaw_service" not in source
