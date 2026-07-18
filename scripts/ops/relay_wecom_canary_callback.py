#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


AUTHORIZATION_ENV = "AICRM_WECOM_CANARY_CALLBACK_RELAY_AUTHORIZED"
EXPECTED_SOURCE_REPOSITORY = "qianlan333/AI-CRM"
EXPECTED_TARGET_URL = "https://id-dev.youcangogogo.com/wecom/external-contact/callback"
EXPECTED_ROUTE = "/wecom/external-contact/callback"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9_@.:-]{1,256}\Z")
QUERY_FIELDS = frozenset({"timestamp", "nonce", "msg_signature"})


class CallbackRelayError(RuntimeError):
    """Stable error that never includes callback ciphertext or query secrets."""


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ARG002
        return None


_EXACT_TARGET_OPENER = urllib.request.build_opener(_RejectRedirectHandler())


def _open_exact_target(request: urllib.request.Request, *, timeout: float):
    return _EXACT_TARGET_OPENER.open(request, timeout=timeout)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=("Relay one exact durable AI-CRM WeCom callback to the ID-validation callback ingress without calling WeCom."))
    parser.add_argument("--repository-path", required=True)
    parser.add_argument("--expected-source-release-sha", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--external-userid", required=True)
    parser.add_argument("--owner-userid", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--after-id", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    parser.add_argument("--maximum-event-age-seconds", type=float, default=10.0)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirmation", default="")
    return parser.parse_args(argv)


def _confirmation(after_id: int) -> str:
    return f"RELAY_WECOM_CANARY_CALLBACK_AFTER_{int(after_id)}"


def _validated_identifier(value: str, *, field: str) -> str:
    normalized = str(value or "").strip()
    if SAFE_IDENTIFIER.fullmatch(normalized) is None:
        raise ValueError(f"invalid {field}")
    return normalized


def _git(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise CallbackRelayError("source repository attestation failed")
    return result.stdout.strip()


def verify_source_checkout(
    repository_path: str,
    *,
    expected_release_sha: str,
) -> dict[str, Any]:
    path = Path(str(repository_path or "")).expanduser().resolve()
    if not path.is_dir() or FULL_SHA.fullmatch(expected_release_sha) is None:
        raise CallbackRelayError("source repository identity is invalid")
    origin = _git(path, "remote", "get-url", "origin")
    allowed_origins = {
        f"https://github.com/{EXPECTED_SOURCE_REPOSITORY}",
        f"https://github.com/{EXPECTED_SOURCE_REPOSITORY}.git",
        f"git@github.com:{EXPECTED_SOURCE_REPOSITORY}",
        f"git@github.com:{EXPECTED_SOURCE_REPOSITORY}.git",
    }
    if origin not in allowed_origins:
        raise CallbackRelayError("source checkout is not the AI-CRM repository")
    if _git(path, "rev-parse", "HEAD") != expected_release_sha:
        raise CallbackRelayError("source checkout release SHA mismatch")
    marker = path / ".release-sha"
    if marker.is_symlink() or not marker.is_file():
        raise CallbackRelayError("source release marker is missing")
    if marker.read_text(encoding="utf-8").strip() != expected_release_sha:
        raise CallbackRelayError("source release marker mismatch")
    return {
        "repository": EXPECTED_SOURCE_REPOSITORY,
        "release_sha": expected_release_sha,
    }


def _connect(database_url: str):
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(database_url, row_factory=dict_row, autocommit=True)


def _event_age_seconds(row: dict[str, Any]) -> float:
    payload = dict(row.get("payload_json") or {})
    try:
        created_at = datetime.fromtimestamp(
            int(str(payload.get("CreateTime") or "0")),
            tz=timezone.utc,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise CallbackRelayError("source callback provider timestamp is invalid") from exc
    return (datetime.now(timezone.utc) - created_at).total_seconds()


def wait_for_exact_callback(
    database_url: str,
    *,
    after_id: int,
    external_userid: str,
    owner_userid: str,
    state: str,
    timeout_seconds: float,
    poll_seconds: float,
    maximum_event_age_seconds: float,
    connect: Callable[[str], Any] = _connect,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    deadline = monotonic() + max(1.0, min(float(timeout_seconds), 1800.0))
    poll = max(0.02, min(float(poll_seconds), 1.0))
    with connect(database_url) as connection:
        while monotonic() < deadline:
            rows = connection.execute(
                """
                SELECT id, route, provider, event_family, event_type, change_type,
                       raw_query_json, raw_body, payload_json, received_at
                FROM webhook_inbox
                WHERE id > %s
                  AND provider = 'wecom'
                  AND event_family = 'external_contact'
                  AND route = %s
                  AND event_type = 'change_external_contact'
                  AND change_type = 'add_external_contact'
                  AND payload_json->>'ExternalUserID' = %s
                  AND payload_json->>'UserID' = %s
                  AND payload_json->>'State' = %s
                  AND COALESCE(payload_json->>'WelcomeCode', '') <> ''
                ORDER BY id ASC
                LIMIT 2
                """,
                (
                    int(after_id),
                    EXPECTED_ROUTE,
                    external_userid,
                    owner_userid,
                    state,
                ),
            ).fetchall()
            if len(rows) > 1:
                raise CallbackRelayError("more than one matching callback arrived after the armed boundary")
            if rows:
                row = dict(rows[0])
                age_seconds = _event_age_seconds(row)
                if age_seconds < -5.0 or age_seconds > maximum_event_age_seconds:
                    raise CallbackRelayError("matching callback is outside the real-time relay window")
                return row
            sleep(poll)
    raise CallbackRelayError("no matching callback arrived before the relay timeout")


def _callback_request(row: dict[str, Any], *, target_url: str) -> urllib.request.Request:
    query = row.get("raw_query_json")
    if not isinstance(query, dict) or not QUERY_FIELDS.issubset(query):
        raise CallbackRelayError("source callback query contract is incomplete")
    exact_query = {field: str(query.get(field) or "").strip() for field in QUERY_FIELDS}
    if (
        not exact_query["timestamp"].isdigit()
        or not exact_query["nonce"]
        or len(exact_query["nonce"]) > 256
        or re.fullmatch(r"[0-9a-fA-F]{40}", exact_query["msg_signature"]) is None
    ):
        raise CallbackRelayError("source callback query contract is invalid")
    raw_body = row.get("raw_body")
    if isinstance(raw_body, memoryview):
        raw_body = raw_body.tobytes()
    if not isinstance(raw_body, bytes) or not raw_body or len(raw_body) > 1024 * 1024:
        raise CallbackRelayError("source callback ciphertext body is invalid")
    target = target_url + "?" + urllib.parse.urlencode(exact_query)
    return urllib.request.Request(
        target,
        data=raw_body,
        method="POST",
        headers={
            "Content-Type": "application/xml",
            "User-Agent": "aicrm-id-validation-callback-relay/1",
        },
    )


def relay_callback(
    row: dict[str, Any],
    *,
    target_url: str,
    open_url: Callable[..., Any] = _open_exact_target,
) -> dict[str, Any]:
    request = _callback_request(row, target_url=target_url)
    started = time.monotonic()
    try:
        with open_url(request, timeout=10.0) as response:  # noqa: S310 - exact guarded URL
            response_body = response.read(65537)
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raise CallbackRelayError(f"ID-validation callback ingress returned HTTP {int(exc.code)}") from None
    except (OSError, urllib.error.URLError) as exc:
        raise CallbackRelayError("ID-validation callback ingress was unavailable") from exc
    if status != 200 or not response_body or len(response_body) > 65536:
        raise CallbackRelayError("ID-validation callback ingress acknowledgement was invalid")
    return {
        "source_inbox_id": int(row.get("id") or 0),
        "http_status": status,
        "ack_body_sha256": hashlib.sha256(response_body).hexdigest(),
        "relay_elapsed_ms": int((time.monotonic() - started) * 1000),
        "callback_relay_executed": True,
        "provider_external_call_executed": False,
        "target_values_redacted": True,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    release_sha = str(args.expected_source_release_sha or "").strip()
    external_userid = _validated_identifier(args.external_userid, field="external_userid")
    owner_userid = _validated_identifier(args.owner_userid, field="owner_userid")
    state = _validated_identifier(args.state, field="state")
    if str(args.target_url or "").strip() != EXPECTED_TARGET_URL:
        raise ValueError("target URL must be the exact ID-validation callback ingress")
    if FULL_SHA.fullmatch(release_sha) is None or int(args.after_id) < 0:
        raise ValueError("source release SHA and after-id are required")
    plan = {
        "ok": True,
        "applied": False,
        "source_repository": EXPECTED_SOURCE_REPOSITORY,
        "source_release_sha": release_sha,
        "after_id": int(args.after_id),
        "target_values_redacted": True,
        "callback_relay_executed": False,
        "provider_external_call_executed": False,
    }
    if not args.apply:
        print(json.dumps(plan, sort_keys=True))
        return 0
    if str(os.getenv(AUTHORIZATION_ENV) or "").strip() != "1":
        raise CallbackRelayError(f"{AUTHORIZATION_ENV}=1 is required")
    if str(args.confirmation or "").strip() != _confirmation(args.after_id):
        raise CallbackRelayError(f"--confirmation must equal {_confirmation(args.after_id)}")
    verify_source_checkout(
        args.repository_path,
        expected_release_sha=release_sha,
    )
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise CallbackRelayError("source PostgreSQL DATABASE_URL is required")
    row = wait_for_exact_callback(
        database_url,
        after_id=int(args.after_id),
        external_userid=external_userid,
        owner_userid=owner_userid,
        state=state,
        timeout_seconds=float(args.timeout_seconds),
        poll_seconds=float(args.poll_seconds),
        maximum_event_age_seconds=float(args.maximum_event_age_seconds),
    )
    result = relay_callback(row, target_url=EXPECTED_TARGET_URL)
    print(json.dumps({**plan, **result, "applied": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CallbackRelayError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
