from __future__ import annotations

from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/architecture/route_ownership_manifest.yml"
TEMPLATE = ROOT / "aicrm_next/admin_shell/templates/admin_shell/p1_group_ops_workspace.html"
ROUTES = ROOT / "aicrm_next/admin_shell/routes.py"
NAVIGATION = ROOT / "aicrm_next/admin_shell/navigation.py"
WORKSPACE_TS_DIR = ROOT / "frontend/admin/p1_group_ops_workspace"
READ_ONLY_CLOSEOUT = ROOT / "docs/reports/p1_group_ops_workspace_read_only_closeout_20260624.md"
DRAFT_PERSISTENCE_RFC = ROOT / "docs/rfcs/p1_group_ops_workspace_draft_persistence_rfc_20260624.md"


@pytest.fixture()
def frontend_client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_p1_group_ops_workspace_route_smoke(frontend_client):
    response = frontend_client.get("/admin/p1/group-ops-workspace")
    html = response.text

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "P1 Native Group Ops Workspace" in html
    assert "TS-native draft-only / preview-only" in html
    assert 'id="p1GroupOpsWorkspaceApp"' in html
    assert 'id="p1GroupOpsWorkspaceApiConfig"' in html
    assert "workspace_layout.js" in html
    assert "不会发送、不审批、不写生产" in html
    assert "返回群运营计划" in html
    assert "查看 P1 诊断状态" in html
    assert "PASS_90_PLUS" not in html


def test_p1_group_ops_workspace_route_manifest_entry():
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entries = [entry for entry in manifest["routes"] if entry["path"] == "/admin/p1/group-ops-workspace"]

    assert len(entries) == 1
    entry = entries[0]
    assert entry["methods"] == ["GET"]
    assert entry["route_name"] == "api.admin_p1_group_ops_workspace"
    assert entry["capability_owner"] == "automation_engine"
    assert entry["runtime_owner"] == "ai_crm_next"
    assert entry["layer"] == "admin_page"
    assert entry["external_effects"] == "none"
    assert entry["requires_auth"] is True


def test_p1_group_ops_workspace_reuses_shared_modules():
    sources = "\n".join(path.read_text(encoding="utf-8") for path in WORKSPACE_TS_DIR.glob("*.ts"))

    for expected in [
        "../shared/status_model.js",
        "../shared/status_badge.js",
        "../shared/status_card.js",
        "../shared/guardrail_notice.js",
        "../shared/interaction_contract.js",
        "../shared/draft_state.js",
        "../shared/drop_validation.js",
        "../shared/interaction_shell.js",
    ]:
        assert expected in sources
    assert "createDraftState" in sources
    assert "applyReadonlyReorderPreview" in sources
    assert "validateDropIntent" in sources
    assert "explainBlockedDrop" in sources
    assert "getExecutionModeForStatus" in sources
    assert "serializeDraftPreviewForDisplay" in sources
    assert "canRenderGlobalPass" in sources
    assert "loadGroupOpsWorkspaceData" in sources
    assert "AdminApi" in sources
    assert "createWorkspaceSelectionState" in sources
    assert "selectWorkspaceEntity" in sources
    assert "renderWorkspaceDetailPanel" in sources
    assert "createWorkspaceViewState" in sources
    assert "updateWorkspaceViewState" in sources
    assert "filterWorkspaceView" in sources
    assert "buildWorkspaceCanvasLanes" in sources
    assert "sortCanvasCards" in sources
    assert "renderGroupedWorkspaceCanvas" in sources
    assert "toggleWorkspaceCanvasLane" in sources
    assert "densityClassName" in sources
    assert "moveWorkspaceCanvasSelection" in sources
    assert "keyboardHintText" in sources
    assert "toggleMultiSelectedEntity" in sources
    assert "clearMultiSelection" in sources
    assert "selectVisibleItems" in sources
    assert "buildWorkspacePreviewBundle" in sources
    assert "buildCopySafeBundleText" in sources
    assert "buildCopySafeBundleJson" in sources
    assert "assertCopySafeBundleOutput" in sources
    assert "copyBundleSummaryToClipboard" in sources
    assert "workspace_draft_api" in sources
    assert "buildWorkspaceDraftPayload" in sources
    assert "assertWorkspaceDraftPayloadSafe" in sources
    assert "createDraft" in sources
    assert "updateDraft" in sources
    assert "archiveDraft" in sources
    assert "isDraftConflictError" in sources


def test_p1_group_ops_workspace_copy_preserves_guardrails():
    template = TEMPLATE.read_text(encoding="utf-8")
    ts_sources = "\n".join(path.read_text(encoding="utf-8") for path in WORKSPACE_TS_DIR.glob("*.ts"))
    source = template + "\n" + ts_sources

    for expected in [
        "P1 Native workspace preview",
        "draft-only / preview-only",
        "不会发送、不审批、不写生产",
        "Group Ops 发送 evidence 已存在，但 governance evidence incomplete",
        "真正执行必须走 approval / allowlist / Push Center / external effect gates",
        "sent evidence 不等于 governance complete",
        "P1_READY_WITH_EXCEPTIONS 不等于 PASS_90_PLUS",
        "selectedPlanId",
        "selectedGroupId",
        "selectedNodeId",
        "selectedExecutionId",
        "selectedPushCenterJobId",
        "selectedEntityType",
        "Selected preview result",
        "Read-only drilldown only",
        "keyword",
        "planStatusFilter",
        "entityTypeFilter",
        "executionStatusFilter",
        "pushCenterStatusFilter",
        "panelMode",
        "laneCollapsedState",
        "canvasSortMode",
        "canvasGroupMode",
        "visibleLaneIds",
        "density",
        "focusedCanvasLaneId",
        "focusedCanvasCardId",
        "selectedEntityIds",
        "activeSelectionMode",
        "lastSelectedEntity",
        "previewBundleId",
        "bulkGuardrailSummary",
        "copyPreviewVisible",
        "copyPreviewFormat",
        "copyStatus",
        "copyStatusMessage",
        "Search / filters",
        "Read-only grouped canvas",
        "Safe preview only",
        "Safety summary",
        "Keyboard preview",
        "aria-selected",
        "data-keyboard-navigation",
        "data-safe-preview-affordance",
        "data-safe-preview-footer",
        "data-density",
        "compact",
        "comfortable",
        "Plans",
        "Audiences / Groups",
        "Tasks / Nodes",
        "Executions",
        "Push Center",
        "Evidence / Guardrails",
        "data-canvas-local-state",
        "data-canvas-sort-mode",
        "data-canvas-group-mode",
        "data-workspace-lane-toggle",
        "data-visible-count",
        "data-blocked-count",
        "data-action-required-count",
        "Select for preview bundle",
        "Read-only preview bundle",
        "复制安全摘要",
        "复制脱敏 JSON",
        "查看复制内容预览",
        "只读复制，不会发送",
        "data-copy-safe-export",
        "data-workspace-copy-bundle",
        "data-workspace-toggle-copy-preview",
        "Draft persistence",
        "Save draft",
        "Save as new draft",
        "Archive draft",
        "data-draft-persistence",
        "frontend_save_only",
        "data-workspace-save-draft",
        "data-workspace-save-as-new-draft",
        "data-workspace-archive-draft",
        "draftSaveStatus",
        "currentDraftId",
        "currentDraftVersion",
        "currentDraftIdempotencyKey",
        "buildWorkspaceDraftPayload",
        "request-review、approval bridge、Push Center bridge 均未接入",
        "草稿不等于 sent/completed",
        "data-workspace-multi-toggle",
        "data-workspace-select-visible",
        "data-workspace-clear-selection",
        "data-workspace-select-lane",
        "aria-checked",
        "aria-live=\"polite\"",
        "not currently visible",
        "any blocked item -> bundle cannot execute",
        "Empty search result",
        "Empty lane",
        "real_data_unavailable",
        "requires_approval",
        "requires_allowlist",
        "requires_gray_window",
        "no_direct_send",
        "no_external_call",
        "no_production_write",
    ]:
        assert expected in source

    for forbidden in [
        "governance_complete",
        "raw_external_userid",
        "Authorization header",
        "手机号",
        "openid",
        "unionid",
    ]:
        assert forbidden not in source


def test_p1_group_ops_workspace_does_not_replace_legacy_group_ops_page(frontend_client):
    legacy_response = frontend_client.get("/admin/automation-conversion/group-ops/ui")
    legacy_html = legacy_response.text

    assert legacy_response.status_code == 200
    assert 'id="group-ops-app"' in legacy_html
    assert 'id="groupOpsP1StatusApp"' in legacy_html
    assert "p1_group_ops_workspace" not in legacy_html
    assert "workspace_layout.js" not in legacy_html

    navigation = NAVIGATION.read_text(encoding="utf-8")
    routes = ROUTES.read_text(encoding="utf-8")
    assert '"/admin/p1/group-ops-workspace"' in navigation
    assert "admin_p1_group_ops_workspace" in routes
    assert '"endpoint": "api.admin_p1_group_ops_workspace"' not in navigation


def test_p1_group_ops_workspace_existing_readonly_api_contract(frontend_client):
    plans = frontend_client.get("/api/admin/automation-conversion/group-ops/plans?limit=2")
    assert plans.status_code == 200
    plans_payload = plans.json()
    assert plans_payload["ok"] is True
    assert plans_payload["route_owner"] == "ai_crm_next"
    assert plans_payload["side_effect_safety"]["real_external_call_executed"] is False
    assert plans_payload["side_effect_safety"]["db_write_executed"] is False
    assert isinstance(plans_payload["items"], list)

    if plans_payload["items"]:
        plan_id = int(plans_payload["items"][0]["id"])
        for path in [
            f"/api/admin/automation-conversion/group-ops/plans/{plan_id}",
            f"/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups",
            f"/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes",
            f"/api/automation/group-ops/plans/{plan_id}/executions?limit=2",
        ]:
            response = frontend_client.get(path)
            assert response.status_code == 200
            payload = response.json()
            assert payload["ok"] is True
            assert payload["route_owner"] == "ai_crm_next"
            assert payload["side_effect_safety"]["real_external_call_executed"] is False
            assert payload["side_effect_safety"]["db_write_executed"] is False

    push_center = frontend_client.get("/api/admin/push-center/jobs?section=group_ops&limit=2")
    assert push_center.status_code == 200
    push_payload = push_center.json()
    assert push_payload["ok"] is True
    assert push_payload["route_owner"] == "ai_crm_next"
    assert push_payload["real_external_call_executed"] is False


def test_p1_group_ops_workspace_read_only_closeout_report_contract():
    report = READ_ONLY_CLOSEOUT.read_text(encoding="utf-8")

    for expected in [
        "READ_ONLY_WORKSPACE_READY",
        "DRAFT_PERSISTENCE_NOT_READY",
        "EXECUTION_NOT_READY",
        "PASS_90_PLUS_NOT_CLAIMED",
        "/admin/p1/group-ops-workspace",
        "/admin/automation-conversion/group-ops/ui",
        "#1369",
        "#1370",
        "#1372",
        "#1374",
        "#1375",
        "#1376",
        "#1377",
        "#1379",
        "preview-only=true",
        "production_write=false",
        "real_external_call=false",
        "can_claim_pass_90_plus=false",
        "preview bundle cannot execute",
        "copied summary cannot execute",
        "P1_READY_WITH_EXCEPTIONS",
        "PASS_90_PLUS",
        "backend draft model",
        "DB migration plan",
        "idempotency key design",
        "audit log design",
        "approval gate design",
        "receiver allowlist gate design",
        "gray-window gate design",
        "Push Center bridge design",
        "external-effect boundary preservation",
        "P1 Group Ops Workspace Draft Persistence Design RFC",
        "npm run build:frontend",
        "npm run typecheck",
        "npm run test:frontend",
        "scripts/diagnose_business_closure_acceptance.py --scenario all",
        "bash scripts/ci/run_architecture_gates.sh",
        "Frontend Skill Checklist",
    ]:
        assert expected in report


def test_p1_group_ops_workspace_draft_persistence_rfc_contract():
    rfc = DRAFT_PERSISTENCE_RFC.read_text(encoding="utf-8")

    for expected in [
        "RFC_READY_FOR_REVIEW",
        "IMPLEMENTATION_NOT_STARTED",
        "EXECUTION_NOT_IN_SCOPE",
        "PASS_90_PLUS_NOT_CLAIMED",
        "/admin/p1/group-ops-workspace",
        "docs/reports/p1_group_ops_workspace_read_only_closeout_20260624.md",
        "group_ops_workspace_drafts",
        "group_ops_workspace_draft_items",
        "group_ops_workspace_draft_audit_logs",
        "draft_status",
        "idempotency_key",
        "snapshot_hash",
        "sanitized_payload_json",
        "guardrail_summary_json",
        "approval_requirements_json",
        "GET `/api/admin/p1/group-ops-workspace/drafts`",
        "GET `/api/admin/p1/group-ops-workspace/drafts/{draft_id}`",
        "POST `/api/admin/p1/group-ops-workspace/drafts`",
        "PATCH `/api/admin/p1/group-ops-workspace/drafts/{draft_id}`",
        "POST `/api/admin/p1/group-ops-workspace/drafts/{draft_id}/archive`",
        "POST `/api/admin/p1/group-ops-workspace/drafts/{draft_id}/request-review`",
        "No external call guarantee: true",
        "No Push Center execution guarantee: true",
        "unauthenticated requests fail closed",
        "create",
        "update",
        "archive",
        "request-review",
        "draft model migration",
        "read/write API",
        "frontend save draft integration",
        "approval/review request integration",
        "Push Center bridge",
        "not execution",
        "PASS_90_PLUS",
        "Frontend Skill Checklist",
    ]:
        assert expected in rfc

    for forbidden in [
        "This RFC implements",
        "migration is created in this PR",
        "Draft APIs must create Push Center jobs",
        "Draft APIs must create `external_effect_job`",
    ]:
        assert forbidden not in rfc
