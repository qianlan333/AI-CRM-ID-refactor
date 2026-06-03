from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOUD_ROOT = ROOT / "aicrm_next/cloud_orchestrator"


def _source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CLOUD_ROOT.rglob("*.py"))


def test_cloud_orchestrator_media_upload_does_not_use_legacy_wecom_uploader():
    source = _source()
    forbidden = [
        "WeComClient" + ".from_app",
        "_upload" + "_private_message_image",
        "upload" + "_cloud_orchestrator_image",
        "access" + "_token",
    ]

    for marker in forbidden:
        assert marker not in source


def test_cloud_orchestrator_media_upload_does_not_use_direct_http_clients():
    source = _source()

    assert "request" + "s." not in source
    assert "http" + "x" not in source


def test_cloud_orchestrator_media_upload_never_marks_real_calls_true_by_default():
    source = _source()

    assert "real_external_call_executed" in source
    assert "wecom_media_upload_executed" in source
    assert "real_external_call_executed=True" not in source
    assert "wecom_media_upload_executed=True" not in source
