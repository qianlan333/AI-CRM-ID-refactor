from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from aicrm_next.owner_migration.application import OwnerMigrationCommand, OwnerMigrationService


class FakeOwnerMigrationRepository:
    source_status = "fake"

    def __init__(self) -> None:
        self.executed = False

    def preview_owner_migration(self, *, source_owner_userid: str, target_owner_userid: str) -> dict:
        return {
            "source_status": self.source_status,
            "candidate_count": 2,
            "sample_external_userids": ["wm_ext_1", "wm_ext_2"],
            "surface_counts": {"contacts": 2},
            "pending_review": {"pending_user_ops_deferred_jobs": 1},
        }

    def execute_owner_migration(
        self,
        *,
        source_owner_userid: str,
        target_owner_userid: str,
        operator: str,
        external_userids: list[str] | None = None,
    ) -> dict:
        self.executed = True
        return {
            **self.preview_owner_migration(
                source_owner_userid=source_owner_userid,
                target_owner_userid=target_owner_userid,
            ),
            "executed": True,
            "touched_count": 2,
            "update_counts": {"contacts": 2},
        }


def test_owner_migration_page_renders_default_mengyu_to_huangyoucan(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = TestClient(create_app()).get("/admin/owner-migration")

    assert response.status_code == 200
    assert 'value="mengyu"' in response.text
    assert 'value="huangyoucan"' in response.text
    assert "执行迁移" in response.text


def test_owner_migration_service_rejects_same_owner():
    service = OwnerMigrationService(FakeOwnerMigrationRepository())

    result = service.run(
        OwnerMigrationCommand(
            source_owner_userid="mengyu",
            target_owner_userid="mengyu",
        )
    )

    assert result["ok"] is False
    assert result["error_code"] == "same_owner_userid"


def test_owner_migration_api_preview_uses_service(monkeypatch):
    repo = FakeOwnerMigrationRepository()
    service = OwnerMigrationService(repo)
    monkeypatch.setattr("aicrm_next.owner_migration.api.build_owner_migration_service", lambda: service)

    response = TestClient(create_app()).post(
        "/api/admin/owner-migration/preview",
        json={"source_owner_userid": "mengyu", "target_owner_userid": "huangyoucan"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["candidate_count"] == 2
    assert payload["sample_external_userids"] == ["wm_ext_1", "wm_ext_2"]
    assert repo.executed is False


def test_owner_migration_api_execute_requires_confirm(monkeypatch):
    service = OwnerMigrationService(FakeOwnerMigrationRepository())
    monkeypatch.setattr("aicrm_next.owner_migration.api.build_owner_migration_service", lambda: service)

    response = TestClient(create_app()).post(
        "/api/admin/owner-migration/execute",
        json={"source_owner_userid": "mengyu", "target_owner_userid": "huangyoucan"},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "confirm_required"


def test_owner_migration_api_execute_with_confirm(monkeypatch):
    repo = FakeOwnerMigrationRepository()
    service = OwnerMigrationService(repo)
    monkeypatch.setattr("aicrm_next.owner_migration.api.build_owner_migration_service", lambda: service)

    response = TestClient(create_app()).post(
        "/api/admin/owner-migration/execute",
        json={
            "source_owner_userid": "mengyu",
            "target_owner_userid": "huangyoucan",
            "operator": "pytest",
            "confirm": True,
            "perform_wecom_transfer": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "execute"
    assert payload["update_counts"] == {"contacts": 2}
    assert repo.executed is True


def test_owner_migration_service_executes_wecom_transfer_before_local_update(monkeypatch):
    class TransferAdapter:
        def transfer_customer(self, payload):
            assert payload["handover_userid"] == "mengyu"
            assert payload["takeover_userid"] == "huangyoucan"
            return {
                "errcode": 0,
                "errmsg": "ok",
                "customer": [
                    {"external_userid": "wm_ext_1", "errcode": 0},
                    {"external_userid": "wm_ext_2", "errcode": 40096},
                ],
            }

    captured = {}

    class ScopedRepo(FakeOwnerMigrationRepository):
        def preview_owner_migration(self, *, source_owner_userid: str, target_owner_userid: str) -> dict:
            payload = super().preview_owner_migration(
                source_owner_userid=source_owner_userid,
                target_owner_userid=target_owner_userid,
            )
            payload["all_external_userids"] = ["wm_ext_1", "wm_ext_2"]
            return payload

        def execute_owner_migration(self, **kwargs) -> dict:
            captured["external_userids"] = kwargs.get("external_userids")
            return super().execute_owner_migration(**kwargs)

    monkeypatch.setattr("aicrm_next.owner_migration.application.missing_wecom_config", lambda: [])
    monkeypatch.setattr("aicrm_next.owner_migration.application.ProductionWeComAdapter", lambda: TransferAdapter())

    result = OwnerMigrationService(ScopedRepo()).run(
        OwnerMigrationCommand(
            source_owner_userid="mengyu",
            target_owner_userid="huangyoucan",
            operator="pytest",
            execute=True,
            confirm=True,
        )
    )

    assert result["ok"] is True
    assert captured["external_userids"] == ["wm_ext_1"]
    assert result["wecom_transfer"]["success_count"] == 1
    assert result["wecom_transfer"]["failed_customers"] == [{"external_userid": "wm_ext_2", "errcode": 40096}]
