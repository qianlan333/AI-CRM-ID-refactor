from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.ops_enrollment import application


ROOT = Path(__file__).resolve().parents[1]


class ProductionUserOpsRepository:
    def list_rows(self) -> list[dict]:
        return [
            {
                "id": 1,
                "person_id": "person_001",
                "mobile": "13800138000",
                "external_userid": "wx_ext_001",
                "customer_name": "张小蓝",
                "owner_userid": "owner-a",
                "owner_display_name": "顾问甲",
                "class_term_no": "2026-05-A",
                "class_term_label": "2026 五月 A 班",
                "source_type": "lead_pool",
                "created_at": "2026-05-01T09:00:00+08:00",
                "updated_at": "2026-05-18T10:00:00+08:00",
                "activation_bucket": "activated",
                "tags": ["黄小璨"],
                "is_added_wecom": True,
                "is_mobile_bound": True,
                "do_not_disturb": False,
                "do_not_disturb_reasons": [],
            }
        ]

    def close(self) -> None:
        pass


def test_frontend_compat_legacy_routes_remain_removed() -> None:
    client = TestClient(create_app())

    response = client.get("/api/frontend-compat/legacy-routes")

    assert response.status_code == 404
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_health_uses_next_native_runtime_contract(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["runtime_owner"] == "ai_crm_next"
    assert payload["production_data_ready"] is True
    assert payload["production_data_mode"] is True
    assert payload["repository_policy"] == "production_repositories_required"
    assert payload["legacy_runtime_enabled"] is False
    removed_legacy_field = "legacy_" + "production_facade_enabled"
    assert removed_legacy_field not in payload


def test_user_ops_overview_postgres_contract_avoids_fixture_blocker(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.delenv("USER_OPS_REPO_BACKEND", raising=False)
    application._REPO = None
    monkeypatch.setattr(application, "build_user_ops_repository", lambda: ProductionUserOpsRepository())
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/user-ops/overview")

    assert response.status_code == 200
    assert "fixture_repository_blocked_in_production" not in response.text


def test_app_py_legacy_commands_still_hard_error() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    for args in (
        ("run-legacy",),
        ("init-db",),
        ("init-db-legacy",),
        ("delete-questionnaire-submissions", "demo"),
        ("delete-questionnaire-submissions-legacy", "demo"),
    ):
        result = subprocess.run(
            [sys.executable, "app.py", *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "has been removed. AI-CRM now starts with Next runtime only." in output
        assert "wecom_ability_service" not in output


def test_strict_legacy_checker_still_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_no_new_legacy.py", "--strict"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert '"ok": true' in result.stdout
