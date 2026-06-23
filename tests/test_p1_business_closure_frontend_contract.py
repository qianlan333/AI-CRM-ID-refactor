from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


ROOT = Path(__file__).resolve().parents[1]
STATUS_MODEL = ROOT / "frontend" / "admin" / "business_closure" / "status_model.ts"
SHARED_STATUS_MODEL = ROOT / "frontend" / "admin" / "shared" / "status_model.ts"
INTERACTION_CONTRACT = ROOT / "frontend" / "admin" / "shared" / "interaction_contract.ts"
OVERVIEW_SCRIPT = ROOT / "frontend" / "admin" / "business_closure" / "business_closure_overview.ts"


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "p1-business-closure-frontend-test")
    return TestClient(create_app())


def _payload_from_html(html: str) -> dict:
    match = re.search(
        r'<script id="businessClosurePayload" type="application/json">(.*?)</script>',
        html,
        re.S,
    )
    assert match, html
    return json.loads(match.group(1))


def test_business_closure_page_renders_p1_with_exceptions_without_pass90(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/business-closure")
    html = response.text
    payload = _payload_from_html(html)

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "Business Closure / P1 Readiness" in html
    assert "P1_READY_WITH_EXCEPTIONS" in html
    assert "PASS_90_PLUS" in html
    assert payload["finalVerdict"] == "P1_READY_WITH_EXCEPTIONS"
    assert payload["canClaimPass90Plus"] is False
    assert any(item["status"] == "external-config-blocked" for item in payload["scenarios"])
    assert any(item["status"] == "governance-missing" for item in payload["scenarios"])
    assert any(item["status"] == "downstream-pending" for item in payload["scenarios"])
    assert "business_closure_overview.js" in html


def test_business_closure_nav_entry_is_available(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin")

    assert response.status_code == 200
    assert 'href="/admin/business-closure"' in response.text
    assert "业务闭环状态" in response.text


def test_status_model_keeps_blocked_and_pending_out_of_success() -> None:
    source = SHARED_STATUS_MODEL.read_text(encoding="utf-8")
    reexport_source = STATUS_MODEL.read_text(encoding="utf-8")

    assert '"external-config-blocked": { label: "外部配置阻塞", tone: "danger", isSuccessComplete: false }' in source
    assert '"governance-missing": { label: "治理证据缺失", tone: "warning", isSuccessComplete: false }' in source
    assert '"downstream-pending": { label: "下游待执行", tone: "info", isSuccessComplete: false }' in source
    assert 'payload.finalVerdict === "PASS_90_PLUS"' in source
    assert "payload.canClaimPass90Plus === true" in source
    assert 'export * from "../shared/status_model.js";' in reexport_source


def test_business_closure_frontend_copy_does_not_claim_false_completion() -> None:
    script = OVERVIEW_SCRIPT.read_text(encoding="utf-8")

    assert "不是 PASS_90_PLUS" in script
    assert "P1_READY_WITH_EXCEPTIONS" in script
    assert "blocked_noop" in script
    assert "renderStatusCard" in script
    for forbidden in ["WeCom 已授权完成", "全局 PASS_90_PLUS 已完成", "downstream completed"]:
        assert forbidden not in script


def test_interaction_contract_blocks_unsafe_drag_outcomes() -> None:
    source = INTERACTION_CONTRACT.read_text(encoding="utf-8")

    assert 'export type DragEntity =' in source
    assert 'export type DropIntent =' in source
    assert 'export type ExecutionMode =' in source
    assert 'export type InteractionGuardrail =' in source
    assert 'if (status === "external-config-blocked") return "external_config_blocked";' in source
    assert 'if (status === "governance-missing") return "requires_approval";' in source
    assert 'return "preview_only";' in source
    assert 'intent === "blocked_noop"' in source
    assert "statusAfterDrop: scenario.status" in source
    for guardrail in ["requires_push_center", "requires_approval", "requires_allowlist", "requires_gray_window", "requires_external_config", "no_external_call", "no_production_write", "no_direct_send"]:
        assert guardrail in source


def test_rendered_page_does_not_expose_sensitive_fixture_strings(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/business-closure")
    html = response.text

    for forbidden in [
        "raw_external_userid",
        "Authorization: Bearer",
        "access_token",
        "corpsecret",
        "13800138000",
        "openid",
        "unionid",
    ]:
        assert forbidden not in html
