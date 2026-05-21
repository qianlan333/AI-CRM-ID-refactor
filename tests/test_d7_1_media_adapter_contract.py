from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = REPO_ROOT / "tools" / "check_d7_1_media_adapter_contract.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_d7_1_media_adapter_contract", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _d7_1_docs() -> str:
    paths = [
        "docs/d7_1_media_storage_wecom_media_adapter_contract.md",
        "docs/d7_1_media_adapter_implementation_report.md",
        "docs/d7_adapter_contract_catalog.md",
        "docs/d7_capability_readiness_matrix.md",
        "docs/d7_write_external_blocker_matrix.md",
    ]
    return "\n".join((REPO_ROOT / path).read_text(encoding="utf-8") for path in paths)


def test_cloud_storage_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter

    for method in ["put_object", "put_base64_object", "put_remote_reference", "get_public_reference", "delete_object"]:
        assert hasattr(CloudStorageAdapter, method)


def test_wecom_media_adapter_contract_exists() -> None:
    from aicrm_next.integration_gateway.media_adapters import WeComMediaAdapter

    for method in ["upload_image", "upload_attachment", "resolve_media_id", "delete_or_expire_reference"]:
        assert hasattr(WeComMediaAdapter, method)


def test_fake_cloud_upload_returns_deterministic_fake_storage_key() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter

    reset_idempotency_store()
    adapter = CloudStorageAdapter("fake")
    first = adapter.put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png")
    second = adapter.put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png")
    assert first["ok"] is True
    assert first["storage_key"] == second["storage_key"]
    assert first["side_effect_executed"] is False


def test_fake_wecom_media_upload_returns_deterministic_fake_media_id() -> None:
    from aicrm_next.integration_gateway.idempotency import reset_idempotency_store
    from aicrm_next.integration_gateway.media_adapters import WeComMediaAdapter

    reset_idempotency_store()
    adapter = WeComMediaAdapter("fake")
    first = adapter.upload_image(data_base64="ZmFrZQ==", file_name="x.png")
    second = adapter.upload_image(data_base64="ZmFrZQ==", file_name="x.png")
    assert first["ok"] is True
    assert first["media_id"] == second["media_id"]
    assert first["side_effect_executed"] is False


def test_repeated_call_with_same_idempotency_key_returns_same_result() -> None:
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter

    adapter = CloudStorageAdapter("fake")
    first = adapter.put_object(content=b"fake", file_name="same.png", content_type="image/png", idempotency_key="idem-1")
    second = adapter.put_object(content=b"different", file_name="changed.png", content_type="image/png", idempotency_key="idem-1")
    assert first["storage_key"] == second["storage_key"]


def test_disabled_mode_returns_stable_disabled_error() -> None:
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter

    result = CloudStorageAdapter("disabled").put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png")
    assert result["ok"] is False
    assert result["error_code"] == "adapter_disabled"
    assert result["side_effect_executed"] is False


def test_production_mode_without_explicit_env_flag_fails_closed(monkeypatch) -> None:
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter, WeComMediaAdapter

    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_CLOUD_STORAGE", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_REAL_WECOM_MEDIA", raising=False)
    cloud = CloudStorageAdapter("production").put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png")
    wecom = WeComMediaAdapter("production").upload_image(data_base64="ZmFrZQ==", file_name="x.png")
    assert cloud["ok"] is False
    assert wecom["ok"] is False
    assert cloud["error_code"] == "production_guard_failed"
    assert wecom["error_code"] == "production_guard_failed"
    assert cloud["side_effect_executed"] is False
    assert wecom["side_effect_executed"] is False


def test_side_effect_executed_is_false_in_all_modes(monkeypatch) -> None:
    from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter

    monkeypatch.setenv("AICRM_NEXT_ENABLE_REAL_CLOUD_STORAGE", "true")
    results = [
        CloudStorageAdapter("fake").put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png"),
        CloudStorageAdapter("disabled").put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png"),
        CloudStorageAdapter("staging").put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png"),
        CloudStorageAdapter("production").put_base64_object(data_base64="ZmFrZQ==", file_name="x.png", content_type="image/png"),
    ]
    assert all(result["side_effect_executed"] is False for result in results)
    assert results[-1]["error_code"] == "production_not_implemented"


def test_audit_record_is_created() -> None:
    from aicrm_next.integration_gateway.audit import list_audit_events, reset_audit_events
    from aicrm_next.integration_gateway.media_adapters import WeComMediaAdapter

    reset_audit_events()
    result = WeComMediaAdapter("fake").upload_attachment(data_base64="ZmFrZQ==", file_name="a.pdf", content_type="application/pdf")
    events = list_audit_events()
    assert result["audit_id"]
    assert events
    assert events[-1]["adapter"] == "WeComMediaAdapter"
    assert events[-1]["side_effect_executed"] is False


def test_media_library_from_base64_uses_adapter_boundary() -> None:
    from aicrm_next.media_library.application import ImportImageFromBase64Command
    from aicrm_next.media_library.dto import ImageFromBase64Request

    result = ImportImageFromBase64Command()(ImageFromBase64Request(data_base64="ZmFrZQ==", name="base64"))
    assert result["ok"] is True
    assert result["adapter_result"]["cloud_storage"]["adapter"] == "CloudStorageAdapter"
    assert result["adapter_result"]["wecom_media"]["adapter"] == "WeComMediaAdapter"
    assert result["adapter_result"]["side_effect_safety"]["real_cloud_upload_executed"] is False


def test_media_library_from_url_does_not_fetch_remote_url() -> None:
    from aicrm_next.media_library.application import ImportImageFromUrlCommand
    from aicrm_next.media_library.dto import ImageFromUrlRequest

    result = ImportImageFromUrlCommand()(ImageFromUrlRequest(url="https://example.invalid/no-fetch.png", name="url"))
    assert result["ok"] is True
    assert result["item"]["source_url"] == "https://example.invalid/no-fetch.png"
    assert result["adapter_result"]["side_effect_safety"]["remote_url_fetched"] is False


def test_media_readonly_smoke_and_parity_static_checks_remain_passable() -> None:
    checker = _load_checker()
    report = checker.build_report()
    assert report["media_smoke"]["ok"] is True
    assert report["media_parity"]["ok"] is True


def test_docs_do_not_mark_production_ready_or_delete_ready() -> None:
    text = _d7_1_docs()
    assert "production_ready" not in text
    assert "production_approved" not in text
    assert "delete_ready" not in text


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in source
        assert "openclaw_service" not in source
