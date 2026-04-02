from __future__ import annotations

from pathlib import Path

from flask import abort, current_app, jsonify, request, send_from_directory

from ..db import init_db
from ..services import list_archived_messages_by_window
from .ops_runtime import build_ops_status_payload


def health():
    return jsonify({"ok": True, "service": "openclaw-wecom-ability-service"})


def serve_root_verification_file(filename: str):
    is_supported_verify_file = (
        (filename.startswith("WW_verify_") or filename.startswith("MP_verify_"))
        and filename.endswith(".txt")
    )
    if not is_supported_verify_file:
        abort(404)
    project_root = Path(current_app.root_path).parent
    return send_from_directory(project_root, filename, mimetype="text/plain")


def archive_messages():
    start_time = request.args.get("start_time", "").strip()
    end_time = request.args.get("end_time", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip() or current_app.config["WECOM_DEFAULT_OWNER_USERID"]
    cursor = request.args.get("cursor", "").strip()

    if not start_time or not end_time or not owner_userid:
        return jsonify({"ok": False, "error": "start_time, end_time and owner_userid are required"}), 400

    result = list_archived_messages_by_window(start_time, end_time, owner_userid, cursor=cursor)
    return jsonify(result)


def api_init_db():
    init_db()
    return jsonify({"ok": True})


def ops_status():
    return jsonify(build_ops_status_payload())


def register_routes(bp):
    bp.route('/health', methods=['GET'])(health)
    bp.route('/<path:filename>', methods=['GET'])(serve_root_verification_file)
    bp.route('/archive/messages', methods=['GET'])(archive_messages)
    bp.route('/api/init-db', methods=['POST'])(api_init_db)
    bp.route('/api/ops/status', methods=['GET'])(ops_status)
