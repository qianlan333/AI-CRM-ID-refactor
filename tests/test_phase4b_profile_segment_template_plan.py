from __future__ import annotations

import subprocess
from pathlib import Path

import tools.check_phase4b_profile_segment_template_plan as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_MD = ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4b_profile_segment_template_implementation_plan.yaml"


def _data() -> dict:
    return checker.load_yaml(PLAN_YAML)


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_yaml_authorization_flags_are_false() -> None:
    data = _data()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_route_family_and_owners_match_expected() -> None:
    data = _data()
    assert data["route_family"] == checker.EXPECTED_ROUTE_FAMILY
    assert data["capability_owner"] == checker.EXPECTED_CAPABILITY_OWNER
    assert data["integration_fallback_boundary"] == checker.EXPECTED_FALLBACK_BOUNDARY


def test_forbidden_scope_contains_required_classes() -> None:
    forbidden = set(_data()["phase_4c_scope"]["forbidden"])
    assert checker.REQUIRED_FORBIDDEN_SCOPE <= forbidden


def test_post_and_put_require_idempotency_audit_rollback_and_no_external_side_effect() -> None:
    routes = {(route["method"], route["path"]): route for route in _data()["routes"]}
    for key in checker.WRITE_ROUTE_KEYS:
        route = routes[key]
        assert route["idempotency_required"] is True
        assert route["audit_required"] is True
        assert route["rollback_required"] is True
        assert route["external_side_effect_allowed"] is False


def test_required_guardrails_all_true() -> None:
    guardrails = _data()["required_guardrails"]
    for field in checker.REQUIRED_GUARDRAILS:
        assert guardrails[field] is True


def test_phase_4c_entry_conditions_all_true() -> None:
    conditions = _data()["phase_4c_entry_conditions"]
    for field in checker.REQUIRED_ENTRY_CONDITIONS:
        assert conditions[field] is True


def test_owner_signoff_statuses_are_pending() -> None:
    signoff = _data()["owner_signoff"]
    for field in checker.REQUIRED_SIGNOFF_PENDING:
        assert signoff[field] == "pending"


def test_legacy_route_registration_exists() -> None:
    report = checker.check_legacy_route_registration()
    assert report["ok"], report


def test_production_compat_fallback_remains() -> None:
    report = checker.check_production_compat_fallback()
    assert report["ok"], report


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    report = checker.check_no_runtime_changes()
    assert report["ok"], report


def test_docs_do_not_claim_runtime_or_production_authorization() -> None:
    text = "\n".join([PLAN_MD.read_text(encoding="utf-8"), PLAN_YAML.read_text(encoding="utf-8")]).lower()
    forbidden_claims = (
        "implementation_authorized: true",
        "production_cutover_authorized: true",
        "fallback_removal_authorized: true",
        "production approved",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    )
    for claim in forbidden_claims:
        assert claim not in text


def test_cli_outputs_json_and_markdown(tmp_path: Path) -> None:
    json_path = tmp_path / "phase4b.json"
    md_path = tmp_path / "phase4b.md"
    completed = subprocess.run(
        [
            "python3",
            "tools/check_phase4b_profile_segment_template_plan.py",
            "--output-json",
            str(json_path),
            "--output-md",
            str(md_path),
        ],
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "overall: PASS" in completed.stdout
    assert json_path.exists()
    assert md_path.exists()
