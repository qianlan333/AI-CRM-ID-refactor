"""图片素材库 admin 端点。

集中管理被各处复用的图片：小程序卡片缩略图、campaign 群发配图、欢迎语 / SOP
配图等。前端有专门的「图片素材库」管理页，每个需要选图的位置（小程序卡片
表单、step 编辑表单、群发任务表单）都可以打开同一个 picker 复用素材库。
"""
from __future__ import annotations

import logging
from typing import Any

from flask import Response, jsonify, render_template, request

from ..domains import image_library
from ..domains.admin_dashboard.service import build_admin_shell_status, list_admin_navigation


logger = logging.getLogger(__name__)


def admin_image_library_workspace() -> Response:
    try:
        shell_status = build_admin_shell_status()
    except Exception:  # pragma: no cover - defensive
        shell_status = None
    return render_template(
        "admin_console/image_library.html",
        page_title="图片素材库",
        page_summary="集中维护可被群发 / 卡片 / 自动化欢迎语等场景引用的图片，支持上传和外链。",
        nav_items=list_admin_navigation("image_library"),
        shell_status=shell_status,
        show_shell_meta=False,
        show_page_header=True,
        breadcrumbs=[
            {"label": "客户管理后台", "href": "/admin"},
            {"label": "图片素材库"},
        ],
        page_actions=[],
    )


def admin_image_library_list() -> Response:
    enabled_only = request.args.get("enabled_only")
    enabled_only_flag = True
    if enabled_only is not None:
        enabled_only_flag = str(enabled_only).strip().lower() not in ("0", "false", "no", "")
    limit = int(request.args.get("limit") or 200)
    items = image_library.list_images(enabled_only=enabled_only_flag, limit=limit)
    return jsonify({"ok": True, "items": items})


def admin_image_library_get(image_id: int) -> Response:
    """详情接口默认带 data_base64，给前端 thumbnail 预览用。"""
    item = image_library.get_image(int(image_id), include_data=True)
    if not item:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "item": item})


def admin_image_library_upload() -> Response:
    """multipart 上传：``image`` 文件 + 可选 ``name`` 备注。"""
    file = request.files.get("image")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "missing image"}), 400
    file_bytes = file.read()
    name = (request.form.get("name") or "").strip()
    try:
        item = image_library.create_image_from_upload(
            file_bytes=file_bytes,
            file_name=file.filename,
            mime_type=(file.mimetype or "").lower(),
            name=name,
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_create_url() -> Response:
    """JSON body：``{url, name?}``，用外链创建一条素材。"""
    body = request.get_json(silent=True) or {}
    try:
        item = image_library.create_image_from_url(
            url=str(body.get("url") or ""),
            name=str(body.get("name") or ""),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_create_base64() -> Response:
    """JSON body：``{data_base64, file_name?, mime_type?, name?}``。"""
    body = request.get_json(silent=True) or {}
    try:
        item = image_library.create_image_from_base64(
            data_base64=str(body.get("data_base64") or ""),
            file_name=str(body.get("file_name") or ""),
            mime_type=str(body.get("mime_type") or "image/png"),
            name=str(body.get("name") or ""),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_update(image_id: int) -> Response:
    body = request.get_json(silent=True) or {}
    try:
        item = image_library.update_image(
            int(image_id),
            name=body.get("name"),
            enabled=body.get("enabled"),
        )
        return jsonify({"ok": True, "item": item})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_image_library_delete(image_id: int) -> Response:
    ok = image_library.delete_image(int(image_id))
    return jsonify({"ok": ok})


def admin_image_library_test_resolve(image_id: int) -> Response:
    try:
        media_id = image_library.resolve_image_media_id(int(image_id))
        return jsonify({"ok": True, "media_id": media_id})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def register_routes(bp) -> None:
    bp.route("/admin/image-library", methods=["GET"])(admin_image_library_workspace)
    bp.route("/api/admin/image-library", methods=["GET"])(admin_image_library_list)
    bp.route("/api/admin/image-library/upload", methods=["POST"])(admin_image_library_upload)
    bp.route("/api/admin/image-library/from-url", methods=["POST"])(admin_image_library_create_url)
    bp.route("/api/admin/image-library/from-base64", methods=["POST"])(admin_image_library_create_base64)
    bp.route("/api/admin/image-library/<int:image_id>", methods=["GET"])(admin_image_library_get)
    bp.route("/api/admin/image-library/<int:image_id>", methods=["PUT"])(admin_image_library_update)
    bp.route("/api/admin/image-library/<int:image_id>", methods=["DELETE"])(admin_image_library_delete)
    bp.route(
        "/api/admin/image-library/<int:image_id>/test-resolve",
        methods=["POST"],
    )(admin_image_library_test_resolve)


__all__ = ["register_routes"]
