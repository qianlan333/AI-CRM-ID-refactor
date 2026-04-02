from __future__ import annotations

from flask import current_app, jsonify, request

from ..infra.settings import list_settings_snapshot, set_settings


def get_settings():
    return jsonify({"ok": True, "settings": list_settings_snapshot(current_app.config)})


def update_settings():
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return jsonify({"ok": False, "error": "settings must be an object"}), 400
    set_settings(settings)
    return jsonify({"ok": True, "settings": list_settings_snapshot(current_app.config)})



def register_routes(bp):
    bp.route('/api/settings', methods=['GET'])(get_settings)
    bp.route('/api/settings', methods=['PUT'])(update_settings)
