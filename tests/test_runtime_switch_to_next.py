from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(wecom_ability_service|openclaw_service)\b|import\s+(wecom_ability_service|openclaw_service)\b)"
)


def test_app_help_includes_next_and_legacy_commands() -> None:
    result = subprocess.run(
        [sys.executable, "app.py", "--help"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "run" in result.stdout
    assert "run-legacy" in result.stdout
    assert "AI-CRM Next" in result.stdout


def test_app_default_run_path_is_documented_as_next() -> None:
    content = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert "command = args.command or \"run\"" in content
    assert "uvicorn.run(NEXT_APP_IMPORT" in content


def test_legacy_flask_runner_exists() -> None:
    assert (REPO_ROOT / "legacy_flask_app.py").exists()


def test_aicrm_next_main_exposes_fastapi_app() -> None:
    from aicrm_next.main import app

    assert isinstance(app, FastAPI)


def test_aicrm_next_route_owner_header_is_next() -> None:
    from aicrm_next.main import app

    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-App"] == "ai_crm_next"


def test_legacy_fallback_docs_exist() -> None:
    assert (REPO_ROOT / "docs" / "runtime_switch_to_next.md").exists()
    assert (REPO_ROOT / "wecom_ability_service" / "LEGACY_FROZEN.md").exists()
    assert not (REPO_ROOT / "openclaw_service").exists()
    deletion_report = (REPO_ROOT / "docs" / "d9_6_openclaw_physical_deletion_report.md").read_text(encoding="utf-8")
    assert "Repository `openclaw_service/`: absent." in deletion_report


def test_no_legacy_backend_imports_in_aicrm_next() -> None:
    findings: list[str] = []
    for path in sorted((REPO_ROOT / "aicrm_next").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN_IMPORT_RE.search(line):
                findings.append(f"{path.relative_to(REPO_ROOT)}:{lineno}:{line.strip()}")
    assert findings == []


def test_legacy_delete_batches_exist() -> None:
    content = (REPO_ROOT / "docs" / "legacy_delete_batches.md").read_text(encoding="utf-8")
    for batch in ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9"]:
        assert batch in content


def test_runtime_switch_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "runtime_switch.md"
    output_json = tmp_path / "runtime_switch.json"
    result = subprocess.run(
        [
            sys.executable,
            "tools/check_runtime_switch_to_next.py",
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
    assert result.returncode == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["default_runtime"]["runtime"] == "ai_crm_next"


def test_legacy_flask_app_does_not_import_old_backend_at_module_import() -> None:
    spec = importlib.util.spec_from_file_location("legacy_flask_app_runtime_test", REPO_ROOT / "legacy_flask_app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")
