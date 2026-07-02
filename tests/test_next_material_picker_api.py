from __future__ import annotations

import pytest


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_validate_returns_route_owner_and_normalized_package(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={
            "content_package": {
                "content_text": "  你好  ",
                "image_library_ids": [12, "12", 13],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            }
        },
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json() == {
        "ok": True,
        "content_package": {
            "content_text": "你好",
            "image_library_ids": [12, 13],
            "miniprogram_library_ids": [34],
            "attachment_library_ids": [56],
        },
    }


def test_validate_error_is_json_not_html(client) -> None:
    response = client.post(
        "/api/admin/send-content/validate",
        json={"content_package": {"image_library_ids": ["abc"]}},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is False
    assert "正整数" in body["error"]


def test_preview_is_local_only_and_does_not_create_tasks(client, monkeypatch) -> None:
    import requests

    def _fail_external_call(*args, **kwargs):
        raise AssertionError("preview must not perform external HTTP calls")

    monkeypatch.setattr(requests, "post", _fail_external_call)
    retired_before = client.get("/api/admin/automation-conversion/tasks")
    assert retired_before.status_code == 404

    response = client.post(
        "/api/admin/send-content/preview",
        json={
            "content_package": {
                "content_text": "  预览  ",
                "image_library_ids": [12],
                "miniprogram_library_ids": [34],
                "attachment_library_ids": [56],
            }
        },
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["preview"]["content_text"] == "预览"
    assert body["preview"]["material_summary"] == {
        "image_count": 1,
        "miniprogram_count": 1,
        "attachment_count": 1,
    }
    assert all("media_id" not in item for item in body["preview"]["materials"])
    retired_after = client.get("/api/admin/automation-conversion/tasks")
    assert retired_after.status_code == 404


def test_material_picker_image_shape_excludes_base64(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=image")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    item = response.json()["items"][0]
    assert {"type", "library_id", "title", "thumbnail_url", "enabled", "metadata"} <= set(item)
    assert item["type"] == "image"
    assert "data_base64" not in item
    assert "data_base64" not in item["metadata"]


def test_material_picker_miniprogram_shape(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=miniprogram")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "miniprogram"
    assert item["metadata"]["appid"]
    assert item["metadata"]["pagepath"]


def test_material_picker_attachment_shape(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=attachment")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["type"] == "attachment"
    assert {"file_name", "mime_type", "file_size"} <= set(item["metadata"])
    assert item["mime_type"] == "application/pdf"
    assert item["metadata"]["mime_type"] == "application/pdf"


def test_material_picker_unknown_type_returns_400_json(client) -> None:
    response = client.get("/api/admin/material-picker/items?type=unknown")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json()["ok"] is False


def test_material_assets_read_model_unifies_library_sources(client) -> None:
    response = client.get("/api/admin/material-assets?limit=10")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["read_model"] == "material_assets"
    assets = body["assets"]
    assert {item["asset_type"] for item in assets} == {"image", "miniprogram", "attachment"}
    assert {item["source_table"] for item in assets} == {"image_library", "miniprogram_library", "attachment_library"}
    assert all(item["material_asset_id"] == f"{item['asset_type']}:{item['source_id']}" for item in assets)
    assert all("data_base64" not in item for item in assets)


def test_material_assets_can_filter_to_one_source_type(client) -> None:
    response = client.get("/api/admin/material-assets?type=miniprogram")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "miniprogram"
    assert body["assets"]
    assert {item["asset_type"] for item in body["assets"]} == {"miniprogram"}


def test_material_assets_single_type_preserves_offset(client) -> None:
    response = client.get("/api/admin/material-assets?type=image&offset=1&limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "image"
    assert body["offset"] == 1
    assert body["limit"] == 1
    assert [item["material_asset_id"] for item in body["assets"]] == ["image:13"]
    assert body["total"] == 2


def test_material_assets_all_type_fetches_enough_rows_before_unified_slice(client) -> None:
    response = client.get("/api/admin/material-assets?type=all&offset=3&limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "all"
    assert body["offset"] == 3
    assert body["limit"] == 1
    assert [item["material_asset_id"] for item in body["assets"]] == ["attachment:56"]
    assert body["total"] == 4


def test_material_assets_all_type_deep_offset_stays_inside_large_source(client, monkeypatch) -> None:
    import aicrm_next.send_content.application as app_module

    repo = _LargeMaterialAssetsRepository()
    monkeypatch.setattr(app_module, "build_send_content_repository", lambda: repo)

    response = client.get("/api/admin/material-assets?type=all&offset=100&limit=1")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "all"
    assert body["offset"] == 100
    assert body["limit"] == 1
    assert [item["material_asset_id"] for item in body["assets"]] == ["image:101"]
    assert body["total"] == 103


class _LargeMaterialAssetsRepository:
    source_status = "test_large_material_assets"

    def __init__(self) -> None:
        self._data = {
            "image": [_picker_item("image", item_id) for item_id in range(1, 102)],
            "miniprogram": [_picker_item("miniprogram", 201)],
            "attachment": [_picker_item("attachment", 301)],
        }

    def list_materials(
        self,
        material_type: str,
        *,
        q: str = "",
        enabled_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        del q, enabled_only
        rows = list(self._data[material_type])
        return {"items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    def get_materials_by_ids(self, material_type: str, ids: list[int]) -> list[dict]:
        by_id = {int(item["library_id"]): item for item in self._data[material_type]}
        return [by_id[item_id] for item_id in ids if item_id in by_id]


def _picker_item(material_type: str, item_id: int) -> dict:
    return {
        "type": material_type,
        "library_id": item_id,
        "title": f"{material_type}-{item_id}",
        "subtitle": "",
        "thumbnail_url": "",
        "enabled": True,
        "metadata": {},
    }
