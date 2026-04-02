from __future__ import annotations

from flask import jsonify, request

from ..customer_timeline import get_customer_timeline, parse_timeline_filters


def customer_timeline_detail(external_userid: str):
    try:
        filters = parse_timeline_filters(request.args)
        timeline = get_customer_timeline(external_userid, filters)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not timeline:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "timeline": timeline})



def register_routes(bp):
    bp.route('/api/customers/<external_userid>/timeline', methods=['GET'])(customer_timeline_detail)
