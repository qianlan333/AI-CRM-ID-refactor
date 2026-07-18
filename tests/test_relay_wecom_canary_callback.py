from __future__ import annotations

import json
import time
import urllib.parse
from types import SimpleNamespace

import pytest

from scripts.ops import relay_wecom_canary_callback as relay


RELEASE_SHA = "a" * 40


def _row() -> dict:
    return {
        "id": 77,
        "route": relay.EXPECTED_ROUTE,
        "provider": "wecom",
        "event_family": "external_contact",
        "event_type": "change_external_contact",
        "change_type": "add_external_contact",
        "raw_query_json": {
            "timestamp": "1784349492",
            "nonce": "nonce-canary",
            "msg_signature": "b" * 40,
        },
        "raw_body": b"<xml>encrypted-callback</xml>",
        "payload_json": {
            "CreateTime": str(int(time.time())),
            "ExternalUserID": "external_canary",
            "UserID": "owner_canary",
            "State": "scene_canary",
            "WelcomeCode": "welcome-secret",
        },
    }


def test_plan_only_redacts_callback_identity_and_never_reads_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        relay,
        "wait_for_exact_callback",
        lambda *args, **kwargs: pytest.fail("plan-only relay must not read the database"),
    )

    assert (
        relay.main(
            [
                "--repository-path",
                "/srv/aicrm",
                "--expected-source-release-sha",
                RELEASE_SHA,
                "--target-url",
                relay.EXPECTED_TARGET_URL,
                "--external-userid",
                "external_canary",
                "--owner-userid",
                "owner_canary",
                "--state",
                "scene_canary",
                "--after-id",
                "76",
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["applied"] is False
    assert payload["provider_external_call_executed"] is False
    for secret_value in ("external_canary", "owner_canary", "scene_canary"):
        assert secret_value not in output


def test_callback_request_replays_only_the_original_signature_contract() -> None:
    request = relay._callback_request(_row(), target_url=relay.EXPECTED_TARGET_URL)
    parsed = urllib.parse.urlparse(request.full_url)
    query = urllib.parse.parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "id-dev.youcangogogo.com"
    assert parsed.path == relay.EXPECTED_ROUTE
    assert set(query) == relay.QUERY_FIELDS
    assert request.data == _row()["raw_body"]


def test_callback_relay_rejects_redirects_before_reposting_callback_body() -> None:
    handler = relay._RejectRedirectHandler()

    assert (
        handler.redirect_request(
            SimpleNamespace(),
            None,
            302,
            "redirect",
            {},
            "https://example.invalid/callback",
        )
        is None
    )


def test_wait_for_exact_callback_returns_one_fresh_row_without_mutation() -> None:
    calls: list[tuple[str, tuple]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, statement, parameters):
            calls.append((" ".join(str(statement).split()), tuple(parameters)))
            return SimpleNamespace(fetchall=lambda: [_row()])

    result = relay.wait_for_exact_callback(
        "postgresql://source",
        after_id=76,
        external_userid="external_canary",
        owner_userid="owner_canary",
        state="scene_canary",
        timeout_seconds=1,
        poll_seconds=0.02,
        maximum_event_age_seconds=10,
        connect=lambda _url: Connection(),
    )

    assert result["id"] == 77
    assert calls
    assert "UPDATE" not in calls[0][0]
    assert calls[0][1] == (
        76,
        relay.EXPECTED_ROUTE,
        "external_canary",
        "owner_canary",
        "scene_canary",
    )


def test_relay_accepts_one_200_ack_and_outputs_only_hashes_and_counts() -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self, _limit):
            return b"<xml>encrypted-success</xml>"

    result = relay.relay_callback(
        _row(),
        target_url=relay.EXPECTED_TARGET_URL,
        open_url=lambda request, timeout: Response(),
    )

    assert result["http_status"] == 200
    assert result["callback_relay_executed"] is True
    assert result["provider_external_call_executed"] is False
    assert len(result["ack_body_sha256"]) == 64
    serialized = json.dumps(result, sort_keys=True)
    for secret_value in ("welcome-secret", "nonce-canary", "encrypted-callback"):
        assert secret_value not in serialized


def test_relay_rejects_stale_callbacks_before_any_http_request() -> None:
    row = _row()
    row["payload_json"]["CreateTime"] = "1"

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def execute(self, _statement, _parameters):
            return SimpleNamespace(fetchall=lambda: [row])

    with pytest.raises(relay.CallbackRelayError, match="real-time relay window"):
        relay.wait_for_exact_callback(
            "postgresql://source",
            after_id=0,
            external_userid="external_canary",
            owner_userid="owner_canary",
            state="scene_canary",
            timeout_seconds=1,
            poll_seconds=0.02,
            maximum_event_age_seconds=10,
            connect=lambda _url: Connection(),
        )
