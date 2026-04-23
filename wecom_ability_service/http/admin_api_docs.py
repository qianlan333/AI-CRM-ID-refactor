from __future__ import annotations

from flask import url_for

from .admin_console import _breadcrumb_items, _render_admin_template


def _api_doc_sections() -> list[dict[str, object]]:
    return [
        {
            "title": "认证方式",
            "items": [
                "后台主认证为企业微信自建应用登录，统一入口在 /login。",
                "PC 浏览器默认走企业微信扫码登录，企业微信内打开时走 OAuth 登录。",
                "企业微信只负责识别 UserId，CRM 本地 admin_users / admin_user_roles 负责 RBAC 授权。",
                "break-glass 兜底入口默认关闭，只在企微 SSO 故障时临时开启。",
                "后台高风险写操作仍建议附带 admin_action_token，避免误触发。",
                "内部自动化接口继续使用 Bearer Token，不与后台页面登录态混用。",
            ],
            "examples": [
                {
                    "label": "企业微信后台登录流程",
                    "request": "GET /login -> /auth/wecom/start -> /auth/wecom/callback?code=...&state=...",
                    "response": '{"session": {"admin_user_id": 12, "wecom_userid": "qianlan333", "login_type": "wecom_qr"}}',
                },
                {
                    "label": "内部 Bearer Token",
                    "request": "Authorization: Bearer <AUTOMATION_INTERNAL_API_TOKEN>",
                    "response": '{"ok": true}',
                }
            ],
        },
        {
            "title": "自动化运营核心接口",
            "items": [
                "GET /admin/automation-conversion 用于自动化运营后台入口。",
                "GET /api/admin/marketing-automation/dispatch-history 查询最近触达与分发记录。",
                "POST /admin/automation-conversion/reply-monitor/run-due 用于手动触发自动接话扫描。",
            ],
            "examples": [
                {
                    "label": "查询自动化分发记录",
                    "request": "GET /api/admin/marketing-automation/dispatch-history?status=acked&limit=20",
                    "response": '{"ok": true, "dispatch_history": {"count": 1, "items": [{"dispatch_status": "acked"}]}}',
                }
            ],
        },
        {
            "title": "问卷核心接口",
            "items": [
                "GET /admin/questionnaires 查看问卷列表与状态。",
                "GET /api/questionnaires/<slug> 获取前台问卷定义。",
                "POST /api/questionnaires/<slug>/submit 提交问卷答案与手机号。",
            ],
            "examples": [
                {
                    "label": "问卷提交",
                    "request": 'POST /api/questionnaires/intent-survey/submit\\n{"answers": [...], "mobile": "13800000000"}',
                    "response": '{"ok": true, "submission_id": 123, "redirect_url": ""}',
                }
            ],
        },
        {
            "title": "配置接口",
            "items": [
                "GET /admin/config 进入配置中心总览。",
                "GET /api/admin/config/overview 获取配置概览。",
                "PUT /api/admin/config/app-settings 保存系统设置。",
            ],
            "examples": [
                {
                    "label": "系统设置保存",
                    "request": 'PUT /api/admin/config/app-settings\\n{"confirm": true, "settings": {"OPENCLAW_WEBHOOK_URL": "https://example.com/hook"}}',
                    "response": '{"ok": true, "changed": ["OPENCLAW_WEBHOOK_URL"]}',
                }
            ],
        },
        {
            "title": "Webhook / Callback",
            "items": [
                "企业微信回调继续走 /api/callbacks，不因后台瘦身移除。",
                "自动化转化相关 webhook 配置在配置中心系统设置中维护。",
                "下线旧页面不会影响 callbacks、contacts、identity、tags、tasks 等底座接口。",
            ],
            "examples": [
                {
                    "label": "企业微信回调",
                    "request": "POST /api/callbacks/wecom/contact-events",
                    "response": '{"ok": true, "accepted": true}',
                }
            ],
        },
        {
            "title": "常见错误码",
            "items": [
                "400: 参数校验失败或 confirm 未勾选。",
                "401: 未登录后台，或内部 Token 缺失/错误。",
                "403: 角色权限不足，或 viewer 执行了写操作。",
                "404: 资源不存在。",
                "503: 内部依赖未配置完成。",
            ],
            "examples": [
                {
                    "label": "权限不足",
                    "request": "GET /admin/config",
                    "response": '{"ok": false, "error": "permission denied"}',
                },
                {
                    "label": "未授权企微成员",
                    "request": "GET /auth/wecom/callback?code=abc&state=xyz",
                    "response": "HTTP 403，返回登录页并提示“当前企微成员尚未被授权登录后台”",
                }
            ],
        },
    ]


def admin_console_api_docs():
    return _render_admin_template(
        "api_docs.html",
        active_nav="api_docs",
        page_title="API 文档",
        page_summary="后台内置的人类可读 API 文档，聚焦企业微信 SSO、自动化运营、问卷、配置以及回调说明。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("API 文档", None)),
        doc_sections=_api_doc_sections(),
        compatibility_notes=[
            "旧的 /admin/mcp 页面已改为兼容跳转到当前文档页。",
            "MCP 协议实现与 /mcp endpoint 这次不硬删，只移除控制台入口和配置入口。",
            "7 天观察期内会继续记录旧页面访问，作为第二阶段硬删依据。",
        ],
    )


def register_routes(bp):
    bp.route("/admin/api-docs", methods=["GET"])(admin_console_api_docs)
