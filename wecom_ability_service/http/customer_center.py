from __future__ import annotations

from flask import jsonify, request

from ..customer_center.routes import parse_customer_filters
from ..customer_center.service import get_customer_detail, list_customers


def customer_center_list():
    filters = parse_customer_filters(request.args)
    try:
        payload = list_customers(filters)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def customer_center_detail(external_userid: str):
    customer = get_customer_detail(external_userid)
    if not customer:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "customer": customer})



def register_routes(bp):
    bp.route('/api/customers', methods=['GET'])(customer_center_list)
    bp.route('/api/customers/<external_userid>', methods=['GET'])(customer_center_detail)
