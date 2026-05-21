from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
OLD_MEDIA_ROUTE_FILES = [
    "wecom_ability_service/http/image_library_endpoint.py",
    "wecom_ability_service/http/image_library_create.py",
    "wecom_ability_service/http/attachment_library_endpoint.py",
    "wecom_ability_service/http/miniprogram_library_endpoint.py",
]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_old_media_route_files_are_absent() -> None:
    assert [path for path in OLD_MEDIA_ROUTE_FILES if (REPO_ROOT / path).exists()] == []


def test_old_http_registrar_has_no_media_library_imports_or_register_entries() -> None:
    content = _read("wecom_ability_service/http/__init__.py")
    forbidden_tokens = [
        "image_library_endpoint",
        "image_library_create",
        "attachment_library_endpoint",
        "miniprogram_library_endpoint",
        "register_image_library_routes",
        "register_attachment_library_routes",
        "register_miniprogram_library_routes",
        '("image_library"',
        '("attachment_library"',
        '("miniprogram_library"',
    ]
    assert [token for token in forbidden_tokens if token in content] == []


def test_aicrm_next_media_library_package_exists() -> None:
    assert (REPO_ROOT / "aicrm_next" / "media_library" / "api.py").exists()
    assert (REPO_ROOT / "aicrm_next" / "media_library" / "repo.py").exists()


def test_next_media_readonly_routes_are_served_by_ai_crm_next() -> None:
    from aicrm_next.main import app

    client = TestClient(app)
    for path in [
        "/admin/image-library",
        "/api/admin/image-library",
        "/admin/attachment-library",
        "/api/admin/attachment-library",
        "/admin/miniprogram-library",
        "/api/admin/miniprogram-library",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_app_py_default_is_still_next() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert "uvicorn.run(NEXT_APP_IMPORT" in content
    assert "command = args.command or \"run\"" in content


def test_legacy_fallback_still_exists() -> None:
    assert (REPO_ROOT / "legacy_flask_app.py").exists()
    help_result = subprocess.run(
        [sys.executable, "legacy_flask_app.py", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "legacy Flask fallback" in help_result.stdout or "legacy Flask fallback" in help_result.stderr


def test_deploy_and_production_config_not_modified_by_d1() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden = [
        path
        for path in changed
        if path.startswith("deploy/")
        or path.startswith(".github/")
        or any(keyword in path.lower() for keyword in ["nginx", "systemd", "supervisor", "docker-compose", "production"])
        and not path.startswith(("docs/", "tests/", "tools/"))
    ]
    assert forbidden == []


def test_d7_to_d9_docs_are_not_marked_retired_or_deleted() -> None:
    content = _read("docs/legacy_delete_batches.md")
    for batch in ["D7", "D8", "D9"]:
        section = content.split(f"## {batch}:", 1)[1].split("## ", 1)[0]
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        assert not status_line.startswith("status: retired")
        assert not status_line.startswith("status: deleted")


def test_d1_retirement_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "d1.md"
    output_json = tmp_path / "d1.json"
    subprocess.run(
        [
            sys.executable,
            "tools/check_legacy_d1_media_retirement.py",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["production_config_modified"] is False
