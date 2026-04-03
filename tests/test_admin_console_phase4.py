from __future__ import annotations

import json
from pathlib import Path

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-console-phase4.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "release-test-sha",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "MCP_BEARER_TOKEN": "mcp-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed_phase4_data(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES ('owner-a', '顾问甲', 'sales', 1)
            """
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES ('ext-1', '客户一', 'owner-a', '高意向', '主客户档案', '2026-04-02 09:30:00')
            """
        )
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (1, '13800138000', 'tp-1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES ('ext-1', 1, 'owner-a', 'owner-a', 'owner-a', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES ('ww-test', 'ext-1', 'union-1', 'openid-1', 'owner-a', '客户一', 'active', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description, raw_follow_user
            )
            VALUES ('ww-test', 'ext-1', 'owner-a', 'active', 1, '主跟进', '一线顾问', '{}')
            """
        )
        db.execute(
            """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES
              ('ext-1', 'owner-a', 'tag-1', 'AI产品报名'),
              ('ext-1', 'owner-a', 'tag-999', '已报名999')
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (
                'ext-1', 'signed_999', '已报名999', '客户一', 'owner-a',
                '13800138000', 'owner-a', '2026-04-02 10:00:00', 'success', '', '{}'
            )
            """
        )
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
                customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
                wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at
            )
            VALUES (
                'ext-1', 'lead', 'signed_999', '报名引流品', '已报名999',
                '客户一', 'owner-a', '13800138000', 'owner-a', '2026-04-02 10:00:00',
                'success', '', '{}', '2026-04-02 10:00:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
            )
            VALUES (
                1, 'msg-1', 'private', 'ext-1', 'owner-a', 'owner-a', 'ext-1', 'text', '你好，欢迎咨询',
                '2026-04-02 10:05:00', '{}', '2026-04-02 10:05:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "private_message",
                json.dumps(
                    {
                        "chat_type": "single",
                        "external_userid": ["ext-1"],
                        "sender": ["owner-a"],
                        "text": {"content": "测试触达"},
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"errcode": 0, "errmsg": "ok"}, ensure_ascii=False),
                "task-1",
                "created",
                "2026-04-02 10:06:00",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (1, 'q-1', 'q-1', '客户问卷', '问卷描述', 0, '', '2026-04-02 09:00:00', '2026-04-02 09:20:00')
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (1, 1, 'single_choice', '当前阶段', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (1, 1, '已报名999', 10, '[\"tag-999\"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_score_rules (
                questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (1, 0, 100, '[\"tag-999\"]', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (
                1, 1, 'resp-1', 'openid-1', 'union-1', 'ext-1', 'owner-a',
                'openid', '13800138000', 88, '[\"tag-999\"]', '', '2026-04-02 10:10:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (
                1, 1, 'single_choice', '当前阶段',
                '[1]', '[\"已报名999\"]', '[10]', '[\"tag-999\"]', '', 10, CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            """
            INSERT INTO questionnaire_scrm_apply_logs (
                submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
            )
            VALUES (1, 'ext-1', 'owner-a', '[\"tag-999\"]', 'success', '', '2026-04-02 10:11:00')
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_current (
                mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
                huangxiaocan_activation_state, class_term_no, class_term_label, first_entry_source, last_entry_source, created_at, updated_at
            )
            VALUES (
                '13800138000', 'ext-1', '客户一', 'owner-a', 1, 1,
                'activated', 1, '1期', 'student_import', 'student_import', '2026-04-02 09:40:00', '2026-04-02 09:45:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_lead_pool_history (
                mobile, external_userid, action_type, source_type, operator, before_json, after_json, remark, created_at
            )
            VALUES (
                '13800138000', 'ext-1', 'lead_pool_insert', 'student_import', 'owner-a', '{}', '{}', 'seed', '2026-04-02 09:45:00'
            )
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_import_batches (
                import_type, file_name, total_rows, success_rows, failed_rows, error_summary, created_by, created_at
            )
            VALUES ('class_term_source', 'seed.csv', 1, 1, 0, '', 'owner-a', '2026-04-02 09:42:00')
            """
        )
        db.execute(
            """
            INSERT INTO user_ops_deferred_jobs (
                job_type, external_userid, owner_userid, run_after, status, attempt_count, payload_json, result_json, created_at, updated_at
            )
            VALUES (
                'verify_class_term_tag_and_upsert_lead_pool', 'ext-1', 'owner-a', '2026-04-02 11:00:00', 'pending', 0, '{}', '{}', '2026-04-02 10:20:00', '2026-04-02 10:20:00'
            )
            """
        )
        db.commit()


def test_admin_customers_pages_render_as_search_and_profile(app, client):
    _seed_phase4_data(app)

    list_response = client.get("/admin/customers")
    detail_response = client.get("/admin/customers/ext-1?tab=questionnaires")

    assert list_response.status_code == 200
    list_html = list_response.get_data(as_text=True)
    assert "客户查找" in list_html
    assert "查看档案" in list_html
    assert "name=\"status\"" not in list_html
    assert "name=\"tag\"" not in list_html
    assert "最近消息" not in list_html
    assert "更新时间" not in list_html

    detail_html = detail_response.get_data(as_text=True)
    assert detail_response.status_code == 200
    assert "客户档案" in detail_html
    assert "实时标签" in detail_html
    assert "问卷记录" in detail_html
    assert "聊天记录" in detail_html
    assert "互动记录" not in detail_html
    assert "高级信息" not in detail_html


def test_admin_customer_detail_tag_preview_is_dry_run(app, client):
    _seed_phase4_data(app)

    response = client.post(
        "/admin/customers/ext-1/tags",
        data={
            "return_tab": "tags",
            "tag_action": "mark",
            "userid": "owner-a",
            "tag_ids": "tag-2,tag-3",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "这里会先展示操作预览，确认后才会真正执行。" in html
    assert '"would_execute": true' in html
    assert "tag-2" in html


def test_admin_questionnaire_pages_render_detail_sections(app, client):
    _seed_phase4_data(app)

    list_response = client.get("/admin/questionnaires")
    detail_response = client.get("/admin/questionnaires/1")

    list_html = list_response.get_data(as_text=True)
    detail_html = detail_response.get_data(as_text=True)

    assert list_response.status_code == 200
    assert "问卷管理" in list_html
    assert "创建新问卷" in list_html
    assert "问卷名称" in list_html
    assert "提交数" in list_html
    assert "/s/q-1" in list_html

    assert detail_response.status_code == 200
    assert "编辑问卷" in detail_html
    assert "返回问卷管理" in detail_html
    assert "问卷内容" in detail_html
    assert "题型 / 组件区" in detail_html
    assert "删除问卷" in detail_html
    assert "下载数据" in detail_html


def test_admin_operations_page_and_migrate_action_are_audited(app, client):
    _seed_phase4_data(app)

    page_response = client.get("/admin/user-ops")
    page_html = page_response.get_data(as_text=True)
    assert page_response.status_code == 200
    assert "运营管理" in page_html
    assert ("运营名单" in page_html) or ("筛选条件" in page_html)
    assert ("班级状态" in page_html) or ("批量群发" in page_html)

    action_response = client.post(
        "/admin/user-ops/actions",
        data={
            "return_tab": "class-history",
            "action": "migrate-class-user",
            "confirm": "1",
            "operator": "tester-phase4",
        },
    )
    action_html = action_response.get_data(as_text=True)
    assert action_response.status_code == 200
    assert "操作已完成" in action_html

    with app.app_context():
        logs = get_db().execute(
            """
            SELECT action_type, operator, target_type
            FROM admin_operation_logs
            WHERE target_type = 'operations_console_action'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchall()
        assert logs
        assert logs[0]["action_type"] == "migrate_class_user_status"
        assert logs[0]["operator"] == "tester-phase4"
