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
INTERACTION_SHELL = ROOT / "frontend" / "admin" / "shared" / "interaction_shell.ts"
DRAFT_STATE = ROOT / "frontend" / "admin" / "shared" / "draft_state.ts"
DROP_VALIDATION = ROOT / "frontend" / "admin" / "shared" / "drop_validation.ts"
OVERVIEW_SCRIPT = ROOT / "frontend" / "admin" / "business_closure" / "business_closure_overview.ts"
PUSH_CENTER_STATUS = ROOT / "frontend" / "admin" / "push_center" / "push_center_status.ts"
PUSH_CENTER_OVERVIEW = ROOT / "frontend" / "admin" / "push_center" / "push_center_overview.ts"
OPS_PLAN_STATUS = ROOT / "frontend" / "admin" / "ops_plan" / "ops_plan_status.ts"
OPS_PLAN_OVERVIEW = ROOT / "frontend" / "admin" / "ops_plan" / "ops_plan_overview.ts"


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


def _push_center_payload_from_html(html: str) -> dict:
    match = re.search(
        r'<script id="pushCenterP1StatusPayload" type="application/json">\s*(.*?)\s*</script>',
        html,
        re.S,
    )
    assert match, html
    return json.loads(match.group(1))


def _ops_plan_payload_from_html(html: str) -> dict:
    match = re.search(
        r'<script id="opsPlanP1StatusPayload" type="application/json">\s*(.*?)\s*</script>',
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
    shell_source = INTERACTION_SHELL.read_text(encoding="utf-8")

    assert "不是 PASS_90_PLUS" in script
    assert "P1_READY_WITH_EXCEPTIONS" in script
    assert "blocked_noop" in shell_source
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


def test_draft_preview_interaction_shell_is_memory_only_and_non_executing() -> None:
    shell_source = INTERACTION_SHELL.read_text(encoding="utf-8")
    draft_source = DRAFT_STATE.read_text(encoding="utf-8")
    validation_source = DROP_VALIDATION.read_text(encoding="utf-8")
    overview_source = OVERVIEW_SCRIPT.read_text(encoding="utf-8")

    assert "createDraftState" in draft_source
    assert 'persistence: "memory_only"' in draft_source
    assert "productionWriteExecuted: false" in draft_source
    assert "realExternalCallExecuted: false" in draft_source
    assert "canClaimPass90Plus: false" in draft_source
    assert "applyReadonlyReorderPreview" in shell_source
    assert "serializeDraftPreviewForDisplay" in shell_source
    assert 'data-persistence="${escapeHtml(display.persistence)}"' in shell_source
    assert 'data-real-external-call-executed="false"' in shell_source
    assert 'data-production-write-executed="false"' in shell_source
    assert 'data-can-claim-pass90="false"' in shell_source
    assert "getExecutionModeForStatus" in validation_source
    assert 'if (status === "ready") return "draft_only";' in validation_source
    assert "external_config_blocked" in validation_source
    assert "requires_approval" in validation_source
    assert "preview_only" in validation_source
    assert "renderInteractionShell(payload)" in overview_source


def test_draft_preview_shell_rendered_page_preserves_p1_exceptions(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/business-closure")
    html = response.text

    assert response.status_code == 200
    assert "Draft-only / preview-only interaction shell" in html
    assert 'data-persistence="memory_only"' in html
    assert 'data-real-external-call-executed="false"' in html
    assert 'data-production-write-executed="false"' in html
    assert 'data-can-claim-pass90="false"' in html
    assert "external-config-blocked" in html
    assert "governance-missing" in html
    assert "downstream-pending" in html
    assert "requires_gray_window" in html
    assert "no_direct_send" in html
    assert "重排只改变本地 preview 顺序" in html
    assert "不保存、不执行、不生成 PASS_90_PLUS" in html


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


def test_push_center_page_renders_p1_readonly_status_slice(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/push-center")
    html = response.text
    payload = _push_center_payload_from_html(html)

    assert response.status_code == 200
    assert "pushCenterP1StatusApp" in html
    assert "pushCenterP1StatusPayload" in html
    assert "push_center_overview.js" in html
    assert "P1 Push Center 状态" in html
    cards = payload["cards"]
    assert any(item["rawStatus"] == "governance_missing" for item in cards)
    assert any(item["rawStatus"] == "downstream_pending" for item in cards)
    assert any(item["rawStatus"] == "external_config_blocked" for item in cards)
    assert any(item["rawStatus"] == "order_linked" for item in cards)
    assert "PASS_90_PLUS" not in json.dumps(payload, ensure_ascii=False)


def test_push_center_frontend_slice_reuses_shared_status_contract() -> None:
    status_source = PUSH_CENTER_STATUS.read_text(encoding="utf-8")
    overview_source = PUSH_CENTER_OVERVIEW.read_text(encoding="utf-8")

    assert 'from "../shared/status_model.js"' in status_source
    assert 'from "../shared/interaction_contract.js"' in status_source
    assert 'from "../shared/status_card.js"' in overview_source
    assert '"pending"' in status_source
    assert '"sent"' in status_source
    assert '"retryable"' in status_source
    assert '"operator-action-required"' in status_source
    assert '"failed-terminal"' in status_source
    assert '"downstream-pending"' in status_source
    assert '"evidence-incomplete"' in status_source
    assert 'validateDropIntent(scenario, "blocked_noop")' in status_source
    assert "Readonly preview only; no direct send." in overview_source


def test_push_center_readonly_status_copy_does_not_claim_false_completion() -> None:
    status_source = PUSH_CENTER_STATUS.read_text(encoding="utf-8")
    overview_source = PUSH_CENTER_OVERVIEW.read_text(encoding="utf-8")

    assert "不能显示为已完成" in status_source
    assert "不得显示为 sent 或 completed" in status_source
    assert "不能假装授权完成" in status_source
    assert "不新增写操作、不绕过 Push Center、不触发真实外呼" in overview_source
    for forbidden in [
        "WeCom 已授权完成",
        "治理证据已完成",
        "downstream completed",
        "PASS_90_PLUS 已完成",
    ]:
        assert forbidden not in status_source
        assert forbidden not in overview_source


def test_ops_plan_page_renders_p1_readonly_downstream_status_slice(monkeypatch) -> None:
    response = _client(monkeypatch).get("/admin/cloud-orchestrator/plans")
    html = response.text
    payload = _ops_plan_payload_from_html(html)

    assert response.status_code == 200
    assert "opsPlanP1StatusApp" in html
    assert "opsPlanP1StatusPayload" in html
    assert "ops_plan_overview.js" in html
    assert "P1 Ops Plan" in html
    cards = payload["cards"]
    assert payload["evidenceSummary"]["planId"] == "p0-1283-plan-20260615152503"
    assert payload["evidenceSummary"]["planType"] == "cloud_plan"
    assert payload["evidenceSummary"]["plannerResult"] == "planner_created_broadcast_job"
    assert payload["evidenceSummary"]["broadcastJobId"] == "broadcast_job:3644"
    assert payload["evidenceSummary"]["pushCenterStatus"] == "pending"
    assert payload["evidenceSummary"]["externalEffectJob"] == "not_created"
    assert payload["evidenceSummary"]["realExternalCallExecuted"] is False
    assert any(item["rawStatus"] == "push_center_pending" for item in cards)
    assert any(item["rawStatus"] == "planner_created_broadcast_job" for item in cards)
    assert any(item["rawStatus"] == "external_effect_not_created" for item in cards)
    assert "PASS_90_PLUS_CANDIDATE" not in json.dumps(payload, ensure_ascii=False)


def test_ops_plan_frontend_slice_reuses_shared_status_contract() -> None:
    status_source = OPS_PLAN_STATUS.read_text(encoding="utf-8")
    overview_source = OPS_PLAN_OVERVIEW.read_text(encoding="utf-8")

    assert 'from "../shared/status_model.js"' in status_source
    assert 'from "../shared/interaction_contract.js"' in status_source
    assert 'from "../shared/status_card.js"' in overview_source
    assert '"downstream-pending"' in status_source
    assert '"pending"' in status_source
    assert '"sent"' in status_source
    assert '"blocked"' in status_source
    assert '"retryable"' in status_source
    assert '"operator-action-required"' in status_source
    assert '"failed-terminal"' in status_source
    assert '"evidence-incomplete"' in status_source
    assert 'validateDropIntent(scenario, "blocked_noop")' in status_source
    assert "Readonly preview only; no direct send." in overview_source


def test_ops_plan_readonly_status_copy_does_not_claim_false_completion() -> None:
    status_source = OPS_PLAN_STATUS.read_text(encoding="utf-8")
    overview_source = OPS_PLAN_OVERVIEW.read_text(encoding="utf-8")

    assert "下游 external effect 尚未执行，不能显示为 completed" in status_source
    assert "Push Center pending 不能显示为 sent 或 completed" in status_source
    assert "broadcast_job created 不等于 external-effect sent" in status_source
    assert "不执行下游 external effect" in overview_source
    for forbidden in [
        "downstream completed",
        "broadcast_job sent",
        "全局 PASS_90_PLUS 已完成",
    ]:
        assert forbidden not in status_source
        assert forbidden not in overview_source
