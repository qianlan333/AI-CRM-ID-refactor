from __future__ import annotations

from flask import jsonify, request

from ..services import resolve_person_identity


def api_identity_resolve():
    external_userid = request.args.get("external_userid", "").strip()
    mobile = request.args.get("mobile", "").strip()
    unionid = request.args.get("unionid", "").strip()
    try:
        payload = resolve_person_identity(external_userid=external_userid, mobile=mobile, unionid=unionid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})



def register_routes(bp):
    bp.route('/api/identity/resolve', methods=['GET'])(api_identity_resolve)
