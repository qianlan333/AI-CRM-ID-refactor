from __future__ import annotations

from flask import redirect, render_template, request, url_for

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
        page_title="问卷管理",
        page_summary="在这里统一管理问卷列表、启停状态和分享入口。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("问卷", None)),
        questionnaire_payload=payload,
    )


def _questionnaire_not_found_response(questionnaire_id: int):
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
        actions=[{"label": "返回问卷管理", "href": url_for("api.admin_console_questionnaires"), "variant": "secondary"}],
        state_title="问卷不存在",
        state_body="请确认问卷编号是否正确，或稍后重试。",
        state_items=["问卷可能已被删除", "当前环境也可能还没有初始化相关数据"],
        page_error="未找到问卷",
    ), 404


def _render_questionnaire_editor_page(
    *,
    questionnaire_id: int | None = None,
):
    payload = build_questionnaire_detail_payload(questionnaire_id) if questionnaire_id is not None else None
    if questionnaire_id is not None and not payload:
        return _questionnaire_not_found_response(questionnaire_id)
    questionnaire = payload["questionnaire"] if payload else None
    return render_template(
        "admin_questionnaires.html",
        editor_mode="edit" if questionnaire_id is not None else "new",
        editor_page_title=(questionnaire or {}).get("title")
        or (questionnaire or {}).get("name")
        or ("编辑问卷" if questionnaire_id is not None else "新建问卷"),
        editor_heading="编辑问卷" if questionnaire_id is not None else "新建问卷",
        editor_subtitle=(
            "维护当前问卷的题目、分数规则和发布设置。"
            if questionnaire_id is not None
            else "从空白模板开始搭建题目、标签和分数规则。"
        ),
        editor_back_href=url_for("api.admin_console_questionnaires"),
        initial_questionnaire=questionnaire,
        initial_questionnaire_id=questionnaire_id,
    )


def admin_console_questionnaire_new():
    return _render_questionnaire_editor_page()


def admin_console_questionnaire_detail(questionnaire_id: int):
    return _render_questionnaire_editor_page(questionnaire_id=questionnaire_id)


def admin_console_questionnaire_save(questionnaire_id: int):
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        save_questionnaire_editor(questionnaire_id, form=request.form, operator=operator)
    except Exception:
        pass
    return redirect(url_for("api.admin_console_questionnaire_detail", questionnaire_id=questionnaire_id))


def admin_console_questionnaire_toggle(questionnaire_id: int):
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        is_disabled = str(request.form.get("toggle_action") or "").strip() == "disable"
        toggle_questionnaire_disabled(questionnaire_id, is_disabled=is_disabled, operator=operator)
    except Exception:
        pass
    return redirect(url_for("api.admin_console_questionnaire_detail", questionnaire_id=questionnaire_id))


def register_routes(bp):
    bp.route("/admin/questionnaires", methods=["GET"])(admin_console_questionnaires)
    bp.route("/admin/questionnaires/new", methods=["GET"])(admin_console_questionnaire_new)
    bp.route("/admin/questionnaires/<int:questionnaire_id>", methods=["GET"])(admin_console_questionnaire_detail)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/save", methods=["POST"])(admin_console_questionnaire_save)
    bp.route("/admin/questionnaires/<int:questionnaire_id>/toggle", methods=["POST"])(admin_console_questionnaire_toggle)
