from __future__ import annotations

import re
import os

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from aicrm_next.main import app as next_app


@pytest.fixture()
def client():
    return TestClient(next_app)


def _connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def _program_row(html: str, program_id: int) -> str:
    match = re.search(rf'<tr id="program-row-{program_id}".*?</tr>', html, flags=re.S)
    assert match
    return match.group(0)


def _seed_program_stats() -> dict[str, int]:
    with _connect() as db:
        program_a = int(
            db.execute(
                """
                INSERT INTO automation_program (program_code, program_name, status, config_json)
                VALUES (%s, '方案 A', 'active', '{}'::jsonb)
                RETURNING id
                """,
                ("stats_program_a",),
            ).fetchone()["id"]
        )
        program_b = int(
            db.execute(
                """
                INSERT INTO automation_program (program_code, program_name, status, config_json)
                VALUES (%s, '方案 B', 'active', '{}'::jsonb)
                RETURNING id
                """,
                ("stats_program_b",),
            ).fetchone()["id"]
        )
        program_empty = int(
            db.execute(
                """
                INSERT INTO automation_program (program_code, program_name, status, config_json)
                VALUES (%s, '方案 空', 'active', '{}'::jsonb)
                RETURNING id
                """,
                ("stats_program_empty",),
            ).fetchone()["id"]
        )
        channel_id = int(
            db.execute(
                """
                INSERT INTO automation_channel (channel_code, channel_name, status)
                VALUES ('stats_channel', '9.9 渠道二维码', 'active')
                RETURNING id
                """
            ).fetchone()["id"]
        )
        people_id = int(
            db.execute(
                "INSERT INTO people (mobile, third_party_user_id) VALUES ('13800000001', 'wm_shared') RETURNING id"
            ).fetchone()["id"]
        )
        db.execute(
            "INSERT INTO contacts (external_userid, customer_name, remark) VALUES ('wm_shared', '客户 A', '客户 A')"
        )
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, master_customer_id, in_pool, current_pool, current_audience_code
            )
            VALUES ('wm_global_only', '13900000000', %s, TRUE, 'operating', 'operating')
            """,
            (people_id,),
        )
        db.execute(
            """
            INSERT INTO automation_program_member (
                program_id, external_contact_id, master_customer_id, latest_source_channel_id,
                in_program, current_stage_code, current_audience_code,
                pool_entered_at, current_stage_entered_at, updated_at
            )
            VALUES
                (%s, 'wm_shared', %s, %s, TRUE, 'operating', 'operating', NOW() - INTERVAL '3 hours', NOW() - INTERVAL '2 hours', NOW()),
                (%s, 'wm_pending', NULL, %s, TRUE, '', 'pending_questionnaire', NOW() - INTERVAL '4 hours', NOW() - INTERVAL '4 hours', NOW() - INTERVAL '1 hour'),
                (%s, 'wm_shared', %s, %s, TRUE, 'converted', 'converted', NOW() - INTERVAL '5 hours', NOW() - INTERVAL '1 hour', NOW()),
                (%s, 'wm_exited', NULL, %s, FALSE, 'operating', 'operating', NOW() - INTERVAL '6 hours', NOW() - INTERVAL '6 hours', NOW())
            """,
            (
                program_a,
                people_id,
                channel_id,
                program_a,
                channel_id,
                program_b,
                people_id,
                channel_id,
                program_a,
                channel_id,
            ),
        )
        db.commit()
    return {"program_a": program_a, "program_b": program_b, "program_empty": program_empty}


def test_program_list_html_uses_program_member_counts_and_removes_global_pool_cards(client):
    ids = _seed_program_stats()

    response = client.get("/admin/automation-conversion")
    html = response.text

    assert response.status_code == 200
    for removed in ["池子统计", "内部 Code", "发布状态", "入口数", "运营动作", "最近执行", "更新时间"]:
        assert removed not in html
    assert "人数" in html
    assert "/api/admin/automation-conversion/overview" not in html
    assert "/api/admin/automation-conversion/pools" not in html

    assert re.search(r"<td>2</td>", _program_row(html, ids["program_a"]))
    assert re.search(r"<td>1</td>", _program_row(html, ids["program_b"]))
    assert re.search(r"<td>0</td>", _program_row(html, ids["program_empty"]))


def test_program_overview_json_and_members_are_program_scoped(client):
    ids = _seed_program_stats()

    overview_page = client.get(f"/admin/automation-conversion/programs/{ids['program_a']}/overview")
    overview_html = overview_page.text
    assert overview_page.status_code == 200
    assert "数据概览" in overview_html
    for removed in ["方案信息", "画像分层", "行为分层", "入口数", "运营动作", "发布状态", "最近执行"]:
        assert removed not in overview_html

    overview = client.get(f"/api/admin/automation-conversion/programs/{ids['program_a']}/overview")
    payload = overview.json()
    assert overview.status_code == 200
    assert overview.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert overview.headers["X-AICRM-Fallback-Used"] == "false"
    assert payload["summary"]["member_count"] == sum(item["count"] for item in payload["stage_segments"])
    assert payload["summary"]["member_count"] == 2
    assert {item["key"]: item["count"] for item in payload["stage_segments"]} == {
        "operating": 1,
        "pending_questionnaire": 1,
    }

    members = client.get(
        f"/api/admin/automation-conversion/programs/{ids['program_a']}/members?stage=operating&page=1&page_size=20"
    )
    members_payload = members.json()
    assert members.status_code == 200
    assert members_payload["total"] == 1
    assert all(item["program_id"] == ids["program_a"] for item in members_payload["items"])
    assert all(item["stage_key"] == "operating" for item in members_payload["items"])

    program_b = client.get(f"/api/admin/automation-conversion/programs/{ids['program_b']}/overview").json()
    assert program_b["summary"]["member_count"] == 1


def test_global_automation_member_never_counts_without_program_member(client):
    ids = _seed_program_stats()

    programs = client.get("/api/admin/automation-conversion/programs").json()
    empty = next(item for item in programs["items"] if item["program"]["id"] == ids["program_empty"])

    assert programs["ok"] is True
    assert programs["route_owner"] == "ai_crm_next"
    assert empty["summary"]["member_count"] == 0
