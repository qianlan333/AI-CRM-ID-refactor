from __future__ import annotations

from flask import jsonify, redirect, request, url_for

from ..domains.admin_config import (
    automation_conversion_dispatch_filter_options,
    automation_conversion_recent_activity,
    automation_conversion_segment_cards,
    automation_conversion_stage_columns,
    build_automation_conversion_stage_detail_payload,
    build_config_home_payload,
    config_tabs,
    list_admin_app_settings,
    list_automation_conversion_dispatch_history,
    list_class_term_tag_mappings,
    list_mcp_tool_settings,
    list_owner_routing_settings,
    list_signup_tag_settings,
    normalize_automation_conversion_dispatch_filter,
    save_admin_app_settings,
    save_class_term_tag_mapping,
    save_mcp_tool_setting,
    save_owner_role_setting,
    save_routing_rule_setting,
    save_signup_tag_setting,
)
from ..services import (
    get_signup_conversion_config,
    get_questionnaire_detail,
    list_questionnaires,
    preview_signup_conversion_customer,
    recompute_signup_conversion_customers,
    save_signup_conversion_config,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_bool(name: str) -> bool:
    return str(request.args.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _query_int(name: str, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _request_confirmed() -> bool:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.values.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
        or str(json_payload.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
    )


def _render_config_template(
    template_name: str,
    *,
    active_tab: str,
    page_title: str,
    page_summary: str,
    breadcrumbs: list[dict[str, str]],
    page_notice: str = "",
    page_error: str = "",
    **extra,
):
    return _render_admin_template(
        template_name,
        active_nav="config",
        page_title=page_title,
        page_summary=page_summary,
        breadcrumbs=breadcrumbs,
        config_tabs=config_tabs(active_tab),
        page_notice=page_notice,
        page_error=page_error,
        **extra,
    )


def admin_config_home():
    payload = build_config_home_payload()
    return _render_config_template(
        "config_overview.html",
        active_tab="overview",
        page_title="配置中心",
        page_summary="在这里维护分配规则、标签规则、班期规则、系统设置和 AI 工具设置。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("配置中心", None)),
        overview_cards=payload["cards"],
    )


def _routing_page(*, page_error: str = ""):
    query = _query_text("q")
    active_only = _query_bool("active_only")
    payload = list_owner_routing_settings(query=query, active_only=active_only)
    edit_owner = _query_text("edit_owner")
    edit_rule = _query_text("edit_rule")
    owner_form = next((row for row in payload["owner_rows"] if row["userid"] == edit_owner), {"active": True, "role": "sales"})
    routing_form = next(
        (row for row in payload["routing_rows"] if row["rule_key"] == edit_rule),
        {"active": True, "routing_target": "manual_review"},
    )
    return _render_config_template(
        "config_routing.html",
        active_tab="routing",
        page_title="负责人 / 分配规则",
        page_summary="在这里维护负责人角色和客户分配规则。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("负责人 / 分配规则", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "active_only": active_only},
        owner_rows=payload["owner_rows"],
        routing_rows=payload["routing_rows"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        role_options=payload["role_options"],
        routing_target_options=payload["routing_target_options"],
        owner_form=owner_form,
        routing_form=routing_form,
    )


def admin_config_routing():
    return _routing_page()


def admin_config_save_owner_role():
    payload = dict(request.form)
    try:
        saved = save_owner_role_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _routing_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_routing", saved=1, edit_owner=saved.get("userid", "")), code=302)


def admin_config_save_routing_rule():
    payload = dict(request.form)
    try:
        saved = save_routing_rule_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _routing_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_routing", saved=1, edit_rule=saved.get("rule_key", "")), code=302)


def _signup_tags_page(*, page_error: str = ""):
    query = _query_text("q")
    active_only = _query_bool("active_only")
    payload = list_signup_tag_settings(query=query, active_only=active_only)
    edit_tag = _query_text("edit_tag")
    form_row = next((row for row in payload["rows"] if row["tag_id"] == edit_tag), {"active": True})
    return _render_config_template(
        "config_signup_tags.html",
        active_tab="signup_tags",
        page_title="报名标签规则",
        page_summary="在这里维护报名标签和业务状态之间的对应关系。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("报名标签规则", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "active_only": active_only},
        rows=payload["rows"],
        definitions=payload["definitions"],
        tag_group_name=payload["tag_group_name"],
        missing_statuses=payload["missing_statuses"],
        bootstrap_initialized=payload["bootstrap_initialized"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        form_row=form_row,
    )


def admin_config_signup_tags():
    return _signup_tags_page()


def admin_config_save_signup_tag():
    payload = dict(request.form)
    try:
        saved = save_signup_tag_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _signup_tags_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_signup_tags", saved=1, edit_tag=saved.get("tag_id", "")), code=302)


def _class_term_tags_page(*, page_error: str = ""):
    query = _query_text("q")
    active_only = _query_bool("active_only")
    payload = list_class_term_tag_mappings(query=query, active_only=active_only)
    edit_mapping = _query_text("edit_mapping")
    form_row = next(
        (row for row in payload["rows"] if str(row["id"]) == edit_mapping),
        {"is_active": True, "tag_group_name": payload["bootstrap_group_name"]},
    )
    return _render_config_template(
        "config_class_term_tags.html",
        active_tab="class_term_tags",
        page_title="班期标签规则",
        page_summary="在这里维护班期和标签之间的对应关系。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("班期标签规则", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "active_only": active_only},
        rows=payload["rows"],
        bootstrap_group_name=payload["bootstrap_group_name"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        form_row=form_row,
    )


def admin_config_class_term_tags():
    return _class_term_tags_page()


def admin_config_save_class_term_tag():
    payload = dict(request.form)
    try:
        saved = save_class_term_tag_mapping(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _class_term_tags_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_class_term_tags", saved=1, edit_mapping=saved.get("id", "")), code=302)


def _app_settings_page(*, page_error: str = ""):
    query = _query_text("q")
    scope = _query_text("scope")
    payload = list_admin_app_settings(query=query, scope=scope)
    editable_rows = [row for row in payload["rows"] if row["mode"] == "editable"]
    masked_rows = [row for row in payload["rows"] if row["mode"] == "masked"]
    return _render_config_template(
        "config_app_settings.html",
        active_tab="app_settings",
        page_title="系统设置",
        page_summary="在这里维护系统参数；涉及敏感信息的内容只显示掩码。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("系统设置", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "scope": scope},
        rows=payload["rows"],
        editable_rows=editable_rows,
        masked_rows=masked_rows,
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
    )


def admin_config_app_settings():
    return _app_settings_page()


def _extract_setting_form_payload() -> dict[str, str]:
    settings: dict[str, str] = {}
    for key, value in request.form.items():
        if not key.startswith("setting__"):
            continue
        settings[key.split("setting__", 1)[1]] = str(value or "")
    return settings


def admin_config_save_app_settings():
    if not _request_confirmed():
        return _app_settings_page(page_error="保存前请先确认本次修改。")
    try:
        save_admin_app_settings(_extract_setting_form_payload(), operator=_operator_from_request())
    except ValueError as exc:
        return _app_settings_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_app_settings", saved=1), code=302)


def _mcp_tools_page(*, page_error: str = ""):
    query = _query_text("q")
    enabled_only = _query_bool("enabled_only")
    payload = list_mcp_tool_settings(query=query, enabled_only=enabled_only)
    edit_tool = _query_text("edit_tool")
    form_row = next(
        (row for row in payload["rows"] if row["tool_name"] == edit_tool),
        {"enabled": True, "visible_in_console": True, "sort_order": 0},
    )
    return _render_config_template(
        "config_mcp_tools.html",
        active_tab="mcp_tools",
        page_title="AI 工具设置",
        page_summary="在这里维护 AI 工具的展示方式、启用状态和说明文字。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("AI 工具设置", None),
        ),
        page_notice="保存成功" if _query_bool("saved") else "",
        page_error=page_error,
        filters={"q": query, "enabled_only": enabled_only},
        rows=payload["rows"],
        auth_configured=payload["auth_configured"],
        auth_source=payload["auth_source"],
        summary_cards=payload["summary_cards"],
        audit_entries=payload["audit_entries"],
        form_row=form_row,
    )


def admin_config_mcp_tools():
    return _mcp_tools_page()


def admin_config_save_mcp_tool():
    payload = dict(request.form)
    try:
        saved = save_mcp_tool_setting(payload, operator=_operator_from_request())
    except ValueError as exc:
        return _mcp_tools_page(page_error=str(exc))
    return redirect(url_for("api.admin_config_mcp_tools", saved=1, edit_tool=saved.get("tool_name", "")), code=302)


def _automation_conversion_status_cards(config: dict[str, object], selected_questionnaire: dict[str, object] | None) -> list[dict[str, str]]:
    questionnaire_name = "还没选择问卷"
    if selected_questionnaire:
        questionnaire_name = str(
            selected_questionnaire.get("title")
            or selected_questionnaire.get("name")
            or questionnaire_name
        ).strip() or questionnaire_name
    elif config.get("questionnaire_missing"):
        missing_id = int(config.get("missing_questionnaire_id") or 0)
        questionnaire_name = f"已失效的问卷 #{missing_id}" if missing_id > 0 else "已失效的问卷"
    thresholds = dict(config.get("silent_threshold_days_by_pool") or {})
    silent_summary = " / ".join(
        [
            f"新{int(thresholds.get('new_user') or 7)}天",
            f"未普{int(thresholds.get('inactive_normal') or 7)}天",
            f"未重{int(thresholds.get('inactive_focus') or 7)}天",
            f"激普{int(thresholds.get('active_normal') or 7)}天",
            f"激重{int(thresholds.get('active_focus') or 7)}天",
        ]
    )
    return [
        {
            "label": "问卷初判开关",
            "value": "已开启" if config.get("enabled") else "已暂停",
            "description": "当前页面只配置自动化转化的问卷初判和首次分流。",
        },
        {
            "label": "当前问卷",
            "value": questionnaire_name,
            "description": "系统会按这份问卷做首次分流，问卷里必须直接收集必填手机号。",
        },
        {
            "label": "重点跟进门槛",
            "value": f"命中 {int(config.get('core_threshold') or 0)} 题",
            "description": "问卷初判只输出普通跟进 / 重点跟进，更细的后续池子不在这里判断。",
        },
        {
            "label": "沉默池规则",
            "value": silent_summary,
            "description": "新用户池、未激活普通/重点、激活普通/重点都可单独配置停留天数；超时自动进入沉默池，沉默池只做留存。",
        },
        {
            "label": "夜间暂停",
            "value": f"{int(config.get('quiet_hour_start') or 23)}:00 后暂停启动",
            "description": f"按 {str(config.get('timezone') or 'Asia/Shanghai').strip() or 'Asia/Shanghai'} 时区执行，夜间不会新启动自动化转化。",
        },
    ]


def admin_automation_conversion():
    config = get_signup_conversion_config()
    questionnaires = list_questionnaires()
    questionnaire_id = config.get("questionnaire_id")
    selected_questionnaire = None
    if questionnaire_id not in (None, ""):
        selected_questionnaire = get_questionnaire_detail(int(questionnaire_id))
    dispatch_filter = normalize_automation_conversion_dispatch_filter(_query_text("status"))
    dispatch_history = automation_conversion_recent_activity(filter_value=dispatch_filter, limit=50)
    return _render_admin_template(
        "automation_conversion.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="用业务步骤维护自动化转化的问卷初判，查看客户所处阶段，并追踪最近交给 AI 的处理情况。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", None),
        ),
        current_status_cards=_automation_conversion_status_cards(config, selected_questionnaire),
        marketing_config=config,
        questionnaires=questionnaires,
        selected_questionnaire=selected_questionnaire,
        priority_distribution=automation_conversion_segment_cards(),
        stage_columns=automation_conversion_stage_columns(),
        dispatch_history=dispatch_history,
        dispatch_status_options=automation_conversion_dispatch_filter_options(),
    )


def admin_automation_conversion_stage_detail(stage_key: str):
    try:
        payload = build_automation_conversion_stage_detail_payload(
            stage_key=stage_key,
            keyword=_query_text("keyword"),
            offset=_query_int("offset", default=0, minimum=0, maximum=100000),
            limit=_query_int("limit", default=50, minimum=1, maximum=100),
        )
    except ValueError:
        return _render_admin_template(
            "placeholder.html",
            active_nav="automation_conversion",
            page_title="阶段不存在",
            page_summary="当前阶段没有对应页面，请返回自动化转化首页重新选择。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("自动化转化", url_for("api.admin_automation_conversion")),
                ("阶段不存在", None),
            ),
            actions=[{"label": "返回自动化转化首页", "href": url_for("api.admin_automation_conversion"), "variant": "secondary"}],
            state_title="阶段不存在",
            state_body="请检查链接是否正确，或重新点击阶段看板进入。",
            state_items=["支持的阶段包括：新用户池、未激活普通池、未激活重点跟进池、激活普通池、激活重点跟进池、沉默池、已确认成交"],
            page_error="未找到对应阶段",
        ), 404

    stage = payload["stage"]
    return _render_admin_template(
        "automation_conversion_stage.html",
        active_nav="automation_conversion",
        page_title=f"{stage['label']}客户",
        page_summary="按阶段查看客户名单，支持继续按姓名、手机号或客户编号缩小范围。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            (stage["label"], None),
        ),
        stage_payload=payload,
    )


def admin_automation_conversion_preview_page():
    return _render_admin_template(
        "automation_conversion_preview.html",
        active_nav="automation_conversion",
        page_title="客户试运行",
        page_summary="输入手机号、客户姓名或客户编号，查看系统当前会不会把这位客户放进自动化转化。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("客户试运行", None),
        ),
    )


def admin_marketing_automation_ui():
    target = url_for("api.admin_automation_conversion")
    query_string = request.query_string.decode("utf-8").strip()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, code=302)


def api_admin_config_overview():
    return jsonify({"ok": True, "overview": build_config_home_payload()})


def api_admin_config_routing():
    return jsonify({"ok": True, "config": list_owner_routing_settings(query=_query_text("q"), active_only=_query_bool("active_only"))})


def api_admin_config_save_owner_role():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_owner_role_setting(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_save_routing_rule():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_routing_rule_setting(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_signup_tags():
    return jsonify({"ok": True, "config": list_signup_tag_settings(query=_query_text("q"), active_only=_query_bool("active_only"))})


def api_admin_config_save_signup_tag():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_signup_tag_setting(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_class_term_tags():
    return jsonify({"ok": True, "config": list_class_term_tag_mappings(query=_query_text("q"), active_only=_query_bool("active_only"))})


def api_admin_config_save_class_term_tag():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_class_term_tag_mapping(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_app_settings():
    return jsonify({"ok": True, "config": list_admin_app_settings(query=_query_text("q"), scope=_query_text("scope"))})


def api_admin_config_save_app_settings():
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return jsonify({"ok": False, "error": "settings must be an object"}), 400
    if not _request_confirmed():
        return jsonify({"ok": False, "error": "confirm is required before saving app settings"}), 400
    try:
        changed = save_admin_app_settings(settings, operator=_operator_from_request())
        return jsonify({"ok": True, "changed": changed, "config": list_admin_app_settings(query="", scope="")})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_config_mcp_tools():
    return jsonify({"ok": True, "config": list_mcp_tool_settings(query=_query_text("q"), enabled_only=_query_bool("enabled_only"))})


def api_admin_config_save_mcp_tool():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_mcp_tool_setting(payload, operator=_operator_from_request())
        return jsonify({"ok": True, "item": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_config():
    try:
        return jsonify({"ok": True, "config": get_signup_conversion_config()})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_save_config():
    payload = request.get_json(silent=True) or {}
    try:
        saved = save_signup_conversion_config(payload)
        return jsonify({"ok": True, "config": saved})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_marketing_automation_preview():
    payload = request.get_json(silent=True) or {}
    try:
        preview = preview_signup_conversion_customer(
            external_userid=payload.get("external_userid", ""),
            person_id=payload.get("person_id"),
        )
        return jsonify({"ok": True, "preview": preview})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def api_admin_marketing_automation_recompute():
    payload = request.get_json(silent=True) or {}
    try:
        result = recompute_signup_conversion_customers(
            external_userid=payload.get("external_userid", ""),
            person_id=payload.get("person_id"),
            external_userids=payload.get("external_userids"),
            person_ids=payload.get("person_ids"),
        )
        return jsonify({"ok": True, "recompute": result})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


def api_admin_marketing_automation_dispatch_history():
    return jsonify(
        {
            "ok": True,
            "dispatch_history": list_automation_conversion_dispatch_history(
                status=_query_text("status"),
                limit=_query_int("limit", default=50, minimum=1, maximum=200),
            ),
        }
    )


def api_admin_config_signup_conversion():
    return api_admin_marketing_automation_config()


def api_admin_config_save_signup_conversion():
    return api_admin_marketing_automation_save_config()


def register_routes(bp):
    bp.route("/admin/config", methods=["GET"])(admin_config_home)
    bp.route("/admin/config/routing", methods=["GET"])(admin_config_routing)
    bp.route("/admin/config/routing/owner-role", methods=["POST"])(admin_config_save_owner_role)
    bp.route("/admin/config/routing/rule", methods=["POST"])(admin_config_save_routing_rule)
    bp.route("/admin/config/signup-tags", methods=["GET"])(admin_config_signup_tags)
    bp.route("/admin/config/signup-tags/save", methods=["POST"])(admin_config_save_signup_tag)
    bp.route("/admin/config/class-term-tags", methods=["GET"])(admin_config_class_term_tags)
    bp.route("/admin/config/class-term-tags/save", methods=["POST"])(admin_config_save_class_term_tag)
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/stage/<stage_key>", methods=["GET"])(admin_automation_conversion_stage_detail)
    bp.route("/admin/automation-conversion/preview", methods=["GET"])(admin_automation_conversion_preview_page)
    bp.route("/admin/marketing-automation/ui", methods=["GET"])(admin_marketing_automation_ui)
    bp.route("/admin/config/app-settings", methods=["GET"])(admin_config_app_settings)
    bp.route("/admin/config/app-settings/save", methods=["POST"])(admin_config_save_app_settings)
    bp.route("/admin/config/mcp-tools", methods=["GET"])(admin_config_mcp_tools)
    bp.route("/admin/config/mcp-tools/save", methods=["POST"])(admin_config_save_mcp_tool)

    bp.route("/api/admin/config/overview", methods=["GET"])(api_admin_config_overview)
    bp.route("/api/admin/config/routing", methods=["GET"])(api_admin_config_routing)
    bp.route("/api/admin/config/routing/owner-role", methods=["POST"])(api_admin_config_save_owner_role)
    bp.route("/api/admin/config/routing/rule", methods=["POST"])(api_admin_config_save_routing_rule)
    bp.route("/api/admin/config/signup-tags", methods=["GET"])(api_admin_config_signup_tags)
    bp.route("/api/admin/config/signup-tags", methods=["POST"])(api_admin_config_save_signup_tag)
    bp.route("/api/admin/config/class-term-tags", methods=["GET"])(api_admin_config_class_term_tags)
    bp.route("/api/admin/config/class-term-tags", methods=["POST"])(api_admin_config_save_class_term_tag)
    bp.route("/api/admin/config/app-settings", methods=["GET"])(api_admin_config_app_settings)
    bp.route("/api/admin/config/app-settings", methods=["PUT"])(api_admin_config_save_app_settings)
    bp.route("/api/admin/config/mcp-tools", methods=["GET"])(api_admin_config_mcp_tools)
    bp.route("/api/admin/config/mcp-tools", methods=["POST"])(api_admin_config_save_mcp_tool)
    bp.route("/api/admin/marketing-automation/config", methods=["GET"])(api_admin_marketing_automation_config)
    bp.route("/api/admin/marketing-automation/config", methods=["PUT"])(api_admin_marketing_automation_save_config)
    bp.route("/api/admin/marketing-automation/config/preview", methods=["POST"])(api_admin_marketing_automation_preview)
    bp.route("/api/admin/marketing-automation/dispatch-history", methods=["GET"])(api_admin_marketing_automation_dispatch_history)
    bp.route("/api/admin/marketing-automation/recompute", methods=["POST"])(api_admin_marketing_automation_recompute)
    bp.route("/api/admin/config/marketing-automation/signup-conversion", methods=["GET"])(api_admin_config_signup_conversion)
    bp.route("/api/admin/config/marketing-automation/signup-conversion", methods=["PUT"])(api_admin_config_save_signup_conversion)
