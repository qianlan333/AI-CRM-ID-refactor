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
        page_summary="问卷列表、preflight、公开路径和提交概览直接纳入 CRM Console；问卷底层 schema 与 admin API 保持不变。",
        breadcrumbs=_breadcrumb_items(("CRM Console", url_for("api.admin_console_home")), ("问卷", None)),
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
            page_summary="当前 questionnaire_id 不存在。",
            breadcrumbs=_breadcrumb_items(
                ("CRM Console", url_for("api.admin_console_home")),
                ("问卷", url_for("api.admin_console_questionnaires")),
                (str(questionnaire_id), None),
            ),
            actions=[{"label": "返回问卷列表", "href": url_for("api.admin_console_questionnaires"), "variant": "secondary"}],
            state_title="问卷不存在",
            state_body="检查 questionnaire_id 是否正确。",
            state_items=["问卷可能已被删除", "也可能当前环境尚未初始化样例数据"],
            page_error=page_error or "questionnaire not found",
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
        page_summary="问卷编辑页继续复用现有问卷 domain 和 admin API 口径，提供定义编辑、发布/禁用、preflight、submission 与 apply 结果查看。",
        breadcrumbs=_breadcrumb_items(
            ("CRM Console", url_for("api.admin_console_home")),
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
        return _render_questionnaire_detail_page(questionnaire_id, page_notice="问卷定义已保存并写入审计。")
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
        notice = "问卷已禁用。" if is_disabled else "问卷已重新启用。"
        return _render_questionnaire_detail_page(questionnaire_id, page_notice=notice)
    except Exception as exc:
        return _render_questionnaire_detail_page(questionnaire_id, page_error=str(exc))


def register_routes(bp):
    bp.route("/admin/questionnaires", methods=["GET"])(admin_console_questionnaires)
    bp.route("/admin/questionnaires/<int:questionnaire_id>", methods=["GET"])(admin_console_questionnaire_detail)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/save", methods=["POST"])(admin_console_questionnaire_save)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/toggle", methods=["POST"])(admin_console_questionnaire_toggle)
