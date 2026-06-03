from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/architecture/cloud_orchestrator_media_upload_route_inventory.md"


def test_cloud_orchestrator_media_upload_inventory_exists_and_has_matrix():
    source = INVENTORY.read_text(encoding="utf-8")

    assert "Frontend ↔ API ↔ Backend Contract Matrix" in source
    assert "| 页面入口 | 前端模板/JS | 动作 | API | Method | Payload | Handler | Adapter/Command | SideEffectPlan | Smoke |" in source


def test_cloud_orchestrator_media_upload_inventory_covers_frontend_callers():
    source = INVENTORY.read_text(encoding="utf-8")

    for marker in [
        "/admin/cloud-orchestrator/campaigns",
        "/admin/cloud-orchestrator/plans",
        "/admin/cloud-orchestrator/plans/{plan_id}",
        "cloud_campaigns_workspace.html",
        "cloud_plan_review.html",
        "/api/admin/cloud-orchestrator/media/upload",
        "API-only/deprecated",
        "plan/step image upload",
    ]:
        assert marker in source


def test_cloud_orchestrator_media_upload_inventory_documents_no_real_side_effects():
    source = INVENTORY.read_text(encoding="utf-8")

    assert "real_external_call_executed=false" in source
    assert "wecom_media_upload_executed=false" in source
    assert "does not execute real WeCom media upload" in source
    assert "campaign execute" in source
    assert "Sidebar material real send" in source
