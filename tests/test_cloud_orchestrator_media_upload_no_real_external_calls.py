from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOUD_ROOT = ROOT / "aicrm_next/cloud_orchestrator"


def _source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CLOUD_ROOT.rglob("*.py"))


def test_cloud_orchestrator_media_upload_uses_approved_wecom_gateway_boundary():
    source = _source()
    forbidden_direct_access = [
        "WeComClient" + ".from_app",
        "upload" + "_cloud_orchestrator_image",
        "access" + "_token",
    ]

    assert "legacy_wecom_client_from_app" in source
    assert "_upload" + "_private_message_image" in source
    for marker in forbidden_direct_access:
        assert marker not in source


def test_cloud_orchestrator_media_upload_does_not_use_direct_http_clients():
    source = _source()

    assert "request" + "s." not in source
    assert "http" + "x" not in source


def test_cloud_orchestrator_media_upload_marks_real_call_only_in_upload_path():
    source = _source()

    assert "real_external_call_executed" in source
    assert "wecom_media_upload_executed" in source
    assert "real_external_call_executed=True" not in source
    assert "wecom_media_upload_executed=True" not in source
