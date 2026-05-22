from __future__ import annotations

import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_D7_STATUS_MARKERS = ("production_ready", "production_approved", "delete_ready")
PROTECTED_FALLBACKS = [
    "legacy_flask_app.py",
    "wecom_ability_service/__init__.py",
    "wecom_ability_service/routes.py",
    "wecom_ability_service/http/__init__.py",
    "wecom_ability_service/http/wechat_pay.py",
    "wecom_ability_service/http/alipay_pay.py",
    "wecom_ability_service/http/admin_wechat_pay.py",
    "wecom_ability_service/http/admin_alipay_pay.py",
    "wecom_ability_service/http/archive.py",
    "wecom_ability_service/http/contacts.py",
    "wecom_ability_service/http/identity.py",
]
HIGH_CRITICAL_CAPABILITIES = [
    "User Ops DND",
    "User Ops batch-send execute",
    "Questionnaire submit",
    "Questionnaire OAuth",
    "WeChat Pay checkout / notify",
    "Alipay checkout / notify / return",
    "WeCom media upload",
    "Customer archive sync",
    "Contacts sync",
    "Identity mapping",
    "Automation activation webhook",
    "Automation OpenClaw push",
    "Automation workflow runtime",
    "MCP / OpenClaw legacy adapter",
]
PARITY_SMOKE_WRAPPERS = [
    "compare_automation_conversion_parity.py",
    "compare_commerce_parity.py",
    "compare_customer_read_model_parity.py",
    "compare_media_library_parity.py",
    "compare_questionnaire_parity.py",
    "compare_user_ops_parity.py",
    "automation_readonly_gray_smoke.py",
    "customer_read_model_gray_smoke.py",
    "media_library_gray_smoke.py",
    "product_management_gray_smoke.py",
    "questionnaire_readonly_gray_smoke.py",
    "user_ops_readonly_gray_smoke.py",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_duplicate_next_source_is_absent() -> None:
    assert not (REPO_ROOT / "experiments/ai_crm_next/src/aicrm_next").exists()
    assert list((REPO_ROOT / "experiments/ai_crm_next").glob("**/src/aicrm_next*")) == []


def test_old_fixture_data_is_not_byte_duplicated_between_root_and_experiments() -> None:
    root_fixture_root = REPO_ROOT / "tests" / "fixtures"
    experiments_fixture_root = REPO_ROOT / "experiments" / "ai_crm_next" / "tests" / "fixtures"
    duplicate_pairs: list[str] = []

    for root_path in root_fixture_root.glob("old_*/*"):
        if not root_path.is_file():
            continue
        experiments_path = experiments_fixture_root / root_path.relative_to(root_fixture_root)
        if experiments_path.exists() and _sha256(root_path) == _sha256(experiments_path):
            duplicate_pairs.append(str(root_path.relative_to(REPO_ROOT)))

    assert duplicate_pairs == []


def test_d7_docs_do_not_claim_production_or_delete_readiness() -> None:
    docs_text = "\n".join(path.read_text(encoding="utf-8") for path in (REPO_ROOT / "docs").glob("d7_*.md"))
    for marker in FORBIDDEN_D7_STATUS_MARKERS:
        assert marker not in docs_text


def test_d7_blocker_matrix_still_covers_high_and_critical_capabilities() -> None:
    matrix = (REPO_ROOT / "docs" / "d7_write_external_blocker_matrix.md").read_text(encoding="utf-8")
    for capability in HIGH_CRITICAL_CAPABILITIES:
        assert capability in matrix
    assert "| critical |" in matrix or "| high |" in matrix


def test_d7_experiment_tools_are_not_byte_copies_of_root_tools() -> None:
    root_tools = REPO_ROOT / "tools"
    experiment_tools = REPO_ROOT / "experiments" / "ai_crm_next" / "tools"
    duplicate_tools: list[str] = []

    for root_path in list(root_tools.glob("compare_*_parity.py")) + list(root_tools.glob("*_smoke.py")):
        experiment_path = experiment_tools / root_path.name
        if experiment_path.exists() and _sha256(root_path) == _sha256(experiment_path):
            duplicate_tools.append(root_path.name)

    assert duplicate_tools == []


def test_d7_experiment_parity_smoke_tools_are_thin_wrappers() -> None:
    experiment_tools = REPO_ROOT / "experiments" / "ai_crm_next" / "tools"
    root_tools = REPO_ROOT / "tools"

    helper = experiment_tools / "_root_tool_wrapper.py"
    helper_text = helper.read_text(encoding="utf-8")
    assert "spec_from_file_location" in helper_text
    assert "sys.modules[module_name]" in helper_text

    for name in PARITY_SMOKE_WRAPPERS:
        wrapper = experiment_tools / name
        root_tool = root_tools / name
        assert wrapper.exists(), name
        assert root_tool.exists(), name
        text = wrapper.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 16, name
        assert "load_root_tool(__file__, __name__)" in text
        assert "def run_smoke" not in text
        assert "def run_compare" not in text
        assert "TestClient" not in text
        assert "httpx" not in text


def test_d7_protected_fallback_files_still_exist() -> None:
    missing = [path for path in PROTECTED_FALLBACKS if not (REPO_ROOT / path).exists()]
    assert missing == []
    assert not (REPO_ROOT / "openclaw_service").exists()


def test_d7_phase2a_late_checkers_use_mechanical_shared_helper() -> None:
    helper = REPO_ROOT / "tools" / "d7_contract_check_common.py"
    assert helper.exists()
    helper_text = helper.read_text(encoding="utf-8")
    for helper_name in [
        "resolve_project_root",
        "read_project_text",
        "check_adapter_methods",
        "check_adapter_mode_guards",
        "check_fake_operation_result_safety",
        "scan_docs_for_forbidden_markers",
        "write_json_report",
        "write_markdown_lines",
    ]:
        assert f"def {helper_name}" in helper_text

    checker_paths = [
        REPO_ROOT / "tools" / "check_d7_5_automation_adapter_contract.py",
        REPO_ROOT / "tools" / "check_d7_6_customer_sync_adapter_contract.py",
        REPO_ROOT / "tools" / "check_d7_7_mcp_openclaw_adapter_contract.py",
    ]
    for path in checker_paths:
        text = path.read_text(encoding="utf-8")
        assert "from tools.d7_contract_check_common import" in text
        assert "def _sample_call" in text
        assert "check_fake_operation_result_safety" in text
        assert "scan_docs_for_forbidden_markers" in text

    assert "automation_application_boundary_missing" in checker_paths[0].read_text(encoding="utf-8")
    assert "customer_sync_application_boundary_missing" in checker_paths[1].read_text(encoding="utf-8")
    assert "openclaw_service_missing" in checker_paths[2].read_text(encoding="utf-8")
