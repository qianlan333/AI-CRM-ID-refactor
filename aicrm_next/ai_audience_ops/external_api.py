from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .external_auth import external_spec_auth_error
from .package_spec import package_payload_from_spec, parse_markdown_spec_text, validate_spec
from .repository import build_audience_repository, _text
from .service import AudiencePackageService

router = APIRouter()

_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Real-External-Call-Executed": "false",
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


@router.post("/api/external/ai-audience/spec/dry-run", name="api.external_ai_audience_spec_dry_run")
def external_ai_audience_spec_dry_run(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:
    if auth := external_spec_auth_error(request):
        return auth
    repo = build_audience_repository()
    result = _dry_run(payload, repo=repo)
    _audit(repo, operator=_operator(payload), action_type="external_spec_dry_run", package_key=_text(result.get("package_key")), before=_audit_before(payload), after=result)
    return _response(result)


@router.post("/api/external/ai-audience/spec/apply", name="api.external_ai_audience_spec_apply")
def external_ai_audience_spec_apply(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:
    if auth := external_spec_auth_error(request):
        return auth
    repo = build_audience_repository()
    dry = _dry_run(payload, repo=repo)
    if not dry.get("ok"):
        _audit(repo, operator=_operator(payload), action_type="external_spec_apply_rejected", package_key=_text(dry.get("package_key")), before=_audit_before(payload), after=dry)
        return _response(dry)
    if bool(payload.get("publish")) and not _allow_publish():
        result = {**dry, "ok": False, "error": "publish_not_allowed", "published": False}
        _audit(repo, operator=_operator(payload), action_type="external_spec_apply_rejected", package_key=_text(dry.get("package_key")), before=_audit_before(payload), after=result)
        return _response(result, status_code=403)
    result = _apply(payload, dry, repo=repo, publish=bool(payload.get("publish")))
    _audit(repo, operator=_operator(payload), action_type="external_spec_apply", package_key=_text(result.get("package_key")), before=_audit_before(payload), after=result)
    return _response(result)


@router.post("/api/external/ai-audience/spec/publish", name="api.external_ai_audience_spec_publish")
def external_ai_audience_spec_publish(request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:
    if auth := external_spec_auth_error(request):
        return auth
    repo = build_audience_repository()
    package_key = _text(payload.get("package_key"))
    prefix_error = _package_key_policy_error(package_key)
    if prefix_error:
        result = {"ok": False, "error": prefix_error, "package_key": package_key, "published": False}
        _audit(repo, operator=_operator(payload), action_type="external_spec_publish_rejected", package_key=package_key, before=_audit_before(payload), after=result)
        return _response(result, status_code=403)
    if not _allow_publish():
        result = {"ok": False, "error": "publish_not_allowed", "package_key": package_key, "published": False}
        _audit(repo, operator=_operator(payload), action_type="external_spec_publish_rejected", package_key=package_key, before=_audit_before(payload), after=result)
        return _response(result, status_code=403)
    package = repo.get_package_by_key(package_key)
    if not package:
        result = {"ok": False, "error": "package_not_found", "package_key": package_key, "published": False}
        _audit(repo, operator=_operator(payload), action_type="external_spec_publish_failed", package_key=package_key, before=_audit_before(payload), after=result)
        return _response(result, status_code=404)
    service = AudiencePackageService(repository=repo)
    result = service.publish_external_package(int(package["id"]), version_id=payload.get("version_id"))
    response = {
        "ok": bool(result.get("ok")),
        "package_key": package_key,
        "package_id": int(package["id"]),
        "version_id": int(((result.get("version") or {}).get("id")) or payload.get("version_id") or 0) or None,
        "published": bool(result.get("ok")),
        "validation_errors": result.get("validation_errors", []),
        "warnings": [],
        "error": result.get("error", ""),
    }
    _audit(repo, operator=_operator(payload), action_type="external_spec_publish", package_key=package_key, before=_audit_before(payload), after=response)
    return _response(response, status_code=200 if response["ok"] else 400)


@router.post("/api/external/ai-audience/packages/{package_key}/archive", name="api.external_ai_audience_package_archive")
def external_ai_audience_package_archive(package_key: str, request: Request, payload: dict[str, Any] = Body(default_factory=dict)) -> JSONResponse:
    if auth := external_spec_auth_error(request):
        return auth
    repo = build_audience_repository()
    package_key = _text(package_key)
    prefix_error = _package_key_policy_error(package_key)
    if prefix_error:
        result = {"ok": False, "error": prefix_error, "package_key": package_key, "archived": False}
        _audit(repo, operator=_operator(payload), action_type="external_spec_archive_rejected", package_key=package_key, before=_audit_before(payload), after=result)
        return _response(result, status_code=403)
    package = repo.get_package_by_key(package_key)
    if not package:
        result = {"ok": False, "error": "package_not_found", "package_key": package_key, "archived": False}
        _audit(repo, operator=_operator(payload), action_type="external_spec_archive_failed", package_key=package_key, before=_audit_before(payload), after=result)
        return _response(result, status_code=404)
    archived = AudiencePackageService(repository=repo).archive_admin_package(int(package["id"]))
    result = {
        "ok": bool(archived.get("ok")),
        "package_key": package_key,
        "package_id": int(package["id"]),
        "status": (archived.get("package") or {}).get("status"),
        "archived": bool(archived.get("ok")),
        "error": archived.get("error", ""),
    }
    _audit(repo, operator=_operator(payload), action_type="external_spec_archive", package_key=package_key, before=_audit_before(payload), after=result)
    return _response(result, status_code=200 if result["ok"] else 400)


def _dry_run(payload: dict[str, Any], *, repo) -> dict[str, Any]:
    spec = parse_markdown_spec_text(_text(payload.get("spec_markdown")), path="<external>")
    errors, warnings = validate_spec(spec)
    package_key = _resolve_package_key(spec.package_key, _text(payload.get("package_key_prefix")))
    prefix_error = _package_key_policy_error(package_key, requested_prefix=_text(payload.get("package_key_prefix")))
    if prefix_error:
        errors.append(prefix_error)
    dependencies = sorted(set(_dependencies_from_spec(spec)))
    return {
        "ok": not errors,
        "mode": "dry_run",
        "package_key": package_key,
        "validation_errors": sorted(set(errors)),
        "warnings": warnings,
        "dependencies": dependencies,
    }


def _apply(payload: dict[str, Any], dry: dict[str, Any], *, repo, publish: bool) -> dict[str, Any]:
    spec = parse_markdown_spec_text(_text(payload.get("spec_markdown")), path="<external>")
    package_key = _text(dry.get("package_key"))
    service = AudiencePackageService(repository=repo)
    existing = repo.get_package_by_key(package_key)
    package_payload = package_payload_from_spec(spec, package_key=package_key)
    if existing:
        package_id = int(existing["id"])
        updated = service.update_admin_package(
            package_id,
            {
                "name": package_payload["name"],
                "natural_language_definition": package_payload["natural_language_definition"],
                "refresh_mode": package_payload["refresh_mode"],
            },
        )
        if not updated.get("ok"):
            return {**dry, "ok": False, "error": updated.get("error", "package_update_failed")}
        version = service.create_admin_version(package_id, package_payload)
        created = False
        updated_flag = True
    else:
        created_result = service.create_admin_package(package_payload)
        if not created_result.get("ok"):
            return {**dry, "ok": False, "error": created_result.get("error", "package_create_failed"), "validation_errors": created_result.get("validation_errors", [])}
        package_id = int((created_result.get("package") or {}).get("id") or 0)
        version = {"ok": True, "version": created_result.get("version")}
        created = True
        updated_flag = False
    version_id = int(((version.get("version") or {}).get("id")) or 0)
    if not version.get("ok"):
        return {**dry, "ok": False, "package_id": package_id, "version_id": version_id or None, "validation_errors": version.get("validation_errors", [])}
    _apply_webhook_and_senders(service, package_id, spec)
    preview = service.preview_admin_package(package_id, {"version_id": version_id, "sql_kind": "incremental", "limit": 5})
    response = {
        **dry,
        "ok": True,
        "package_id": package_id,
        "version_id": version_id or None,
        "created": created,
        "updated": updated_flag,
        "preview_ok": bool(preview.get("ok")),
        "published": False,
        "error": "",
    }
    if publish:
        published = service.publish_external_package(package_id, version_id=version_id or None)
        response["published"] = bool(published.get("ok"))
        if not published.get("ok"):
            response["ok"] = False
            response["error"] = published.get("error", "publish_failed")
            response["validation_errors"] = published.get("validation_errors", [])
    return response


def _apply_webhook_and_senders(service: AudiencePackageService, package_id: int, spec) -> None:
    webhook = spec.frontmatter.get("webhook") if isinstance(spec.frontmatter.get("webhook"), dict) else {}
    if webhook:
        service.update_admin_webhook(
            package_id,
            {
                "outbound_enabled": bool(webhook.get("outbound_enabled")),
                "outbound_webhook_url": _text(webhook.get("outbound_webhook_url")),
                "outbound_signing_secret": _text(webhook.get("outbound_signing_secret")),
            },
        )
    senders = spec.frontmatter.get("senders") if isinstance(spec.frontmatter.get("senders"), list) else []
    if senders:
        service.replace_admin_senders(package_id, {"items": senders})


def _dependencies_from_spec(spec) -> list[str]:
    from .sql_linter import lint_sql

    dependencies: list[str] = []
    for sql_text in (spec.incremental_sql, spec.snapshot_sql):
        if not sql_text:
            continue
        dependencies.extend(lint_sql(sql_text).dependencies)
    return dependencies


def _resolve_package_key(package_key: str, package_key_prefix: str) -> str:
    package_key = _text(package_key)
    package_key_prefix = _text(package_key_prefix)
    if package_key_prefix and not package_key.startswith(package_key_prefix):
        return f"{package_key_prefix}{package_key}"
    return package_key


def _package_key_policy_error(package_key: str, *, requested_prefix: str = "") -> str:
    package_key = _text(package_key)
    requested_prefix = _text(requested_prefix)
    allowed = _allowed_prefixes()
    if requested_prefix and requested_prefix not in allowed:
        return "package_key_prefix_not_allowed"
    if not any(package_key.startswith(prefix) for prefix in allowed):
        return "package_key_prefix_not_allowed"
    if not _allow_non_verify_prefix() and not package_key.startswith("prod_verify_"):
        return "non_verify_prefix_not_allowed"
    return ""


def _allowed_prefixes() -> list[str]:
    raw = _text(os.getenv("AICRM_AI_AUDIENCE_SPEC_ALLOWED_PREFIXES")) or "prod_verify_"
    return [item.strip() for item in raw.split(",") if item.strip()]


def _allow_publish() -> bool:
    return _text(os.getenv("AICRM_AI_AUDIENCE_SPEC_ALLOW_PUBLISH")).lower() in {"1", "true", "yes"}


def _allow_non_verify_prefix() -> bool:
    return _text(os.getenv("AICRM_AI_AUDIENCE_SPEC_ALLOW_NON_VERIFY_PREFIX")).lower() in {"1", "true", "yes"}


def _operator(payload: dict[str, Any]) -> str:
    return _text(payload.get("operator")) or "external"


def _audit_before(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_key_prefix": _text(payload.get("package_key_prefix")),
        "package_key": _text(payload.get("package_key")),
        "publish": bool(payload.get("publish")),
        "operator": _operator(payload),
        "spec_markdown_present": bool(_text(payload.get("spec_markdown"))),
    }


def _audit(repo, *, operator: str, action_type: str, package_key: str, before: dict[str, Any], after: dict[str, Any]) -> None:
    repo.insert_external_spec_audit(operator=operator, action_type=action_type, package_key=package_key, before=before, after=_redact_payload(after))


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    forbidden = ("secret", "token", "dsn", "database_url", "cookie")
    redacted: dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if any(marker in str(key).lower() for marker in forbidden):
            redacted[key] = "***"
        elif isinstance(value, dict):
            redacted[key] = _redact_payload(value)
        else:
            redacted[key] = value
    return redacted


def _response(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    if not payload.get("ok", True) and status_code == 200:
        status_code = 400
    return JSONResponse(jsonable_encoder(_redact_payload(payload)), status_code=status_code, headers=_HEADERS)
