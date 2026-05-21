from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


@dataclass(frozen=True)
class RetiredRouteRule:
    pattern: str
    method: str
    category: str
    reason: str
    next_owner: str
    lockdown_action: str


@dataclass(frozen=True)
class AllowedFallbackRule:
    pattern: str
    method: str
    reason: str
    retirement_condition: str
    risk: str


RETIRED_ROUTE_RULES: tuple[RetiredRouteRule, ...] = (
    RetiredRouteRule("/admin/image-library", "GET", "media_readonly", "retired_readonly_route", "aicrm_next.media_library", "return_410"),
    RetiredRouteRule("/api/admin/image-library*", "GET", "media_readonly", "retired_readonly_route", "aicrm_next.media_library", "return_410"),
    RetiredRouteRule("/admin/attachment-library", "GET", "media_readonly", "retired_readonly_route", "aicrm_next.media_library", "return_410"),
    RetiredRouteRule("/api/admin/attachment-library*", "GET", "media_readonly", "retired_readonly_route", "aicrm_next.media_library", "return_410"),
    RetiredRouteRule("/admin/miniprogram-library", "GET", "media_readonly", "retired_readonly_route", "aicrm_next.media_library", "return_410"),
    RetiredRouteRule("/api/admin/miniprogram-library*", "GET", "media_readonly", "retired_readonly_route", "aicrm_next.media_library", "return_410"),
    RetiredRouteRule("/admin/wechat-pay/products", "GET", "product_readonly", "retired_readonly_route", "aicrm_next.commerce", "return_410"),
    RetiredRouteRule("/api/admin/wechat-pay/products*", "GET", "product_readonly", "retired_readonly_route", "aicrm_next.commerce", "return_410"),
    RetiredRouteRule("/admin/customers", "GET", "customer_readonly", "retired_readonly_route", "aicrm_next.customer_read_model", "return_410"),
    RetiredRouteRule("/api/customers", "GET", "customer_readonly", "retired_readonly_route", "aicrm_next.customer_read_model", "return_410"),
    RetiredRouteRule("/api/customers/{external_userid}", "GET", "customer_readonly", "retired_readonly_route", "aicrm_next.customer_read_model", "return_410"),
    RetiredRouteRule("/api/customers/{external_userid}/timeline", "GET", "customer_readonly", "retired_readonly_route", "aicrm_next.customer_read_model", "return_410"),
    RetiredRouteRule("/admin/user-ops/ui", "GET", "user_ops_readonly", "retired_readonly_route", "aicrm_next.ops_enrollment", "return_410"),
    RetiredRouteRule("/api/admin/user-ops/overview", "GET", "user_ops_readonly", "retired_readonly_route", "aicrm_next.ops_enrollment", "return_410"),
    RetiredRouteRule("/api/admin/user-ops/list*", "GET", "user_ops_readonly", "retired_readonly_route", "aicrm_next.ops_enrollment", "return_410"),
    RetiredRouteRule("/api/admin/user-ops/send-records*", "GET", "user_ops_readonly", "retired_readonly_route", "aicrm_next.ops_enrollment", "return_410"),
    RetiredRouteRule("/admin/questionnaires", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/admin/questionnaires/ui", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/api/admin/questionnaires", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/api/admin/questionnaires/preflight", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/api/admin/questionnaires/{questionnaire_id}", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/api/admin/questionnaires/{questionnaire_id}/export", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/s/{slug}", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/s/{slug}/submitted", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/s/{slug}/result/{result_token}", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/api/h5/questionnaires/{slug}", "GET", "questionnaire_readonly", "retired_readonly_route", "aicrm_next.questionnaire", "return_410"),
    RetiredRouteRule("/admin/automation-conversion", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/overview", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/pools", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/members*", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/execution-records", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/dashboard", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/member", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/executions*", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/api/admin/automation-conversion/programs/{program_id}/members/segment-search", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/admin/automation-conversion/programs/{program_id}/overview", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/admin/automation-conversion/programs/{program_id}/executions", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
    RetiredRouteRule("/admin/automation-conversion/programs/{program_id}/member-ops", "GET", "automation_readonly", "retired_readonly_route", "aicrm_next.automation_engine", "return_410"),
)


ALLOWED_FALLBACK_RULES: tuple[AllowedFallbackRule, ...] = (
    AllowedFallbackRule("/p/{product_code}", "GET", "payment checkout fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/product/{product_code}", "GET", "payment checkout fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/pay/{product_code}", "GET", "payment checkout fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/api/products/{product_code}", "GET", "payment product fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/api/h5/wechat-pay/products/{product_code}", "GET", "payment product fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/api/h5/wechat-pay/oauth*", "GET", "payment OAuth fallback", "provider OAuth evidence", "identity mismatch"),
    AllowedFallbackRule("/api/h5/wechat-pay/jsapi/orders", "POST", "payment order fallback", "provider evidence and replay guard", "duplicate payment side effect"),
    AllowedFallbackRule("/api/h5/wechat-pay/notify", "POST", "payment notify fallback", "provider callback evidence and replay guard", "duplicate payment side effect"),
    AllowedFallbackRule("/alipay/pay/{product_code}", "GET", "payment checkout fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/api/h5/alipay/wap/orders", "POST", "payment order fallback", "provider evidence and replay guard", "duplicate payment side effect"),
    AllowedFallbackRule("/api/h5/alipay/notify", "POST", "payment notify fallback", "provider callback evidence and replay guard", "duplicate payment side effect"),
    AllowedFallbackRule("/api/h5/alipay/return", "GET", "payment return fallback", "provider evidence and reconciliation proof", "payment return drift"),
    AllowedFallbackRule("/api/h5/alipay/orders/{out_trade_no}", "GET", "payment order status fallback", "provider evidence and reconciliation proof", "payment drift"),
    AllowedFallbackRule("/api/admin/questionnaires", "POST", "questionnaire admin write fallback", "approved questionnaire write canary", "duplicate writes"),
    AllowedFallbackRule("/api/admin/questionnaires/{questionnaire_id}", "PUT", "questionnaire admin write fallback", "approved questionnaire write canary", "duplicate writes"),
    AllowedFallbackRule("/api/admin/questionnaires/{questionnaire_id}", "DELETE", "questionnaire admin write fallback", "approved questionnaire write canary", "duplicate writes"),
    AllowedFallbackRule("/api/h5/questionnaires/{slug}/submit", "POST", "questionnaire submit fallback", "submit canary and replay guard", "duplicate submission"),
    AllowedFallbackRule("/api/h5/wechat/oauth/start", "GET", "questionnaire OAuth fallback", "provider callback evidence", "identity mismatch"),
    AllowedFallbackRule("/api/h5/wechat/oauth/callback", "GET", "questionnaire OAuth fallback", "provider callback evidence", "identity mismatch"),
    AllowedFallbackRule("/admin/questionnaires/external-push-logs*", "GET", "questionnaire diagnostics fallback", "Next diagnostics replacement", "operator confusion"),
    AllowedFallbackRule("/admin/questionnaires/{questionnaire_id}/external-push-logs*", "GET", "questionnaire diagnostics fallback", "Next diagnostics replacement", "operator confusion"),
    AllowedFallbackRule("/api/archive/sync", "POST", "archive sync fallback", "cursor and replay proof", "cursor replay"),
    AllowedFallbackRule("/api/contacts/sync-new", "POST", "contacts sync fallback", "merge and conflict proof", "duplicate contact merge"),
    AllowedFallbackRule("/api/contacts/full-sync", "POST", "contacts sync fallback", "merge and conflict proof", "duplicate contact merge"),
    AllowedFallbackRule("/api/customers/automation/activation-webhook", "POST", "automation activation fallback", "signature and replay proof", "duplicated activation"),
    AllowedFallbackRule("/api/admin/automation-conversion/member/push-openclaw", "POST", "OpenClaw push fallback", "OpenClaw compatibility and retry proof", "duplicate OpenClaw push"),
    AllowedFallbackRule("/api/admin/automation-conversion/stage/{stage_key}/manual-send", "POST", "automation write fallback", "operator approval and rollback proof", "duplicate dispatch"),
    AllowedFallbackRule("/api/admin/automation-conversion/programs/{program_id}/members/segment-search", "POST", "automation segment fallback", "Next replacement evidence", "operator confusion"),
    AllowedFallbackRule("/admin/jobs", "GET", "operational diagnostic fallback", "Next diagnostics replacement", "operator confusion"),
    AllowedFallbackRule("/api/system/health", "GET", "operational diagnostic fallback", "Next diagnostics replacement", "false confidence"),
)


def load_lockdown_rules() -> tuple[tuple[RetiredRouteRule, ...], tuple[AllowedFallbackRule, ...]]:
    return RETIRED_ROUTE_RULES, ALLOWED_FALLBACK_RULES


def _method_matches(rule_method: str, method: str) -> bool:
    return rule_method.upper() in {"*", "ANY", method.upper()}


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    wildcard_suffix = pattern.endswith("*")
    if wildcard_suffix:
        pattern = pattern[:-1]
    escaped = re.escape(pattern)
    escaped = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", escaped)
    if wildcard_suffix:
        return re.compile("^" + escaped)
    return re.compile("^" + escaped + "$")


def _matches(pattern: str, path: str) -> bool:
    return bool(_pattern_to_regex(pattern).search(path))


def match_allowed_fallback_route(method: str, path: str) -> tuple[bool, AllowedFallbackRule | None]:
    for rule in ALLOWED_FALLBACK_RULES:
        if _method_matches(rule.method, method) and _matches(rule.pattern, path):
            return True, rule
    return False, None


def match_retired_route(method: str, path: str) -> tuple[bool, RetiredRouteRule | None]:
    for rule in RETIRED_ROUTE_RULES:
        if _method_matches(rule.method, method) and _matches(rule.pattern, path):
            return True, rule
    return False, None


def _retired_response(rule: RetiredRouteRule, method: str, path: str):
    from flask import jsonify

    response = jsonify(
        {
            "ok": False,
            "error": "legacy_route_retired",
            "route_owner": "ai_crm_next",
            "legacy_fallback": True,
            "method": method.upper(),
            "path": path,
            "reason": rule.reason,
            "next_owner": rule.next_owner,
            "status": "retired",
        }
    )
    response.status_code = 410
    response.headers["X-AICRM-Route-Owner"] = "legacy_flask_retired"
    response.headers["X-AICRM-Next-Owner"] = rule.next_owner
    return response


def register_legacy_lockdown(app: "Flask") -> None:
    @app.before_request
    def _legacy_lockdown_guard():
        from flask import request

        path = request.path
        method = request.method.upper()
        allowed, _ = match_allowed_fallback_route(method, path)
        if allowed:
            return None
        retired, rule = match_retired_route(method, path)
        if retired and rule is not None:
            return _retired_response(rule, method, path)
        return None
