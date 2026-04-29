from __future__ import annotations

from flask import url_for

from .admin_console import _breadcrumb_items, _render_admin_template


def _api_endpoint_groups() -> list[dict]:
    return [
        {
            "id": "auth",
            "title": "认证",
            "description": "企业微信 SSO 扫码登录、OAuth 登录（企业微信内打开）及 break-glass 兜底入口。所有写操作建议附带 admin_action_token。",
            "endpoints": [
                {
                    "id": "get-login",
                    "method": "GET",
                    "path": "/login",
                    "summary": "后台统一登录入口",
                    "description": "PC 浏览器跳转企业微信扫码，企业微信内打开则走 OAuth。登录成功后重定向到 /admin/automation-conversion。",
                    "auth": "public",
                    "params": [
                        {"name": "redirect", "type": "string", "required": False, "description": "登录成功后的跳转路径，默认为后台首页"},
                    ],
                    "request_example": None,
                    "response_example": "HTTP 302 → /admin/automation-conversion",
                },
                {
                    "id": "get-wecom-start",
                    "method": "GET",
                    "path": "/auth/wecom/start",
                    "summary": "企业微信扫码登录发起",
                    "description": "生成企业微信扫码授权 URL 并重定向。state 参数用于 CSRF 防护。",
                    "auth": "public",
                    "params": [],
                    "request_example": None,
                    "response_example": "HTTP 302 → https://open.work.weixin.qq.com/wwopen/sso/qrConnect?...",
                },
                {
                    "id": "get-wecom-callback",
                    "method": "GET",
                    "path": "/auth/wecom/callback",
                    "summary": "企业微信扫码回调",
                    "description": "企业微信回调，校验 code + state，拉取 UserId 后写入 session。若该 UserId 未在 admin_users 中授权，返回 403。",
                    "auth": "public",
                    "params": [
                        {"name": "code", "type": "string", "required": True, "description": "企业微信下发的临时授权码"},
                        {"name": "state", "type": "string", "required": True, "description": "CSRF 防护用的随机态值"},
                    ],
                    "request_example": "GET /auth/wecom/callback?code=abc123&state=xyz789",
                    "response_example": 'HTTP 302 → /admin/automation-conversion\n# 或 HTTP 403 当该企微成员未被授权',
                },
                {
                    "id": "post-logout",
                    "method": "POST",
                    "path": "/admin/logout",
                    "summary": "退出登录",
                    "description": "清除当前登录 session，重定向到登录页。",
                    "auth": "session",
                    "params": [],
                    "request_example": None,
                    "response_example": "HTTP 302 → /login",
                },
            ],
        },
        {
            "id": "automation",
            "title": "自动化运营",
            "description": "自动化转化核心接口：运营概览数据、自动接话监控开关、扫描与放行动作、近期话术输出评审。",
            "endpoints": [
                {
                    "id": "get-automation-dashboard",
                    "method": "GET",
                    "path": "/api/admin/automation-conversion/dashboard",
                    "summary": "获取自动化运营概览",
                    "description": "返回三类人群规模（未填问卷、运营中、已转化）、启用任务流数量、池子用户明细及任务流执行摘要。",
                    "auth": "session",
                    "params": [],
                    "request_example": "GET /api/admin/automation-conversion/dashboard",
                    "response_example": """{
  "ok": true,
  "dashboard": {
    "audience_overview": {
      "pending_questionnaire_count": 42,
      "operating_count": 18,
      "converted_count": 7
    },
    "active_workflow_count": 3,
    "task_execution_summary": {
      "items": [
        {"workflow_name": "意向高-跟进流", "execution_count": 120, "latest_execution_at": "2026-04-27 09:00:00"}
      ]
    }
  }
}""",
                },
                {
                    "id": "post-automation-member-ops-stage-send",
                    "method": "POST",
                    "path": "/admin/automation-conversion/programs/<program_id>/member-ops/stage/<stage_key>/send",
                    "summary": "成员运营 no-JS 阶段发送表单",
                    "description": "后台 member-ops 页面 multipart/form-data 兜底入口，支持页面直接上传 images 并在成功后重定向回方案内 member-ops。旧路径 /admin/automation-conversion/stage/<stage_key>/send 已下线；manual-send API 仍保持 JSON/API 调用协议，不承担页面 multipart 实际发送。",
                    "auth": "session",
                    "params": [
                        {"name": "program_id", "type": "int (path)", "required": True, "description": "自动化运营方案 ID"},
                        {"name": "stage_key", "type": "string (path)", "required": True, "description": "阶段 route key，如 new-user 或 inactive-focus"},
                        {"name": "admin_action_token", "type": "string", "required": True, "description": "后台动作令牌"},
                        {"name": "content", "type": "string", "required": False, "description": "普通阶段群发正文"},
                        {"name": "images", "type": "file[]", "required": False, "description": "普通阶段本地图片，最多 3 张，每张不超过 5MB"},
                    ],
                    "request_example": "POST /admin/automation-conversion/programs/1/member-ops/stage/new-user/send\nContent-Type: multipart/form-data\n\nadmin_action_token=TOKEN&content=hello&images=@page.png",
                    "response_example": "HTTP 302 → /admin/automation-conversion/programs/1/member-ops?stage=new-user&panel=send&manual_send_notice=sent&record_id=123",
                },
                {
                    "id": "post-reply-monitor-toggle",
                    "method": "POST",
                    "path": "/admin/automation-conversion/auto-reply/reply-monitor/toggle",
                    "summary": "切换自动接话监控开关",
                    "description": "开启或关闭自动接话监控。enabled=1 为开启，enabled=0 为关闭。旧路径 /admin/automation-conversion/reply-monitor/toggle 已下线。",
                    "auth": "session",
                    "params": [
                        {"name": "admin_action_token", "type": "string", "required": True, "description": "操作令牌，防止误触发"},
                        {"name": "enabled", "type": "int", "required": True, "description": "1 = 开启，0 = 关闭"},
                    ],
                    "request_example": 'POST /admin/automation-conversion/auto-reply/reply-monitor/toggle\nContent-Type: application/x-www-form-urlencoded\n\nadmin_action_token=TOKEN&enabled=1',
                    "response_example": '{"ok": true, "status": "enabled", "message": "自动接话已开启"}',
                },
                {
                    "id": "post-reply-monitor-capture",
                    "method": "POST",
                    "path": "/admin/automation-conversion/auto-reply/reply-monitor/capture",
                    "summary": "立即扫描新消息",
                    "description": "手动触发一次自动接话扫描，将最新未处理消息抓取入队。正常情况由定时任务自动执行。旧路径 /admin/automation-conversion/reply-monitor/capture 已下线；internal-token 调用仍使用 /api/admin/automation-conversion/reply-monitor/capture。",
                    "auth": "session",
                    "params": [
                        {"name": "admin_action_token", "type": "string", "required": True, "description": "操作令牌"},
                    ],
                    "request_example": 'POST /admin/automation-conversion/auto-reply/reply-monitor/capture\n\nadmin_action_token=TOKEN',
                    "response_example": '{"ok": true, "status": "captured", "message": "扫描完成，新增 3 条入队"}',
                },
                {
                    "id": "post-reply-monitor-run-due",
                    "method": "POST",
                    "path": "/admin/automation-conversion/auto-reply/reply-monitor/run-due",
                    "summary": "立即放行到期队列",
                    "description": "手动触发放行逻辑，处理当前到期的自动接话队列，生成 Agent 话术输出。旧路径 /admin/automation-conversion/reply-monitor/run-due 已下线；internal-token 调用仍使用 /api/admin/automation-conversion/reply-monitor/run-due。",
                    "auth": "session",
                    "params": [
                        {"name": "admin_action_token", "type": "string", "required": True, "description": "操作令牌"},
                    ],
                    "request_example": 'POST /admin/automation-conversion/auto-reply/reply-monitor/run-due\n\nadmin_action_token=TOKEN',
                    "response_example": '{"ok": true, "status": "idle", "message": "本次无到期项"}',
                },
                {
                    "id": "get-auto-reply-outputs",
                    "method": "GET",
                    "path": "/api/admin/automation-conversion/auto-reply/outputs",
                    "summary": "获取近期话术输出列表",
                    "description": "返回最近生成的自动化应答话术，可用于人工评审（采用 / 未采用）。",
                    "auth": "session",
                    "params": [
                        {"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 20"},
                    ],
                    "request_example": "GET /api/admin/automation-conversion/auto-reply/outputs?limit=20",
                    "response_example": """{
  "ok": true,
  "rows": [
    {
      "output_id": "out_abc123",
      "external_contact_id": "wmXXX",
      "agent_code": "intent_high_v2",
      "rendered_output_text": "您好，关于您咨询的问题...",
      "outcome_status_label": "未闭环",
      "created_at": "2026-04-27 09:43:01"
    }
  ]
}""",
                },
                {
                    "id": "get-dispatch-history",
                    "method": "GET",
                    "path": "/api/admin/marketing-automation/dispatch-history",
                    "summary": "查询自动化分发历史",
                    "description": "查询营销自动化触达与分发记录，支持按状态过滤。",
                    "auth": "session",
                    "params": [
                        {"name": "status", "type": "string", "required": False, "description": "过滤状态，如 acked、pending"},
                        {"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 20"},
                    ],
                    "request_example": "GET /api/admin/marketing-automation/dispatch-history?status=acked&limit=20",
                    "response_example": """{
  "ok": true,
  "dispatch_history": {
    "count": 1,
    "items": [{"dispatch_status": "acked", "dispatched_at": "2026-04-27 09:00:00"}]
  }
}""",
                },
            ],
        },
        {
            "id": "questionnaire",
            "title": "问卷",
            "description": "问卷前台提交接口（公开）及后台问卷管理接口（需要登录态）。",
            "endpoints": [
                {
                    "id": "get-questionnaire",
                    "method": "GET",
                    "path": "/api/questionnaires/<slug>",
                    "summary": "获取问卷定义",
                    "description": "前台问卷页面加载时调用，返回题目列表、问卷配置及展示文案。slug 为问卷唯一标识符。",
                    "auth": "public",
                    "params": [
                        {"name": "slug", "type": "string (path)", "required": True, "description": "问卷唯一标识，如 intent-survey"},
                    ],
                    "request_example": "GET /api/questionnaires/intent-survey",
                    "response_example": """{
  "ok": true,
  "questionnaire": {
    "id": 1,
    "slug": "intent-survey",
    "title": "意向调查问卷",
    "questions": [
      {"id": 1, "type": "single_choice", "title": "您目前最关心的是？", "options": ["价格", "效果", "服务"]}
    ]
  }
}""",
                },
                {
                    "id": "post-questionnaire-submit",
                    "method": "POST",
                    "path": "/api/questionnaires/<slug>/submit",
                    "summary": "提交问卷答案",
                    "description": "前台用户提交问卷，包含答案列表和手机号。提交成功后返回 submission_id 及可选跳转 URL。",
                    "auth": "public",
                    "params": [
                        {"name": "slug", "type": "string (path)", "required": True, "description": "问卷唯一标识"},
                        {"name": "answers", "type": "array", "required": True, "description": "答案列表，每项包含 question_id 和 value"},
                        {"name": "mobile", "type": "string", "required": True, "description": "用户手机号"},
                        {"name": "external_userid", "type": "string", "required": False, "description": "企业微信外部联系人 ID，用于关联 CRM 记录"},
                    ],
                    "request_example": 'POST /api/questionnaires/intent-survey/submit\nContent-Type: application/json\n\n{"answers": [{"question_id": 1, "value": "价格"}], "mobile": "13800000000"}',
                    "response_example": '{"ok": true, "submission_id": 123, "redirect_url": ""}',
                },
                {
                    "id": "get-questionnaire-list",
                    "method": "GET",
                    "path": "/api/admin/questionnaire-console/list",
                    "summary": "获取问卷列表（后台）",
                    "description": "后台问卷管理页面调用，返回所有问卷及其状态。需要管理员登录态。",
                    "auth": "session",
                    "params": [],
                    "request_example": "GET /api/admin/questionnaire-console/list",
                    "response_example": """{
  "ok": true,
  "questionnaires": [
    {"id": 1, "slug": "intent-survey", "title": "意向调查", "enabled": true, "submission_count": 42}
  ]
}""",
                },
            ],
        },
        {
            "id": "config",
            "title": "配置",
            "description": "系统设置、路由规则、报名标签及营销自动化配置接口。所有写操作需要 admin 角色。",
            "endpoints": [
                {
                    "id": "get-config-overview",
                    "method": "GET",
                    "path": "/api/admin/config/overview",
                    "summary": "获取配置概览",
                    "description": "返回当前系统核心配置项的摘要，包括 Webhook URL、SSO 状态、营销自动化是否启用等。",
                    "auth": "session",
                    "params": [],
                    "request_example": "GET /api/admin/config/overview",
                    "response_example": """{
  "ok": true,
  "overview": {
    "webhook_url": "https://example.com/hook",
    "wecom_sso_enabled": true,
    "marketing_automation_enabled": true
  }
}""",
                },
                {
                    "id": "get-config-app-settings",
                    "method": "GET",
                    "path": "/api/admin/config/app-settings",
                    "summary": "获取系统设置",
                    "description": "返回所有可配置的系统环境变量键值对。",
                    "auth": "session",
                    "params": [],
                    "request_example": "GET /api/admin/config/app-settings",
                    "response_example": '{"ok": true, "settings": {"OPENCLAW_WEBHOOK_URL": "https://...", "WECOM_CORP_ID": "ww..."}}',
                },
                {
                    "id": "put-config-app-settings",
                    "method": "PUT",
                    "path": "/api/admin/config/app-settings",
                    "summary": "保存系统设置",
                    "description": "批量更新系统配置项。confirm=true 为必填，防止误操作。返回实际发生变更的键名列表。",
                    "auth": "session",
                    "params": [
                        {"name": "confirm", "type": "boolean", "required": True, "description": "必须为 true，防止误触发"},
                        {"name": "settings", "type": "object", "required": True, "description": "要更新的配置键值对"},
                    ],
                    "request_example": 'PUT /api/admin/config/app-settings\nContent-Type: application/json\n\n{"confirm": true, "settings": {"OPENCLAW_WEBHOOK_URL": "https://example.com/hook"}}',
                    "response_example": '{"ok": true, "changed": ["OPENCLAW_WEBHOOK_URL"]}',
                },
                {
                    "id": "get-config-routing",
                    "method": "GET",
                    "path": "/api/admin/config/routing",
                    "summary": "获取路由规则",
                    "description": "返回当前配置的客户路由规则和负责人角色映射。",
                    "auth": "session",
                    "params": [],
                    "request_example": "GET /api/admin/config/routing",
                    "response_example": '{"ok": true, "routing": {"owner_role": "sales", "rules": []}}',
                },
                {
                    "id": "post-config-signup-tags",
                    "method": "POST",
                    "path": "/api/admin/config/signup-tags",
                    "summary": "保存报名转化标签",
                    "description": "新增或更新一个报名转化标签配置。",
                    "auth": "session",
                    "params": [
                        {"name": "tag_id", "type": "string", "required": True, "description": "企业微信标签 ID"},
                        {"name": "label", "type": "string", "required": True, "description": "标签显示名称"},
                        {"name": "conversion_type", "type": "string", "required": True, "description": "转化类型，如 enrolled"},
                    ],
                    "request_example": 'POST /api/admin/config/signup-tags\nContent-Type: application/json\n\n{"tag_id": "tag_abc", "label": "已报名", "conversion_type": "enrolled"}',
                    "response_example": '{"ok": true}',
                },
                {
                    "id": "put-marketing-automation-config",
                    "method": "PUT",
                    "path": "/api/admin/marketing-automation/config",
                    "summary": "保存营销自动化配置",
                    "description": "更新营销自动化全局设置，包括静默时段、每日触达上限等。",
                    "auth": "session",
                    "params": [
                        {"name": "quiet_hours_start", "type": "string", "required": False, "description": "静默开始时间，格式 HH:MM"},
                        {"name": "quiet_hours_end", "type": "string", "required": False, "description": "静默结束时间，格式 HH:MM"},
                        {"name": "daily_dispatch_limit", "type": "int", "required": False, "description": "每日每用户最大触达次数"},
                    ],
                    "request_example": 'PUT /api/admin/marketing-automation/config\nContent-Type: application/json\n\n{"quiet_hours_start": "22:00", "quiet_hours_end": "08:00", "daily_dispatch_limit": 3}',
                    "response_example": '{"ok": true}',
                },
            ],
        },
        {
            "id": "customers",
            "title": "客户",
            "description": "客户画像查询、联系人同步及详情接口。external_userid 为企业微信外部联系人唯一标识。",
            "endpoints": [
                {
                    "id": "get-customer-profile",
                    "method": "GET",
                    "path": "/api/admin/customers/profile",
                    "summary": "获取客户画像",
                    "description": "返回客户的基本信息、标签、问卷答案、自动化状态及对话摘要。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "企业微信外部联系人 ID"},
                    ],
                    "request_example": "GET /api/admin/customers/profile?external_userid=wmXXXXXXXX",
                    "response_example": """{
  "ok": true,
  "profile": {
    "external_userid": "wmXXXXXXXX",
    "name": "张三",
    "mobile": "138****0000",
    "tags": ["意向高", "已问卷"],
    "automation_status": "operating"
  }
}""",
                },
                {
                    "id": "get-contacts",
                    "method": "GET",
                    "path": "/api/contacts",
                    "summary": "获取联系人列表",
                    "description": "分页返回所有外部联系人，支持按负责人过滤。",
                    "auth": "session",
                    "params": [
                        {"name": "owner_staff_id", "type": "string", "required": False, "description": "按负责人工号过滤"},
                        {"name": "limit", "type": "int", "required": False, "description": "每页条数，默认 50"},
                        {"name": "cursor", "type": "string", "required": False, "description": "分页游标"},
                    ],
                    "request_example": "GET /api/contacts?limit=50",
                    "response_example": '{"ok": true, "contacts": [], "next_cursor": null, "total": 0}',
                },
                {
                    "id": "get-contact-detail",
                    "method": "GET",
                    "path": "/api/contacts/<external_userid>",
                    "summary": "获取联系人详情",
                    "description": "返回单个外部联系人的完整信息，包含企业微信基础资料和本地备注。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string (path)", "required": True, "description": "企业微信外部联系人 ID"},
                    ],
                    "request_example": "GET /api/contacts/wmXXXXXXXX",
                    "response_example": '{"ok": true, "contact": {"external_userid": "wmXXX", "name": "张三", "description": ""}}',
                },
                {
                    "id": "post-contact-description",
                    "method": "POST",
                    "path": "/api/contacts/description",
                    "summary": "更新联系人备注",
                    "description": "更新指定联系人的本地备注字段，不影响企业微信侧数据。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                        {"name": "description", "type": "string", "required": True, "description": "新备注内容"},
                    ],
                    "request_example": 'POST /api/contacts/description\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "description": "高意向，跟进中"}',
                    "response_example": '{"ok": true}',
                },
            ],
        },
        {
            "id": "tags",
            "title": "标签",
            "description": "企业微信标签的查询、创建及标记/取消标记操作。",
            "endpoints": [
                {
                    "id": "get-tags",
                    "method": "GET",
                    "path": "/api/tags",
                    "summary": "获取标签列表",
                    "description": "返回当前企业所有可用的外部联系人标签。",
                    "auth": "session",
                    "params": [],
                    "request_example": "GET /api/tags",
                    "response_example": '{"ok": true, "tags": [{"tag_id": "tag_abc", "name": "意向高"}]}',
                },
                {
                    "id": "post-tags",
                    "method": "POST",
                    "path": "/api/tags",
                    "summary": "创建标签",
                    "description": "在企业微信侧创建新的外部联系人标签并同步到本地。",
                    "auth": "session",
                    "params": [
                        {"name": "name", "type": "string", "required": True, "description": "标签名称"},
                    ],
                    "request_example": 'POST /api/tags\nContent-Type: application/json\n\n{"name": "意向高"}',
                    "response_example": '{"ok": true, "tag": {"tag_id": "tag_new", "name": "意向高"}}',
                },
                {
                    "id": "post-tags-mark",
                    "method": "POST",
                    "path": "/api/tags/mark",
                    "summary": "给联系人打标签",
                    "description": "为指定外部联系人打上一个或多个标签。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                        {"name": "tag_ids", "type": "array", "required": True, "description": "要打上的标签 ID 列表"},
                    ],
                    "request_example": 'POST /api/tags/mark\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "tag_ids": ["tag_abc", "tag_def"]}',
                    "response_example": '{"ok": true}',
                },
                {
                    "id": "post-tags-unmark",
                    "method": "POST",
                    "path": "/api/tags/unmark",
                    "summary": "移除联系人标签",
                    "description": "移除指定外部联系人身上的一个或多个标签。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                        {"name": "tag_ids", "type": "array", "required": True, "description": "要移除的标签 ID 列表"},
                    ],
                    "request_example": 'POST /api/tags/unmark\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "tag_ids": ["tag_abc"]}',
                    "response_example": '{"ok": true}',
                },
            ],
        },
        {
            "id": "tasks",
            "title": "任务",
            "description": "创建企业微信消息任务，包括私聊消息、朋友圈及客户群发。任务创建后由企业微信提醒对应员工确认发送。",
            "endpoints": [
                {
                    "id": "post-task-private-message",
                    "method": "POST",
                    "path": "/api/tasks/private-message",
                    "summary": "创建私聊消息任务",
                    "description": "创建一条发给指定外部联系人的私聊消息任务。员工需在企业微信客户端确认后发送。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "目标外部联系人 ID"},
                        {"name": "content", "type": "string", "required": True, "description": "消息文本内容"},
                        {"name": "staff_id", "type": "string", "required": False, "description": "指定发送员工，默认为该联系人负责人"},
                    ],
                    "request_example": 'POST /api/tasks/private-message\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "content": "您好，关于您咨询的问题..."}',
                    "response_example": '{"ok": true, "task_id": "task_abc123"}',
                },
                {
                    "id": "post-task-moment",
                    "method": "POST",
                    "path": "/api/tasks/moment",
                    "summary": "创建朋友圈任务",
                    "description": "创建一条朋友圈发布任务，员工需在企业微信确认后发布到朋友圈。",
                    "auth": "session",
                    "params": [
                        {"name": "content", "type": "string", "required": True, "description": "朋友圈文字内容"},
                        {"name": "staff_ids", "type": "array", "required": False, "description": "指定发布的员工列表，默认全部"},
                    ],
                    "request_example": 'POST /api/tasks/moment\nContent-Type: application/json\n\n{"content": "今日好课推荐..."}',
                    "response_example": '{"ok": true, "task_id": "task_moment_abc"}',
                },
                {
                    "id": "post-task-group-message",
                    "method": "POST",
                    "path": "/api/tasks/group-message",
                    "summary": "创建群发任务",
                    "description": "向一批外部联系人创建批量群发消息任务。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userids", "type": "array", "required": True, "description": "目标外部联系人 ID 列表"},
                        {"name": "content", "type": "string", "required": True, "description": "消息内容"},
                    ],
                    "request_example": 'POST /api/tasks/group-message\nContent-Type: application/json\n\n{"external_userids": ["wmAAA", "wmBBB"], "content": "您好..."}',
                    "response_example": '{"ok": true, "task_id": "task_group_abc", "accepted_count": 2}',
                },
            ],
        },
        {
            "id": "sidebar",
            "title": "侧边栏",
            "description": "企业微信侧边栏应用接口，用于在客服会话侧边栏中展示客户状态、绑定手机号、查询营销状态等。",
            "endpoints": [
                {
                    "id": "get-sidebar-contact-binding",
                    "method": "GET",
                    "path": "/api/sidebar/contact-binding-status",
                    "summary": "查询联系人绑定状态",
                    "description": "返回当前会话联系人的手机号绑定状态及基础画像信息。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "当前会话的外部联系人 ID"},
                    ],
                    "request_example": "GET /api/sidebar/contact-binding-status?external_userid=wmXXX",
                    "response_example": '{"ok": true, "bound": true, "mobile_masked": "138****0000"}',
                },
                {
                    "id": "post-sidebar-bind-mobile",
                    "method": "POST",
                    "path": "/api/sidebar/bind-mobile",
                    "summary": "绑定手机号",
                    "description": "将手机号与外部联系人关联，写入本地 CRM 记录。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                        {"name": "mobile", "type": "string", "required": True, "description": "11 位手机号"},
                    ],
                    "request_example": 'POST /api/sidebar/bind-mobile\nContent-Type: application/json\n\n{"external_userid": "wmXXX", "mobile": "13800000000"}',
                    "response_example": '{"ok": true}',
                },
                {
                    "id": "get-sidebar-marketing-status",
                    "method": "GET",
                    "path": "/api/sidebar/marketing-status",
                    "summary": "查询营销状态",
                    "description": "返回联系人当前的营销自动化状态、分层标签及跟进阶段。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                    ],
                    "request_example": "GET /api/sidebar/marketing-status?external_userid=wmXXX",
                    "response_example": '{"ok": true, "status": "operating", "followup_segment": "intent_high", "enrolled": false}',
                },
                {
                    "id": "get-sidebar-signup-tags",
                    "method": "GET",
                    "path": "/api/sidebar/signup-tags/status",
                    "summary": "查询报名标签状态",
                    "description": "返回联系人当前命中的报名转化标签列表。",
                    "auth": "session",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "外部联系人 ID"},
                    ],
                    "request_example": "GET /api/sidebar/signup-tags/status?external_userid=wmXXX",
                    "response_example": '{"ok": true, "tags": [{"tag_id": "tag_abc", "label": "已报名", "marked": true}]}',
                },
            ],
        },
        {
            "id": "webhooks",
            "title": "Webhook / 回调",
            "description": "企业微信服务端事件回调接口。需在企业微信管理后台配置回调 URL 及 Token。与后台页面登录态完全隔离。",
            "endpoints": [
                {
                    "id": "post-wecom-contact-events",
                    "method": "POST",
                    "path": "/api/callbacks/wecom/contact-events",
                    "summary": "企业微信联系人事件回调",
                    "description": "接收企业微信推送的外部联系人变更事件（新增、删除、修改跟进人等）。企业微信会对请求做签名验证，需配合 Token 和 EncodingAESKey 使用。",
                    "auth": "public",
                    "params": [
                        {"name": "msg_signature", "type": "string (query)", "required": True, "description": "企业微信消息签名"},
                        {"name": "timestamp", "type": "string (query)", "required": True, "description": "时间戳"},
                        {"name": "nonce", "type": "string (query)", "required": True, "description": "随机字符串"},
                        {"name": "[XML Body]", "type": "XML", "required": True, "description": "企业微信加密消息体"},
                    ],
                    "request_example": "POST /api/callbacks/wecom/contact-events?msg_signature=XXX&timestamp=1714176000&nonce=abc\n\n<xml><ToUserName>...</ToUserName><Encrypt>...</Encrypt></xml>",
                    "response_example": '{"ok": true, "accepted": true}',
                },
            ],
        },
        {
            "id": "internal",
            "title": "内部接口",
            "description": "供内部自动化服务调用的接口，使用 Bearer Token 认证（Authorization: Bearer <AUTOMATION_INTERNAL_API_TOKEN>），不与后台页面登录态混用。",
            "endpoints": [
                {
                    "id": "get-internal-pulse-inbox",
                    "method": "GET",
                    "path": "/api/internal/customer-pulse/inbox",
                    "summary": "获取客户脉搏收件箱",
                    "description": "内部服务拉取待处理的客户脉搏消息列表，用于触发后续自动化动作。",
                    "auth": "bearer",
                    "params": [
                        {"name": "limit", "type": "int", "required": False, "description": "返回条数，默认 50"},
                    ],
                    "request_example": "GET /api/internal/customer-pulse/inbox\nAuthorization: Bearer <AUTOMATION_INTERNAL_API_TOKEN>",
                    "response_example": '{"ok": true, "items": [], "count": 0}',
                },
                {
                    "id": "post-internal-pulse-recompute",
                    "method": "POST",
                    "path": "/api/internal/customer-pulse/recompute",
                    "summary": "重算客户脉搏评分",
                    "description": "触发对指定客户的脉搏评分重算，更新其在各分层中的位置。",
                    "auth": "bearer",
                    "params": [
                        {"name": "external_userid", "type": "string", "required": True, "description": "目标外部联系人 ID"},
                    ],
                    "request_example": 'POST /api/internal/customer-pulse/recompute\nAuthorization: Bearer <TOKEN>\nContent-Type: application/json\n\n{"external_userid": "wmXXX"}',
                    "response_example": '{"ok": true, "recomputed": true}',
                },
                {
                    "id": "post-internal-pulse-run-due",
                    "method": "POST",
                    "path": "/api/internal/customer-pulse/run-due",
                    "summary": "执行到期脉搏任务",
                    "description": "处理当前时刻到期的所有客户脉搏定时任务，由外部 cron 调用。",
                    "auth": "bearer",
                    "params": [],
                    "request_example": "POST /api/internal/customer-pulse/run-due\nAuthorization: Bearer <TOKEN>",
                    "response_example": '{"ok": true, "processed": 3}',
                },
            ],
        },
        {
            "id": "errors",
            "title": "错误码",
            "description": "所有 API 在出错时返回统一结构：{\"ok\": false, \"error\": \"<message>\"}。HTTP 状态码含义如下。",
            "endpoints": [
                {
                    "id": "error-400",
                    "method": "GET",
                    "path": "HTTP 400",
                    "summary": "参数校验失败",
                    "description": "请求体缺少必填字段、字段格式错误，或高风险操作未带 confirm=true。",
                    "auth": None,
                    "params": [],
                    "request_example": None,
                    "response_example": '{"ok": false, "error": "mobile is required"}',
                },
                {
                    "id": "error-401",
                    "method": "GET",
                    "path": "HTTP 401",
                    "summary": "未认证",
                    "description": "后台页面未登录，或内部接口缺少 / 错误的 Bearer Token。",
                    "auth": None,
                    "params": [],
                    "request_example": None,
                    "response_example": '{"ok": false, "error": "authentication required"}',
                },
                {
                    "id": "error-403",
                    "method": "GET",
                    "path": "HTTP 403",
                    "summary": "权限不足",
                    "description": "该企微成员未在 admin_users 中授权，或当前角色（viewer）无权执行写操作。",
                    "auth": None,
                    "params": [],
                    "request_example": None,
                    "response_example": '{"ok": false, "error": "permission denied"}',
                },
                {
                    "id": "error-404",
                    "method": "GET",
                    "path": "HTTP 404",
                    "summary": "资源不存在",
                    "description": "请求的问卷、客户或配置项不存在。",
                    "auth": None,
                    "params": [],
                    "request_example": None,
                    "response_example": '{"ok": false, "error": "not found"}',
                },
                {
                    "id": "error-503",
                    "method": "GET",
                    "path": "HTTP 503",
                    "summary": "服务未就绪",
                    "description": "内部依赖（数据库、企业微信 API 凭据）未配置完成，服务暂时不可用。",
                    "auth": None,
                    "params": [],
                    "request_example": None,
                    "response_example": '{"ok": false, "error": "service unavailable: wecom credentials not configured"}',
                },
            ],
        },
    ]


def admin_console_api_docs():
    return _render_admin_template(
        "api_docs.html",
        active_nav="api_docs",
        page_title="API 文档",
        page_summary="后台全量接口参考，涵盖认证、自动化运营、问卷、配置、客户、标签、任务、侧边栏、Webhook 及内部接口。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("API 文档", None)),
        endpoint_groups=_api_endpoint_groups(),
    )


def register_routes(bp):
    bp.route("/admin/api-docs", methods=["GET"])(admin_console_api_docs)
