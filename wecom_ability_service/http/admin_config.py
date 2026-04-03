from __future__ import annotations

from flask import jsonify, redirect, render_template, request, url_for

from ..domains.admin_config import (
    build_config_home_payload,
    config_tabs,
    list_admin_app_settings,
    list_class_term_tag_mappings,
    list_mcp_tool_settings,
    list_owner_routing_settings,
    list_signup_tag_settings,
    save_admin_app_settings,
    save_class_term_tag_mapping,
    save_mcp_tool_setting,
    save_owner_role_setting,
    save_routing_rule_setting,
    save_signup_tag_setting,
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
        page_summary="配置中心统一承接 owner/routing、标签规则、app settings 和 MCP settings。运行时表优先，代码常量只做 seed/fallback。",
        breadcrumbs=_breadcrumb_items(("CRM Console", url_for("api.admin_console_home")), ("配置中心", None)),
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
        page_title="Owner / Routing 配置",
        page_summary="owner_role_map 与 routing_rule_config 共用一个页面维护。routing runtime 优先走表配置，不再只靠 definitions.py。",
        breadcrumbs=_breadcrumb_items(
            ("CRM Console", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("Owner / Routing", None),
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
        page_title="Signup Tags 配置",
        page_summary="signup_tag_rules 负责 WeCom tag 到内部 signup_status 的映射。页面同时展示 bootstrap 状态和业务状态定义。",
        breadcrumbs=_breadcrumb_items(
            ("CRM Console", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("Signup Tags", None),
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
        page_title="Class Term Tags 配置",
        page_summary="class_term_tag_mapping 负责班期与 WeCom tag 的映射。页面展示 bootstrap 覆盖情况，并允许直接维护结构化映射。",
        breadcrumbs=_breadcrumb_items(
            ("CRM Console", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("Class Term Tags", None),
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
        page_title="App Settings",
        page_summary="app_settings 区分可直接编辑项和 secret 掩码项。secret 只显示 masked 状态，更新时留空表示保持不变。",
        breadcrumbs=_breadcrumb_items(
            ("CRM Console", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("App Settings", None),
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
        return _app_settings_page(page_error="confirm is required before saving app settings")
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
        page_title="MCP Tools 配置",
        page_summary="MCP tool settings 负责工具启停、后台展示分组/文案，以及 sample args / output 可见性。tool name 保持不变。",
        breadcrumbs=_breadcrumb_items(
            ("CRM Console", url_for("api.admin_console_home")),
            ("配置中心", url_for("api.admin_config_home")),
            ("MCP Tools", None),
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


def register_routes(bp):
    bp.route("/admin/config", methods=["GET"])(admin_config_home)
    bp.route("/admin/config/routing", methods=["GET"])(admin_config_routing)
    bp.route("/admin/config/routing/owner-role", methods=["POST"])(admin_config_save_owner_role)
    bp.route("/admin/config/routing/rule", methods=["POST"])(admin_config_save_routing_rule)
    bp.route("/admin/config/signup-tags", methods=["GET"])(admin_config_signup_tags)
    bp.route("/admin/config/signup-tags/save", methods=["POST"])(admin_config_save_signup_tag)
    bp.route("/admin/config/class-term-tags", methods=["GET"])(admin_config_class_term_tags)
    bp.route("/admin/config/class-term-tags/save", methods=["POST"])(admin_config_save_class_term_tag)
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
