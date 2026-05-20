from __future__ import annotations

from conftest import make_client


def test_image_library_crud_and_fake_imports() -> None:
    client = make_client()
    payload = client.get("/api/admin/image-library").json()
    assert payload["ok"] is True
    item = payload["items"][0]
    for key in ["id", "name", "file_name", "content_type", "file_size", "width", "height", "data_url", "tags", "created_at", "updated_at"]:
        assert key in item
    facets = client.get("/api/admin/image-library/facets").json()
    assert facets == {"ok": True, "categories": [], "tags": ["commerce"]}
    created = client.post(
        "/api/admin/image-library",
        json={"name": "图片", "file_name": "x.png", "content_type": "image/png", "file_size": 8, "width": 1, "height": 1, "data_url": "data:image/png;base64,ZmFrZQ=="},
    ).json()["item"]
    assert client.get(f"/api/admin/image-library/{created['id']}").json()["item"]["name"] == "图片"
    assert client.put(f"/api/admin/image-library/{created['id']}", json={**created, "name": "图片更新"}).json()["item"]["name"] == "图片更新"
    assert client.post("/api/admin/image-library/from-url", json={"url": "https://example.invalid/a.png", "name": "外链"}).json()["source_status"] == "fake_import"
    assert client.post("/api/admin/image-library/from-base64", json={"data_base64": "ZmFrZQ==", "name": "base64"}).json()["source_status"] == "fake_import"
    assert client.delete(f"/api/admin/image-library/{created['id']}").json()["soft_deleted"] is True


def test_attachment_library_crud() -> None:
    client = make_client()
    payload = client.get("/api/admin/attachment-library").json()
    assert payload["ok"] is True
    item = payload["items"][0]
    for key in ["id", "name", "file_name", "mime_type", "file_size", "data_base64", "tags", "enabled", "created_at", "updated_at"]:
        assert key in item
    created = client.post(
        "/api/admin/attachment-library",
        json={"name": "附件", "file_name": "a.pdf", "mime_type": "application/pdf", "file_size": 10, "data_base64": "ZmFrZQ=="},
    ).json()["item"]
    assert client.get(f"/api/admin/attachment-library/{created['id']}").json()["item"]["file_name"] == "a.pdf"
    assert client.put(f"/api/admin/attachment-library/{created['id']}", json={**created, "enabled": False}).json()["item"]["enabled"] is False
    assert client.delete(f"/api/admin/attachment-library/{created['id']}").json()["deleted"] is True


def test_miniprogram_library_crud() -> None:
    client = make_client()
    payload = client.get("/api/admin/miniprogram-library").json()
    assert payload["ok"] is True
    item = payload["items"][0]
    for key in ["id", "title", "appid", "page_path", "thumb_image_id", "description", "tags", "enabled", "created_at", "updated_at"]:
        assert key in item
    created = client.post(
        "/api/admin/miniprogram-library",
        json={"title": "小程序", "appid": "appid_masked_new", "page_path": "pages/a/index", "thumb_image_id": "image_masked_001"},
    ).json()["item"]
    assert client.get(f"/api/admin/miniprogram-library/{created['id']}").json()["item"]["appid"] == "appid_masked_new"
    assert client.put(f"/api/admin/miniprogram-library/{created['id']}", json={**created, "enabled": False}).json()["item"]["enabled"] is False
    assert client.delete(f"/api/admin/miniprogram-library/{created['id']}").json()["deleted"] is True
