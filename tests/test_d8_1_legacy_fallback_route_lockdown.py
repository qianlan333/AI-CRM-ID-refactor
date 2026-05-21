from __future__ import annotations

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def _checker():
    return importlib.import_module("tools.check_d8_1_legacy_fallback_route_lockdown")


def test_d8_1_required_files_exist() -> None:
    for relpath in [
        "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
        "docs/d8_1_legacy_fallback_route_matrix.md",
        "tools/check_d8_1_legacy_fallback_route_lockdown.py",
        "tests/test_d8_1_legacy_fallback_route_lockdown.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists(), relpath


def test_retired_readonly_routes_are_present_in_matrix() -> None:
    text = _read("docs/d8_1_legacy_fallback_route_matrix.md")
    required = [
        "/admin/image-library",
        "/api/admin/image-library",
        "/admin/attachment-library",
        "/api/admin/attachment-library",
        "/admin/miniprogram-library",
        "/api/admin/miniprogram-library",
        "/admin/wechat-pay/products",
        "/api/admin/wechat-pay/products",
        "/api/customers",
        "/admin/customers",
        "/api/admin/user-ops/overview",
        "/api/admin/user-ops/list",
        "/api/admin/user-ops/send-records",
        "/api/admin/questionnaires",
        "/admin/questionnaires",
        "/s/{slug}",
        "/api/h5/questionnaires/{slug}",
        "/admin/automation-conversion",
        "/api/admin/automation-conversion/overview",
        "/api/admin/automation-conversion/pools",
        "/api/admin/automation-conversion/members",
        "/api/admin/automation-conversion/execution-records",
    ]
    for route in required:
        assert route in text


def test_retired_readonly_routes_have_expected_false() -> None:
    checker = _checker()
    rows = checker.parse_matrix(PROJECT_ROOT / "docs/d8_1_legacy_fallback_route_matrix.md")
    retired = [row for row in rows if row["category"] == "retired_readonly_route"]
    assert retired
    assert all(row["legacy_registration_expected"].lower() == "false" for row in retired)


def test_allowed_fallback_routes_have_expected_true() -> None:
    checker = _checker()
    rows = checker.parse_matrix(PROJECT_ROOT / "docs/d8_1_legacy_fallback_route_matrix.md")
    allowed = [
        row
        for row in rows
        if row["category"] in {"allowed_fallback", "write_external_fallback", "diagnostic_only"}
    ]
    assert allowed
    assert all(row["legacy_registration_expected"].lower() == "true" for row in allowed)


def test_checker_runs_and_returns_ok() -> None:
    result = _checker().run_check("docs/d8_1_legacy_fallback_route_matrix.md")
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["retired_routes_still_registered"] == []
    assert result["legacy_route_map_available"] is True
    assert result["production_config_modified"] is False
    assert result["recommendation"] == "READY_FOR_D8_1_LOCKDOWN_PLANNING_ACCEPTANCE_NOT_ENFORCED"


def test_checker_fails_if_retired_route_is_marked_expected_true(tmp_path: Path) -> None:
    matrix = _read("docs/d8_1_legacy_fallback_route_matrix.md")
    broken = matrix.replace(
        "| `/admin/image-library` | GET | retired_readonly_route | false |",
        "| `/admin/image-library` | GET | retired_readonly_route | true |",
        1,
    )
    matrix_path = tmp_path / "broken_matrix.md"
    matrix_path.write_text(broken, encoding="utf-8")
    result = _checker().run_check(str(matrix_path))
    assert result["ok"] is False
    assert any(item["reason"] == "retired_route_expected_true" for item in result["blockers"])


def test_checker_fails_if_matrix_omits_d1_d6_route_groups(tmp_path: Path) -> None:
    matrix_path = tmp_path / "missing_groups.md"
    matrix_path.write_text(
        "\n".join(
            [
                "| route_or_pattern | method | category | legacy_registration_expected | next_owner | reason | lockdown_action | retirement_condition | risk | notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                "| `/admin/image-library` | GET | retired_readonly_route | false | `aicrm_next.media_library` | only one row | blocker if registered | done | stale | incomplete |",
                "| `/admin/jobs` | GET | diagnostic_only | true | future diagnostics | allowed | allow | replaced | confusion | diagnostic |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    result = _checker().run_check(str(matrix_path))
    assert result["ok"] is False
    assert any(item["reason"] == "retired_route_group_missing" for item in result["blockers"])


def test_app_py_default_remains_next() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert 'command = args.command or "run"' in content
    assert "run_next()" in content


def test_legacy_shell_and_openclaw_still_exist() -> None:
    assert (PROJECT_ROOT / "legacy_flask_app.py").exists()
    assert (PROJECT_ROOT / "wecom_ability_service").exists()
    assert (PROJECT_ROOT / "wecom_ability_service/http/__init__.py").exists()
    assert (PROJECT_ROOT / "openclaw_service").exists()


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
        "docs/d8_1_legacy_fallback_route_matrix.md",
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/d8_legacy_shell_allowed_fallback_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_retirement_plan.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_production_config_not_modified(monkeypatch) -> None:
    checker = _checker()
    monkeypatch.setattr(checker, "_changed_paths", lambda: ["docs/d8_1_legacy_fallback_route_matrix.md"])
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
    assert blockers == []
