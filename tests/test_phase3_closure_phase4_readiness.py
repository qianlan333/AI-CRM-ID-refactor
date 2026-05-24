from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_phase3_closure_phase4_readiness.py"
READINESS_YAML = ROOT / "docs/development/phase_3_closure_and_phase_4_readiness.yaml"
READINESS_MD = ROOT / "docs/development/phase_3_closure_and_phase_4_readiness.md"

EXPECTED_ROUTES = {
    "/api/sidebar/contact-binding-status",
    "/api/sidebar/customer-context",
    "/api/admin/customers/profile",
    "/api/admin/customers/profile/tags",
    "/api/customers",
    "/api/customers/{external_userid}",
    "/api/customers/{external_userid}/timeline",
    "/api/messages/{external_userid}/recent",
    "/admin/customers",
}
PROTECTED_RUNTIME_FILES = {
    "aicrm_next/main.py",
    "aicrm_next/production_compat/api.py",
    "aicrm_next/customer_read_model/api.py",
    "aicrm_next/customer_read_model/application.py",
    "aicrm_next/frontend_compat/legacy_routes.py",
}


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_phase3_closure_phase4_readiness",
        CHECKER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _readiness_data() -> dict:
    checker = _load_checker()
    return checker.load_readiness_yaml(READINESS_YAML)


def test_closure_readiness_checker_current_repo_passes():
    checker = _load_checker()
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_phase3_closure_flags_are_conservative():
    data = _readiness_data()
    phase3 = data["phase_3"]
    assert phase3["closeable"] is True
    assert phase3["fallback_removal_authorized"] is False
    assert phase3["production_cutover_authorized"] is False
    assert phase3["write_replacement_authorized"] is False


def test_yaml_includes_all_nine_phase3_routes_with_safety_fields():
    data = _readiness_data()
    routes = data["phase_3"]["routes"]
    assert {route["route_pattern"] for route in routes} == EXPECTED_ROUTES
    assert len(routes) == 9
    for route in routes:
        assert route["exact_next_owner_confirmed"] is True
        assert route["fallback_retained"] is True
        assert route["production_compat_unchanged"] is True
        assert route["delete_ready"] is False
        assert route["checker"]
        assert route["business_continuity_requirement"]


def test_phase4_cannot_start_automatically_and_forbidden_classes_are_listed():
    readiness = _readiness_data()["phase_4_readiness"]
    assert readiness["can_start_after_this_report"] is False
    assert readiness["requires_explicit_approval"] is True
    forbidden = set(readiness["forbidden_first_batch"])
    assert {
        "payment",
        "oauth",
        "wecom_external_call",
        "timer",
        "automation_execution",
        "media_upload",
        "openclaw_mcp_real_external_call",
    }.issubset(forbidden)


def test_phase4_candidate_rules_require_write_safety_gate():
    rules = _readiness_data()["phase_4_readiness"]["first_batch_candidate_rules"]
    for rule in (
        "no_real_external_side_effect",
        "bounded_internal_write_only",
        "idempotency_required",
        "audit_or_operator_identity_required",
        "rollback_required",
        "fallback_retained",
        "production_smoke_required",
        "checker_required",
    ):
        assert rules[rule] is True


def test_next_candidates_do_not_include_forbidden_external_side_effect_first_batch():
    data = _readiness_data()
    forbidden_terms = (
        "payment",
        "oauth",
        "wecom",
        "timer",
        "automation execution",
        "media upload",
        "openclaw",
        "mcp",
    )
    for candidate in data["next_candidates"]:
        text = f"{candidate['route_family']} {candidate['recommendation']}".lower()
        assert not any(term in text and "evaluate" not in text for term in forbidden_terms)
        assert candidate["excluded_side_effects"]
        assert candidate["required_guardrails"]
        assert candidate["rollback_requirement"]
        assert "daily" in candidate["daily_business_continuity_requirement"].lower()


def test_report_docs_do_not_claim_production_approval_or_cutover():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (READINESS_MD, READINESS_YAML)
    ).lower()
    forbidden_claims = (
        "production approved",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
        "fallback removal authorized",
        "production cutover authorized",
    )
    assert not any(claim in combined for claim in forbidden_claims)


def test_no_runtime_files_are_changed_when_git_diff_is_available():
    changed: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "origin/main"],
        ["git", "diff", "--name-only", "origin/main...HEAD"],
    ):
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0:
            changed.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    assert not (changed & PROTECTED_RUNTIME_FILES)
