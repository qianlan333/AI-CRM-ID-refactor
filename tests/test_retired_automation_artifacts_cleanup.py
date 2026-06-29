from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_old_automation_conversion_fixtures_are_removed() -> None:
    assert not (ROOT / "tests" / "fixtures" / "old_automation_conversion").exists()
    assert not (ROOT / "experiments" / "ai_crm_next" / "tests" / "fixtures" / "old_automation_conversion").exists()


def test_old_automation_conversion_experiment_parity_tools_are_removed() -> None:
    retired_paths = [
        ROOT / "experiments" / "ai_crm_next" / "tools" / "compare_automation_conversion_parity.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "automation_readonly_gray_smoke.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_6_automation_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "seed_old_flask_automation_sample.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_automation_conversion_parity.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_automation_readonly_gray_smoke.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_6_automation_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_seed_old_flask_automation_sample.py",
    ]
    for path in retired_paths:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_retired_reply_monitor_readiness_tool_is_removed() -> None:
    assert not (ROOT / "tools" / "check_reply_monitor_run_due_readiness.py").exists()


def test_retired_experiment_canary_readiness_tools_are_removed() -> None:
    retired_paths = [
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_1_media_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_1_media_production_signoff_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_2_product_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_3_customer_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_4_user_ops_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_batch_5_questionnaire_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "check_production_canary_approval_package.py",
        ROOT / "experiments" / "ai_crm_next" / "tools" / "generate_gray_release_report.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_1_media_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_1_media_production_signoff_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_2_product_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_3_customer_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_4_user_ops_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_batch_5_questionnaire_canary_readiness.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_gray_release_runbook.py",
        ROOT / "experiments" / "ai_crm_next" / "tests" / "test_production_canary_approval_package.py",
    ]
    for path in retired_paths:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_retired_automation_conversion_split_blueprint_is_removed() -> None:
    assert not (ROOT / "docs" / "refactor" / "automation-conversion-split-blueprint.md").exists()
