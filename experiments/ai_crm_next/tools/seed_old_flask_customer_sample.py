#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg.types.json import Jsonb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
REQUIRED_DATABASE = "aicrm_old_flask_test"

SAMPLE = {
    "external_userid": "external_user_masked_001",
    "customer_name": "customer_masked_001",
    "mobile": "mobile_masked_001",
    "owner_userid": "owner_masked_001",
    "tag_id": "tag_masked_001",
    "tag_name": "tag_masked_001",
    "msgid": "msg_masked_001",
    "corp_id": "corp_masked_test",
    "unionid": "unionid_masked_001",
    "openid": "openid_masked_001",
}


@dataclass(frozen=True)
class SafeDatabaseUrl:
    raw_url: str
    redacted_url: str
    host: str
    database_name: str


def redact_database_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    netloc = host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username:
        netloc = f"{quote(parsed.username)}:***@{netloc}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def validate_database_url(url: str) -> SafeDatabaseUrl:
    if not url:
        raise ValueError("database URL is required")
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    database_name = parsed.path.lstrip("/")
    if parsed.scheme not in {"postgresql", "postgresql+psycopg", "postgres"}:
        raise ValueError(f"unsupported database URL scheme: {parsed.scheme}")
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"refusing non-local database host: {host}")
    if database_name != REQUIRED_DATABASE:
        raise ValueError(f"refusing database {database_name!r}; expected {REQUIRED_DATABASE!r}")
    if "test" not in database_name:
        raise ValueError(f"refusing database without test marker: {database_name}")
    return SafeDatabaseUrl(
        raw_url=url,
        redacted_url=redact_database_url(url),
        host=host,
        database_name=database_name,
    )


def _now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def seed_sample(database_url: str, *, apply: bool) -> dict[str, object]:
    safe_url = validate_database_url(database_url)
    plan = {
        "database": safe_url.database_name,
        "host": safe_url.host,
        "redacted_url": safe_url.redacted_url,
        "apply": apply,
        "sample": {
            "external_userid": SAMPLE["external_userid"],
            "customer_name": SAMPLE["customer_name"],
            "mobile": SAMPLE["mobile"],
            "owner_userid": SAMPLE["owner_userid"],
            "tag": SAMPLE["tag_name"],
            "msgid": SAMPLE["msgid"],
        },
        "tables": [
            "people",
            "contacts",
            "external_contact_bindings",
            "wecom_external_contact_identity_map",
            "wecom_external_contact_follow_users",
            "owner_role_map",
            "class_user_status_current",
            "class_user_status_history",
            "archived_messages",
        ],
    }
    if not apply:
        return {"ok": True, "dry_run": True, **plan}

    now = _now_text()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO people (mobile, third_party_user_id, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (mobile) DO UPDATE SET
                    third_party_user_id = EXCLUDED.third_party_user_id,
                    updated_at = NOW()
                RETURNING id
                """,
                (SAMPLE["mobile"], "third_party_user_masked_001"),
            )
            person_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (external_userid) DO UPDATE SET
                    customer_name = EXCLUDED.customer_name,
                    owner_userid = EXCLUDED.owner_userid,
                    remark = EXCLUDED.remark,
                    description = EXCLUDED.description,
                    updated_at = NOW()
                """,
                (
                    SAMPLE["external_userid"],
                    SAMPLE["customer_name"],
                    SAMPLE["owner_userid"],
                    "remark_masked_001",
                    "description_masked_001",
                ),
            )
            cur.execute(
                """
                INSERT INTO external_contact_bindings (
                    external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (external_userid) DO UPDATE SET
                    person_id = EXCLUDED.person_id,
                    first_bound_by_userid = EXCLUDED.first_bound_by_userid,
                    first_owner_userid = EXCLUDED.first_owner_userid,
                    last_owner_userid = EXCLUDED.last_owner_userid,
                    updated_at = NOW()
                """,
                (
                    SAMPLE["external_userid"],
                    person_id,
                    SAMPLE["owner_userid"],
                    SAMPLE["owner_userid"],
                    SAMPLE["owner_userid"],
                ),
            )
            cur.execute(
                """
                INSERT INTO wecom_external_contact_identity_map (
                    corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, NOW())
                ON CONFLICT (corp_id, external_userid) DO UPDATE SET
                    unionid = EXCLUDED.unionid,
                    openid = EXCLUDED.openid,
                    follow_user_userid = EXCLUDED.follow_user_userid,
                    name = EXCLUDED.name,
                    status = 'active',
                    raw_profile = EXCLUDED.raw_profile,
                    updated_at = NOW()
                """,
                (
                    SAMPLE["corp_id"],
                    SAMPLE["external_userid"],
                    SAMPLE["unionid"],
                    SAMPLE["openid"],
                    SAMPLE["owner_userid"],
                    SAMPLE["customer_name"],
                    Jsonb({"source": "aicrm_next_local_masked_seed"}),
                ),
            )
            cur.execute(
                """
                INSERT INTO wecom_external_contact_follow_users (
                    corp_id, external_userid, user_id, relation_status, is_primary, remark, description, add_way,
                    oper_userid, createtime, raw_follow_user, updated_at
                )
                VALUES (%s, %s, %s, 'active', TRUE, %s, %s, 0, %s, 1800000000, %s, NOW())
                ON CONFLICT (corp_id, external_userid, user_id) DO UPDATE SET
                    relation_status = 'active',
                    is_primary = TRUE,
                    remark = EXCLUDED.remark,
                    description = EXCLUDED.description,
                    oper_userid = EXCLUDED.oper_userid,
                    raw_follow_user = EXCLUDED.raw_follow_user,
                    updated_at = NOW()
                """,
                (
                    SAMPLE["corp_id"],
                    SAMPLE["external_userid"],
                    SAMPLE["owner_userid"],
                    "remark_masked_001",
                    "description_masked_001",
                    SAMPLE["owner_userid"],
                    Jsonb({"source": "aicrm_next_local_masked_seed"}),
                ),
            )
            cur.execute(
                """
                INSERT INTO owner_role_map (userid, display_name, role, active, updated_at)
                VALUES (%s, %s, %s, TRUE, NOW())
                ON CONFLICT (userid) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    role = EXCLUDED.role,
                    active = TRUE,
                    updated_at = NOW()
                """,
                (SAMPLE["owner_userid"], "owner_masked_display_001", "test_owner"),
            )
            # Keep the masked sample's tag coverage in class_user_status_current
            # so the old runtime emits a list shape compatible with the current
            # fixture parity contract (tags: list[str]).
            cur.execute(
                "DELETE FROM contact_tags WHERE external_userid = %s AND userid = %s AND tag_id = %s",
                (SAMPLE["external_userid"], SAMPLE["owner_userid"], SAMPLE["tag_id"]),
            )
            cur.execute(
                """
                INSERT INTO class_user_status_current (
                    external_userid, signup_status, signup_label_name, customer_name_snapshot,
                    owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status,
                    wecom_tag_sync_error, status_flags_json, updated_at
                )
                VALUES (%s, 'activated', %s, %s, %s, %s, %s, NOW(), 'skipped_fake_seed', '', %s, NOW())
                ON CONFLICT (external_userid) DO UPDATE SET
                    signup_status = EXCLUDED.signup_status,
                    signup_label_name = EXCLUDED.signup_label_name,
                    customer_name_snapshot = EXCLUDED.customer_name_snapshot,
                    owner_userid_snapshot = EXCLUDED.owner_userid_snapshot,
                    mobile_snapshot = EXCLUDED.mobile_snapshot,
                    set_by_userid = EXCLUDED.set_by_userid,
                    set_at = EXCLUDED.set_at,
                    wecom_tag_sync_status = EXCLUDED.wecom_tag_sync_status,
                    wecom_tag_sync_error = '',
                    status_flags_json = EXCLUDED.status_flags_json,
                    updated_at = NOW()
                """,
                (
                    SAMPLE["external_userid"],
                    SAMPLE["tag_name"],
                    SAMPLE["customer_name"],
                    SAMPLE["owner_userid"],
                    SAMPLE["mobile"],
                    SAMPLE["owner_userid"],
                    Jsonb({"seed": "aicrm_next_local_masked_seed"}),
                ),
            )
            cur.execute("DELETE FROM class_user_status_history WHERE external_userid = %s", (SAMPLE["external_userid"],))
            cur.execute(
                """
                INSERT INTO class_user_status_history (
                    external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
                    customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
                    wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
                )
                VALUES (%s, '', 'activated', '', %s, %s, %s, %s, %s, NOW(), 'skipped_fake_seed', '', %s)
                """,
                (
                    SAMPLE["external_userid"],
                    SAMPLE["tag_name"],
                    SAMPLE["customer_name"],
                    SAMPLE["owner_userid"],
                    SAMPLE["mobile"],
                    SAMPLE["owner_userid"],
                    Jsonb({"seed": "aicrm_next_local_masked_seed"}),
                ),
            )
            cur.execute(
                """
                INSERT INTO archived_messages (
                    seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                    msgtype, content, send_time, raw_payload
                )
                VALUES (900001, %s, 'private', %s, %s, %s, %s, 'text', %s, %s, %s)
                ON CONFLICT (msgid) DO UPDATE SET
                    chat_type = EXCLUDED.chat_type,
                    external_userid = EXCLUDED.external_userid,
                    owner_userid = EXCLUDED.owner_userid,
                    sender = EXCLUDED.sender,
                    receiver = EXCLUDED.receiver,
                    msgtype = EXCLUDED.msgtype,
                    content = EXCLUDED.content,
                    send_time = EXCLUDED.send_time,
                    raw_payload = EXCLUDED.raw_payload
                """,
                (
                    SAMPLE["msgid"],
                    SAMPLE["external_userid"],
                    SAMPLE["owner_userid"],
                    SAMPLE["external_userid"],
                    SAMPLE["owner_userid"],
                    "masked message content 001",
                    now,
                    '{"msgtype":"text","text":{"content":"masked message content 001"},"source":"aicrm_next_local_masked_seed"}',
                ),
            )
        conn.commit()
    return {"ok": True, "dry_run": False, **plan}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed a masked customer sample into local old Flask test PostgreSQL.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("AICRM_OLD_FLASK_TEST_DATABASE_URL", ""),
        help="Local old Flask test DB URL. Defaults to AICRM_OLD_FLASK_TEST_DATABASE_URL.",
    )
    parser.add_argument("--apply", action="store_true", help="Actually write the masked sample. Omit for dry-run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = seed_sample(args.database_url, apply=bool(args.apply))
    print(f"safe_url: {result['redacted_url']}")
    print(f"database: {result['database']}")
    print(f"dry_run: {result['dry_run']}")
    print(f"sample_external_userid: {SAMPLE['external_userid']}")
    print(f"tables: {', '.join(result['tables'])}")
    if result["dry_run"]:
        print("no writes executed; rerun with --apply to seed the local test DB")
    else:
        print("masked sample seed applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
