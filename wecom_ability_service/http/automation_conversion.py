from __future__ import annotations

import json

from flask import jsonify, redirect, request, url_for

from ..domains.automation_conversion import (
    generate_default_channel_qr,
    get_debug_payload,
    get_member_detail,
    get_overview_payload,
    get_settings_payload,
    get_stage_detail_payload,
    mark_won,
    put_in_pool,
    push_openclaw,
    remove_from_pool,
    save_settings,
    set_follow_type,
    unmark_won,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_int(name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _parse_question_rules_json(raw_value: str) -> list[dict]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("关键题规则 JSON 格式不正确") from exc
    if not isinstance(parsed, list):
        raise ValueError("关键题规则必须是数组")
    return parsed


def _build_settings_form_payload() -> dict[str, object]:
    return {
        "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
        "questionnaire_id": request.form.get("questionnaire_id"),
        "core_threshold": request.form.get("core_threshold"),
        "top_threshold": request.form.get("top_threshold"),
        "quiet_hour_start": request.form.get("quiet_hour_start"),
        "timezone": request.form.get("timezone"),
        "silent_threshold_days_by_pool": {
            "new_user": request.form.get("silent_threshold_new_user"),
            "inactive_normal": request.form.get("silent_threshold_inactive_normal"),
            "inactive_focus": request.form.get("silent_threshold_inactive_focus"),
            "active_normal": request.form.get("silent_threshold_active_normal"),
            "active_focus": request.form.get("silent_threshold_active_focus"),
        },
        "question_rules": _parse_question_rules_json(request.form.get("question_rules_json", "")),
    }


def admin_automation_conversion():
    overview_payload = get_overview_payload()
    return _render_admin_template(
        "automation_conversion.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
        overview_payload=overview_payload,
    )


def admin_automation_conversion_stage_detail(stage_key: str):
    try:
        payload = get_stage_detail_payload(
            route_key=stage_key,
            keyword=_query_text("keyword"),
            offset=_query_int("offset", default=0, minimum=0, maximum=100000),
            limit=_query_int("limit", default=50, minimum=1, maximum=100),
        )
    except ValueError:
        return _render_admin_template(
            "placeholder.html",
            active_nav="automation_conversion",
            page_title="阶段不存在",
            page_summary="当前阶段不存在，请返回自动化转化首页重新选择。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("自动化转化", url_for("api.admin_automation_conversion")),
                ("阶段不存在", None),
            ),
            actions=[{"label": "返回自动化转化首页", "href": url_for("api.admin_automation_conversion"), "variant": "secondary"}],
            state_title="阶段不存在",
            state_body="请检查链接是否正确。",
            state_items=["支持查看：新用户池、未激活普通池、未激活重点跟进池、激活普通池、激活重点跟进池、沉默池、已成交。"],
            page_error="未找到对应阶段",
        ), 404
    return _render_admin_template(
        "automation_conversion_stage.html",
        active_nav="automation_conversion",
        page_title=f"{payload['stage']['label']}客户",
        page_summary="按阶段查看自动化成员名单。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            (payload["stage"]["label"], None),
        ),
        stage_payload=payload,
    )


def admin_automation_conversion_settings():
    payload = get_settings_payload()
    return _render_admin_template(
        "automation_conversion_settings.html",
        active_nav="automation_conversion",
        page_title="自动化转化设置",
        page_summary="把问卷、关键题、沉默规则和默认二维码统一放到设置页维护。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("设置", None),
        ),
        settings_payload=payload,
        question_rules_json=json.dumps(payload["config"].get("question_rules") or [], ensure_ascii=False, indent=2),
        page_notice="设置已保存" if _query_text("saved") == "1" else ("默认渠道二维码已更新" if _query_text("channel_saved") == "1" else ""),
    )


def admin_automation_conversion_save_settings():
    try:
        save_settings(_build_settings_form_payload())
        return redirect(url_for("api.admin_automation_conversion_settings", saved=1), code=302)
    except ValueError as exc:
        payload = get_settings_payload()
        return _render_admin_template(
            "automation_conversion_settings.html",
            active_nav="automation_conversion",
            page_title="自动化转化设置",
            page_summary="把问卷、关键题、沉默规则和默认二维码统一放到设置页维护。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("自动化转化", url_for("api.admin_automation_conversion")),
                ("设置", None),
            ),
            settings_payload=payload,
            question_rules_json=request.form.get("question_rules_json", ""),
            page_error=str(exc),
        )


def admin_automation_conversion_generate_default_channel():
    result = generate_default_channel_qr(operator=_operator_from_request())
    if result.get("generated"):
        return redirect(url_for("api.admin_automation_conversion_settings", channel_saved=1), code=302)
    payload = get_settings_payload()
    return _render_admin_template(
        "automation_conversion_settings.html",
        active_nav="automation_conversion",
        page_title="自动化转化设置",
        page_summary="把问卷、关键题、沉默规则和默认二维码统一放到设置页维护。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("设置", None),
        ),
        settings_payload=payload,
        question_rules_json=json.dumps(payload["config"].get("question_rules") or [], ensure_ascii=False, indent=2),
        page_error=str(result.get("error") or "默认渠道二维码生成失败"),
    )


def admin_automation_conversion_debug():
    payload = None
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if external_contact_id or phone:
        payload = get_debug_payload(external_contact_id=external_contact_id, phone=phone)
    return _render_admin_template(
        "automation_conversion_debug.html",
        active_nav="automation_conversion",
        page_title="自动化转化调试",
        page_summary="单客试算与状态诊断已经迁到这个管理员调试页。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("调试", None),
        ),
        debug_payload=payload,
    )


def admin_automation_conversion_preview():
    target = url_for("api.admin_automation_conversion_debug")
    query_string = request.query_string.decode("utf-8").strip()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, code=302)


def api_admin_automation_conversion_overview():
    return jsonify({"ok": True, "overview": get_overview_payload()})


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


def api_admin_automation_conversion_settings():
    return jsonify({"ok": True, "settings": get_settings_payload()})


def api_admin_automation_conversion_save_settings():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "settings": save_settings(payload)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_generate_default_channel():
    result = generate_default_channel_qr(operator=_operator_from_request())
    status_code = 200 if result.get("generated") else int(result.get("status_code") or 400)
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_conversion_debug_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "debug": get_debug_payload(external_contact_id=external_contact_id, phone=phone)})


def register_routes(bp):
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/stage/<stage_key>", methods=["GET"])(admin_automation_conversion_stage_detail)
    bp.route("/admin/automation-conversion/settings", methods=["GET"])(admin_automation_conversion_settings)
    bp.route("/admin/automation-conversion/settings/save", methods=["POST"])(admin_automation_conversion_save_settings)
    bp.route("/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(admin_automation_conversion_generate_default_channel)
    bp.route("/admin/automation-conversion/debug", methods=["GET"])(admin_automation_conversion_debug)
    bp.route("/admin/automation-conversion/preview", methods=["GET"])(admin_automation_conversion_preview)

    bp.route("/api/admin/automation-conversion/overview", methods=["GET"])(api_admin_automation_conversion_overview)
    bp.route("/api/admin/automation-conversion/member", methods=["GET"])(api_admin_automation_conversion_member)
    bp.route("/api/admin/automation-conversion/member/put-in-pool", methods=["POST"])(api_admin_automation_conversion_put_in_pool)
    bp.route("/api/admin/automation-conversion/member/remove-from-pool", methods=["POST"])(api_admin_automation_conversion_remove_from_pool)
    bp.route("/api/admin/automation-conversion/member/set-focus", methods=["POST"])(api_admin_automation_conversion_set_focus)
    bp.route("/api/admin/automation-conversion/member/set-normal", methods=["POST"])(api_admin_automation_conversion_set_normal)
    bp.route("/api/admin/automation-conversion/member/mark-won", methods=["POST"])(api_admin_automation_conversion_mark_won)
    bp.route("/api/admin/automation-conversion/member/unmark-won", methods=["POST"])(api_admin_automation_conversion_unmark_won)
    bp.route("/api/admin/automation-conversion/member/push-openclaw", methods=["POST"])(api_admin_automation_conversion_push_openclaw)
    bp.route("/api/admin/automation-conversion/settings", methods=["GET"])(api_admin_automation_conversion_settings)
    bp.route("/api/admin/automation-conversion/settings", methods=["POST"])(api_admin_automation_conversion_save_settings)
    bp.route("/api/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(api_admin_automation_conversion_generate_default_channel)
    bp.route("/api/admin/automation-conversion/debug/member", methods=["GET"])(api_admin_automation_conversion_debug_member)
