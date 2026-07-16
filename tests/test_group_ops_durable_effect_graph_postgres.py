from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from sqlalchemy.exc import IntegrityError

from aicrm_next.automation_engine.group_ops.durable_effects_repository import (
    GroupOpsEffectGraphRequest,
    GroupOpsEffectMaterial,
    SQLAlchemyGroupOpsEffectGraphRepository,
)
from aicrm_next.shared.db_session import get_session_factory


pytestmark = pytest.mark.usefixtures("next_pg_schema")
PNG = b"\x89PNG\r\n\x1a\n" + b"postgres-group-ops"


@pytest.fixture(autouse=True)
def _wecom_contract(monkeypatch):
    monkeypatch.setenv("AICRM_WECOM_EXECUTION_MODE", "execute")
    monkeypatch.setenv(
        "AICRM_WECOM_ENABLED_EFFECT_TYPES",
        "wecom.media.upload,wecom.message.group.send",
    )


def _repo() -> SQLAlchemyGroupOpsEffectGraphRepository:
    return SQLAlchemyGroupOpsEffectGraphRepository(get_session_factory())


def _request(
    key: str,
    *,
    material_count: int = 1,
    source_kind: str = "direct_send",
    version: str = "v1",
    scheduled_at: datetime | None = None,
) -> GroupOpsEffectGraphRequest:
    return GroupOpsEffectGraphRequest(
        idempotency_key=key,
        source_kind=source_kind,
        plan_id=700,
        node_id=701 if source_kind == "plan_node" else 0,
        chat_ids=["chat-postgres"],
        content_payload={
            "channel": "wecom_customer_group",
            "sender": "owner-postgres",
            "text": {"content": f"hello {version}"},
            "attachments": [],
        },
        content_summary=f"hello {version}",
        actor_id="pytest",
        owner_userid="owner-postgres",
        source_module="pytest.group_ops",
        source_route="/pytest/group-ops",
        source_command_id=key,
        scheduled_at=scheduled_at or datetime.now(timezone.utc) + timedelta(hours=1),
        version_fingerprint=version,
        materials=tuple(
            GroupOpsEffectMaterial(
                material_key=f"image:{index}",
                role="image",
                file_name=f"image-{index}.png",
                content_type="image/png",
                file_bytes=PNG + bytes([index]),
            )
            for index in range(1, material_count + 1)
        ),
    )


def _connect():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, row_factory=dict_row)


def _complete_upload(job_id: int, *, media_id: str) -> None:
    attempt_id = f"eea_{uuid4().hex}"
    with _connect() as connection:
        payload = connection.execute(
            "SELECT payload_json FROM external_effect_job WHERE id = %s",
            (job_id,),
        ).fetchone()["payload_json"]
        connection.execute(
            "UPDATE image_library SET thumb_media_id = %s WHERE id = %s",
            (media_id, int(payload["material_id"])),
        )
        connection.execute(
            """
            INSERT INTO external_effect_attempt (
                attempt_id, job_id, adapter_name, adapter_mode, operation,
                status, request_summary_json, response_summary_json,
                started_at, completed_at
            )
            SELECT %s, id, adapter_name, 'execute', operation,
                   'succeeded', '{}'::jsonb,
                   jsonb_build_object('provider_result_received', TRUE),
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM external_effect_job WHERE id = %s
            """,
            (attempt_id, job_id),
        )
        connection.execute(
            """
            UPDATE external_effect_job
            SET status = 'succeeded', last_attempt_id = %s,
                provider_call_started_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (attempt_id, job_id),
        )


def test_postgres_graph_is_atomic_across_material_and_effect_rows():
    request = _request("atomic-invalid-role", material_count=0)
    request = GroupOpsEffectGraphRequest(
        **{
            **request.__dict__,
            "materials": (
                GroupOpsEffectMaterial(
                    material_key="bad-role",
                    role="unsupported",
                    file_name="bad.png",
                    content_type="image/png",
                    file_bytes=PNG,
                ),
            ),
        }
    )

    with pytest.raises(IntegrityError):
        _repo().plan(request)

    with _connect() as connection:
        graph_count = connection.execute(
            "SELECT COUNT(*) AS count FROM automation_group_ops_effect_graph WHERE idempotency_key = %s",
            (request.idempotency_key,),
        ).fetchone()["count"]
        effect_count = connection.execute(
            "SELECT COUNT(*) AS count FROM external_effect_job WHERE idempotency_key LIKE %s",
            (f"{request.idempotency_key}:%",),
        ).fetchone()["count"]
    assert graph_count == 0
    assert effect_count == 0


def test_postgres_future_send_keeps_media_ineligible_until_preparation_window():
    due_at = datetime.now(timezone.utc) + timedelta(days=7)
    planned = _repo().plan(
        _request("postgres-future-media-window", material_count=1, scheduled_at=due_at)
    )

    with _connect() as connection:
        upload = connection.execute(
            "SELECT status, scheduled_at, available_at FROM external_effect_job WHERE id = %s",
            (planned["upload_effect_job_ids"][0],),
        ).fetchone()
        final = connection.execute(
            "SELECT status, scheduled_at, available_at FROM external_effect_job WHERE id = %s",
            (planned["final_effect_job_id"],),
        ).fetchone()

    assert upload["status"] == "queued"
    assert upload["scheduled_at"] == final["scheduled_at"]
    assert timedelta(hours=11, minutes=59) <= due_at - upload["available_at"] <= timedelta(hours=12, seconds=1)
    assert upload["available_at"] > datetime.now(timezone.utc)
    assert final["status"] == "planned"


def test_postgres_dependency_release_requires_every_upload_and_is_restart_idempotent():
    repo = _repo()
    planned = repo.plan(_request("postgres-release", material_count=2))
    first, second = planned["upload_effect_job_ids"]

    _complete_upload(first, media_id="media-first")
    waiting = repo.release_after_upload(first)
    _complete_upload(second, media_id="media-second")
    released = SQLAlchemyGroupOpsEffectGraphRepository(get_session_factory()).release_after_upload(second)
    duplicate = SQLAlchemyGroupOpsEffectGraphRepository(get_session_factory()).release_after_upload(second)

    assert waiting["released"] is False
    assert waiting["remaining"] == 1
    assert released["released"] is True
    assert duplicate["released"] is False
    assert duplicate["reason"] == "final_effect_already_released"
    with _connect() as connection:
        final = connection.execute(
            "SELECT status, payload_json, parent_execution_id FROM external_effect_job WHERE id = %s",
            (planned["final_effect_job_id"],),
        ).fetchone()
    assert final["status"] == "queued"
    assert final["parent_execution_id"] == planned["execution_id"]
    assert final["payload_json"]["content_payload"]["attachments"] == [
        {"msgtype": "image", "image": {"media_id": "media-first"}},
        {"msgtype": "image", "image": {"media_id": "media-second"}},
    ]


def test_failed_or_cancelled_upload_never_releases_final_effect():
    repo = _repo()
    planned = repo.plan(_request("postgres-cancel", material_count=1))
    upload_id = planned["upload_effect_job_ids"][0]
    with _connect() as connection:
        connection.execute(
            "UPDATE external_effect_job SET status = 'failed_terminal', completed_at = CURRENT_TIMESTAMP WHERE id = %s",
            (upload_id,),
        )
    failed = repo.release_after_upload(upload_id)
    cancelled = repo.cancel(planned["execution_id"], actor="pytest", reason="cancelled")
    _complete_upload(upload_id, media_id="late-media")
    late = SQLAlchemyGroupOpsEffectGraphRepository(get_session_factory()).release_after_upload(upload_id)

    assert failed["released"] is False
    assert failed["reason"] == "upload_not_succeeded"
    assert cancelled["cancelled"] is True
    assert late["released"] is False
    assert late["reason"] == "graph_cancelled"
    with _connect() as connection:
        final_status = connection.execute(
            "SELECT status FROM external_effect_job WHERE id = %s",
            (planned["final_effect_job_id"],),
        ).fetchone()["status"]
    assert final_status == "cancelled"


def test_plan_edit_increments_version_and_preserves_crossed_provider_boundary():
    repo = _repo()
    first = repo.plan(_request("plan-edit-v1", material_count=0, source_kind="plan_node", version="v1"))
    with _connect() as connection:
        connection.execute(
            """
            UPDATE external_effect_job
            SET status = 'dispatching', provider_call_started_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (first["final_effect_job_id"],),
        )
    second = repo.plan(_request("plan-edit-v2", material_count=0, source_kind="plan_node", version="v2"))

    assert first["source_version"] == 1
    assert second["source_version"] == 2
    with _connect() as connection:
        old = connection.execute(
            "SELECT status, provider_call_started_at FROM external_effect_job WHERE id = %s",
            (first["final_effect_job_id"],),
        ).fetchone()
        old_graph = connection.execute(
            "SELECT status FROM automation_group_ops_effect_graph WHERE execution_id = %s",
            (first["execution_id"],),
        ).fetchone()
    assert old["status"] == "dispatching"
    assert old["provider_call_started_at"] is not None
    assert old_graph["status"] == "superseded"
