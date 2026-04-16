from __future__ import annotations

import requests

from flask import jsonify, redirect, request, url_for

from ..domains.automation_conversion import (
    activate_conversion_workflow,
    build_rejected_feedback_clipboard_payload,
    create_agent_config,
    create_conversion_profile_segment_template,
    create_conversion_workflow,
    create_conversion_workflow_node,
    delete_conversion_workflow,
    get_conversion_dashboard_payload,
    get_conversion_workflow_detail_summary,
    get_conversion_workflow_execution_detail,
    get_conversion_workflow_execution_item_detail,
    list_agent_configs,
    list_conversion_agent_options,
    list_recent_reviewable_agent_outputs,
    get_conversion_profile_segment_template_bundle,
    get_conversion_workflow_model_bundle,
    get_member_detail,
    get_overview_payload,
    get_agent_config_detail,
    get_default_channel_settings_payload,
    get_model_infra_payload,
    handle_agent_router_callback,
    list_conversion_profile_segment_catalog,
    list_conversion_profile_segment_templates,
    list_conversion_profile_segment_template_options,
    list_conversion_workflow_execution_items,
    list_conversion_workflow_execution_records,
    list_conversion_workflow_nodes,
    list_conversion_workflow_registry,
    list_conversion_workflows,
    mark_won,
    put_in_pool,
    push_openclaw,
    remove_from_pool,
    run_registered_due_jobs,
    run_due_reply_monitor,
    run_message_activity_sync,
    run_router_test_dispatch,
    run_reply_monitor_capture,
    review_agent_reply_output,
    publish_agent_config,
    generate_default_channel_qr,
    save_reply_monitor_enabled,
    save_agent_config_draft,
    save_default_channel_settings,
    save_model_infra_settings,
    pause_conversion_workflow,
    send_conversion_execution_item_via_bazhuayu,
    set_follow_type,
    unmark_won,
    update_conversion_profile_segment_template,
    update_conversion_workflow,
    update_conversion_workflow_node,
    delete_conversion_workflow_node,
    test_model_infra_connection,
)
from ..domains.automation_conversion.orchestration_service import validate_router_callback_signature
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token, require_internal_api_token, validate_admin_console_action_token


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_int(name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _query_bool(name: str, *, default: bool = False) -> bool:
    raw_value = request.args.get(name)
    if raw_value is None:
        return bool(default)
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _overview_notice() -> str:
    reply_monitor_action = _query_text("reply_monitor")
    if reply_monitor_action == "enabled":
        return "自动接话已开启"
    if reply_monitor_action == "disabled":
        return "自动接话已关闭"
    if reply_monitor_action == "captured":
        return "自动接话扫描已完成"
    if reply_monitor_action == "dispatched":
        return "自动接话放行已执行"
    return ""


_AUTOMATION_CONVERSION_WORKSPACE_TABS = (
    {
        "key": "overview",
        "label": "数据概览",
        "summary": "概览、运行状态与任务流执行摘要",
        "endpoint": "api.admin_automation_conversion_overview",
        "params": {},
    },
    {
        "key": "operations",
        "label": "自动化运营",
        "summary": "任务流列表、节点摘要与执行入口",
        "endpoint": "api.admin_automation_conversion_operations",
        "params": {},
    },
    {
        "key": "auto_reply",
        "label": "自动化应答",
        "summary": "应答监控、队列状态与稳定入口",
        "endpoint": "api.admin_automation_conversion_auto_reply",
        "params": {},
    },
    {
        "key": "agent_config",
        "label": "模型 / Agent 配置",
        "summary": "可用 Agent 与基础画像分层模板配置",
        "endpoint": "api.admin_automation_conversion_agent_config",
        "params": {},
    },
)
def _redirect_to(endpoint: str, **params):
    compact_params = {key: value for key, value in params.items() if value not in (None, "", False)}
    return redirect(url_for(endpoint, **compact_params), code=302)


def _operations_page_api_urls() -> dict[str, str]:
    return {
        "registry": url_for("api.api_admin_automation_conversion_workflow_registry"),
        "dashboard": url_for("api.api_admin_automation_conversion_dashboard"),
        "workflows": url_for("api.api_admin_automation_conversion_workflows"),
        "workflow_detail_base": url_for("api.api_admin_automation_conversion_workflow_detail", workflow_id=0),
        "workflow_summary_base": url_for("api.api_admin_automation_conversion_workflow_summary", workflow_id=0),
        "workflow_activate_base": url_for("api.api_admin_automation_conversion_workflow_activate", workflow_id=0),
        "workflow_pause_base": url_for("api.api_admin_automation_conversion_workflow_pause", workflow_id=0),
        "workflow_delete_base": url_for("api.api_admin_automation_conversion_workflow_delete", workflow_id=0),
        "workflow_nodes_base": url_for("api.api_admin_automation_conversion_workflow_nodes", workflow_id=0),
        "workflow_node_base": url_for("api.api_admin_automation_conversion_workflow_node_update", node_id=0),
        "agents_options": url_for("api.api_admin_automation_conversion_agent_options", enabled_only=0),
        "profile_segment_templates_options": url_for("api.api_admin_automation_conversion_profile_segment_template_options", enabled_only=0),
        "profile_segment_templates_catalog": url_for("api.api_admin_automation_conversion_profile_segment_catalog"),
        "profile_segment_template_detail_base": url_for("api.api_admin_automation_conversion_profile_segment_template_detail", template_id=0),
        "executions": url_for("api.api_admin_automation_conversion_execution_batches"),
        "execution_detail_base": url_for("api.api_admin_automation_conversion_execution_detail", execution_id=0),
        "jobs_run_due": url_for("api.api_admin_automation_conversion_jobs_run_due"),
    }


def _operations_page_entry_urls() -> dict[str, str]:
    return {
        "list": url_for("api.admin_automation_conversion_operations"),
        "workflow_new": url_for("api.admin_automation_conversion_workflow_new"),
        "workflow_edit_base": url_for("api.admin_automation_conversion_workflow_edit", workflow_id=0),
        "workflow_nodes_base": url_for("api.admin_automation_conversion_workflow_nodes", workflow_id=0),
        "executions": url_for("api.admin_automation_conversion_execution_records"),
    }


def _build_operations_list_workspace() -> dict[str, object]:
    return {
        "page_mode": "list",
        "api_urls": _operations_page_api_urls(),
        "entry_urls": _operations_page_entry_urls(),
        "action_urls": {
            "workflow_new": url_for("api.admin_automation_conversion_workflow_new"),
            "execution_records": url_for("api.admin_automation_conversion_execution_records"),
        },
    }


def _build_workflow_editor_workspace(workflow_id: int | None = None) -> dict[str, object]:
    normalized_workflow_id = int(workflow_id or 0) or None
    page_mode = "workflow_edit" if normalized_workflow_id else "workflow_new"
    return {
        "page_mode": page_mode,
        "selected_workflow_id": normalized_workflow_id,
        "api_urls": _operations_page_api_urls(),
        "entry_urls": _operations_page_entry_urls(),
        "action_urls": {
            "list": url_for("api.admin_automation_conversion_operations"),
            "workflow_edit": url_for("api.admin_automation_conversion_workflow_edit", workflow_id=normalized_workflow_id or 0),
            "workflow_nodes": url_for("api.admin_automation_conversion_workflow_nodes", workflow_id=normalized_workflow_id or 0),
            "execution_records": url_for("api.admin_automation_conversion_execution_records"),
        },
    }


def _build_workflow_nodes_workspace(workflow_id: int) -> dict[str, object]:
    normalized_workflow_id = int(workflow_id or 0) or None
    return {
        "page_mode": "nodes",
        "selected_workflow_id": normalized_workflow_id,
        "api_urls": _operations_page_api_urls(),
        "entry_urls": _operations_page_entry_urls(),
        "action_urls": {
            "list": url_for("api.admin_automation_conversion_operations"),
            "workflow_edit": url_for("api.admin_automation_conversion_workflow_edit", workflow_id=normalized_workflow_id or 0),
            "execution_records": url_for("api.admin_automation_conversion_execution_records"),
        },
    }


def _build_execution_records_workspace() -> dict[str, object]:
    workflow_id = _query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None
    execution_id = _query_int("execution_id", default=0, minimum=0, maximum=100000000) or None
    return {
        "page_mode": "executions",
        "selected_workflow_id": workflow_id,
        "selected_execution_id": execution_id,
        "api_urls": _operations_page_api_urls(),
        "entry_urls": _operations_page_entry_urls(),
        "action_urls": {
            "list": url_for("api.admin_automation_conversion_operations"),
            "workflow_edit": url_for("api.admin_automation_conversion_workflow_edit", workflow_id=workflow_id or 0),
            "workflow_nodes": url_for("api.admin_automation_conversion_workflow_nodes", workflow_id=workflow_id or 0),
            "execution_item_bazhuayu_send_base": url_for(
                "api.api_admin_automation_conversion_execution_item_send_via_bazhuayu",
                execution_item_id=0,
            ),
        },
    }


def _build_overview_workspace() -> dict[str, object]:
    return {
        "api_urls": {
            "dashboard": url_for("api.api_admin_automation_conversion_dashboard"),
            "message_activity_sync_run": url_for("api.admin_automation_conversion_run_message_activity_sync"),
            "reply_monitor_capture": url_for("api.admin_automation_conversion_reply_monitor_capture"),
            "reply_monitor_run_due": url_for("api.admin_automation_conversion_reply_monitor_run_due"),
        },
    }


def _build_auto_reply_workspace() -> dict[str, object]:
    overview_payload = get_overview_payload()
    reply_monitor = dict(overview_payload.get("reply_monitor") or {})
    agent_config_bundle = list_agent_configs()
    return {
        "reply_monitor": reply_monitor,
        "message_activity_sync": dict(overview_payload.get("message_activity_sync") or {}),
        "agent_configs": list(agent_config_bundle.get("items") or []),
        "agent_config_total": int(agent_config_bundle.get("total") or 0),
        "agent_config_href": url_for("api.admin_automation_conversion_agent_config"),
        "action_urls": {
            "toggle": url_for("api.admin_automation_conversion_reply_monitor_toggle"),
            "capture": url_for("api.admin_automation_conversion_reply_monitor_capture"),
            "run_due": url_for("api.admin_automation_conversion_reply_monitor_run_due"),
        },
        "api_urls": {
            "review_outputs": url_for("api.api_admin_automation_conversion_review_outputs"),
            "review_output_base": url_for("api.api_admin_automation_conversion_review_output", output_id="__OUTPUT_ID__"),
        },
    }


def _build_agent_config_workspace() -> dict[str, object]:
    initial_templates = list(list_conversion_profile_segment_templates(enabled_only=False).get("items") or [])
    initial_catalog = list(list_conversion_profile_segment_catalog().get("items") or [])
    return {
        "api_urls": {
            "registry": url_for("api.api_admin_automation_conversion_workflow_registry"),
            "agents_options": url_for("api.api_admin_automation_conversion_agent_options", enabled_only=0),
            "agent_create": url_for("api.api_admin_automation_conversion_agent_create"),
            "agent_detail_base": url_for("api.api_admin_automation_conversion_agent_detail", agent_code="__AGENT_CODE__"),
            "agent_draft_base": url_for("api.api_admin_automation_conversion_agent_draft", agent_code="__AGENT_CODE__"),
            "agent_publish_base": url_for("api.api_admin_automation_conversion_agent_publish", agent_code="__AGENT_CODE__"),
            "default_channel_settings": url_for("api.api_admin_automation_conversion_default_channel_settings"),
            "default_channel_generate_qr": url_for("api.api_admin_automation_conversion_default_channel_generate_qr"),
            "model_settings": url_for("api.api_admin_automation_conversion_model_settings"),
            "model_settings_test": url_for("api.api_admin_automation_conversion_model_settings_test"),
            "profile_segment_templates": url_for("api.api_admin_automation_conversion_profile_segment_templates", enabled_only=0),
            "profile_segment_template_detail_base": url_for("api.api_admin_automation_conversion_profile_segment_template_detail", template_id=0),
            "profile_segment_template_catalog": url_for("api.api_admin_automation_conversion_profile_segment_catalog"),
        },
        "entry_urls": {
            "operations": url_for("api.admin_automation_conversion_operations"),
            "auto_reply": url_for("api.admin_automation_conversion_auto_reply"),
        },
        "selected_template_id": _query_int("template_id", default=0, minimum=0, maximum=100000000) or None,
        "available_agents": list(list_conversion_agent_options(enabled_only=False).get("items") or []),
        "initial_templates": initial_templates,
        "initial_template_catalog": initial_catalog,
    }


def _automation_conversion_workspace_tabs(active_key: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in _AUTOMATION_CONVERSION_WORKSPACE_TABS:
        items.append(
            {
                **item,
                "href": url_for(str(item["endpoint"]), **dict(item.get("params") or {})),
                "active": item["key"] == active_key,
            }
        )
    return items


def _wants_json_response() -> bool:
    accept = str(request.headers.get("Accept") or "").lower()
    requested_with = str(request.headers.get("X-Requested-With") or "").strip()
    return "application/json" in accept or requested_with == "XMLHttpRequest"


def _json_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _render_overview_page(*, page_error: str = ""):
    return _render_admin_template(
        "automation_conversion_overview_workspace.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="先看四个一级入口、当前运行状态和任务流执行摘要，再进入对应工作面处理。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
        workspace_tabs=_automation_conversion_workspace_tabs("overview"),
        overview_workspace=_build_overview_workspace(),
        page_notice=_overview_notice(),
        page_error=page_error,
        show_shell_meta=False,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_operations_page(*, page_error: str = ""):
    return _render_admin_template(
        "automation_conversion_operations_workspace.html",
        active_nav="automation_conversion",
        page_title="自动化运营",
        page_summary="模块内自动化运营工作面，先统一任务流、节点和执行入口，不再暴露旧运营概念。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动化运营", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("operations"),
        operations_workspace=_build_operations_list_workspace(),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        page_notice="当前页面只保留自动化运营列表和一级入口。",
    )


def _render_workflow_editor_page(*, workflow_id: int | None = None, page_error: str = ""):
    is_new = int(workflow_id or 0) <= 0
    return _render_admin_template(
        "automation_conversion_workflow_editor.html",
        active_nav="automation_conversion",
        page_title="新建任务流" if is_new else "编辑任务流",
        page_summary="任务流层只负责适用人群、发给谁、怎么发、生成方式和 Agent 绑定，不再和节点配置混排。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动化运营", url_for("api.admin_automation_conversion_operations")),
            ("新建任务流" if is_new else "编辑任务流", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("operations"),
        operations_workspace=_build_workflow_editor_workspace(workflow_id=workflow_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        page_notice="当前页面只承载任务流编辑骨架。",
    )


def _render_workflow_nodes_page(*, workflow_id: int, page_error: str = ""):
    return _render_admin_template(
        "automation_conversion_workflow_nodes.html",
        active_nav="automation_conversion",
        page_title="节点配置",
        page_summary="节点层只负责节点名称、目标人群、触发方式和节点内容；任务流配置不再与节点编辑混排。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动化运营", url_for("api.admin_automation_conversion_operations")),
            ("节点配置", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("operations"),
        operations_workspace=_build_workflow_nodes_workspace(workflow_id=workflow_id),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        page_notice="当前页面只承载节点配置骨架。",
    )


def _render_execution_records_page(*, page_error: str = ""):
    return _render_admin_template(
        "automation_conversion_execution_records.html",
        active_nav="automation_conversion",
        page_title="执行记录",
        page_summary="执行记录页只看批次与单用户执行明细，不再和任务流编辑、节点配置混排。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动化运营", url_for("api.admin_automation_conversion_operations")),
            ("执行记录", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("operations"),
        operations_workspace=_build_execution_records_workspace(),
        admin_action_token=ensure_admin_console_action_token(),
        page_error=page_error,
        page_notice="当前页面只承载执行记录骨架。",
    )


def _render_auto_reply_page(*, page_error: str = "", page_notice: str = ""):
    return _render_admin_template(
        "automation_conversion_auto_reply_workspace.html",
        active_nav="automation_conversion",
        page_title="自动化应答",
        page_summary="复用现有自动化应答链路，只在模块内补稳定入口和状态壳子，不重做应答业务逻辑。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动化应答", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("auto_reply"),
        auto_reply_workspace=_build_auto_reply_workspace(),
        page_error=page_error,
        page_notice=page_notice,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_agent_config_page(*, page_error: str = ""):
    return _render_admin_template(
        "automation_conversion_agent_config_workspace.html",
        active_nav="automation_conversion",
        page_title="模型 / Agent 配置",
        page_summary="当前页面已经收口成自动化转化模块的底层配置工作台：Agent 编排、分层模板、欢迎语 / 二维码和大模型配置统一都从这里维护。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("模型 / Agent 配置", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("agent_config"),
        agent_config_workspace=_build_agent_config_workspace(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def admin_automation_conversion():
    return _render_overview_page()


def admin_automation_conversion_overview():
    return _render_overview_page()


def admin_automation_conversion_operations():
    return _render_operations_page()


def admin_automation_conversion_workflow_new():
    return _render_workflow_editor_page()


def admin_automation_conversion_workflow_edit(workflow_id: int):
    return _render_workflow_editor_page(workflow_id=workflow_id)


def admin_automation_conversion_workflow_nodes(workflow_id: int):
    return _render_workflow_nodes_page(workflow_id=workflow_id)


def admin_automation_conversion_execution_records():
    return _render_execution_records_page()


def admin_automation_conversion_auto_reply():
    return _render_auto_reply_page()


def admin_automation_conversion_agent_config():
    return _render_agent_config_page()


def admin_automation_conversion_flow_design():
    return _redirect_to("api.admin_automation_conversion_operations")


def admin_automation_conversion_member_ops():
    return _redirect_to("api.admin_automation_conversion_operations")


def admin_automation_conversion_run_center():
    return _redirect_to("api.admin_automation_conversion_agent_config", **request.args.to_dict(flat=True))


def admin_automation_conversion_reply_monitor_toggle():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_auto_reply_page(page_error=action_token_error)
    enabled = _json_bool(request.form.get("enabled") or request.values.get("enabled"))
    try:
        save_reply_monitor_enabled(enabled=enabled, operator_id=_operator_from_request())
    except ValueError as exc:
        return _render_auto_reply_page(page_error=str(exc))
    return redirect(
        url_for(
            "api.admin_automation_conversion_auto_reply",
            reply_monitor="enabled" if enabled else "disabled",
        ),
        code=302,
    )


def admin_automation_conversion_reply_monitor_capture():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if _wants_json_response():
        status = str(result.get("status") or "").strip()
        ok = bool(result.get("ok")) or status in {"disabled", "idle", "throttled", "quiet_hours"}
        status_code = 200 if ok else 400
        return (
            jsonify(
                {
                    "ok": ok,
                    "status": status,
                    "message": str(result.get("message") or result.get("error") or "自动接话扫描已完成"),
                    "result": result,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_auto_reply", reply_monitor="captured"),
            code=302,
        )
    return _render_auto_reply_page(page_error=str(result.get("error") or "自动接话监控扫描失败"))


def admin_automation_conversion_reply_monitor_run_due():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_auto_reply_page(page_error=action_token_error)
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if _wants_json_response():
        status = str(result.get("status") or "").strip()
        ok = bool(result.get("ok")) or status in {"disabled", "idle", "throttled", "quiet_hours"}
        status_code = 200 if ok else 400
        return (
            jsonify(
                {
                    "ok": ok,
                    "status": status,
                    "message": str(result.get("message") or result.get("error") or "自动接话放行已完成"),
                    "result": result,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_auto_reply", reply_monitor="dispatched"),
            code=302,
        )
    return _render_auto_reply_page(page_error=str(result.get("error") or "自动接话监控放行失败"))


def admin_automation_conversion_run_message_activity_sync():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_overview_page(page_error=action_token_error)
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="user",
        trigger_source="manual",
    )
    if _wants_json_response():
        overview_payload = get_overview_payload()
        message_activity_sync = dict(overview_payload.get("message_activity_sync") or {})
        status_code = 200 if result.get("ok") else 400
        return (
            jsonify(
                {
                    "ok": bool(result.get("ok")),
                    "message": "消息活跃同步已完成" if result.get("ok") else str(result.get("error") or "消息活跃同步失败"),
                    "run": result.get("run") or {},
                    "message_activity_sync": message_activity_sync,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_overview", message_activity_sync=1),
            code=302,
        )
    if result.get("status") == "not_configured":
        missing_keys = "、".join(result.get("missing_keys") or [])
        return _render_overview_page(page_error=f"消息库尚未配置，请先补齐 {missing_keys}")
    return _render_overview_page(page_error=str(result.get("error") or "消息活跃同步失败"))


def api_admin_automation_conversion_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "detail": get_member_detail(external_contact_id=external_contact_id, phone=phone)})


def _json_action_payload() -> dict[str, str]:
    payload = request.get_json(silent=True) or {}
    return {
        "external_contact_id": str(payload.get("external_contact_id") or "").strip(),
        "phone": str(payload.get("phone") or "").strip(),
        "operator_id": _operator_from_request(),
    }


def _run_member_action(action_fn):
    payload = _json_action_payload()
    try:
        result = action_fn(**payload)
        return jsonify({"ok": True, **result})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_put_in_pool():
    return _run_member_action(put_in_pool)


def api_admin_automation_conversion_remove_from_pool():
    return _run_member_action(remove_from_pool)


def api_admin_automation_conversion_set_focus():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="focus"))


def api_admin_automation_conversion_set_normal():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="normal"))


def api_admin_automation_conversion_mark_won():
    return _run_member_action(mark_won)


def api_admin_automation_conversion_unmark_won():
    return _run_member_action(unmark_won)


def api_admin_automation_conversion_push_openclaw():
    payload = _json_action_payload()
    try:
        result = push_openclaw(**payload)
        if result.get("accepted"):
            return jsonify({"ok": True, **result}), 202
        if result.get("status") == "cooldown_blocked":
            return jsonify({"ok": False, "error": f"OpenClaw 冷却中，还剩 {result.get('remaining_seconds') or 0} 秒", **result}), 429
        return jsonify({"ok": False, "error": str(result.get("error") or "OpenClaw 推送失败"), **result}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_agent_options():
    return jsonify(
        {
            "ok": True,
            **list_conversion_agent_options(
                enabled_only=_query_bool("enabled_only", default=True),
            ),
        }
    )


def api_admin_automation_conversion_agent_detail(agent_code: str):
    try:
        payload = get_agent_config_detail(agent_code)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "item": payload})


def api_admin_automation_conversion_agent_create():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = create_agent_config(
            payload,
            operator_id=_operator_from_request(),
            source="automation_conversion_agent_config",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_agent_draft(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = save_agent_config_draft(
            agent_code,
            payload,
            operator_id=_operator_from_request(),
            source="automation_conversion_agent_config",
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_agent_publish(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        result = publish_agent_config(
            agent_code,
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_default_channel_settings():
    return jsonify({"ok": True, **get_default_channel_settings_payload()})


def api_admin_automation_conversion_default_channel_settings_save():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = save_default_channel_settings(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_default_channel_generate_qr():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    result = generate_default_channel_qr(operator=_operator_from_request())
    status_code = int(result.get("status_code") or (200 if result.get("generated") else 400))
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_conversion_model_settings():
    return jsonify({"ok": True, **get_model_infra_payload(limit_logs=10)})


def api_admin_automation_conversion_model_settings_save():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    payload = request.get_json(silent=True) or {}
    try:
        result = save_model_infra_settings(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_model_settings_test():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    result = test_model_infra_connection()
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


def api_admin_automation_conversion_profile_segment_catalog():
    return jsonify({"ok": True, **list_conversion_profile_segment_catalog()})


def api_admin_automation_conversion_profile_segment_templates():
    payload = list_conversion_profile_segment_templates(enabled_only=_query_bool("enabled_only", default=False))
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_profile_segment_template_detail(template_id: int):
    try:
        payload = get_conversion_profile_segment_template_bundle(int(template_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "template_bundle": payload, **payload})


def api_admin_automation_conversion_profile_segment_template_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_profile_segment_template(payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_profile_segment_template_update(template_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_profile_segment_template(int(template_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_registry():
    return jsonify({"ok": True, **list_conversion_workflow_registry()})


def api_admin_automation_conversion_workflows():
    payload = list_conversion_workflows(
        include_archived=_query_bool("include_archived", default=False),
        status=_query_text("status"),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_workflow_detail(workflow_id: int):
    try:
        payload = get_conversion_workflow_model_bundle(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "workflow_bundle": payload})


def api_admin_automation_conversion_dashboard():
    return jsonify({"ok": True, "dashboard": get_conversion_dashboard_payload()})


def api_admin_automation_conversion_workflow_summary(workflow_id: int):
    try:
        payload = get_conversion_workflow_detail_summary(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "summary": payload})


def api_admin_automation_conversion_workflow_create():
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_workflow(payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflow_update(workflow_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_workflow(int(workflow_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_activate(workflow_id: int):
    try:
        result = activate_conversion_workflow(int(workflow_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_pause(workflow_id: int):
    try:
        result = pause_conversion_workflow(int(workflow_id), operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_delete(workflow_id: int):
    try:
        result = delete_conversion_workflow(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_nodes(workflow_id: int):
    try:
        payload = list_conversion_workflow_nodes(int(workflow_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_workflow_node_create(workflow_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = create_conversion_workflow_node(int(workflow_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_workflow_node_update(node_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        result = update_conversion_workflow_node(int(node_id), payload, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_workflow_node_delete(node_id: int):
    try:
        result = delete_conversion_workflow_node(int(node_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_execution_batches():
    try:
        payload = list_conversion_workflow_execution_records(
            workflow_id=_query_int("workflow_id", default=0, minimum=0, maximum=100000000) or None,
            node_id=_query_int("node_id", default=0, minimum=0, maximum=100000000) or None,
            limit=_query_int("limit", default=20, minimum=1, maximum=100),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_detail(execution_id: int):
    try:
        payload = get_conversion_workflow_execution_detail(int(execution_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_items(execution_id: int):
    try:
        payload = list_conversion_workflow_execution_items(int(execution_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_item_detail(execution_item_id: int):
    try:
        payload = get_conversion_workflow_execution_item_detail(int(execution_item_id))
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_execution_item_send_via_bazhuayu(execution_item_id: int):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return jsonify({"ok": False, "error": action_token_error}), 400
    try:
        payload = send_conversion_execution_item_via_bazhuayu(
            int(execution_item_id),
            operator_id=_operator_from_request(),
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502
    return jsonify(payload)


def api_admin_automation_conversion_profile_segment_template_options():
    return jsonify(
        {
            "ok": True,
            **list_conversion_profile_segment_template_options(
                enabled_only=_query_bool("enabled_only", default=True),
            ),
        }
    )


def api_admin_automation_conversion_review_outputs():
    payload = list_recent_reviewable_agent_outputs(
        limit=_query_int("limit", default=20, minimum=1, maximum=50),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_review_output(output_id: str):
    payload = request.get_json(silent=True) or {}
    decision = _query_text("decision") or str(payload.get("decision") or "").strip()
    review_note = str(payload.get("review_note") or request.values.get("review_note") or "").strip()
    normalized_decision = decision.lower()
    is_rejected = normalized_decision in {"reject", "rejected", "not_adopted", "declined"}
    if is_rejected and not review_note:
        return jsonify({"ok": False, "error": "review_note is required when decision is rejected"}), 400
    try:
        reviewed_output = review_agent_reply_output(
            output_id,
            decision=decision,
            operator_id=_operator_from_request(),
            review_note=review_note,
            source="automation_conversion_auto_reply",
        )
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    response_payload = {
        "ok": True,
        "reviewed_output": reviewed_output,
    }
    if is_rejected:
        response_payload["clipboard_text"] = build_rejected_feedback_clipboard_payload(
            output_id,
            not_adopted_reason=review_note,
        )
    return jsonify(response_payload)


def api_admin_automation_conversion_run_message_activity_sync():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="system",
        trigger_source=str(payload.get("trigger_source") or request.values.get("trigger_source") or "scheduled").strip() or "scheduled",
    )
    if result.get("ok"):
        status_code = 200
    elif result.get("status") == "not_configured":
        status_code = 400
    else:
        status_code = 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_capture():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 500),
    )
    status_code = 200 if result.get("ok") or result.get("status") == "disabled" else 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 20),
    )
    status_code = 200 if result.get("ok") or result.get("status") in {"disabled", "idle", "throttled", "quiet_hours"} else 502
    return jsonify(result), status_code


def api_internal_automation_conversion_lobster_results():
    auth_failure = require_internal_api_token(token_keys=("AUTOMATION_LOBSTER_CALLBACK_TOKEN",), require_configured=True)
    if auth_failure is not None:
        return auth_failure
    body_text = request.get_data(cache=True, as_text=True) or ""
    signature_ok, signature_error = validate_router_callback_signature(body_text=body_text, headers=dict(request.headers))
    if not signature_ok:
        return jsonify({"ok": False, "error": signature_error}), 401
    payload = request.get_json(silent=True) or {}
    result = handle_agent_router_callback(payload)
    if result.get("ok") and result.get("status") in {"applied", "idempotent"}:
        return jsonify(result), 200
    if result.get("status") == "rejected":
        status_code = 404 if result.get("error") == "request_not_found" else 409
        return jsonify(result), status_code
    return jsonify(result), 400


def api_internal_automation_conversion_router_test_dispatch():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_test_dispatch(
        external_contact_id=str(payload.get("external_contact_id") or request.values.get("external_contact_id") or "").strip(),
        phone=str(payload.get("phone") or request.values.get("phone") or "").strip(),
        operator_id=str(payload.get("operator") or _operator_from_request() or "").strip(),
        mode=str(payload.get("mode") or request.values.get("mode") or "").strip(),
        force_capture=_json_bool(payload.get("force_capture")) or str(request.values.get("force_capture") or "").strip().lower() in {"1", "true", "yes", "on"},
        force_run_due=_json_bool(payload.get("force_run_due")) or str(request.values.get("force_run_due") or "").strip().lower() in {"1", "true", "yes", "on"},
    )
    status_code = 200 if result.get("ok") else (404 if result.get("error") == "member_not_found" else 409)
    return jsonify(result), status_code


def api_admin_automation_conversion_jobs_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    try:
        result = run_registered_due_jobs(
            job_codes=list(payload.get("jobs") or []),
            operator_id=_operator_from_request(),
            operator_type="system",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def register_routes(bp):
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/overview", methods=["GET"])(admin_automation_conversion_overview)
    bp.route("/admin/automation-conversion/operations", methods=["GET"])(admin_automation_conversion_operations)
    bp.route("/admin/automation-conversion/operations/workflows/new", methods=["GET"])(admin_automation_conversion_workflow_new)
    bp.route("/admin/automation-conversion/operations/workflows/<int:workflow_id>/edit", methods=["GET"])(admin_automation_conversion_workflow_edit)
    bp.route("/admin/automation-conversion/operations/workflows/<int:workflow_id>/nodes", methods=["GET"])(admin_automation_conversion_workflow_nodes)
    bp.route("/admin/automation-conversion/operations/executions", methods=["GET"])(admin_automation_conversion_execution_records)
    bp.route("/admin/automation-conversion/auto-reply", methods=["GET"])(admin_automation_conversion_auto_reply)
    bp.route("/admin/automation-conversion/agent-config", methods=["GET"])(admin_automation_conversion_agent_config)
    bp.route("/admin/automation-conversion/flow-design", methods=["GET"])(admin_automation_conversion_flow_design)
    bp.route("/admin/automation-conversion/member-ops", methods=["GET"])(admin_automation_conversion_member_ops)
    bp.route("/admin/automation-conversion/run-center", methods=["GET"])(admin_automation_conversion_run_center)
    bp.route("/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(admin_automation_conversion_run_message_activity_sync)
    bp.route("/admin/automation-conversion/reply-monitor/toggle", methods=["POST"])(admin_automation_conversion_reply_monitor_toggle)
    bp.route("/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(admin_automation_conversion_reply_monitor_capture)
    bp.route("/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(admin_automation_conversion_reply_monitor_run_due)

    bp.route("/api/admin/automation-conversion/member", methods=["GET"])(api_admin_automation_conversion_member)
    bp.route("/api/admin/automation-conversion/member/put-in-pool", methods=["POST"])(api_admin_automation_conversion_put_in_pool)
    bp.route("/api/admin/automation-conversion/member/remove-from-pool", methods=["POST"])(api_admin_automation_conversion_remove_from_pool)
    bp.route("/api/admin/automation-conversion/member/set-focus", methods=["POST"])(api_admin_automation_conversion_set_focus)
    bp.route("/api/admin/automation-conversion/member/set-normal", methods=["POST"])(api_admin_automation_conversion_set_normal)
    bp.route("/api/admin/automation-conversion/member/mark-won", methods=["POST"])(api_admin_automation_conversion_mark_won)
    bp.route("/api/admin/automation-conversion/member/unmark-won", methods=["POST"])(api_admin_automation_conversion_unmark_won)
    bp.route("/api/admin/automation-conversion/member/push-openclaw", methods=["POST"])(api_admin_automation_conversion_push_openclaw)
    bp.route("/api/admin/automation-conversion/dashboard", methods=["GET"])(api_admin_automation_conversion_dashboard)
    bp.route("/api/admin/automation-conversion/agents", methods=["POST"])(api_admin_automation_conversion_agent_create)
    bp.route("/api/admin/automation-conversion/agents/options", methods=["GET"])(api_admin_automation_conversion_agent_options)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>", methods=["GET"])(api_admin_automation_conversion_agent_detail)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>/draft", methods=["POST"])(api_admin_automation_conversion_agent_draft)
    bp.route("/api/admin/automation-conversion/agents/<agent_code>/publish", methods=["POST"])(api_admin_automation_conversion_agent_publish)
    bp.route("/api/admin/automation-conversion/default-channel-settings", methods=["GET"])(api_admin_automation_conversion_default_channel_settings)
    bp.route("/api/admin/automation-conversion/default-channel-settings", methods=["PUT"])(api_admin_automation_conversion_default_channel_settings_save)
    bp.route("/api/admin/automation-conversion/default-channel-settings/generate-qr", methods=["POST"])(api_admin_automation_conversion_default_channel_generate_qr)
    bp.route("/api/admin/automation-conversion/model-settings", methods=["GET"])(api_admin_automation_conversion_model_settings)
    bp.route("/api/admin/automation-conversion/model-settings", methods=["PUT"])(api_admin_automation_conversion_model_settings_save)
    bp.route("/api/admin/automation-conversion/model-settings/test", methods=["POST"])(api_admin_automation_conversion_model_settings_test)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/catalog", methods=["GET"])(api_admin_automation_conversion_profile_segment_catalog)
    bp.route("/api/admin/automation-conversion/profile-segment-templates", methods=["GET"])(api_admin_automation_conversion_profile_segment_templates)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/options", methods=["GET"])(api_admin_automation_conversion_profile_segment_template_options)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", methods=["GET"])(api_admin_automation_conversion_profile_segment_template_detail)
    bp.route("/api/admin/automation-conversion/profile-segment-templates", methods=["POST"])(api_admin_automation_conversion_profile_segment_template_create)
    bp.route("/api/admin/automation-conversion/profile-segment-templates/<int:template_id>", methods=["PUT"])(api_admin_automation_conversion_profile_segment_template_update)
    bp.route("/api/admin/automation-conversion/review-outputs", methods=["GET"])(api_admin_automation_conversion_review_outputs)
    bp.route("/api/admin/automation-conversion/review-outputs/<output_id>/review", methods=["POST"])(api_admin_automation_conversion_review_output)
    bp.route("/api/admin/automation-conversion/workflows/registry", methods=["GET"])(api_admin_automation_conversion_workflow_registry)
    bp.route("/api/admin/automation-conversion/workflows", methods=["GET"])(api_admin_automation_conversion_workflows)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["GET"])(api_admin_automation_conversion_workflow_detail)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/summary", methods=["GET"])(api_admin_automation_conversion_workflow_summary)
    bp.route("/api/admin/automation-conversion/workflows", methods=["POST"])(api_admin_automation_conversion_workflow_create)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["PUT"])(api_admin_automation_conversion_workflow_update)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>", methods=["DELETE"])(api_admin_automation_conversion_workflow_delete)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/activate", methods=["POST"])(api_admin_automation_conversion_workflow_activate)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/pause", methods=["POST"])(api_admin_automation_conversion_workflow_pause)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", methods=["GET"])(api_admin_automation_conversion_workflow_nodes)
    bp.route("/api/admin/automation-conversion/workflows/<int:workflow_id>/nodes", methods=["POST"])(api_admin_automation_conversion_workflow_node_create)
    bp.route("/api/admin/automation-conversion/workflow-nodes/<int:node_id>", methods=["PUT"])(api_admin_automation_conversion_workflow_node_update)
    bp.route("/api/admin/automation-conversion/workflow-nodes/<int:node_id>", methods=["DELETE"])(api_admin_automation_conversion_workflow_node_delete)
    bp.route("/api/admin/automation-conversion/executions", methods=["GET"])(api_admin_automation_conversion_execution_batches)
    bp.route("/api/admin/automation-conversion/executions/<int:execution_id>", methods=["GET"])(api_admin_automation_conversion_execution_detail)
    bp.route("/api/admin/automation-conversion/executions/<int:execution_id>/items", methods=["GET"])(api_admin_automation_conversion_execution_items)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>", methods=["GET"])(api_admin_automation_conversion_execution_item_detail)
    bp.route("/api/admin/automation-conversion/execution-items/<int:execution_item_id>/send-via-bazhuayu", methods=["POST"])(api_admin_automation_conversion_execution_item_send_via_bazhuayu)
    bp.route("/api/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(api_admin_automation_conversion_run_message_activity_sync)
    bp.route("/api/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(api_admin_automation_conversion_reply_monitor_capture)
    bp.route("/api/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(api_admin_automation_conversion_reply_monitor_run_due)
    bp.route("/api/internal/automation-conversion/lobster-results", methods=["POST"])(api_internal_automation_conversion_lobster_results)
    bp.route("/api/internal/automation-conversion/router-test-dispatch", methods=["POST"])(api_internal_automation_conversion_router_test_dispatch)
    bp.route("/api/admin/automation-conversion/jobs/run-due", methods=["POST"])(api_admin_automation_conversion_jobs_run_due)
