from __future__ import annotations

from time import time

from aicrm_next.questionnaire.result_access import (
    issue_questionnaire_result_grant,
    result_grant_cookie_name,
    validate_questionnaire_result_grant,
)


def test_result_grant_is_bound_to_slug_and_random_result_token(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "questionnaire-result-grant")
    now = int(time())
    grant = issue_questionnaire_result_grant(
        slug="hxc-activation-v1",
        result_access_token="result-token-a",
        now=now,
    )

    assert grant.cookie_name == result_grant_cookie_name("result-token-a")
    assert validate_questionnaire_result_grant(
        grant.cookie_value,
        slug="hxc-activation-v1",
        result_access_token="result-token-a",
        now=now,
    )
    assert not validate_questionnaire_result_grant(
        grant.cookie_value,
        slug="other-questionnaire",
        result_access_token="result-token-a",
        now=now,
    )
    assert not validate_questionnaire_result_grant(
        grant.cookie_value,
        slug="hxc-activation-v1",
        result_access_token="result-token-b",
        now=now,
    )


def test_result_grant_rejects_tampering_and_expiry(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "questionnaire-result-grant-expiry")
    now = int(time())
    grant = issue_questionnaire_result_grant(
        slug="hxc-activation-v1",
        result_access_token="result-token-expiring",
        now=now,
        ttl_seconds=60,
    )

    assert not validate_questionnaire_result_grant(
        f"{grant.cookie_value}tampered",
        slug="hxc-activation-v1",
        result_access_token="result-token-expiring",
        now=now,
        ttl_seconds=60,
    )
    assert not validate_questionnaire_result_grant(
        grant.cookie_value,
        slug="hxc-activation-v1",
        result_access_token="result-token-expiring",
        now=now + 61,
        ttl_seconds=60,
    )
