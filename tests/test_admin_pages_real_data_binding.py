from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_admin_pages_real_data_binding as checker


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")
    return TestClient(create_app())


def test_admin_pages_do_not_render_forbidden_state_markers(monkeypatch):
    client = _client(monkeypatch)

    for route in checker.ADMIN_PAGES:
        response = client.get(route, follow_redirects=False)
        assert response.status_code != 404, route
        assert checker._bad_marker_hits(route, response.text) == []


def test_key_admin_pages_render_server_side_rows_or_stats(monkeypatch):
    client = _client(monkeypatch)

    for route in [
        "/admin/cloud-orchestrator",
        "/admin/hxc-dashboard",
        "/admin/wechat-pay/products",
        "/admin/wechat-pay/transactions",
        "/admin/image-library",
        "/admin/miniprogram-library",
        "/admin/attachment-library",
        "/admin/jobs",
        "/admin/runtime-config",
        "/admin/api-docs",
    ]:
        response = client.get(route)
        has_real_data, row_count = checker._has_real_data(route, response.text)
        assert has_real_data, (route, row_count)


def test_ai_assistant_entry_uses_campaign_review_workspace(monkeypatch):
    client = _client(monkeypatch)

    redirect = client.get("/admin/cloud-orchestrator", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "/admin/cloud-orchestrator/campaigns"

    response = client.get("/admin/cloud-orchestrator/campaigns")

    assert response.status_code == 200
    assert "AI 助手 · 运营计划审阅" in response.text
    assert "Agent 上架的多分层多步骤运营计划在这里审阅启动。" in response.text
    assert "/api/admin/cloud-orchestrator/campaigns?" in response.text
    assert "只读展示 automation_agent_config" not in response.text
    assert "production_unavailable" not in response.text


def test_funnel_dashboard_entry_uses_hxc_dashboard_workspace(monkeypatch):
    client = _client(monkeypatch)

    redirect = client.get("/admin/user-ops", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "/admin/hxc-dashboard"

    response = client.get("/admin/hxc-dashboard")

    assert response.status_code == 200
    assert "用户激活漏斗看板" in response.text
    assert "漏斗状态汇总" in response.text
    assert "立即刷新" in response.text
    assert "发送人管理" in response.text
    assert "/api/admin/hxc-dashboard/refresh" in response.text
    assert "/api/admin/hxc-dashboard/broadcast-tasks" in response.text
    assert "production_unavailable" not in response.text
    assert "生产漏斗数据读取失败" not in response.text


def test_wecom_tags_page_uses_full_management_workspace(monkeypatch):
    response = _client(monkeypatch).get("/admin/wecom-tags")

    assert response.status_code == 200
    assert "data-wecom-tags-page" in response.text
    assert 'data-api-tags="/api/admin/wecom/tags"' in response.text
    assert 'data-api-groups="/api/admin/wecom/tag-groups"' in response.text
    assert "同步企微标签" in response.text
    assert "新增标签组" in response.text
    assert "新增标签" in response.text
    assert "集中管理企业客户标签：同步、搜索、新增、编辑、删除和复制 tag_id。" in response.text
    assert "本地标签缓存" not in response.text
    assert "标签使用记录" not in response.text
    assert "远程同步" not in response.text
    assert "有缓存" not in response.text


def test_customer_page_does_not_render_sample_fixture_names(monkeypatch):
    response = _client(monkeypatch).get("/admin/customers")

    assert response.status_code == 200
    for marker in checker.SAMPLE_CUSTOMERS:
        assert marker not in response.text


def test_customer_page_uses_production_facade_when_database_ready(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)

    def fake_list_customers(query):
        return {
            "customers": [
                {
                    "external_userid": "real_ext_001",
                    "customer_name": "真实客户甲",
                    "owner_display_name": "真实负责人",
                    "owner_userid": "owner_real",
                    "mobile": "138****0000",
                }
            ],
            "total": 23709,
        }

    monkeypatch.setattr(legacy_routes, "list_customers_via_legacy", fake_list_customers)

    response = _client(monkeypatch).get("/admin/customers")

    assert response.status_code == 200
    assert "共 23709 位客户" in response.text
    assert "真实客户甲" in response.text
    assert "张小蓝" not in response.text


def test_questionnaire_page_uses_production_facade_when_database_ready(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        legacy_routes,
        "list_questionnaires_from_legacy",
        lambda limit, offset: {
            "ok": True,
            "questionnaires": [
                {
                    "id": 101,
                    "slug": "real-questionnaire",
                    "title": "真实生产问卷",
                    "name": "真实生产问卷",
                    "enabled": True,
                    "is_disabled": False,
                    "created_at": "2026-05-01T00:00:00Z",
                    "updated_at": "2026-05-22T00:00:00Z",
                    "submission_count": 1171,
                    "assessment_enabled": False,
                    "public_path": "/s/real-questionnaire",
                }
            ],
            "total": 7,
            "source_status": "production_postgres",
        },
    )

    response = _client(monkeypatch).get("/admin/questionnaires")

    assert response.status_code == 200
    assert "real-questionnaire" in response.text
    assert "1171" in response.text
    assert "hxc-activation-v1" not in response.text
    assert "disabled-demo" not in response.text


def test_questionnaire_editor_nests_production_questions_for_legacy_editor(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        legacy_routes,
        "get_questionnaire_detail_from_legacy",
        lambda questionnaire_id: {
            "ok": True,
            "questionnaire": {
                "id": questionnaire_id,
                "slug": "real-questionnaire",
                "title": "真实生产问卷",
                "name": "真实生产问卷",
                "enabled": True,
                "is_disabled": False,
            },
            "questions": [
                {
                    "id": 501,
                    "type": "textarea",
                    "title": "真实生产题目",
                    "required": True,
                    "options": [],
                    "placeholder_text": "请填写",
                    "sidebar_profile_field": "needs_blockers_followup",
                }
            ],
            "source_status": "production_postgres",
        },
    )

    response = _client(monkeypatch).get("/admin/questionnaires/101")

    assert response.status_code == 200
    assert "真实生产问卷" in response.text
    assert (
        "真实生产题目" in response.text
        or "\\u771f\\u5b9e\\u751f\\u4ea7\\u9898\\u76ee" in response.text
    )
    assert "needs_blockers_followup" in response.text
    assert "侧边栏核心画像映射" in response.text
    assert "/admin/questionnaires/external-push-logs" in response.text
    assert "/api/admin/questionnaires/${state.currentId}/export" in response.text
    assert "/admin/questionnaires/${state.currentId}/external-push-logs" in response.text


def test_questionnaire_external_push_log_routes_forward_to_legacy(monkeypatch):
    from fastapi.responses import HTMLResponse

    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    forwarded_paths: list[str] = []

    async def fake_forward_to_legacy_flask(request):
        forwarded_paths.append(request.url.path)
        return HTMLResponse("<h1>问卷外部推送记录</h1>")

    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fake_forward_to_legacy_flask)
    client = _client(monkeypatch)

    for method, path in [
        ("get", "/admin/questionnaires/external-push-logs?status=failed"),
        ("get", "/admin/questionnaires/101/external-push-logs?limit=10"),
        ("post", "/admin/questionnaires/external-push-logs/1/retry"),
        ("post", "/admin/questionnaires/101/external-push-logs/retry-batch"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 200, path
        assert "问卷外部推送记录" in response.text

    assert forwarded_paths == [
        "/admin/questionnaires/external-push-logs",
        "/admin/questionnaires/101/external-push-logs",
        "/admin/questionnaires/external-push-logs/1/retry",
        "/admin/questionnaires/101/external-push-logs/retry-batch",
    ]


def test_wechat_pay_transactions_page_uses_legacy_management_when_database_ready(monkeypatch):
    from fastapi.responses import HTMLResponse

    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    forwarded_paths: list[str] = []

    async def fake_forward_to_legacy_flask(request):
        forwarded_paths.append(request.url.path)
        return HTMLResponse("<h2>筛选</h2><h2>订单列表</h2><button>导出筛选结果</button>")

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fake_forward_to_legacy_flask)

    response = _client(monkeypatch).get("/admin/wechat-pay/transactions")

    assert response.status_code == 200
    assert forwarded_paths == ["/admin/wechat-pay/transactions"]
    assert "筛选" in response.text
    assert "订单列表" in response.text
    assert "导出筛选结果" in response.text


def test_wechat_pay_transaction_detail_uses_legacy_management_when_database_ready(monkeypatch):
    from fastapi.responses import HTMLResponse

    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    forwarded_paths: list[str] = []

    async def fake_forward_to_legacy_flask(request):
        forwarded_paths.append(request.url.path)
        return HTMLResponse("<h2>订单详情</h2><button>提交退款申请</button>")

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(legacy_routes, "forward_to_legacy_flask", fake_forward_to_legacy_flask)

    response = _client(monkeypatch).get("/admin/wechat-pay/transactions/42")

    assert response.status_code == 200
    assert forwarded_paths == ["/admin/wechat-pay/transactions/42"]
    assert "订单详情" in response.text
    assert "提交退款申请" in response.text


def test_questionnaire_page_accepts_legacy_items_shape(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        legacy_routes,
        "list_questionnaires_from_legacy",
        lambda limit, offset: {
            "ok": True,
            "items": [
                {
                    "id": 20,
                    "slug": "q-20260414113428-da92d4",
                    "title": "黄小璨月度体验开通",
                    "name": "黄小璨月度体验开通",
                    "enabled": True,
                    "is_disabled": False,
                    "created_at": "2026-04-14T11:34:28.626862",
                    "updated_at": "2026-05-21T03:40:18.539121",
                    "submission_count": 911,
                    "assessment_enabled": False,
                    "public_path": "/s/q-20260414113428-da92d4",
                }
            ],
            "total": 7,
            "source_status": "production_postgres",
        },
    )

    response = _client(monkeypatch).get("/admin/questionnaires")

    assert response.status_code == 200
    assert "q-20260414113428-da92d4" in response.text
    assert "911" in response.text
    assert "Internal Server Error" not in response.text


def test_questionnaire_page_serializes_datetime_items(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        legacy_routes,
        "list_questionnaires_from_legacy",
        lambda limit, offset: {
            "ok": True,
            "items": [
                {
                    "id": 21,
                    "slug": "q-20260414135818-5d8fba",
                    "title": "填写问卷激活黄小璨AI",
                    "name": "黄小璨激活问卷",
                    "enabled": True,
                    "is_disabled": False,
                    "created_at": datetime(2026, 4, 14, 13, 58, 18, tzinfo=timezone.utc),
                    "updated_at": datetime(2026, 5, 21, 3, 40, 33, tzinfo=timezone.utc),
                    "submission_count": 82,
                    "assessment_enabled": False,
                    "public_path": "/s/q-20260414135818-5d8fba",
                }
            ],
            "total": 7,
            "source_status": "production_postgres",
        },
    )

    response = _client(monkeypatch).get("/admin/questionnaires")

    assert response.status_code == 200
    assert "q-20260414135818-5d8fba" in response.text
    assert "2026-04-14T13:58:18" in response.text
    assert "Internal Server Error" not in response.text


def test_questionnaire_detail_page_uses_production_facade_when_database_ready(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        legacy_routes,
        "get_questionnaire_detail_from_legacy",
        lambda questionnaire_id: {
            "ok": True,
            "questionnaire": {
                "id": questionnaire_id,
                "slug": "q-20260414135818-5d8fba",
                "name": "黄小璨激活问卷",
                "title": "填写问卷激活黄小璨AI",
                "description": "真实生产问卷详情",
                "redirect_url": "",
                "is_disabled": False,
                "enabled": True,
                "assessment_enabled": False,
                "assessment_config": {},
                "questions": [],
                "score_rules": [],
                "external_push_enabled": False,
            },
            "source_status": "production_postgres",
        },
    )

    response = _client(monkeypatch).get("/admin/questionnaires/21")

    assert response.status_code == 200
    assert "填写问卷激活黄小璨AI" in response.text
    assert "q-20260414135818-5d8fba" in response.text
    assert "initialQuestionnaireId: 21" in response.text
    assert "Not Found" not in response.text


def test_questionnaire_new_page_renders_editor_shell(monkeypatch):
    response = _client(monkeypatch).get("/admin/questionnaires/new")

    assert response.status_code == 200
    assert "新建问卷" in response.text
    assert 'mode: "new"' in response.text
    assert "Not Found" not in response.text


def test_automation_conversion_page_uses_next_program_repository_without_fixture_repo(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)
    monkeypatch.setattr(
        legacy_routes,
        "list_automation_programs_payload",
        lambda: {
            "ok": True,
            "items": [
                {
                    "program": {
                        "id": 7,
                        "program_name": "真实自动化运营方案",
                        "program_code": "real_program_v1",
                        "status": "active",
                        "updated_at": "2026-05-22T00:00:00Z",
                    },
                    "summary": {
                        "channel_count": 3,
                        "workflow_count": 9,
                        "latest_execution_at": "2026-05-22T01:00:00Z",
                    },
                }
            ],
            "default_program": {"id": 7, "program_name": "真实自动化运营方案"},
            "total": 1,
            "source_status": "next_postgres",
        },
    )

    response = TestClient(create_app(), raise_server_exceptions=False).get("/admin/automation-conversion")

    assert response.status_code == 200
    assert "真实自动化运营方案" in response.text
    assert "real_program_v1" in response.text
    assert "fixture_repository_blocked_in_production" not in response.text
    assert "next_local_preview" not in response.text
    assert 'href="/admin/automation-conversion/programs/7/setup?step=basic">编辑</a>' in response.text
    assert 'href="/admin/automation-conversion/programs/7/overview">概览</a>' in response.text
    assert 'action="/admin/automation-conversion/programs/7/pause"' in response.text


def test_automation_program_setup_overview_and_copy_render_next_pages(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")
    program_data = {
        "program": {
            "id": 7,
            "program_name": "真实自动化运营方案",
            "program_code": "real_program_v1",
            "status": "active",
            "description": "生产方案",
            "updated_at": "2026-05-22T00:00:00Z",
            "config_json": {},
        },
        "summary": {
            "channel_count": 3,
            "workflow_count": 9,
            "latest_execution_at": "2026-05-22T01:00:00Z",
            "publish_status_label": "入口已发布",
        },
    }
    monkeypatch.setattr(legacy_routes, "get_automation_program_with_summary", lambda program_id: program_data)

    client = TestClient(create_app(), raise_server_exceptions=False)
    setup_response = client.get("/admin/automation-conversion/programs/7/setup?step=basic")
    overview_response = client.get("/admin/automation-conversion/programs/7/overview")
    copy_response = client.get("/admin/automation-conversion/programs/7/copy")

    assert setup_response.status_code == 200
    assert "配置向导" in setup_response.text
    assert "第 1 步" in setup_response.text
    assert "基础信息" in setup_response.text
    assert 'action="/admin/automation-conversion/programs/7/update"' in setup_response.text
    assert overview_response.status_code == 200
    assert "方案概览" in overview_response.text
    assert "入口已发布" in overview_response.text
    assert copy_response.status_code == 200
    assert "复制自动化运营方案" in copy_response.text
    assert 'action="/admin/automation-conversion/programs/7/copy"' in copy_response.text


def test_automation_program_setup_steps_render_configured_data(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")
    program_data = {
        "program": {
            "id": 7,
            "program_name": "202605沙龙商业修行峰会",
            "program_code": "202505",
            "status": "active",
            "description": "生产方案",
            "updated_at": "2026-05-22T00:00:00Z",
            "config_json": {},
        },
        "summary": {
            "channel_count": 1,
            "workflow_count": 1,
            "latest_execution_at": "2026-05-23 09:00:00",
            "publish_status_label": "完整自动化已发布",
        },
    }
    setup_payload = {
        **program_data,
        "step": "basic",
        "steps": legacy_routes.SETUP_STEPS,
        "is_default_program": False,
        "basic": {},
        "entry_channel": {"qrcode": {"channel_name": "默认渠道二维码"}},
        "entry": {
            "channels": [
                {
                    "id": 31,
                    "channel_name": "默认渠道二维码",
                    "channel_code": "aqr_260521_b91c",
                    "channel_type": "qrcode",
                    "carrier_type": "qrcode",
                    "status": "active",
                    "binding_status": "active",
                    "initial_audience_label": "待填问卷",
                    "qr_url": "https://wework.qpic.cn/example",
                    "scene_value": "aqr_260521_b91c",
                    "welcome_message": "欢迎来到峰会",
                    "updated_at": "2026-05-23T09:00:00Z",
                }
            ],
            "qrcode_channel": {
                "id": 31,
                "channel_name": "默认渠道二维码",
                "channel_code": "aqr_260521_b91c",
                "channel_type": "qrcode",
                "carrier_type": "qrcode",
                "status": "active",
                "binding_status": "active",
                "initial_audience_label": "待填问卷",
                "qr_url": "https://wework.qpic.cn/example",
                "scene_value": "aqr_260521_b91c",
                "welcome_message": "欢迎来到峰会",
            },
            "customer_acquisition_links": [
                {
                    "link_name": "获客助手链接",
                    "link_id": "link_001",
                    "initial_audience_code": "operating",
                    "status": "active",
                    "final_url": "https://work.weixin.qq.com/ca/example",
                    "last_event_at": "2026-05-23T10:00:00Z",
                }
            ],
        },
        "segmentation": {
            "selected_questionnaire": {"title": "信息收集测试"},
            "default_strategy": "normal_question_rules",
            "normal_question_rules": {
                "segmentation_question_title": "你当前最关注什么",
                "category_rows": [
                    {
                        "category_name": "入门用户",
                        "description": "刚开始了解",
                        "option_ids": [1],
                        "option_snapshots": [{"id": 1, "option_text": "先了解"}],
                    }
                ],
                "unassigned_options": [],
            },
            "score_segments": {
                "enabled": True,
                "rows": [{"segment_name": "高意向", "segment_key": "high", "min_score": 80, "max_score": 100}],
            },
            "profile_dimension": {"template_id": 9},
        },
        "audience_entry_rule": {
            "normalized_cards": {
                "channel_enter": {
                    "event_label": "入口进入后",
                    "condition_type": "any_entry_channel",
                    "condition_options": {"any_entry_channel": "任一当前方案入口"},
                    "target_audience_code": "pending_questionnaire",
                    "target_options": {"pending_questionnaire": "待填问卷"},
                    "enabled": True,
                },
                "questionnaire_submitted": {
                    "event_label": "问卷提交后",
                    "condition_type": "questionnaire_id_matched",
                    "condition_options": {"questionnaire_id_matched": "当前方案问卷提交"},
                    "target_audience_code": "operating",
                    "target_options": {"operating": "运营中"},
                    "enabled": True,
                },
            },
            "manual_cards": [{"event_label": "成交标记", "target_label": "已转化"}],
        },
        "operations": {
            "active_count": 1,
            "tasks": [
                {
                    "id": 8,
                    "task_name": "首日欢迎触达",
                    "description": "入池后第一天触达",
                    "group_name": "峰会跟进",
                    "status": "active",
                    "trigger_type": "scheduled_daily",
                    "send_time": "09:30",
                    "target_audience_label": "运营中",
                    "content_mode": "unified",
                    "updated_at": "2026-05-23T11:00:00Z",
                }
            ],
        },
        "publish_check": {
            "entry": {"items": [{"label": "至少有一个当前方案入口", "passed": True, "message": "已完成"}]},
            "full": {"items": [{"label": "存在启用中的运营任务", "passed": True, "message": "已完成"}]},
        },
    }

    monkeypatch.setattr(legacy_routes, "get_automation_program_with_summary", lambda program_id: program_data)
    monkeypatch.setattr(
        legacy_routes,
        "get_automation_program_setup_payload",
        lambda program_id, *, step="basic": {**setup_payload, "step": step},
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    assertions = {
        "entry": ["默认渠道二维码", "aqr_260521_b91c", "获客助手链接", "https://wework.qpic.cn/example"],
        "segmentation": ["信息收集测试", "你当前最关注什么", "入门用户", "高意向"],
        "entry-rule": ["入口进入后", "任一当前方案入口", "问卷提交后", "成交标记"],
        "operations": ["首日欢迎触达", "峰会跟进", "运营中", "unified"],
        "publish": ["入口发布检查", "至少有一个当前方案入口", "完整自动化发布检查", "存在启用中的运营任务"],
    }
    for step, markers in assertions.items():
        response = client.get(f"/admin/automation-conversion/programs/7/setup?step={step}")
        assert response.status_code == 200, step
        for marker in markers:
            assert marker in response.text, (step, marker)
        assert "Not Found" not in response.text


def test_legacy_admin_login_routes_forward_to_legacy(monkeypatch):
    import aicrm_next.production_compat.api as production_api

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")

    async def fake_forward(request):
        from fastapi.responses import HTMLResponse

        return HTMLResponse(
            f"legacy-auth-forwarded:{request.method}:{request.url.path}:{request.url.query}",
            headers={"X-AICRM-Compatibility-Facade": "legacy_flask_facade"},
        )

    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fake_forward)

    response = TestClient(create_app(), raise_server_exceptions=False).get(
        "/login?next=/admin/automation-conversion/programs/7/entry-channels"
    )

    assert response.status_code == 200
    assert response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert "legacy-auth-forwarded:GET:/login:next=/admin/automation-conversion/programs/7/entry-channels" in response.text


def test_admin_wecom_tag_routes_forward_to_legacy(monkeypatch):
    import aicrm_next.production_compat.api as production_api

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")

    async def fake_forward(request):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "ok": True,
                "forwarded": f"{request.method}:{request.url.path}",
                "items": [{"tag_id": "et-tag-001", "tag_name": "高意向", "group_name": "客户分层"}],
            },
            headers={"X-AICRM-Compatibility-Facade": "legacy_flask_facade"},
        )

    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fake_forward)

    response = TestClient(create_app(), raise_server_exceptions=False).get("/api/admin/wecom/tags")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert response.json()["forwarded"] == "GET:/api/admin/wecom/tags"
    assert response.json()["items"][0]["tag_id"] == "et-tag-001"


def test_admin_cloud_orchestrator_campaign_routes_forward_to_legacy(monkeypatch):
    import aicrm_next.production_compat.api as production_api

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")

    async def fake_forward(request):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "ok": True,
                "forwarded": f"{request.method}:{request.url.path}:{request.url.query}",
                "campaigns": [{"campaign_code": "camp_probe", "review_status": "pending_review"}],
            },
            headers={"X-AICRM-Compatibility-Facade": "legacy_flask_facade"},
        )

    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fake_forward)
    client = TestClient(create_app(), raise_server_exceptions=False)

    list_response = client.get("/api/admin/cloud-orchestrator/campaigns?review_status=pending_review")
    step_response = client.patch(
        "/api/admin/cloud-orchestrator/campaigns/camp_probe/steps/1",
        json={"content_text": "updated"},
    )

    assert list_response.status_code == 200
    assert list_response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert list_response.json()["forwarded"] == "GET:/api/admin/cloud-orchestrator/campaigns:review_status=pending_review"
    assert step_response.status_code == 200
    assert step_response.json()["forwarded"] == "PATCH:/api/admin/cloud-orchestrator/campaigns/camp_probe/steps/1:"


def test_admin_hxc_dashboard_routes_forward_to_legacy(monkeypatch):
    import aicrm_next.production_compat.api as production_api

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")

    async def fake_forward(request):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "ok": True,
                "forwarded": f"{request.method}:{request.url.path}:{request.url.query}",
            },
            headers={"X-AICRM-Compatibility-Facade": "legacy_flask_facade"},
        )

    monkeypatch.setattr(production_api, "forward_to_legacy_flask", fake_forward)
    client = TestClient(create_app(), raise_server_exceptions=False)

    page_response = client.get("/admin/hxc-dashboard")
    refresh_response = client.post("/api/admin/hxc-dashboard/refresh", json={"trigger_source": "probe"})
    send_config_response = client.get("/api/admin/hxc-dashboard/send-config")

    assert page_response.status_code == 200
    assert page_response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert page_response.json()["forwarded"] == "GET:/admin/hxc-dashboard:"
    assert refresh_response.status_code == 200
    assert refresh_response.json()["forwarded"] == "POST:/api/admin/hxc-dashboard/refresh:"
    assert send_config_response.status_code == 200
    assert send_config_response.json()["forwarded"] == "GET:/api/admin/hxc-dashboard/send-config:"


def test_real_data_binding_checker_returns_ok():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["bad_marker_hits"] == []
    assert result["auth_failures"] == []
    assert result["placeholder_pages"] == []
    assert result["empty_data_pages"] == []
    assert result["data_blockers"] == []
    assert result["production_config_modified"] is False


def test_api_docs_page_lists_real_route_groups(monkeypatch):
    response = _client(monkeypatch).get("/admin/api-docs")

    assert response.status_code == 200
    assert "/api/admin/automation-conversion/jobs/run-due" in response.text
    assert "/api/wechat-pay/notify" in response.text
    assert checker._row_count(response.text) >= 10


def test_jobs_page_mentions_scheduled_safe_mode_without_disabled_timer_copy(monkeypatch):
    response = _client(monkeypatch).get("/admin/jobs")

    assert response.status_code == 200
    assert "同步与任务总览" in response.text
    assert "Webhook 投递" in response.text
    assert "群发队列" in response.text
    assert "数据读取状态" not in response.text
    assert "degraded" not in response.text
    assert "disabled timers" not in response.text.lower()
