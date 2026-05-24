from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "tools/check_phase3_readonly_acceptance.py"
ACCEPTANCE_YAML = ROOT / "docs/development/phase_3_readonly_replacement_acceptance_report.yaml"
ACCEPTANCE_MD = ROOT / "docs/development/phase_3_readonly_replacement_acceptance_report.md"


EXPECTED_ENDPOINTS = {
    "/api/sidebar/contact-binding-status": "aicrm_next.identity_contact.api",
    "/api/sidebar/customer-context": "aicrm_next.customer_read_model.api",
    "/api/admin/customers/profile": "aicrm_next.customer_read_model.api",
    "/api/admin/customers/profile/tags": "aicrm_next.customer_read_model.api",
    "/api/customers": "aicrm_next.customer_read_model.api",
    "/api/customers/{external_userid}": "aicrm_next.customer_read_model.api",
    "/api/customers/{external_userid}/timeline": "aicrm_next.customer_read_model.api",
    "/api/messages/{external_userid}/recent": "aicrm_next.customer_read_model.api",
}


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_phase3_readonly_acceptance",
        CHECKER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _acceptance_data() -> dict:
    checker = _load_checker()
    return checker.load_acceptance_yaml(ACCEPTANCE_YAML)


def test_acceptance_checker_current_repo_passes_when_fastapi_available():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    report = checker.build_report()
    assert report["overall"] == "PASS", report


def test_acceptance_yaml_contains_eight_phase3_routes():
    data = _acceptance_data()
    routes = data["routes"]
    assert len(routes) == 8
    assert {route["route_pattern"] for route in routes} == set(EXPECTED_ENDPOINTS)


def test_each_route_has_required_safety_fields():
    data = _acceptance_data()
    for route in data["routes"]:
        assert route["legacy_fallback_retained"] is True
        assert route["production_compat_unchanged"] is True
        assert route["delete_ready"] is False
        assert route["exact_next_owner_required"] is True
        assert route["compatibility_facade_header_allowed"] is False
        assert route["production_unavailable_must_degrade"] is True
        assert route["fixture_success_blocked"] is True
        assert route["real_external_calls_allowed"] is False
        assert route["business_continuity_requirement"]
        assert route["rollback"]


def test_endpoint_modules_match_expected_exact_owners():
    data = _acceptance_data()
    for route in data["routes"]:
        assert route["endpoint_module"] == EXPECTED_ENDPOINTS[route["route_pattern"]]


def test_production_probe_does_not_return_200_fake_success():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    with checker.production_phase3_acceptance_probe_env():
        client = checker._make_client()
        probe_report = checker.check_fastapi_acceptance_probes()
    assert probe_report["ok"], probe_report
    for record in probe_report["probes"]:
        assert not (record["status_code"] == 200 and record["fixture_marker_present"])


def test_child_phase_checkers_are_referenced_and_pass():
    pytest.importorskip("fastapi")
    checker = _load_checker()
    data = _acceptance_data()
    referenced = {route["checker"] for route in data["routes"]}
    assert referenced == set(checker.EXPECTED_CHECKERS)
    report = checker.check_phase_reports()
    assert report["ok"], report


def test_report_docs_do_not_claim_cutover_or_delete_ready():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ACCEPTANCE_MD, ACCEPTANCE_YAML)
    ).lower()
    forbidden_phrases = (
        "production cutover",
        "production approved",
        "canary approved",
        "delete_ready: true",
        "delete ready: true",
    )
    assert not any(phrase in combined for phrase in forbidden_phrases)


def test_next_candidates_defer_side_effect_families():
    data = _acceptance_data()
    candidates = data["next_candidates"]
    deferred = [candidate for candidate in candidates if candidate["category"] == "defer"]
    assert deferred
    immediate = [
        candidate
        for candidate in candidates
        if candidate["recommendation"] != "defer"
    ]
    side_effect_terms = {"Payment", "OAuth", "WeCom", "timer", "automation execution"}
    assert not any(
        any(term.lower() in str(candidate["route_pattern"]).lower() for term in side_effect_terms)
        for candidate in immediate
    )


def test_runtime_behavior_files_are_not_modified():
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "origin/main",
            "--",
            "aicrm_next/main.py",
            "aicrm_next/production_compat/api.py",
        ],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    assert result.stdout.strip() == ""
