from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools" / "check_d7_scope_isolation.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_d7_scope_isolation", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _docs_text() -> str:
    paths = [
        "docs/d7_adapter_baseline_summary.md",
        "docs/d7_4_scope_isolation_report.md",
        "docs/d7_4_product_payment_adapter_contract.md",
        "docs/d7_4_product_payment_adapter_implementation_report.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]
    return "\n".join((REPO_ROOT / path).read_text(encoding="utf-8") for path in paths)


def test_d7_adapter_baseline_summary_exists() -> None:
    assert (REPO_ROOT / "docs/d7_adapter_baseline_summary.md").exists()


def test_d7_4_scope_isolation_report_exists() -> None:
    assert (REPO_ROOT / "docs/d7_4_scope_isolation_report.md").exists()


def test_d7_1_to_d7_3_are_marked_accepted_prerequisite() -> None:
    text = (REPO_ROOT / "docs/d7_adapter_baseline_summary.md").read_text(encoding="utf-8")
    for stage in ("D7.1", "D7.2", "D7.3"):
        assert stage in text
    assert text.count("accepted_prerequisite") >= 3


def test_d7_4_is_marked_current_increment() -> None:
    text = (REPO_ROOT / "docs/d7_adapter_baseline_summary.md").read_text(encoding="utf-8")
    assert "D7.4" in text
    assert "current_increment" in text


def test_d7_4_report_lists_increment_files() -> None:
    text = (REPO_ROOT / "docs/d7_4_scope_isolation_report.md").read_text(encoding="utf-8")
    assert "### D7.4 increment files" in text
    assert "aicrm_next/integration_gateway/payment_adapters.py" in text
    assert "aicrm_next/commerce/application.py" in text


def test_no_out_of_scope_production_deploy_nginx_files() -> None:
    text = (REPO_ROOT / "docs/d7_4_scope_isolation_report.md").read_text(encoding="utf-8")
    assert "### out-of-scope files" in text
    assert "- none" in text
    increment = text.split("### D7.4 increment files", 1)[1].split("### Shared infrastructure files", 1)[0].lower()
    for token in ("deploy/", "nginx", "systemd", "supervisor", "docker-compose"):
        assert token not in increment


def test_no_forbidden_status_markers_in_d7_docs() -> None:
    text = _docs_text()
    assert "production_ready" not in text
    assert "production_approved" not in text
    assert "delete_ready" not in text


def test_scope_checker_returns_ok() -> None:
    checker = _load_checker()
    report = checker.build_report(
        baseline_summary=REPO_ROOT / "docs/d7_adapter_baseline_summary.md",
        d7_4_scope_report=REPO_ROOT / "docs/d7_4_scope_isolation_report.md",
    )
    assert report["ok"] is True
    assert report["accepted_prerequisites"] == ["D7.1", "D7.2", "D7.3"]
    assert report["current_increment"] == ["D7.4"]
    assert report["out_of_scope_files"] == []


def test_checker_fails_if_prerequisite_classification_is_omitted(tmp_path: Path) -> None:
    checker = _load_checker()
    baseline = tmp_path / "baseline.md"
    scope = tmp_path / "scope.md"
    baseline.write_text(
        "| stage | status |\n| --- | --- |\n| D7.1 | accepted_prerequisite |\n| D7.2 | accepted_prerequisite |\n| D7.3 | accepted_prerequisite |\n| D7.4 | current_increment |\n",
        encoding="utf-8",
    )
    scope.write_text(
        "### D7.4 increment files\n\n- `aicrm_next/commerce/application.py`\n\n"
        "### shared infrastructure files\n\n- `aicrm_next/integration_gateway/idempotency.py`\n\n"
        "### docs/tests/checkers\n\n- `docs/d7_4_scope_isolation_report.md`\n\n"
        "### out-of-scope files\n\n- none\n",
        encoding="utf-8",
    )
    report = checker.build_report(
        baseline_summary=baseline,
        d7_4_scope_report=scope,
        changed_files=["aicrm_next/commerce/application.py", "docs/d7_4_scope_isolation_report.md"],
    )
    assert report["ok"] is False
    assert any(item["reason"] == "missing_scope_classification_section" for item in report["blockers"])


def test_checker_fails_if_production_config_appears_in_d7_4_increment(tmp_path: Path) -> None:
    checker = _load_checker()
    baseline = tmp_path / "baseline.md"
    scope = tmp_path / "scope.md"
    baseline.write_text(
        "| stage | status |\n| --- | --- |\n| D7.1 | accepted_prerequisite |\n| D7.2 | accepted_prerequisite |\n| D7.3 | accepted_prerequisite |\n| D7.4 | current_increment |\n",
        encoding="utf-8",
    )
    scope.write_text(
        "### D7.1 baseline files\n\n- `aicrm_next/media_library/application.py`\n\n"
        "### D7.2 baseline files\n\n- `aicrm_next/questionnaire/application.py`\n\n"
        "### D7.3 baseline files\n\n- `aicrm_next/ops_enrollment/application.py`\n\n"
        "### D7.4 increment files\n\n- `deploy/production-nginx.conf`\n\n"
        "### shared infrastructure files\n\n- `aicrm_next/integration_gateway/idempotency.py`\n\n"
        "### docs/tests/checkers\n\n- `docs/d7_4_scope_isolation_report.md`\n\n"
        "### out-of-scope files\n\n- none\n",
        encoding="utf-8",
    )
    report = checker.build_report(
        baseline_summary=baseline,
        d7_4_scope_report=scope,
        changed_files=["deploy/production-nginx.conf"],
    )
    assert report["ok"] is False
    assert any(item["reason"] == "production_config_in_current_increment" for item in report["blockers"])


def test_app_py_default_runtime_remains_next() -> None:
    import app

    assert app.NEXT_APP_IMPORT == "aicrm_next.main:app"
    parser = app.build_parser()
    args = parser.parse_args([])
    assert args.command is None


def test_aicrm_next_has_no_old_backend_imports() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in text
        assert "openclaw_service" not in text
