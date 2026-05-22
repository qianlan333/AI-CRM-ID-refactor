from __future__ import annotations

from tools import check_mainline_architecture_guardrails as checker


def _ok_results() -> dict[str, dict]:
    return {
        "architecture_skill_compliance": {"ok": True, "blockers": [], "warnings": []},
        "architecture_doc_consistency": {"ok": True, "blockers": [], "warnings": []},
        "route_ownership_manifest": {"ok": True, "blockers": [], "warnings": []},
        "production_route_resolution": {"ok": True, "blockers": [], "warnings": [], "shadowed_exact_routes": []},
        "repository_provider_hardening": {"ok": True, "blockers": [], "warnings": []},
        "admin_read_model_boundary": {"ok": True, "blockers": [], "warnings": []},
        "admin_real_data_binding": {"ok": True, "blockers": [], "warnings": []},
        "production_runtime_gaps": {"ok": True, "blockers": [], "warnings": []},
        "timer_route_readiness": {
            "ok": False,
            "blockers": ["dry_run_db_sentinel_not_passed"],
            "warnings": [],
            "safe_to_enable_timers": False,
        },
    }


def test_mainline_guardrail_report_keeps_safety_defaults_false(monkeypatch):
    monkeypatch.delenv("AICRM_MAINLINE_SERVER_CANARY_EVIDENCE", raising=False)

    result = checker.build_report(_ok_results())

    assert result["ok"] is True
    assert result["safe_to_enable_timers"] is False
    assert result["safe_to_remove_legacy_fallback"] is False
    assert result["safe_to_enable_real_external_calls"] is False
    assert result["production_canary_evidence_present"] is False
    assert "timer_route_readiness:dry_run_db_sentinel_not_passed" in result["warnings"]


def test_architecture_skill_failure_is_blocker():
    results = _ok_results()
    results["architecture_skill_compliance"] = {"ok": False, "blockers": ["openclaw_live_reference"], "warnings": []}

    result = checker.build_report(results)

    assert result["ok"] is False
    assert "architecture_skill_compliance:openclaw_live_reference" in result["blockers"]
    assert "architecture_skill_compliance:required_checker_not_ok" in result["blockers"]


def test_repository_provider_failure_is_blocker():
    results = _ok_results()
    results["repository_provider_hardening"] = {"ok": False, "blockers": ["allow_fixture_repo_in_prod_enabled"], "warnings": []}

    result = checker.build_report(results)

    assert result["ok"] is False
    assert "repository_provider_hardening:allow_fixture_repo_in_prod_enabled" in result["blockers"]
    assert "repository_provider_hardening:required_checker_not_ok" in result["blockers"]


def test_route_resolution_missing_or_shadowed_routes_are_blockers():
    results = _ok_results()
    results["production_route_resolution"] = {
        "ok": True,
        "blockers": [],
        "warnings": [],
        "shadowed_exact_routes": [{"method": "GET", "path": "/api/customers"}],
    }

    result = checker.build_report(results)

    assert result["ok"] is False
    assert "production_route_resolution:shadowed_exact_routes_present" in result["blockers"]


def test_timer_success_still_requires_server_canary_evidence(monkeypatch):
    monkeypatch.delenv("AICRM_MAINLINE_SERVER_CANARY_EVIDENCE", raising=False)
    results = _ok_results()
    results["timer_route_readiness"] = {"ok": True, "blockers": [], "warnings": [], "safe_to_enable_timers": True}

    result = checker.build_report(results)

    assert result["ok"] is True
    assert result["safe_to_enable_timers"] is False
    assert "timer_route_readiness:local_timer_success_is_not_production_canary_evidence" in result["warnings"]


def test_current_repo_guardrail_checker_runs():
    result = checker.build_report()

    assert set(result) >= {
        "ok",
        "blockers",
        "warnings",
        "checker_results",
        "safe_to_enable_timers",
        "safe_to_remove_legacy_fallback",
        "safe_to_enable_real_external_calls",
        "production_canary_evidence_present",
    }
    assert "architecture_skill_compliance" in result["checker_results"]
    assert "production_route_resolution" in result["checker_results"]
