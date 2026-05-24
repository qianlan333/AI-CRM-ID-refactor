from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import check_phase4c_profile_segment_template_native_contract as checker


ROOT = Path(__file__).resolve().parents[1]


def test_phase4c_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_phase4c_static_routes_are_registered_without_delete() -> None:
    routes = checker._find_route_decorators()
    for route in checker.EXPECTED_ROUTES:
        assert route in routes
    assert not [
        (method, path)
        for method, path in routes
        if method == "DELETE" and "profile-segment-templates" in path
    ]


def test_phase4c_docs_do_not_claim_cutover_or_delete_ready() -> None:
    text = checker.DOC.read_text(encoding="utf-8").lower()
    forbidden_claims = [
        "production approved",
        "canary approved",
        "production cutover authorized",
        "fallback removal authorized",
        "delete_ready true",
    ]
    assert not [claim for claim in forbidden_claims if claim in text]
    assert "pre-cutover" in text
    assert "production ownership is unchanged" in text


def test_phase4c_no_forbidden_runtime_files_changed() -> None:
    result = checker.check_no_forbidden_file_changes()
    assert result["ok"], result


def test_phase4c_static_contract_mentions_required_guardrails() -> None:
    result = checker.check_static_contract_code()
    assert result["ok"], result


@pytest.fixture()
def profile_segment_runtime(monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    from aicrm_next.automation_engine.application import (
        CreateProfileSegmentTemplateCommand,
        GetProfileSegmentTemplateCatalogQuery,
        GetProfileSegmentTemplateOptionsQuery,
        GetProfileSegmentTemplateQuery,
        ListProfileSegmentTemplatesQuery,
        UpdateProfileSegmentTemplateCommand,
    )
    from aicrm_next.automation_engine.dto import (
        ProfileSegmentTemplateCreateRequest,
        ProfileSegmentTemplateListRequest,
        ProfileSegmentTemplateUpdateRequest,
    )
    from aicrm_next.automation_engine.repo import InMemoryAutomationRepository
    from aicrm_next.shared.errors import ContractError, NotFoundError

    repo = InMemoryAutomationRepository()
    return {
        "repo": repo,
        "Create": CreateProfileSegmentTemplateCommand,
        "List": ListProfileSegmentTemplatesQuery,
        "Catalog": GetProfileSegmentTemplateCatalogQuery,
        "Options": GetProfileSegmentTemplateOptionsQuery,
        "Detail": GetProfileSegmentTemplateQuery,
        "Update": UpdateProfileSegmentTemplateCommand,
        "CreateRequest": ProfileSegmentTemplateCreateRequest,
        "ListRequest": ProfileSegmentTemplateListRequest,
        "UpdateRequest": ProfileSegmentTemplateUpdateRequest,
        "ContractError": ContractError,
        "NotFoundError": NotFoundError,
    }


def test_phase4c_fixture_contract_list_catalog_options_detail(profile_segment_runtime) -> None:
    rt = profile_segment_runtime
    repo = rt["repo"]
    assert rt["Catalog"](repo)()["ok"] is True
    listed = rt["List"](repo)(rt["ListRequest"]())
    assert listed["count"] >= 1
    assert rt["Options"](repo)(rt["ListRequest"](enabled_only=False))["count"] >= 1
    detail = rt["Detail"](repo)(1)
    assert detail["template"]["id"] == 1
    assert all(value is False for key, value in detail["side_effect_safety"].items() if key.startswith("real_"))


def test_phase4c_create_idempotency_duplicate_and_update(profile_segment_runtime) -> None:
    rt = profile_segment_runtime
    repo = rt["repo"]
    created = rt["Create"](repo)(
        rt["CreateRequest"](
            name="Phase 4C pytest template",
            code="phase4c_pytest",
            idempotency_key="pytest-idempotency",
            operator="pytest",
        )
    )
    assert created["status_code"] == 201
    template_id = created["template"]["id"]
    replay = rt["Create"](repo)(
        rt["CreateRequest"](
            name="Phase 4C pytest template",
            code="phase4c_pytest",
            idempotency_key="pytest-idempotency",
            operator="pytest",
        )
    )
    assert replay["template"]["id"] == template_id
    assert replay["idempotent_replay"] is True
    with pytest.raises(rt["ContractError"]):
        rt["Create"](repo)(
            rt["CreateRequest"](
                name="Phase 4C pytest template",
                code="phase4c_pytest_duplicate",
                idempotency_key="pytest-other-key",
            )
        )
    updated = rt["Update"](repo)(template_id, rt["UpdateRequest"](description="updated", operator="pytest"))
    assert updated["template"]["description"] == "updated"
    assert updated["rollback"]["before"]["id"] == template_id
    assert updated["audit_event"]["action"] == "profile_segment_template_updated"


def test_phase4c_validation_and_production_guard(profile_segment_runtime, monkeypatch) -> None:
    rt = profile_segment_runtime
    repo = rt["repo"]
    with pytest.raises(rt["ContractError"]):
        rt["Create"](repo)(rt["CreateRequest"](name="", idempotency_key="missing-name"))
    with pytest.raises(rt["ContractError"]):
        rt["Create"](repo)(rt["CreateRequest"](name="Invalid", status="published", idempotency_key="bad-status"))
    with pytest.raises(rt["ContractError"]):
        rt["Create"](repo)(rt["CreateRequest"](name="Danger", rules={"run_due": True}, idempotency_key="danger"))
    with pytest.raises(rt["NotFoundError"]):
        rt["Update"](repo)(9999, rt["UpdateRequest"](description="missing"))

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://phase4c:phase4c@127.0.0.1:1/aicrm_phase4c_pytest")
    result = rt["Create"]()(
        rt["CreateRequest"](
            name="Production should degrade",
            code="prod_guard",
            idempotency_key="prod-guard",
            operator="pytest",
        )
    )
    assert result["status_code"] == 503
    assert result["source_status"] == "production_unavailable"
    assert result["ok"] is False


def test_phase4c_fastapi_route_owner_and_production_probe(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    app = create_app()
    routes = checker._registered_routes(app)
    for route in checker.EXPECTED_ROUTES:
        assert routes.get(route) == checker.EXPECTED_MODULE

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/admin/automation-conversion/profile-segment-templates",
        json={"name": "Route owner", "code": "route_owner", "idempotency_key": "route-owner", "operator": "pytest"},
    )
    assert response.status_code in {200, 201}
    assert response.headers.get("X-AICRM-Route-Owner") == "ai_crm_next"
    assert response.headers.get("X-AICRM-Compatibility-Facade") != "legacy_flask_facade"
    body = response.json()
    assert all(value is False for key, value in body["side_effect_safety"].items() if key.startswith("real_"))

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://phase4c:phase4c@127.0.0.1:1/aicrm_phase4c_pytest")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    prod_client = TestClient(create_app(), raise_server_exceptions=False)
    prod_response = prod_client.post(
        "/api/admin/automation-conversion/profile-segment-templates",
        json={"name": "Prod", "code": "prod", "idempotency_key": "prod", "operator": "pytest"},
    )
    if prod_response.status_code in {200, 201}:
        assert not checker._body_has_fixture_success(prod_response.json())
