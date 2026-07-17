from __future__ import annotations

import pytest

from scripts.ops import run_test_loopback_canary


def test_loopback_canary_plan_is_redacted_and_does_not_touch_runtime(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        run_test_loopback_canary,
        "raw_database_url",
        lambda: pytest.fail("plan-only mode must not read runtime database settings"),
    )

    assert (
        run_test_loopback_canary.main(
            [
                "--base-url",
                "https://id-dev.example.test",
                "--run-id",
                "loopback-001",
                "--expected-release-sha",
                "a" * 40,
                "--generation",
                "17",
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
    assert "test-receiver" not in output


@pytest.mark.parametrize(
    "url",
    (
        "http://id-dev.example.test",
        "https://user:password@id-dev.example.test",
        "https://id-dev.example.test/path",
        "https://id-dev.example.test?target=other",
    ),
)
def test_loopback_canary_rejects_non_origin_https_base_urls(url: str) -> None:
    with pytest.raises(ValueError, match="origin-only HTTPS"):
        run_test_loopback_canary._request_for_base_url(url)


def test_loopback_request_never_accepts_a_caller_supplied_receiver_path() -> None:
    request = run_test_loopback_canary._request_for_base_url("https://id-dev.example.test")

    assert request.url.scheme == "https"
    assert request.headers["host"] == "id-dev.example.test"
    assert request.url.path == "/api/admin/external-effects/test-loopback/jobs"
