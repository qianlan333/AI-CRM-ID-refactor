from __future__ import annotations

import json

from flask import request, url_for

from ..domains.admin_console.service import (
    build_questionnaire_detail_payload,
    build_questionnaire_index_payload,
    save_questionnaire_editor,
    toggle_questionnaire_disabled,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_console_questionnaires():
    payload = build_questionnaire_index_payload()
    return _render_admin_template(
        "questionnaires.html",
        active_nav="questionnaires",
        page_title="问卷中心",
        page_summary="在这里管理问卷、查看发布状态、环境检查和提交情况。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("问卷", None)),
        questionnaire_payload=payload,
    )


def _render_questionnaire_detail_page(
    questionnaire_id: int,
    *,
    page_notice: str = "",
    page_error: str = "",
    editor_override: dict | None = None,
):
    payload = build_questionnaire_detail_payload(questionnaire_id)
    if not payload:
        return _render_admin_template(
            "placeholder.html",
            active_nav="questionnaires",
            page_title="问卷不存在",
            page_summary="当前没有找到这个问卷。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("问卷", url_for("api.admin_console_questionnaires")),
                (str(questionnaire_id), None),
            ),
            actions=[{"label": "返回问卷列表", "href": url_for("api.admin_console_questionnaires"), "variant": "secondary"}],
            state_title="问卷不存在",
            state_body="请确认问卷编号是否正确，或稍后重试。",
            state_items=["问卷可能已被删除", "当前环境也可能还没有初始化相关数据"],
            page_error=page_error or "未找到问卷",
        ), 404
    questionnaire = payload["questionnaire"]
    editor_payload = editor_override or {
        "name": questionnaire.get("name", ""),
        "slug": questionnaire.get("slug", ""),
        "title": questionnaire.get("title", ""),
        "description": questionnaire.get("description", ""),
        "redirect_url": questionnaire.get("redirect_url", ""),
        "is_disabled": bool(questionnaire.get("is_disabled")),
        "questions_json": json.dumps(questionnaire.get("questions") or [], ensure_ascii=False, indent=2),
        "score_rules_json": json.dumps(questionnaire.get("score_rules") or [], ensure_ascii=False, indent=2),
    }
    return _render_admin_template(
        "questionnaire_detail.html",
        active_nav="questionnaires",
        page_title=questionnaire.get("title") or questionnaire.get("name") or f"问卷 #{questionnaire_id}",
        page_summary="查看问卷内容、提交结果、发布状态和环境情况。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("问卷", url_for("api.admin_console_questionnaires")),
            (questionnaire.get("title") or questionnaire.get("name") or str(questionnaire_id), None),
        ),
        questionnaire_payload=payload,
        editor_payload=editor_payload,
        page_notice=page_notice,
        page_error=page_error,
    )


def admin_console_questionnaire_detail(questionnaire_id: int):
    return _render_questionnaire_detail_page(questionnaire_id)


def admin_console_questionnaire_save(questionnaire_id: int):
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        save_questionnaire_editor(questionnaire_id, form=request.form, operator=operator)
        return _render_questionnaire_detail_page(questionnaire_id, page_notice="问卷内容已保存，并已记录操作人和时间。")
    except Exception as exc:
        editor_override = {
            "name": str(request.form.get("name") or "").strip(),
            "slug": str(request.form.get("slug") or "").strip(),
            "title": str(request.form.get("title") or "").strip(),
            "description": str(request.form.get("description") or "").strip(),
            "redirect_url": str(request.form.get("redirect_url") or "").strip(),
            "is_disabled": bool(request.form.get("is_disabled")),
            "questions_json": str(request.form.get("questions_json") or "").strip(),
            "score_rules_json": str(request.form.get("score_rules_json") or "").strip(),
        }
        return _render_questionnaire_detail_page(
            questionnaire_id,
            page_error=str(exc),
            editor_override=editor_override,
        )


def admin_console_questionnaire_toggle(questionnaire_id: int):
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        is_disabled = str(request.form.get("toggle_action") or "").strip() == "disable"
        toggle_questionnaire_disabled(questionnaire_id, is_disabled=is_disabled, operator=operator)
        notice = "问卷已停用。" if is_disabled else "问卷已重新启用。"
        return _render_questionnaire_detail_page(questionnaire_id, page_notice=notice)
    except Exception as exc:
        return _render_questionnaire_detail_page(questionnaire_id, page_error=str(exc))


def register_routes(bp):
    bp.route("/admin/questionnaires", methods=["GET"])(admin_console_questionnaires)
    bp.route("/admin/questionnaires/<int:questionnaire_id>", methods=["GET"])(admin_console_questionnaire_detail)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/save", methods=["POST"])(admin_console_questionnaire_save)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/toggle", methods=["POST"])(admin_console_questionnaire_toggle)
