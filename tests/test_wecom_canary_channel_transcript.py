from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

import scripts.ops.import_wecom_canary_channel_asset as channel_import
import scripts.ops.ingest_wecom_canary_callback as callback_ingest


RELEASE_SHA = "a" * 40
SOURCE_SHA = "b" * 40


def _write_private(tmp_path, name: str, payload: dict) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)
    return str(path)


def _asset() -> dict:
    return {
        "channel_name": "ID validation channel",
        "channel_code": "id_validation_20260718_ffe00315",
        "scene_value": "idv_260718_ffe00315",
        "config_id": "12622aca4e711395368fadcdce55d830",
        "qr_url": "https://wework.qpic.cn/wwpic3az/test/0",
        "qr_image_sha256": "c" * 64,
        "owner_userid": "owner_canary",
        "tag_id": "tag_canary_001",
        "tag_name": "Disposable canary tag",
        "tag_group_name": "ID validation tags",
        "welcome_message": "ID validation welcome",
        "source_repository": "qianlan333/AI-CRM",
        "source_release_sha": SOURCE_SHA,
    }


def _spec() -> dict:
    return {
        "external_userids": ["external_canary"],
        "owner_userids": ["owner_canary"],
        "group_webhook_keys": [],
        "group_chat_ids": ["chat_canary"],
        "media_targets": ["image:7:image"],
        "enabled_effect_types": [
            "wecom.message.private.send",
            "wecom.message.group.send",
            "wecom.welcome_message.send",
            "wecom.contact.tag.mark",
            "wecom.contact.tag.unmark",
            "wecom.profile.update",
            "wecom.external_contact.detail.fetch",
            "wecom.media.upload",
        ],
    }


def _callback() -> dict:
    event_data = {
        "ToUserName": "corp_canary",
        "CreateTime": str(int(time.time())),
        "Event": "change_external_contact",
        "ChangeType": "add_external_contact",
        "UserID": "owner_canary",
        "ExternalUserID": "external_canary",
        "State": "idv_260718_ffe00315",
        "WelcomeCode": "welcome_canary_secret",
    }
    return {
        "event_data": event_data,
        "source": {
            "repository": "qianlan333/AI-CRM",
            "release_sha": SOURCE_SHA,
            "event_log_id": 77,
            "event_payload_sha256": callback_ingest._event_hash(event_data),
            "received_at": "2026-07-18T04:00:00+00:00",
        },
    }


def test_channel_import_plan_is_exact_owner_bound_and_redacted(tmp_path, capsys) -> None:
    asset = _asset()
    assert (
        channel_import.main(
            [
                "--asset-file",
                _write_private(tmp_path, "asset.json", asset),
                "--spec-file",
                _write_private(tmp_path, "spec.json", _spec()),
                "--expected-release-sha",
                RELEASE_SHA,
                "--generation",
                "1",
                "--expected-policy-version",
                "queue-v2-test-loopback",
                "--actor",
                "pytest",
                "--reason",
                "plan only",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"applied": false' in output
    assert '"target_values_redacted": true' in output
    for value in asset.values():
        assert str(value) not in output


def test_callback_transcript_plan_binds_real_source_and_redacts_provider_fields(tmp_path, monkeypatch, capsys) -> None:
    callback = _callback()
    monkeypatch.setattr(callback_ingest, "callback_config", lambda: {"corp_id": "corp_canary"})

    assert (
        callback_ingest.main(
            [
                "--event-file",
                _write_private(tmp_path, "event.json", callback),
                "--asset-file",
                _write_private(tmp_path, "asset.json", _asset()),
                "--spec-file",
                _write_private(tmp_path, "spec.json", _spec()),
                "--expected-release-sha",
                RELEASE_SHA,
                "--generation",
                "1",
                "--expected-policy-version",
                "queue-v2-test-loopback",
                "--actor",
                "pytest",
                "--reason",
                "plan only",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"authorization_required": true' in output
    assert callback["source"]["event_payload_sha256"] in output
    assert SOURCE_SHA in output
    for value in callback["event_data"].values():
        assert str(value) not in output


def test_callback_transcript_rejects_fingerprint_or_target_drift(tmp_path, monkeypatch) -> None:
    callback = _callback()
    callback["source"]["event_payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        callback_ingest.load_callback_event(_write_private(tmp_path, "bad-event.json", callback))

    callback = _callback()
    loaded = callback_ingest.load_callback_event(_write_private(tmp_path, "event.json", callback))
    monkeypatch.setattr(callback_ingest, "callback_config", lambda: {"corp_id": "corp_canary"})
    asset = _asset()
    asset["owner_userid"] = "other_owner"
    with pytest.raises(ValueError, match="owner"):
        callback_ingest._validate_event(
            loaded,
            asset=asset,
            canary_spec={key: tuple(value) for key, value in _spec().items()},
        )


def test_callback_jobs_remain_unattempted_and_require_separate_authorization(monkeypatch) -> None:
    jobs = {
        11: SimpleNamespace(
            id=11,
            effect_type="wecom.external_contact.detail.fetch",
            execution_id="exe_detail",
            row_version=3,
            status="queued",
            provider_call_started_at="",
            attempt_count=0,
            max_attempts=1,
            side_effect_executed=False,
            payload_json={},
        ),
        12: SimpleNamespace(
            id=12,
            effect_type="wecom.welcome_message.send",
            execution_id="exe_welcome",
            row_version=4,
            status="queued",
            provider_call_started_at="",
            attempt_count=0,
            max_attempts=1,
            side_effect_executed=False,
            payload_json={},
        ),
        13: SimpleNamespace(
            id=13,
            effect_type="wecom.contact.tag.mark",
            execution_id="exe_tag",
            row_version=5,
            status="queued",
            provider_call_started_at="",
            attempt_count=0,
            max_attempts=1,
            side_effect_executed=False,
            payload_json={},
        ),
    }

    class Repository:
        def get_job(self, job_id: int):
            return jobs.get(job_id)

    monkeypatch.setattr(callback_ingest, "SQLAlchemyExternalEffectRepository", Repository)
    result = callback_ingest._job_metadata(
        {
            "identity_sync": {"external_effect_job_id": 11},
            "entry_result": {
                "welcome_message": {"external_effect_job_id": 12},
                "entry_tag": {"external_effect_job_id": 13},
            },
        }
    )
    assert [item["job_id"] for item in result] == [11, 12, 13]
    assert [item["row_version"] for item in result] == [3, 4, 5]
