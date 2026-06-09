from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
LEGACY_BACKLOG_CHECK = "tools/generate_legacy_replacement_backlog.py --check"
LEGACY_LAYOUT_TARGETS = (
    "tests/test_refactor_guardrails.py",
    "tests/test_service_layer_layout.py",
)
RETIRED_LEGACY_SMOKE_TESTS = (
    "tests/integration/test_pg_compat_smoke.py",
    "tests/test_postgres_schema_retry.py",
    "tests/test_hxc_dashboard_snapshot.py",
    "tests/test_admin_rbac_navigation.py",
    "tests/test_admin_navigation_groups.py",
)


def _ci_source() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _job_block(source: str, job_name: str, next_job_name: str | None = None) -> str:
    start = source.index(f"{job_name}:")
    if next_job_name is None:
        return source[start:]
    return source[start:source.index(f"{next_job_name}:")]


def test_main_push_uses_smoke_not_full_regression():
    source = _ci_source()

    main_smoke_block = _job_block(source, "main-smoke", "full-test")
    full_test_block = _job_block(source, "full-test")

    assert "if: github.event_name == 'push'" in main_smoke_block
    assert "Run main smoke tests (PG-only, targeted)" in main_smoke_block
    assert "python -m pytest \\" in main_smoke_block
    assert "if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'" in full_test_block
    assert "python -m pytest tests/ -n auto" in full_test_block


def test_full_test_keeps_complete_regression_and_backlog_drift_check():
    source = _ci_source()
    full_test_block = _job_block(source, "full-test")

    assert "python -m pytest tests/ -n auto" in full_test_block
    assert LEGACY_BACKLOG_CHECK in full_test_block


def test_pr_and_main_smoke_skip_legacy_doc_and_layout_guardrails():
    source = _ci_source()
    smoke_blocks = (
        _job_block(source, "pr-smoke", "main-smoke"),
        _job_block(source, "main-smoke", "full-test"),
    )

    for smoke_block in smoke_blocks:
        assert LEGACY_BACKLOG_CHECK not in smoke_block
        for test_path in LEGACY_LAYOUT_TARGETS:
            assert test_path not in smoke_block
        for test_path in RETIRED_LEGACY_SMOKE_TESTS:
            assert test_path not in smoke_block


def test_main_smoke_keeps_recently_touched_critical_paths():
    source = _ci_source()
    main_smoke_block = _job_block(source, "main-smoke", "full-test")

    for test_path in (
        "tests/test_post_closeout_production_contract.py",
        "tests/test_next_source_consolidation.py",
        "tests/test_user_ops_import_parsers.py",
        "tests/test_user_ops_page_service_helpers.py",
        "tests/test_hxc_dashboard_api_contract.py",
        "tests/test_send_task.py",
        "tests/test_admin_auth_route_precedence.py",
        "tests/test_admin_shell_native.py",
        "tests/test_wechat_pay_products.py",
        "tests/test_wechat_pay_admin_transactions.py",
    ):
        assert test_path in main_smoke_block


def test_pr_smoke_covers_admin_navigation_and_wechat_pay_splits():
    source = _ci_source()
    pr_smoke_block = _job_block(source, "pr-smoke", "main-smoke")

    assert "bash scripts/check_no_duplicate_next_source.sh" in pr_smoke_block

    for test_path in (
        "tests/test_admin_auth_route_precedence.py",
        "tests/test_admin_shell_native.py",
        "tests/test_wechat_pay_products.py",
        "tests/test_wechat_pay_admin_transactions.py",
    ):
        assert test_path in pr_smoke_block
