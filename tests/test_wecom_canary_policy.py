from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from aicrm_next.platform_foundation.external_effects import wecom_canary_policy as policy
from aicrm_next.platform_foundation.external_effects.models import (
    WECOM_MESSAGE_PRIVATE_SEND,
    ExternalEffectJob,
)
from aicrm_next.platform_foundation.external_effects.repo import SQLAlchemyExternalEffectRepository
from aicrm_next.platform_foundation.external_effects.repo_memory import InMemoryExternalEffectRepository
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService
from aicrm_next.platform_foundation.execution_runtime.listener import (
    PostgresQueueWakeListener,
)
from aicrm_next.shared.db_session import get_session_factory


def _database_url() -> str:
    return str(os.getenv("AICRM_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()


def _configure(monkeypatch, *, mode: str = "allowlisted_canary", **allowlists: set[str]) -> None:
    values = {
        policy.WECOM_ALLOWED_EXTERNAL_USERIDS_KEY: allowlists.get("external_userids", set()),
        policy.WECOM_ALLOWED_OWNER_USERIDS_KEY: allowlists.get("owner_userids", set()),
        policy.WECOM_ALLOWED_GROUP_WEBHOOK_KEYS_KEY: allowlists.get("group_webhook_keys", set()),
        policy.WECOM_ALLOWED_GROUP_CHAT_IDS_KEY: allowlists.get("group_chat_ids", set()),
        policy.WECOM_ALLOWED_MEDIA_TARGETS_KEY: allowlists.get("media_targets", set()),
    }
    monkeypatch.setattr(
        policy,
        "runtime_setting",
        lambda key, default="": mode if key == policy.WECOM_PROVIDER_TARGET_POLICY_KEY else default,
    )
    monkeypatch.setattr(policy, "runtime_csv", lambda key: set(values.get(key, set())))


def test_wecom_canary_policy_is_blocked_by_default(monkeypatch) -> None:
    _configure(monkeypatch, mode="blocked")

    assert (
        policy.wecom_canary_gate_error(
            payload={"execution_scope": "allowlisted_canary"},
            external_userids=["wm_canary"],
        )
        == "wecom_provider_target_policy_blocked"
    )


def test_wecom_canary_policy_requires_explicit_execution_scope(monkeypatch) -> None:
    _configure(monkeypatch, external_userids={"wm_canary"})

    assert (
        policy.wecom_canary_gate_error(payload={}, external_userids=["wm_canary"])
        == "wecom_execution_scope_not_allowlisted_canary"
    )


def test_wecom_canary_private_target_and_owner_must_both_match(monkeypatch) -> None:
    _configure(
        monkeypatch,
        external_userids={"wm_canary"},
        owner_userids={"owner_canary"},
    )
    payload = {"execution_scope": "allowlisted_canary"}

    assert (
        policy.wecom_canary_gate_error(
            payload=payload,
            external_userids=["wm_canary"],
            owner_userids=["owner_canary"],
        )
        == ""
    )
    assert (
        policy.wecom_canary_gate_error(
            payload=payload,
            external_userids=["wm_other"],
            owner_userids=["owner_canary"],
        )
        == "wecom_target_not_allowlisted"
    )
    assert (
        policy.wecom_canary_gate_error(
            payload=payload,
            external_userids=["wm_canary"],
            owner_userids=["owner_other"],
        )
        == "wecom_owner_not_allowlisted"
    )


def test_wecom_canary_group_requires_webhook_chats_owner_and_no_mention_all(monkeypatch) -> None:
    _configure(
        monkeypatch,
        owner_userids={"owner_canary"},
        group_webhook_keys={"group-canary"},
        group_chat_ids={"chat_a", "chat_b"},
    )
    payload = {"execution_scope": "allowlisted_canary"}
    arguments = {
        "payload": payload,
        "owner_userids": ["owner_canary"],
        "group_webhook_key": "group-canary",
        "group_chat_ids": ["chat_a", "chat_b"],
    }

    assert policy.wecom_canary_gate_error(**arguments) == ""
    assert (
        policy.wecom_canary_gate_error(**arguments, mention_all=True)
        == "wecom_canary_mention_all_blocked"
    )
    assert (
        policy.wecom_canary_gate_error(**{**arguments, "group_chat_ids": ["chat_other"]})
        == "wecom_group_chat_not_allowlisted"
    )
    assert (
        policy.wecom_canary_gate_error(**{**arguments, "group_webhook_key": "group-other"})
        == "wecom_group_webhook_not_allowlisted"
    )


def test_wecom_canary_media_target_is_exact_and_snapshot_redacts_values(monkeypatch) -> None:
    target = "image:7:image"
    _configure(monkeypatch, media_targets={target})

    assert (
        policy.wecom_canary_gate_error(
            payload={"execution_scope": "allowlisted_canary"},
            media_target=target,
        )
        == ""
    )
    snapshot = policy.wecom_canary_policy_snapshot()
    assert snapshot["allowlist_counts"]["media_target"] == 1
    assert target not in str(snapshot)


def test_wecom_provider_boundary_rejects_scope_without_durable_authorization(monkeypatch) -> None:
    _configure(
        monkeypatch,
        external_userids={"wm_canary"},
        owner_userids={"owner_canary"},
    )
    monkeypatch.setenv("AICRM_WECOM_DEFAULT_SENDER_USERID", "owner_canary")
    job = ExternalEffectJob(
        id=1,
        effect_type=WECOM_MESSAGE_PRIVATE_SEND,
        target_type="external_user",
        target_id="wm_canary",
        payload_json={
            "execution_scope": "allowlisted_canary",
            "channel": "wecom_private",
            "owner_userid": "owner_canary",
            "external_userids": ["wm_canary"],
            "content_text": "canary",
        },
    )

    assert policy.wecom_canary_job_gate_error(job) == "wecom_canary_authorization_missing"


@pytest.mark.parametrize(
    ("job", "expected_error"),
    (
        (
            ExternalEffectJob(
                id=11,
                effect_type="wecom.message.private.send",
                payload_json={"external_userids": ["wm_canary"]},
            ),
            "wecom_canary_owner_required",
        ),
        (
            ExternalEffectJob(
                id=12,
                effect_type="wecom.message.group.send",
                payload_json={"owner_userid": "owner_canary"},
            ),
            "wecom_canary_group_chat_required",
        ),
        (
            ExternalEffectJob(
                id=13,
                effect_type="wecom.welcome_message.send",
                payload_json={"follow_user_userid": "owner_canary"},
            ),
            "wecom_canary_external_target_required",
        ),
        (
            ExternalEffectJob(
                id=14,
                effect_type="wecom.external_contact.detail.fetch",
                payload_json={},
            ),
            "wecom_canary_external_target_required",
        ),
        (
            ExternalEffectJob(
                id=15,
                effect_type="wecom.media.upload",
                target_id="",
                payload_json={},
            ),
            "wecom_canary_media_target_required",
        ),
    ),
)
def test_wecom_provider_boundary_rejects_missing_required_targets(
    monkeypatch,
    job: ExternalEffectJob,
    expected_error: str,
) -> None:
    _configure(
        monkeypatch,
        external_userids={"wm_canary"},
        owner_userids={"owner_canary"},
        group_chat_ids={"chat_canary"},
    )
    monkeypatch.setattr(
        policy,
        "load_wecom_execution_config",
        lambda: SimpleNamespace(default_sender_userid=""),
    )

    assert policy.wecom_canary_job_gate_error(job) == expected_error


def test_normal_effect_planning_cannot_forge_canary_authorization(monkeypatch) -> None:
    _configure(
        monkeypatch,
        external_userids={"wm_canary"},
        owner_userids={"owner_canary"},
    )
    monkeypatch.setenv("AICRM_WECOM_DEFAULT_SENDER_USERID", "owner_canary")
    service = ExternalEffectService(InMemoryExternalEffectRepository())

    planned = service.plan_effect(
        effect_type=WECOM_MESSAGE_PRIVATE_SEND,
        adapter_name="wecom_private_message",
        operation="send",
        target_type="external_user",
        target_id="wm_canary",
        payload={
            "execution_scope": "allowlisted_canary",
            "external_userids": ["wm_canary"],
            "owner_userid": "owner_canary",
        },
        payload_summary={
            "canary_authorization": {
                "actor": "forged",
                "reason": "bypass CAS",
                "authorized_at": "2026-07-17T00:00:00Z",
                "duplicate_risk_confirmed": False,
            }
        },
        idempotency_key="canary-forgery-is-stripped",
    )
    job = service.get(planned["id"])

    assert job is not None
    assert "execution_scope" not in job.payload_json
    assert "canary_authorization" not in job.payload_summary_json
    assert (
        policy.wecom_canary_job_gate_error(job)
        == "wecom_execution_scope_not_allowlisted_canary"
    )


def test_wecom_canary_authorization_is_versioned_and_only_before_provider_boundary(monkeypatch) -> None:
    _configure(
        monkeypatch,
        external_userids={"wm_canary"},
        owner_userids={"owner_canary"},
    )
    monkeypatch.setenv("AICRM_WECOM_DEFAULT_SENDER_USERID", "owner_canary")
    repository = InMemoryExternalEffectRepository()
    service = ExternalEffectService(repository)

    def plan(key: str, *, available_at: datetime | None = None) -> dict:
        return service.plan_effect(
            effect_type=WECOM_MESSAGE_PRIVATE_SEND,
            adapter_name="wecom_private_message",
            operation="send",
            target_type="external_user",
            target_id="wm_canary",
            payload={
                "channel": "wecom_private",
                "owner_userid": "owner_canary",
                "external_userids": ["wm_canary"],
                "content_text": "canary",
            },
            idempotency_key=key,
            available_at=available_at,
        )

    first = plan(
        "canary-authorize-safe",
        available_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    authorized = service.authorize_allowlisted_canary(
        first["id"],
        actor="pytest",
        reason="explicit canary target confirmation",
        expected_version=first["row_version"],
    )

    assert authorized is not None
    assert authorized.payload_json["execution_scope"] == "allowlisted_canary"
    assert authorized.payload_summary_json["canary_authorization"]["actor"] == "pytest"
    assert authorized.available_at is not None
    assert datetime.fromisoformat(authorized.available_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    assert authorized.payload_summary_json["canary_authorization"]["authorized_job_id"] == first["id"]
    assert (
        authorized.payload_summary_json["canary_authorization"]["authorized_from_version"]
        == first["row_version"]
    )
    assert policy.wecom_canary_job_gate_error(authorized) == ""
    assert authorized.row_version == first["row_version"] + 1
    assert (
        service.authorize_allowlisted_canary(
            first["id"],
            actor="pytest",
            reason="stale replay",
            expected_version=first["row_version"],
        )
        is None
    )

    second = plan("canary-authorize-after-boundary")
    claimed = repository.acquire_job(second["id"], locked_by="pytest")
    assert claimed is not None
    assert repository.begin_provider_attempt(job=claimed, request_summary={}) is not None
    assert (
        service.authorize_allowlisted_canary(
            second["id"],
            actor="pytest",
            reason="must not authorize after boundary",
            expected_version=repository.get_job(second["id"]).row_version,  # type: ignore[union-attr]
        )
        is None
    )


@pytest.mark.skipif(not _database_url(), reason="PostgreSQL integration database is not configured")
@pytest.mark.usefixtures("next_pg_schema")
def test_postgres_wecom_canary_authorization_is_cas_and_audited(monkeypatch) -> None:
    _configure(
        monkeypatch,
        external_userids={"wm_canary"},
        owner_userids={"owner_canary"},
    )
    monkeypatch.setenv("AICRM_WECOM_DEFAULT_SENDER_USERID", "owner_canary")
    repository = SQLAlchemyExternalEffectRepository(get_session_factory(_database_url()))
    service = ExternalEffectService(repository)
    key = "canary-postgres-authorize-" + uuid4().hex
    planned = service.plan_effect(
        effect_type=WECOM_MESSAGE_PRIVATE_SEND,
        adapter_name="wecom_private_message",
        operation="send",
        target_type="external_user",
        target_id="wm_canary",
        payload={
            "channel": "wecom_private",
            "owner_userid": "owner_canary",
            "external_userids": ["wm_canary"],
            "content_text": "canary",
        },
        idempotency_key=key,
        available_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    listener = PostgresQueueWakeListener(_database_url())
    listener.connect()
    try:
        authorized = service.authorize_allowlisted_canary(
            planned["id"],
            actor="pytest-postgres",
            reason="explicit canary target confirmation",
            expected_version=planned["row_version"],
        )
        wake_hint = listener.wait(timeout_seconds=1.0)
    finally:
        listener.close()

    assert authorized is not None
    assert authorized.available_at is not None
    assert datetime.fromisoformat(authorized.available_at.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
    assert wake_hint is not None
    assert wake_hint.queue_kind == "external_effect"
    assert wake_hint.lane == "wecom_interactive"
    assert authorized.payload_json["execution_scope"] == "allowlisted_canary"
    assert authorized.payload_summary_json["canary_authorization"]["actor"] == "pytest-postgres"
    assert authorized.payload_summary_json["canary_authorization"]["authorized_job_id"] == planned["id"]
    assert (
        authorized.payload_summary_json["canary_authorization"]["authorized_from_version"]
        == planned["row_version"]
    )
    assert authorized.payload_summary_json["canary_authorization"]["duplicate_risk_confirmed"] is False
    assert authorized.row_version == planned["row_version"] + 1
    assert (
        service.authorize_allowlisted_canary(
            planned["id"],
            actor="pytest-postgres",
            reason="stale version must lose",
            expected_version=planned["row_version"],
        )
        is None
    )

    claimed = repository.acquire_job(planned["id"], locked_by="pytest-postgres")
    assert claimed is not None
    assert repository.begin_provider_attempt(job=claimed, request_summary={}) is not None
    current = repository.get_job(planned["id"])
    assert current is not None
    assert (
        service.authorize_allowlisted_canary(
            planned["id"],
            actor="pytest-postgres",
            reason="provider boundary must be irreversible",
            expected_version=current.row_version,
        )
        is None
    )
