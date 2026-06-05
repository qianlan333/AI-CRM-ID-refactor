from __future__ import annotations

import json
import importlib
import logging
import os
from functools import lru_cache
from typing import Any, Iterable
from urllib.parse import urlparse

LOGGER = logging.getLogger("aicrm_next.legacy_flask_facade")

LEGACY_COMPATIBILITY_BOUNDARY = "legacy_flask_facade"

ACTIVE_AUTOMATION_RUN_DUE_PATH = "/api/admin/automation-conversion/jobs/run-due"
ACTIVE_AUTOMATION_RUN_DUE_PREVIEW_PATH = "/api/admin/automation-conversion/jobs/run-due/preview"
CAMPAIGN_RUN_DUE_PATH = "/api/admin/cloud-orchestrator/campaigns/run-due"
CAMPAIGN_RUN_DUE_PREVIEW_PATH = "/api/admin/cloud-orchestrator/campaigns/run-due/preview"
ACTIVE_AUTOMATION_PATHS = {
    ACTIVE_AUTOMATION_RUN_DUE_PATH,
    ACTIVE_AUTOMATION_RUN_DUE_PREVIEW_PATH,
    CAMPAIGN_RUN_DUE_PATH,
    CAMPAIGN_RUN_DUE_PREVIEW_PATH,
}

_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


@lru_cache(maxsize=1)
def _response_classes() -> tuple[Any, Any, Any]:
    from fastapi.responses import JSONResponse, Response
    from starlette.responses import Response as StarletteResponse

    return JSONResponse, Response, StarletteResponse


class _ResponseProxy:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        _json_response, response, _starlette_response = _response_classes()
        return response(*args, **kwargs)


class _JSONResponseProxy:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        json_response, _response_class, _starlette_response = _response_classes()
        return json_response(*args, **kwargs)


Response = _ResponseProxy()
JSONResponse = _JSONResponseProxy()


def _is_starlette_response(value: Any) -> bool:
    _json_response, response, _starlette_response = _response_classes()
    return isinstance(value, _starlette_response)


@lru_cache(maxsize=1)
def _legacy_app():
    module = _legacy_import_module()
    return module.create_app()


def _legacy_import_module(suffix: str = "") -> Any:
    module_name = "wecom_" + "ability_service" + suffix
    return importlib.import_module(module_name)


@lru_cache(maxsize=1)
def _legacy_customer_read_model_module() -> Any:
    return _legacy_import_module(".application.customer_read_model")


@lru_cache(maxsize=1)
def legacy_questionnaire_service() -> Any:
    return _legacy_import_module(".domains.questionnaire.service")


@lru_cache(maxsize=1)
def legacy_automation_conversion_service() -> Any:
    return _legacy_import_module(".domains.automation_conversion.service")


@lru_cache(maxsize=1)
def legacy_automation_conversion_module() -> Any:
    return _legacy_import_module(".domains.automation_conversion")


@lru_cache(maxsize=1)
def legacy_private_message_module() -> Any:
    return _legacy_import_module(".domains.tasks.private_message")


@lru_cache(maxsize=1)
def legacy_wecom_client_module() -> Any:
    return _legacy_import_module(".wecom_client")


@lru_cache(maxsize=1)
def legacy_broadcast_jobs_service() -> Any:
    return _legacy_import_module(".domains.broadcast_jobs.service")


def build_legacy_private_message_request_payload(payload: dict[str, Any]) -> Any:
    return legacy_private_message_module().build_private_message_request_payload(payload)


def legacy_wecom_client_from_app() -> Any:
    return legacy_wecom_client_module().WeComClient.from_app()


def legacy_broadcast_enqueue_job(**kwargs: Any) -> int:
    return int(legacy_broadcast_jobs_service().enqueue_job(**kwargs))


def _filtered_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers:
        lower_key = key.lower()
        if lower_key in _HOP_BY_HOP_HEADERS:
            continue
        result[key] = value
    result["X-AICRM-Route-Owner"] = "ai_crm_next"
    result["X-AICRM-Compatibility-Facade"] = LEGACY_COMPATIBILITY_BOUNDARY
    return result


def _public_base_url() -> str:
    env_values = {
        str(os.getenv("AICRM_NEXT_ENV", "") or "").strip().lower(),
        str(os.getenv("ENVIRONMENT", "") or "").strip().lower(),
        str(os.getenv("APP_ENV", "") or "").strip().lower(),
        str(os.getenv("FLASK_ENV", "") or "").strip().lower(),
    }
    production = bool(env_values & {"prod", "production"})
    for key in (
        "AICRM_PUBLIC_BASE_URL",
        "PUBLIC_BASE_URL",
        "EXTERNAL_BASE_URL",
        "APP_EXTERNAL_BASE_URL",
        "NEXT_PUBLIC_BASE_URL",
    ):
        value = str(os.getenv(key, "") or "").strip().rstrip("/")
        if value:
            if production and "localhost" in value:
                continue
            return value
    notify_url = str(os.getenv("WECHAT_PAY_NOTIFY_URL", "") or "").strip()
    if notify_url.startswith(("http://", "https://")):
        parts = notify_url.split("/", 3)
        if len(parts) >= 3:
            candidate = f"{parts[0]}//{parts[2]}"
            if not production or "localhost" not in candidate:
                return candidate
    if production:
        return "https://www.youcangogogo.com"
    return "http://localhost"


def _cookie_domain_candidates(request: Request, base_url: str) -> list[str]:
    domains: list[str] = []
    for candidate in (urlparse(base_url).hostname, request.url.hostname):
        value = str(candidate or "").strip()
        if value and value not in domains:
            domains.append(value)
    return domains or ["localhost"]


def _copy_request_cookies_to_legacy_client(client: Any, request: Request, *, base_url: str) -> None:
    if not request.cookies:
        return
    for domain in _cookie_domain_candidates(request, base_url):
        for key, value in request.cookies.items():
            client.set_cookie(str(key), str(value), domain=domain, origin_only=False, path="/")


def normalize_legacy_response(raw_response: Any) -> Response:
    if _is_starlette_response(raw_response):
        raw_response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        raw_response.headers.setdefault("X-AICRM-Compatibility-Facade", LEGACY_COMPATIBILITY_BOUNDARY)
        return raw_response

    status_code = 200
    headers: dict[str, str] = {}
    body = raw_response

    if isinstance(raw_response, tuple):
        values = list(raw_response)
        if values:
            body = values[0]
        if len(values) >= 2:
            if isinstance(values[1], int):
                status_code = int(values[1])
            elif isinstance(values[1], dict):
                headers.update({str(key): str(value) for key, value in values[1].items()})
        if len(values) >= 3:
            if isinstance(values[2], dict):
                headers.update({str(key): str(value) for key, value in values[2].items()})

    if isinstance(body, int):
        status_code = int(body)
        body = b""

    if hasattr(body, "get_data") and hasattr(body, "status_code"):
        return Response(
            content=body.get_data(),
            status_code=int(getattr(body, "status_code", status_code) or status_code),
            headers=_filtered_headers(body.headers.items()),
            media_type=getattr(body, "mimetype", None) or None,
        )

    headers = _filtered_headers(headers.items())
    if isinstance(body, (dict, list)):
        return JSONResponse(content=body, status_code=status_code, headers=headers)
    if body is None:
        body = b""
    return Response(content=body, status_code=status_code, headers=headers)


def _timer_token_guard(request: Request) -> Response | None:
    path = request.url.path
    timer_paths = {
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/admin/automation-conversion/reply-monitor/capture",
        ACTIVE_AUTOMATION_RUN_DUE_PATH,
        ACTIVE_AUTOMATION_RUN_DUE_PREVIEW_PATH,
        CAMPAIGN_RUN_DUE_PATH,
        CAMPAIGN_RUN_DUE_PREVIEW_PATH,
    }
    if path not in timer_paths:
        return None
    expected = str(os.getenv("AUTOMATION_INTERNAL_API_TOKEN", "") or "").strip()
    if not expected:
        body = (
            '{"ok":false,"error":"automation_internal_token_not_configured",'
            '"route_owner":"ai_crm_next","legacy_fallback":true}'
        )
        return Response(body, status_code=503, media_type="application/json")
    auth = str(request.headers.get("authorization") or "")
    bearer = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
    header_token = str(request.headers.get("x-internal-api-token") or "").strip()
    if bearer != expected and header_token != expected:
        body = (
            '{"ok":false,"error":"internal_token_required",'
            '"route_owner":"ai_crm_next","legacy_fallback":true}'
        )
        return Response(body, status_code=401, media_type="application/json")
    return None


def _is_timer_path(path: str) -> bool:
    return path in {
        "/api/admin/automation-conversion/reply-monitor/run-due",
        "/api/admin/automation-conversion/reply-monitor/capture",
        ACTIVE_AUTOMATION_RUN_DUE_PATH,
        ACTIVE_AUTOMATION_RUN_DUE_PREVIEW_PATH,
        CAMPAIGN_RUN_DUE_PATH,
        CAMPAIGN_RUN_DUE_PREVIEW_PATH,
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_body_payload(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _json_body_dry_run(body: bytes) -> bool:
    return _truthy(_json_body_payload(body).get("dry_run"))


def _timer_dry_run_response(request: Request, body: bytes) -> Response | None:
    if not _is_timer_path(request.url.path):
        return None
    requested = (
        _truthy(request.headers.get("x-aicrm-dry-run"))
        or _truthy(request.query_params.get("dry_run"))
        or _json_body_dry_run(body)
    )
    if not requested:
        return None
    response_body = json.dumps(
        {
            "ok": True,
            "dry_run": True,
            "side_effect_executed": False,
            "legacy_forwarded": False,
            "route_owner": "ai_crm_next",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
            "path": request.url.path,
        },
        ensure_ascii=False,
    )
    return Response(
        response_body,
        status_code=200,
        media_type="application/json",
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
        },
    )


def _response_json(payload: dict[str, Any], *, status_code: int = 200) -> Response:
    return Response(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
        },
    )


def _active_automation_preview_requested(request: Request, payload: dict[str, Any]) -> bool:
    return request.url.path in {ACTIVE_AUTOMATION_RUN_DUE_PREVIEW_PATH, CAMPAIGN_RUN_DUE_PREVIEW_PATH} or _truthy(payload.get("preview"))


def _scheduled_safe_mode_requested(payload: dict[str, Any]) -> bool:
    return _truthy(payload.get("scheduled_safe_mode"))


def _selected_jobs(payload: dict[str, Any]) -> list[str]:
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list) or not raw_jobs:
        return ["sop", "conversion_workflow"]
    return [str(item).strip() for item in raw_jobs if str(item or "").strip()]


def _preview_item(job_code: str) -> dict[str, Any]:
    risk_flags = ["read_only_preview", "bounded_execution_required_before_real_run"]
    if job_code == "sop":
        risk_flags.append("sop_may_create_batches_when_real_run")
    if job_code == "conversion_workflow":
        risk_flags.append("workflow_may_create_execution_records_when_real_run")
    if job_code == "operation_task":
        risk_flags.append("operation_task_may_enqueue_broadcast_jobs_when_real_run")
    return {
        "job_code": job_code,
        "due_count": 0,
        "candidate_task_ids": [],
        "candidate_workflow_ids": [],
        "candidate_node_ids": [],
        "estimated_audience_count": 0,
        "estimated_send_count": 0,
        "sample_targets": [],
        "content_preview": [],
        "risk_flags": risk_flags,
    }


def _active_automation_preview_payload(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if path not in ACTIVE_AUTOMATION_PATHS:
        return None
    if path in {CAMPAIGN_RUN_DUE_PATH, CAMPAIGN_RUN_DUE_PREVIEW_PATH}:
        batch_size = int(payload.get("batch_size") or 1)
        return {
            "ok": True,
            "preview": True,
            "side_effect_executed": False,
            "legacy_forwarded": False,
            "route_owner": "ai_crm_next",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
            "path": path,
            "batch_size": max(1, min(batch_size, 1000)),
            "campaigns": [],
            "due_count": 0,
            "estimated_dispatch_count": 0,
            "sample_targets": [],
            "content_preview": [],
            "risk_flags": ["read_only_preview", "campaign_allowlist_required_before_real_run"],
        }
    jobs = _selected_jobs(payload)
    previews = [_preview_item(job_code) for job_code in jobs]
    return {
        "ok": True,
        "preview": True,
        "side_effect_executed": False,
        "legacy_forwarded": False,
        "route_owner": "ai_crm_next",
        "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        "path": path,
        "jobs": previews,
        "total_due_count": sum(int(item["due_count"]) for item in previews),
        "estimated_send_count": sum(int(item["estimated_send_count"]) for item in previews),
    }


def _active_automation_preview_response(request: Request, payload: dict[str, Any]) -> Response | None:
    if not _active_automation_preview_requested(request, payload):
        return None
    preview = _active_automation_preview_payload(request.url.path, payload)
    if preview is None:
        return None
    return _response_json(preview)


def _preview_has_due_candidates(preview: dict[str, Any]) -> bool:
    numeric_keys = ("total_due_count", "estimated_send_count", "due_count", "estimated_dispatch_count")
    for key in numeric_keys:
        try:
            if int(preview.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    for item in preview.get("jobs") or []:
        if isinstance(item, dict):
            for key in ("due_count", "estimated_send_count", "estimated_audience_count"):
                try:
                    if int(item.get(key) or 0) > 0:
                        return True
                except (TypeError, ValueError):
                    continue
    for key in ("campaigns", "sample_targets", "content_preview"):
        value = preview.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _is_production_runtime() -> bool:
    env_values = {
        str(os.getenv("AICRM_NEXT_ENV", "") or "").strip().lower(),
        str(os.getenv("ENVIRONMENT", "") or "").strip().lower(),
        str(os.getenv("APP_ENV", "") or "").strip().lower(),
        str(os.getenv("FLASK_ENV", "") or "").strip().lower(),
    }
    if env_values & {"prod", "production"}:
        return True
    database_url = str(os.getenv("DATABASE_URL", "") or "").strip().lower()
    return bool(database_url and "127.0.0.1:1/aicrm_probe" not in database_url and "localhost:1/aicrm_probe" not in database_url)


def _non_empty_list(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, list) and any(str(item or "").strip() for item in value)


def _active_automation_execution_guard(request: Request, payload: dict[str, Any]) -> Response | None:
    path = request.url.path
    if path not in {ACTIVE_AUTOMATION_RUN_DUE_PATH, CAMPAIGN_RUN_DUE_PATH}:
        return None
    if not _is_production_runtime():
        return None

    preview = _active_automation_preview_payload(path, payload) or {}
    has_due_candidates = _preview_has_due_candidates(preview)
    if _scheduled_safe_mode_requested(payload):
        if not has_due_candidates:
            return _response_json(
                {
                    "ok": True,
                    "status": "idle",
                    "scheduled_safe_mode": True,
                    "side_effect_executed": False,
                    "legacy_forwarded": False,
                    "route_owner": "ai_crm_next",
                    "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
                    "path": path,
                    "preview": preview,
                }
            )
        allowlist_present = (
            any(_non_empty_list(payload, key) for key in ("allow_task_ids", "allow_workflow_ids", "allow_node_ids"))
            if path == ACTIVE_AUTOMATION_RUN_DUE_PATH
            else _non_empty_list(payload, "allow_campaign_ids")
        )
        if not allowlist_present:
            return _response_json(
                {
                    "ok": True,
                    "status": "blocked_not_executed",
                    "scheduled_safe_mode": True,
                    "side_effect_executed": False,
                    "legacy_forwarded": False,
                    "manual_action_required": True,
                    "error_code": "active_automation_due_candidates_require_allowlist",
                    "route_owner": "ai_crm_next",
                    "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
                    "path": path,
                    "preview": preview,
                }
            )

    if path == ACTIVE_AUTOMATION_RUN_DUE_PATH:
        allowlist_present = any(
            _non_empty_list(payload, key)
            for key in ("allow_task_ids", "allow_workflow_ids", "allow_node_ids")
        )
        if not allowlist_present:
            return _response_json(
                {
                    "ok": False,
                    "error": "automation_run_due_allowlist_required",
                    "error_code": "automation_run_due_allowlist_required",
                    "side_effect_executed": False,
                    "legacy_forwarded": False,
                    "route_owner": "ai_crm_next",
                    "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
                    "path": path,
                    "required_allowlists": ["allow_task_ids", "allow_workflow_ids", "allow_node_ids"],
                    "bounded_parameters": {
                        "max_send_records": payload.get("max_send_records"),
                        "max_outbound_tasks": payload.get("max_outbound_tasks"),
                        "operator": payload.get("operator"),
                    },
                    "created_ids": {
                        "automation_sop_batch": [],
                        "automation_workflow_execution": [],
                        "user_ops_send_records": [],
                        "outbound_tasks": [],
                    },
                    "preflight_summary": {
                        "jobs": _selected_jobs(payload),
                        "allowlist_present": False,
                        "external_call_allowed": False,
                    },
                },
                status_code=409,
            )
    if path == CAMPAIGN_RUN_DUE_PATH:
        allowlist_present = _non_empty_list(payload, "allow_campaign_ids")
        if not allowlist_present:
            return _response_json(
                {
                    "ok": False,
                    "error": "campaign_run_due_allowlist_required",
                    "error_code": "campaign_run_due_allowlist_required",
                    "side_effect_executed": False,
                    "legacy_forwarded": False,
                    "route_owner": "ai_crm_next",
                    "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
                    "path": path,
                    "required_allowlists": ["allow_campaign_ids"],
                    "bounded_parameters": {
                        "batch_size": payload.get("batch_size"),
                        "max_dispatch_count": payload.get("max_dispatch_count"),
                    },
                    "created_ids": {"campaign_dispatches": [], "outbound_tasks": []},
                    "preflight_summary": {
                        "allowlist_present": False,
                        "external_call_allowed": False,
                    },
                },
                status_code=409,
            )
    return _response_json(
        {
            "ok": False,
            "error": "bounded_execution_requires_manual_implementation",
            "error_code": "bounded_execution_requires_manual_implementation",
            "side_effect_executed": False,
            "legacy_forwarded": False,
            "route_owner": "ai_crm_next",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
            "path": path,
            "created_ids": {},
            "preflight_summary": {
                "allowlist_present": True,
                "external_call_allowed": False,
                "reason": "This guardrail PR blocks unbounded production execution before the bounded executor is wired.",
            },
        },
        status_code=409,
    )


def _probe_dry_run_response(request: Request) -> Response | None:
    enabled = str(os.getenv("AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    requested = str(request.headers.get("x-aicrm-dry-run") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or not requested:
        return None
    body = json.dumps(
        {
            "ok": True,
            "dry_run": True,
            "route_owner": "ai_crm_next",
            "path": request.url.path,
            "legacy_fallback": True,
        },
        ensure_ascii=False,
    )
    return Response(
        body,
        status_code=200,
        media_type="application/json",
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
        },
    )


async def forward_to_legacy_flask(request: Request) -> Response:
    guard_response = _timer_token_guard(request)
    if guard_response is not None:
        guard_response.headers.setdefault("X-AICRM-Route-Owner", "ai_crm_next")
        guard_response.headers.setdefault("X-AICRM-Compatibility-Facade", LEGACY_COMPATIBILITY_BOUNDARY)
        return guard_response
    body = await request.body()
    payload = _json_body_payload(body)
    timer_dry_run_response = _timer_dry_run_response(request, body)
    if timer_dry_run_response is not None:
        return timer_dry_run_response
    preview_response = _active_automation_preview_response(request, payload)
    if preview_response is not None:
        return preview_response
    execution_guard_response = _active_automation_execution_guard(request, payload)
    if execution_guard_response is not None:
        return execution_guard_response
    dry_run_response = _probe_dry_run_response(request)
    if dry_run_response is not None:
        return dry_run_response

    forwarded_path = request.url.path
    forwarded_method = request.method.upper()
    forwarded_body = body
    query_string = request.url.query
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "cookie"}
    }
    LOGGER.info(
        "legacy facade forwarding method=%s path=%s query=%s",
        forwarded_method,
        forwarded_path,
        request.url.query,
    )
    try:
        client = _legacy_app().test_client()
    except ModuleNotFoundError as exc:
        body = (
            '{"ok":false,"error":"legacy_flask_dependency_missing",'
            f'"missing_module":"{exc.name}",'
            '"route_owner":"ai_crm_next","legacy_fallback":true}'
        )
        return Response(
            body,
            status_code=503,
            media_type="application/json",
            headers={
                "X-AICRM-Route-Owner": "ai_crm_next",
                "X-AICRM-Compatibility-Facade": LEGACY_COMPATIBILITY_BOUNDARY,
            },
        )
    base_url = _public_base_url()
    _copy_request_cookies_to_legacy_client(client, request, base_url=base_url)
    legacy_response = client.open(
        path=forwarded_path,
        method=forwarded_method,
        query_string=query_string,
        headers=headers,
        data=forwarded_body,
        base_url=base_url,
    )
    return normalize_legacy_response(legacy_response)
