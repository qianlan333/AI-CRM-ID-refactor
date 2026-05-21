#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
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
    "slug": "questionnaire_slug_masked_001",
    "name": "questionnaire_title_masked_001",
    "title": "questionnaire_title_masked_001",
    "description": "questionnaire_description_masked_001",
    "question_title": "question_title_masked_001",
    "option_label": "option_label_masked_001",
    "mobile": "mobile_masked_001",
    "openid": "openid_masked_001",
    "unionid": "unionid_masked_001",
    "external_userid": "external_user_masked_001",
    "follow_user_userid": "owner_masked_001",
    "respondent_key": "respondent_masked_001",
    "source_channel": "source_masked_001",
    "campaign_id": "campaign_masked_001",
    "staff_id": "staff_masked_001",
    "result_token": "result_token_masked_001",
}


@dataclass(frozen=True)
class SafeDatabaseUrl:
    raw_url: str
    connect_url: str
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


def _connectable_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url.split("://", 1)[1]
    return url


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
        connect_url=_connectable_url(url),
        redacted_url=redact_database_url(url),
        host=host,
        database_name=database_name,
    )


def _assessment_snapshot() -> dict[str, object]:
    return {
        "total_score": 8,
        "tag_codes": ["tag_masked_001"],
        "overall_level": {
            "id": "level_masked_001",
            "title": "level_title_masked_001",
            "description": "level_description_masked_001",
        },
        "strengths": [{"name": "strength_masked_001"}],
        "weaknesses": [{"name": "weakness_masked_001"}],
        "dimensions": [{"key": "dimension_masked_001", "name": "dimension_masked_001", "score": 8}],
        "tag_plan": {
            "matched_score_tier_id": "tier_masked_001",
            "matched_score_tier_name": "tier_masked_001",
            "score_tier_tag_ids": ["tag_masked_001"],
            "matched_dimension_categories": [],
            "final_tag_ids": ["tag_masked_001"],
        },
        "result_path": f"/s/{SAMPLE['slug']}/result/{SAMPLE['result_token']}",
    }


def seed_sample(database_url: str, *, apply: bool) -> dict[str, object]:
    safe_url = validate_database_url(database_url)
    plan = {
        "database": safe_url.database_name,
        "host": safe_url.host,
        "redacted_url": safe_url.redacted_url,
        "apply": apply,
        "sample": {
            "slug": SAMPLE["slug"],
            "title": SAMPLE["title"],
            "question_title": SAMPLE["question_title"],
            "option_label": SAMPLE["option_label"],
            "openid": SAMPLE["openid"],
            "unionid": SAMPLE["unionid"],
            "external_userid": SAMPLE["external_userid"],
            "result_token": SAMPLE["result_token"],
        },
        "tables": [
            "questionnaires",
            "questionnaire_questions",
            "questionnaire_options",
            "questionnaire_score_rules",
            "questionnaire_submissions",
            "questionnaire_submission_answers",
            "questionnaire_scrm_apply_logs",
        ],
    }
    if not apply:
        return {"ok": True, "dry_run": True, **plan}

    with psycopg.connect(safe_url.connect_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO questionnaires (
                    slug, name, title, description, is_disabled, redirect_url,
                    answer_display_mode, assessment_enabled, assessment_config,
                    external_push_enabled, external_push_url, external_push_type,
                    external_push_expires_at_ts, external_push_day, external_push_frequency,
                    external_push_remark, external_push_custom_params, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, FALSE, '',
                    'all_in_one', TRUE, %s,
                    FALSE, '', 'subscription',
                    1809100800, NULL, NULL,
                    '', %s, NOW(), NOW()
                )
                ON CONFLICT (slug) DO UPDATE SET
                    name = EXCLUDED.name,
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    is_disabled = FALSE,
                    answer_display_mode = 'all_in_one',
                    assessment_enabled = TRUE,
                    assessment_config = EXCLUDED.assessment_config,
                    external_push_enabled = FALSE,
                    external_push_url = '',
                    external_push_custom_params = '[]'::jsonb,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    SAMPLE["slug"],
                    SAMPLE["name"],
                    SAMPLE["title"],
                    SAMPLE["description"],
                    Jsonb({"seed": "aicrm_next_local_masked_questionnaire_sample"}),
                    Jsonb([]),
                ),
            )
            questionnaire_id = int(cur.fetchone()[0])

            cur.execute("DELETE FROM questionnaire_scrm_apply_logs WHERE questionnaire_id = %s", (questionnaire_id,))
            cur.execute(
                """
                DELETE FROM questionnaire_submission_answers
                WHERE submission_id IN (
                    SELECT id FROM questionnaire_submissions WHERE questionnaire_id = %s
                )
                """,
                (questionnaire_id,),
            )
            cur.execute("DELETE FROM questionnaire_submissions WHERE questionnaire_id = %s", (questionnaire_id,))
            cur.execute("DELETE FROM questionnaire_score_rules WHERE questionnaire_id = %s", (questionnaire_id,))
            cur.execute("DELETE FROM questionnaire_options WHERE question_id IN (SELECT id FROM questionnaire_questions WHERE questionnaire_id = %s)", (questionnaire_id,))
            cur.execute("DELETE FROM questionnaire_questions WHERE questionnaire_id = %s", (questionnaire_id,))

            cur.execute(
                """
                INSERT INTO questionnaire_questions (
                    questionnaire_id, type, title, placeholder_text, assessment_dimension_key,
                    required, sort_order, created_at, updated_at
                )
                VALUES (%s, 'single_choice', %s, '', 'dimension_masked_001', TRUE, 10, NOW(), NOW())
                RETURNING id
                """,
                (questionnaire_id, SAMPLE["question_title"]),
            )
            question_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO questionnaire_options (
                    question_id, option_text, score, assessment_type_key, tag_codes,
                    sort_order, created_at, updated_at
                )
                VALUES (%s, %s, 8, 'assessment_type_masked_001', %s, 10, NOW(), NOW())
                RETURNING id
                """,
                (question_id, SAMPLE["option_label"], Jsonb(["tag_masked_001"])),
            )
            option_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO questionnaire_score_rules (
                    questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
                )
                VALUES (%s, 0, 10, %s, 10, NOW(), NOW())
                """,
                (questionnaire_id, Jsonb(["tag_masked_001"])),
            )

            assessment_snapshot = _assessment_snapshot()
            cur.execute(
                """
                INSERT INTO questionnaire_submissions (
                    questionnaire_id, identity_map_id, respondent_key, openid, unionid,
                    external_userid, follow_user_userid, matched_by, mobile_snapshot,
                    source_channel, campaign_id, staff_id, total_score, final_tags,
                    assessment_result_snapshot, result_token, redirect_url_snapshot, submitted_at
                )
                VALUES (%s, NULL, %s, %s, %s, %s, %s, 'masked_seed', %s, %s, %s, %s, 8, %s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (
                    questionnaire_id,
                    SAMPLE["respondent_key"],
                    SAMPLE["openid"],
                    SAMPLE["unionid"],
                    SAMPLE["external_userid"],
                    SAMPLE["follow_user_userid"],
                    SAMPLE["mobile"],
                    SAMPLE["source_channel"],
                    SAMPLE["campaign_id"],
                    SAMPLE["staff_id"],
                    Jsonb(["tag_masked_001"]),
                    Jsonb(assessment_snapshot),
                    SAMPLE["result_token"],
                    assessment_snapshot["result_path"],
                ),
            )
            submission_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot,
                    selected_option_scores_snapshot, selected_option_tags_snapshot,
                    text_value, score_contribution, created_at
                )
                VALUES (%s, %s, 'single_choice', %s, %s, %s, %s, %s, '', 8, NOW())
                """,
                (
                    submission_id,
                    question_id,
                    SAMPLE["question_title"],
                    Jsonb([option_id]),
                    Jsonb([SAMPLE["option_label"]]),
                    Jsonb([8]),
                    Jsonb(["tag_masked_001"]),
                ),
            )

            cur.execute(
                """
                INSERT INTO questionnaire_scrm_apply_logs (
                    submission_id, questionnaire_id, openid, unionid, external_userid,
                    follow_user_userid, final_tags, matched_score_tier_id,
                    matched_score_tier_name, matched_dimension_categories, add_tag_ids,
                    status, error_message, wecom_response, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'tier_masked_001', 'tier_masked_001', %s, %s, 'skipped', 'masked seed: no real WeCom tag call', %s, NOW())
                """,
                (
                    submission_id,
                    questionnaire_id,
                    SAMPLE["openid"],
                    SAMPLE["unionid"],
                    SAMPLE["external_userid"],
                    SAMPLE["follow_user_userid"],
                    Jsonb(["tag_masked_001"]),
                    Jsonb([]),
                    Jsonb(["tag_masked_001"]),
                    Jsonb({"seed": "aicrm_next_local_masked_questionnaire_sample", "real_wecom_call": False}),
                ),
            )

        conn.commit()

    return {
        "ok": True,
        "dry_run": False,
        **plan,
        "questionnaire_id": questionnaire_id,
        "question_id": question_id,
        "option_id": option_id,
        "submission_id": submission_id,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed masked questionnaire sample data into local old Flask test DB.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("OLD_FLASK_TEST_DATABASE_URL", ""),
        help="Local old Flask test PostgreSQL URL. Password is redacted in output.",
    )
    parser.add_argument("--apply", action="store_true", help="Actually write the masked sample. Default is dry-run.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = seed_sample(args.database_url, apply=bool(args.apply))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
