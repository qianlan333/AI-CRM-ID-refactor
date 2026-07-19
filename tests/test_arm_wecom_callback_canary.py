from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from aicrm_next.platform_foundation.external_effects.models import ExternalEffectJob
from scripts.ops import arm_wecom_callback_canary as arm


RELEASE_SHA = "a" * 40
SOURCE_SHA = "b" * 40
POLICY_VERSION = "queue-v2-allowlisted-canary"


def _write_private(tmp_path, name: str, payload: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _spec() -> dict:
    return {
        "external_userids": ["external_canary"],
        "owner_userids": ["owner_canary"],
        "group_webhook_keys": [],
        "group_chat_ids": ["chat_canary"],
        "media_targets": ["image:7:image"],
        "enabled_effect_types": [
            "wecom.welcome_message.send",
            "wecom.contact.tag.mark",
            "wecom.external_contact.detail.fetch",
        ],
    }


def _asset() -> dict:
    return {
        "channel_name": "ID validation channel",
        "channel_code": "id_validation_canary",
        "scene_value": "scene_canary",
        "config_id": "config_canary",
        "qr_url": "https://wework.qpic.cn/wwpic3az/test/0",
        "qr_image_sha256": "c" * 64,
        "owner_userid": "owner_canary",
        "tag_id": "tag_canary",
        "tag_name": "Canary tag",
        "tag_group_name": "Canary group",
        "welcome_message": "ID validation welcome",
        "source_repository": "qianlan333/AI-CRM",
        "source_release_sha": SOURCE_SHA,
    }


def _inbox_row(*, status: str = "received") -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": 91,
        "status": status,
        "processing_summary_json": {
            "handled": True,
            "event_log_id": 42,
            "external_effect_job_ids": [11, 12, 13],
        },
        "payload_json": {
            "CreateTime": str(int(now.timestamp())),
            "WelcomeCode": "welcome-secret",
        },
        "received_at": now.isoformat(),
        "started_at": now.isoformat(),
        "execution_id": "exe_callback_canary",
        "policy_version": POLICY_VERSION,
        "duplicate_count": 0,
        "attempt_count": 0,
        "worker_generation": 1,
    }


def test_plan_only_redacts_every_private_callback_target(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        arm,
        "raw_database_url",
        lambda: pytest.fail("plan-only arm must not read the runtime database"),
    )

    assert (
        arm.main(
            [
                "--spec-file",
                _write_private(tmp_path, "spec.json", _spec()),
                "--asset-file",
                _write_private(tmp_path, "asset.json", _asset()),
                "--expected-release-sha",
                RELEASE_SHA,
                "--generation",
                "1",
                "--expected-policy-version",
                POLICY_VERSION,
                "--actor",
                "pytest",
                "--reason",
                "plan only",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["applied"] is False
    assert payload["target_values_redacted"] is True
    for private_value in (
        "external_canary",
        "owner_canary",
        "scene_canary",
        "tag_canary",
        "ID validation welcome",
    ):
        assert private_value not in output


def test_wait_for_callback_requires_one_exact_fresh_policy_bound_row() -> None:
    row = _inbox_row()
    calls: list[tuple] = []

    class Connection:
        autocommit = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, _statement, parameters):
            calls.append(tuple(parameters))
            return SimpleNamespace(fetchall=lambda: [row])

    result = arm.wait_for_callback(
        "postgresql://canary",
        baseline_id=90,
        corp_id="corp_canary",
        external_userid="external_canary",
        owner_userid="owner_canary",
        state="scene_canary",
        policy_version=POLICY_VERSION,
        timeout_seconds=1,
        maximum_event_age_seconds=12,
        connect=lambda _url: Connection(),
    )

    assert result["id"] == 91
    assert calls == [
        (
            90,
            arm.EXPECTED_ROUTE,
            "corp_canary",
            "external_canary",
            "owner_canary",
            "scene_canary",
        )
    ]


def test_single_callback_recheck_rejects_a_late_second_match() -> None:
    rows = [_inbox_row(), {**_inbox_row(), "id": 92}]

    class Connection:
        autocommit = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, _statement, _parameters):
            return SimpleNamespace(fetchall=lambda: rows)

    with pytest.raises(arm.CallbackCanaryError, match="exactly one matching callback"):
        arm.assert_single_callback(
            "postgresql://canary",
            baseline_id=90,
            inbox_id=91,
            corp_id="corp_canary",
            external_userid="external_canary",
            owner_userid="owner_canary",
            state="scene_canary",
            connect=lambda _url: Connection(),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("duplicate_count", 1),
        ("attempt_count", 1),
        ("started_at", ""),
        ("worker_generation", 2),
    ),
)
def test_clean_worker_processing_rejects_duplicate_retry_or_wrong_generation(
    field: str,
    value: object,
) -> None:
    inbox = _inbox_row(status="succeeded")
    inbox[field] = value

    with pytest.raises(arm.CallbackCanaryError, match="one clean runtime claim"):
        arm._assert_clean_worker_processing(inbox, generation=1)


def test_freeze_jobs_rejects_a_historical_relationship_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        @staticmethod
        def transaction():
            return nullcontext()

        @staticmethod
        def execute(_statement, _parameters):
            rows = [
                {
                    "id": job_id,
                    "source_event_id": "41" if job_id == 12 else "42",
                    "status": "succeeded" if job_id == 12 else "queued",
                    "attempt_count": 1 if job_id == 12 else 0,
                    "provider_call_started_at": "2026-07-18T00:00:00Z" if job_id == 12 else None,
                    "cancel_requested_at": None,
                }
                for job_id in (11, 12, 13)
            ]
            return SimpleNamespace(fetchall=lambda: rows)

    monkeypatch.setattr(arm, "open_runtime_connection", lambda _url: Connection())

    with pytest.raises(arm.CallbackCanaryError, match="historical relationship job"):
        arm._freeze_jobs(
            "postgresql://canary",
            job_ids=[11, 12, 13],
            event_log_id=42,
        )


def test_job_map_requires_exact_welcome_tag_and_detail_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = {
        11: ExternalEffectJob(
            id=11,
            effect_type="wecom.welcome_message.send",
            policy_version=POLICY_VERSION,
            max_attempts=1,
            payload_json={
                "external_userid": "external_canary",
                "follow_user_userid": "owner_canary",
                "welcome_code": "welcome-secret",
                "scene_value": "scene_canary",
                "text": {"content": "ID validation welcome"},
            },
        ),
        12: ExternalEffectJob(
            id=12,
            effect_type="wecom.contact.tag.mark",
            policy_version=POLICY_VERSION,
            max_attempts=1,
            payload_json={
                "external_userid": "external_canary",
                "follow_user_userid": "owner_canary",
                "add_tags": ["tag_canary"],
                "remove_tags": [],
            },
        ),
        13: ExternalEffectJob(
            id=13,
            effect_type="wecom.external_contact.detail.fetch",
            policy_version=POLICY_VERSION,
            max_attempts=1,
            payload_json={
                "external_userid": "external_canary",
                "owner_userid": "owner_canary",
            },
        ),
    }

    class Repository:
        def get_job(self, job_id: int):
            return jobs.get(job_id)

    monkeypatch.setattr(arm, "wecom_canary_job_gate_error", lambda job, authorize_scope: "")
    result = arm._job_map(
        Repository(),
        job_ids=[11, 12, 13],
        external_userid="external_canary",
        owner_userid="owner_canary",
        asset={key: str(value) for key, value in _asset().items()},
        policy_version=POLICY_VERSION,
    )

    assert set(result) == {"welcome", "entry_tag", "identity_detail"}
    assert result["welcome"].id == 11

    jobs[11].payload_json["attachments"] = [{"msgtype": "image", "media_id": "unreviewed-media"}]
    with pytest.raises(arm.CallbackCanaryError, match="welcome job does not match"):
        arm._job_map(
            Repository(),
            job_ids=[11, 12, 13],
            external_userid="external_canary",
            owner_userid="owner_canary",
            asset={key: str(value) for key, value in _asset().items()},
            policy_version=POLICY_VERSION,
        )


def test_apply_authorizes_welcome_before_other_effects_and_records_all_evidence(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = datetime.now(timezone.utc)
    inbox = _inbox_row(status="succeeded")
    jobs = {
        "welcome": SimpleNamespace(id=11, effect_type="wecom.welcome_message.send", row_version=2),
        "entry_tag": SimpleNamespace(id=12, effect_type="wecom.contact.tag.mark", row_version=2),
        "identity_detail": SimpleNamespace(
            id=13,
            effect_type="wecom.external_contact.detail.fetch",
            row_version=2,
        ),
    }
    authorization_order: list[str] = []
    repository = SimpleNamespace()

    monkeypatch.setenv(arm.AUTHORIZATION_ENV, "1")
    monkeypatch.setattr(arm, "current_release_sha", lambda: RELEASE_SHA)
    monkeypatch.setattr(arm, "raw_database_url", lambda: "postgresql://canary")
    monkeypatch.setattr(arm, "_runtime_preflight", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        arm,
        "load_wecom_execution_config",
        lambda: SimpleNamespace(
            execution_mode="execute",
            real_calls_enabled=True,
            enabled_effect_types=set(arm.EXPECTED_EFFECTS.values()),
        ),
    )
    monkeypatch.setattr(arm, "callback_config", lambda: {"corp_id": "corp_canary"})
    monkeypatch.setattr(arm, "_assert_channel_asset", lambda *args, **kwargs: {"id": 1})
    monkeypatch.setattr(arm, "_baseline_inbox_id", lambda _url: 90)
    monkeypatch.setattr(arm, "wait_for_callback", lambda *args, **kwargs: inbox)
    monkeypatch.setattr(arm, "wait_for_inbox_success", lambda *args, **kwargs: inbox)
    monkeypatch.setattr(arm, "_freeze_jobs", lambda *args, **kwargs: None)
    callback_rechecks: list[int] = []

    def assert_single(_database_url, **kwargs):
        callback_rechecks.append(int(kwargs["inbox_id"]))
        return inbox

    monkeypatch.setattr(arm, "assert_single_callback", assert_single)
    monkeypatch.setattr(arm, "SQLAlchemyExternalEffectRepository", lambda: repository)
    monkeypatch.setattr(arm, "ExternalEffectService", lambda _repo: SimpleNamespace())
    monkeypatch.setattr(arm, "_job_map", lambda *args, **kwargs: jobs)

    def authorize(_service, job, **_kwargs):
        authorization_order.append(job.effect_type)
        return job

    monkeypatch.setattr(arm, "_authorize_job", authorize)
    monkeypatch.setattr(
        arm,
        "wait_for_provider_boundary",
        lambda *args, **kwargs: SimpleNamespace(provider_call_started_at=now.isoformat()),
    )

    def completed(_repository, *, job_id: int, timeout_seconds: float):
        del _repository, timeout_seconds
        effect_type = next(job.effect_type for job in jobs.values() if job.id == job_id)
        return (
            SimpleNamespace(
                id=job_id,
                effect_type=effect_type,
                execution_id=f"exe_{job_id}",
                side_effect_executed=True,
            ),
            [SimpleNamespace()],
        )

    monkeypatch.setattr(arm, "wait_for_result", completed)
    monkeypatch.setattr(
        arm,
        "record_external_effect_evidence",
        lambda _url, *, job, **_kwargs: {
            "job_id": job.id,
            "status": "passed",
            "side_effect_executed": True,
        },
    )

    assert (
        arm.main(
            [
                "--spec-file",
                _write_private(tmp_path, "spec.json", _spec()),
                "--asset-file",
                _write_private(tmp_path, "asset.json", _asset()),
                "--expected-release-sha",
                RELEASE_SHA,
                "--generation",
                "1",
                "--expected-policy-version",
                POLICY_VERSION,
                "--actor",
                "pytest",
                "--reason",
                "real-time canary",
                "--apply",
                "--confirmation",
                "ARM_WECOM_CALLBACK_CANARY_1",
            ]
        )
        == 0
    )

    assert authorization_order == [
        "wecom.welcome_message.send",
        "wecom.external_contact.detail.fetch",
        "wecom.contact.tag.mark",
    ]
    output = json.loads(capsys.readouterr().out)
    assert output["ok"] is True
    assert output["job_count"] == 3
    assert len(output["evidence"]) == 3
    assert output["target_values_redacted"] is True
    assert "welcome-secret" not in json.dumps(output)
    assert callback_rechecks == [91, 91]
