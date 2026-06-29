from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from tools import media_library_gray_smoke as gray_smoke
from tools.doc_paths import read_experiment_doc

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _args(*, include_fake_writes: bool = False, next_testclient: bool = True, next_base_url: str = "") -> Namespace:
    return Namespace(
        next_testclient=next_testclient,
        next_base_url=next_base_url,
        include_fake_writes=include_fake_writes,
        output_md="/tmp/unused.md",
        output_json="/tmp/unused.json",
    )


def test_default_smoke_endpoints_are_get_only() -> None:
    assert gray_smoke.DEFAULT_READ_ENDPOINTS
    assert all(endpoint.method == "GET" for endpoint in gray_smoke.DEFAULT_READ_ENDPOINTS)


def test_default_smoke_covers_media_list_routes() -> None:
    paths = {endpoint.path for endpoint in gray_smoke.DEFAULT_READ_ENDPOINTS}
    assert "/admin/image-library" in paths
    assert "/api/admin/image-library" in paths
    assert "/admin/attachment-library" in paths
    assert "/api/admin/attachment-library" in paths
    assert "/admin/miniprogram-library" in paths
    assert "/api/admin/miniprogram-library" in paths


def test_default_smoke_runs_readonly_against_next_testclient() -> None:
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is True
    assert report["side_effect_safety"]["old_write_endpoints_executed"] is False
    assert report["side_effect_safety"]["external_upload_executed"] is False
    assert report["side_effect_safety"]["wecom_media_upload_executed"] is False
    assert all(item["method"] == "GET" for item in report["route_results"])
    assert any(item["reason"] == "fake_writes_not_requested" for item in report["skipped"])


def test_fake_writes_require_explicit_include_fake_writes() -> None:
    default_report = gray_smoke.run_smoke(_args())
    assert not any(item["method"] in {"POST", "PUT", "DELETE"} for item in default_report["route_results"])

    write_report = gray_smoke.run_smoke(_args(include_fake_writes=True))
    assert write_report["ok"] is True
    assert {"POST", "PUT", "DELETE"} <= {item["method"] for item in write_report["route_results"]}
    assert write_report["side_effect_safety"]["old_write_endpoints_executed"] is False


def test_fake_write_mode_only_targets_next_testclient() -> None:
    report = gray_smoke.run_smoke(_args(include_fake_writes=True, next_testclient=False, next_base_url="http://127.0.0.1:8000"))
    assert report["ok"] is False
    assert any(item["reason"] == "fake_writes_require_next_testclient" for item in report["blockers"])


def test_report_includes_side_effect_safety(tmp_path: Path) -> None:
    report = gray_smoke.run_smoke(_args())
    output_md = tmp_path / "media_gray.md"
    output_json = tmp_path / "media_gray.json"
    gray_smoke.write_markdown_report(report, output_md)
    gray_smoke.write_json_report(report, output_json)
    assert "old_write_endpoints_executed" in output_md.read_text(encoding="utf-8")
    assert "side_effect_safety" in output_json.read_text(encoding="utf-8")


def test_report_fails_if_route_returns_500(monkeypatch) -> None:
    def fake_request(_client, method: str, path: str, payload=None):
        if path == "/api/admin/image-library":
            return 500, {"ok": False}
        return 200, {"ok": True, "items": [], "total": 0, "limit": 100, "offset": 0}

    monkeypatch.setattr(gray_smoke, "_request_testclient", fake_request)
    report = gray_smoke.run_smoke(_args())
    assert report["ok"] is False
    assert any(item["reason"] == "route_returned_5xx" for item in report["blockers"])


def test_route_cutover_manifest_includes_all_media_routes() -> None:
    text = (PROJECT_ROOT / "docs" / "media_library_route_cutover_manifest.md").read_text(encoding="utf-8")
    required_routes = [
        "/admin/image-library",
        "/api/admin/image-library",
        "/api/admin/image-library/from-url",
        "/api/admin/image-library/from-base64",
        "/api/admin/image-library/{image_id}",
        "/admin/attachment-library",
        "/api/admin/attachment-library",
        "/api/admin/attachment-library/{attachment_id}",
        "/admin/miniprogram-library",
        "/api/admin/miniprogram-library",
        "/api/admin/miniprogram-library/{item_id}",
    ]
    for route in required_routes:
        assert route in text
    for method in ["GET", "POST", "PUT", "DELETE"]:
        assert f"| {method} |" in text


def test_gray_release_plan_does_not_mark_production_ready() -> None:
    text = read_experiment_doc("media_library_gray_release_plan.md")
    assert "production_ready |" not in text
    assert "status: production_ready" not in text
    assert "not ready" in text
    assert "Real WeCom media upload" in text


def test_media_gray_smoke_tool_does_not_import_old_backend() -> None:
    assert Path(gray_smoke.__file__).resolve().relative_to(PROJECT_ROOT.parents[1]) == Path("tools/media_library_gray_smoke.py")
    report = gray_smoke.run_smoke(_args())
    safety = report["side_effect_safety"]
    assert safety["old_write_endpoints_executed"] is False
    assert safety["external_upload_executed"] is False
    assert safety["wecom_media_upload_executed"] is False
