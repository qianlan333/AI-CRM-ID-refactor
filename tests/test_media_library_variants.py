from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
    b"\x00\x00\x00\x0bIDATx\xdac`\x00\x01\x00\x00\x07\x00\x01\xe9\x15\x08-"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_client() -> TestClient:
    return TestClient(create_app())


def test_image_upload_returns_variant_urls_and_variant_endpoint_is_cacheable() -> None:
    client = make_client()
    uploaded = client.post(
        "/api/admin/image-library/upload",
        files={"image": ("hero.png", BytesIO(TINY_PNG), "image/png")},
        data={"name": "variant hero"},
    ).json()["item"]

    assert uploaded["thumb_160_url"].endswith("/variants/thumb_160")
    assert uploaded["thumb_320_url"].endswith("/variants/thumb_320")
    assert uploaded["preview_url"].endswith("/variants/preview_720")

    listed = client.get("/api/admin/image-library", params={"enabled_only": "true"}).json()
    row = next(item for item in listed["items"] if item["id"] == uploaded["id"])
    assert row["thumb_url"].endswith("/variants/thumb_320")
    assert "data_base64" not in row

    variant = client.get(uploaded["thumb_160_url"])
    assert variant.status_code == 200
    assert variant.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert variant.headers.get("etag")
    assert variant.headers["content-type"].startswith("image/")
    assert len(variant.content) < len(TINY_PNG) * 20

    cached = client.get(uploaded["thumb_160_url"], headers={"If-None-Match": variant.headers["etag"]})
    assert cached.status_code == 304


def test_image_detail_requires_include_data_for_original_base64() -> None:
    client = make_client()
    uploaded = client.post(
        "/api/admin/image-library/upload",
        files={"image": ("hero.png", BytesIO(TINY_PNG), "image/png")},
    ).json()["item"]

    detail = client.get(f"/api/admin/image-library/{uploaded['id']}").json()
    assert detail["ok"] is True
    assert "data_base64" not in detail["item"]

    with_data = client.get(f"/api/admin/image-library/{uploaded['id']}?include_data=true").json()
    assert with_data["ok"] is True
    assert with_data["item"]["data_base64"]
