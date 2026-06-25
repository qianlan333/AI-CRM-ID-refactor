#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aicrm_next.ai_audience_ops.repository import build_audience_repository  # noqa: E402
from aicrm_next.ai_audience_ops.service import AudiencePackageService  # noqa: E402
from aicrm_next.ai_audience_ops.sql_linter import extract_params, lint_sql  # noqa: E402


REFRESH_MODES = {"manual", "incremental_3m", "daily_0200", "incremental_3m_plus_daily_0200"}
SYSTEM_SQL_PARAMS = {"last_watermark_at", "refresh_started_at", "lookback_seconds", "package_id"}
SECRET_RE = re.compile(r'("(?:[^"]*(?:secret|token|dsn|database_url)[^"]*)"\s*:\s*)"[^"]*"', re.IGNORECASE)


@dataclass(frozen=True)
class PackageSpec:
    path: Path
    frontmatter: dict[str, Any]
    incremental_sql: str = ""
    snapshot_sql: str = ""

    @property
    def package_key(self) -> str:
        return str(self.frontmatter.get("package_key") or "").strip()


def parse_markdown_spec(path: str | Path) -> PackageSpec:
    spec_path = Path(path)
    text = spec_path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    metadata = _load_frontmatter(frontmatter)
    sql_blocks = _extract_sql_blocks(body)
    return PackageSpec(
        path=spec_path,
        frontmatter=metadata,
        incremental_sql=sql_blocks.get("incremental", ""),
        snapshot_sql=sql_blocks.get("snapshot", ""),
    )


def validate_spec(spec: PackageSpec) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    metadata = spec.frontmatter

    for key in ("package_key", "name", "refresh_mode", "natural_language_definition"):
        if not str(metadata.get(key) or "").strip():
            errors.append(f"frontmatter_required:{key}")

    refresh_mode = str(metadata.get("refresh_mode") or "").strip()
    if refresh_mode and refresh_mode not in REFRESH_MODES:
        errors.append("invalid_refresh_mode")

    if refresh_mode in {"incremental_3m", "incremental_3m_plus_daily_0200"} and not spec.incremental_sql:
        errors.append("incremental_sql_required")
    if refresh_mode in {"daily_0200", "incremental_3m_plus_daily_0200"} and not spec.snapshot_sql:
        errors.append("snapshot_sql_required")

    parameters = metadata.get("parameters") if isinstance(metadata.get("parameters"), dict) else {}
    for kind, sql_text in (("incremental", spec.incremental_sql), ("snapshot", spec.snapshot_sql)):
        if not sql_text:
            continue
        validation = lint_sql(sql_text)
        errors.extend(f"{kind}:{item}" for item in validation.errors)
        undeclared = [item for item in extract_params(sql_text) if item not in parameters and item not in SYSTEM_SQL_PARAMS]
        errors.extend(f"{kind}:parameter_not_declared:{item}" for item in undeclared)

    webhook = metadata.get("webhook") if isinstance(metadata.get("webhook"), dict) else {}
    if webhook.get("payload_template") or webhook.get("headers"):
        errors.append("webhook_payload_or_headers_not_allowed")

    senders = metadata.get("senders") if isinstance(metadata.get("senders"), list) else []
    priorities: list[int] = []
    for index, sender in enumerate(senders):
        if not isinstance(sender, dict):
            errors.append(f"sender_invalid:{index}")
            continue
        if not str(sender.get("sender_userid") or "").strip():
            errors.append(f"sender_userid_required:{index}")
        status = str(sender.get("status") or "active").strip()
        if status not in {"active", "paused"}:
            errors.append(f"sender_status_invalid:{index}")
        try:
            priorities.append(int(sender.get("priority") or 100))
        except Exception:
            errors.append(f"sender_priority_invalid:{index}")
    if priorities and priorities != sorted(priorities):
        warnings.append("senders_should_be_sorted_by_priority")

    return sorted(set(errors)), sorted(set(warnings))


def apply_spec(
    spec: PackageSpec,
    *,
    apply: bool = False,
    publish: bool = False,
    api_base: str = "",
    admin_session_cookie: str = "",
    package_key_prefix: str = "",
    operator: str = "codex",
) -> dict[str, Any]:
    errors, warnings = validate_spec(spec)
    package_key = f"{package_key_prefix}{spec.package_key}"
    report: dict[str, Any] = {
        "ok": not errors,
        "spec_path": str(spec.path),
        "package_key": package_key,
        "package_id": None,
        "version_id": None,
        "created": False,
        "updated": False,
        "preview_ok": False,
        "published": False,
        "validation_errors": errors,
        "warnings": warnings,
        "operator": operator,
    }
    if errors or not apply:
        return report
    if api_base:
        return _apply_via_api(spec, report, api_base=api_base, admin_session_cookie=admin_session_cookie, package_key=package_key, publish=publish)
    return _apply_direct(spec, report, package_key=package_key, publish=publish)


def _apply_direct(spec: PackageSpec, report: dict[str, Any], *, package_key: str, publish: bool) -> dict[str, Any]:
    repo = build_audience_repository()
    service = AudiencePackageService(repository=repo)
    existing = repo.get_package_by_key(package_key)
    payload = _package_payload(spec, package_key=package_key)

    if existing:
        package_id = int(existing["id"])
        update = service.update_admin_package(
            package_id,
            {
                "name": payload["name"],
                "natural_language_definition": payload["natural_language_definition"],
                "refresh_mode": payload["refresh_mode"],
            },
        )
        if not update.get("ok"):
            return {**report, "ok": False, "validation_errors": [str(update.get("error") or "package_update_failed")]}
        version = service.create_admin_version(package_id, payload)
        report.update({"updated": True, "package_id": package_id})
    else:
        create = service.create_admin_package(payload)
        if not create.get("ok"):
            return {**report, "ok": False, "validation_errors": [str(create.get("error") or "package_create_failed"), *create.get("validation_errors", [])]}
        package_id = int((create.get("package") or {}).get("id") or 0)
        version = {"ok": True, "version": create.get("version")}
        report.update({"created": True, "package_id": package_id})

    version_id = int(((version.get("version") or {}).get("id")) or 0)
    report["version_id"] = version_id or None
    if not version.get("ok"):
        return {**report, "ok": False, "validation_errors": version.get("validation_errors", [])}

    _apply_webhook_and_senders(service, int(report["package_id"]), spec)
    preview = service.preview_admin_package(int(report["package_id"]), {"version_id": version_id, "sql_kind": "incremental", "limit": 5})
    report["preview_ok"] = bool(preview.get("ok"))
    if publish:
        published = service.publish_admin_package(int(report["package_id"]), {"version_id": version_id or None})
        report["published"] = bool(published.get("ok"))
        if not published.get("ok"):
            report["ok"] = False
            report["validation_errors"] = [str(published.get("error") or "publish_failed"), *published.get("validation_errors", [])]
    return report


def _apply_via_api(
    spec: PackageSpec,
    report: dict[str, Any],
    *,
    api_base: str,
    admin_session_cookie: str,
    package_key: str,
    publish: bool,
) -> dict[str, Any]:
    if not admin_session_cookie:
        return {**report, "ok": False, "validation_errors": ["admin_session_cookie_required"]}
    base = api_base.rstrip("/")
    payload = _package_payload(spec, package_key=package_key)
    packages = _api_json("GET", f"{base}/api/admin/ai-audience/packages", cookie=admin_session_cookie)
    existing = next((item for item in packages.get("items", []) if item.get("package_key") == package_key), None)

    if existing:
        package_id = int(existing["id"])
        _api_json(
            "PATCH",
            f"{base}/api/admin/ai-audience/packages/{package_id}",
            cookie=admin_session_cookie,
            payload={
                "name": payload["name"],
                "natural_language_definition": payload["natural_language_definition"],
                "refresh_mode": payload["refresh_mode"],
            },
        )
        version = _api_json("POST", f"{base}/api/admin/ai-audience/packages/{package_id}/versions", cookie=admin_session_cookie, payload=payload)
        report.update({"updated": True, "package_id": package_id})
    else:
        created = _api_json("POST", f"{base}/api/admin/ai-audience/packages", cookie=admin_session_cookie, payload=payload)
        package_id = int((created.get("package") or {}).get("id") or 0)
        version = {"version": created.get("version")}
        report.update({"created": True, "package_id": package_id})

    version_id = int(((version.get("version") or {}).get("id")) or 0)
    report["version_id"] = version_id or None

    webhook = spec.frontmatter.get("webhook") if isinstance(spec.frontmatter.get("webhook"), dict) else {}
    if webhook:
        _api_json(
            "PATCH",
            f"{base}/api/admin/ai-audience/packages/{report['package_id']}/webhooks",
            cookie=admin_session_cookie,
            payload={
                "outbound_enabled": bool(webhook.get("outbound_enabled")),
                "outbound_webhook_url": str(webhook.get("outbound_webhook_url") or ""),
                "outbound_signing_secret": str(webhook.get("outbound_signing_secret") or ""),
            },
        )
    senders = spec.frontmatter.get("senders") if isinstance(spec.frontmatter.get("senders"), list) else []
    if senders:
        _api_json("PUT", f"{base}/api/admin/ai-audience/packages/{report['package_id']}/senders", cookie=admin_session_cookie, payload={"items": senders})

    preview = _api_json(
        "POST",
        f"{base}/api/admin/ai-audience/packages/{report['package_id']}/preview",
        cookie=admin_session_cookie,
        payload={"version_id": version_id, "sql_kind": "incremental", "limit": 5},
    )
    report["preview_ok"] = bool(preview.get("ok"))
    if publish:
        published = _api_json(
            "POST",
            f"{base}/api/admin/ai-audience/packages/{report['package_id']}/publish",
            cookie=admin_session_cookie,
            payload={"version_id": version_id or None},
        )
        report["published"] = bool(published.get("ok"))
    return report


def _package_payload(spec: PackageSpec, *, package_key: str) -> dict[str, Any]:
    metadata = spec.frontmatter
    return {
        "package_key": package_key,
        "name": str(metadata.get("name") or "").strip(),
        "status": str(metadata.get("status") or "paused").strip(),
        "query_mode": str(metadata.get("query_mode") or "incremental_event").strip(),
        "identity_policy": str(metadata.get("identity_policy") or "external_userid").strip(),
        "refresh_mode": str(metadata.get("refresh_mode") or "manual").strip(),
        "natural_language_definition": str(metadata.get("natural_language_definition") or "").strip(),
        "parameters": metadata.get("parameters") if isinstance(metadata.get("parameters"), dict) else {},
        "incremental_sql_text": spec.incremental_sql,
        "snapshot_sql_text": spec.snapshot_sql,
    }


def _apply_webhook_and_senders(service: AudiencePackageService, package_id: int, spec: PackageSpec) -> None:
    webhook = spec.frontmatter.get("webhook") if isinstance(spec.frontmatter.get("webhook"), dict) else {}
    if webhook:
        service.update_admin_webhook(
            package_id,
            {
                "outbound_enabled": bool(webhook.get("outbound_enabled")),
                "outbound_webhook_url": str(webhook.get("outbound_webhook_url") or ""),
                "outbound_signing_secret": str(webhook.get("outbound_signing_secret") or ""),
            },
        )
    senders = spec.frontmatter.get("senders") if isinstance(spec.frontmatter.get("senders"), list) else []
    if senders:
        service.replace_admin_senders(package_id, {"items": senders})


def _api_json(method: str, url: str, *, cookie: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method=method.upper(), headers={"Cookie": cookie, "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"admin_api_failed:{exc.code}:{_redact(body)}") from exc


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    if end < 0:
        return "", text
    body_start = text.find("\n", end + 4)
    return text[4:end].strip(), text[body_start + 1 :].lstrip() if body_start >= 0 else ""


def _load_frontmatter(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return _load_simple_yaml(text)


def _load_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    current_key = ""
    current_list_item: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            current_list_item = None
            root[current_key] = _parse_scalar(value.strip()) if value.strip() else {}
            continue
        if indent == 2 and line.startswith("- ") and current_key:
            if not isinstance(root.get(current_key), list):
                root[current_key] = []
            current_list_item = {}
            root[current_key].append(current_list_item)
            item_line = line[2:].strip()
            if ":" in item_line:
                key, value = item_line.split(":", 1)
                current_list_item[key.strip()] = _parse_scalar(value.strip())
            continue
        if indent >= 2 and ":" in line and current_key:
            key, value = line.split(":", 1)
            target: dict[str, Any]
            if current_list_item is not None:
                target = current_list_item
            else:
                if not isinstance(root.get(current_key), dict):
                    root[current_key] = {}
                target = root[current_key]
            target[key.strip()] = _parse_scalar(value.strip())
    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value.strip("'\"")


def _extract_sql_blocks(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    current_kind = ""
    heading_re = re.compile(r"^#{1,6}\s+(.*)$")
    fence_re = re.compile(r"^```(\w*)\s*$")
    lines = body.splitlines()
    index = 0
    while index < len(lines):
        heading = heading_re.match(lines[index].strip())
        if heading:
            title = heading.group(1).lower()
            if "incremental sql" in title:
                current_kind = "incremental"
            elif "snapshot sql" in title:
                current_kind = "snapshot"
        fence = fence_re.match(lines[index].strip())
        if fence and current_kind:
            block: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            result[current_kind] = "\n".join(block).strip()
            current_kind = ""
        index += 1
    return result


def _redact(value: str) -> str:
    return SECRET_RE.sub(r'\1"***"', value)


def _production_like(api_base: str) -> bool:
    return "youcangogogo.com" in api_base or os.getenv("PRODUCTION_DATA_MODE", "").lower() in {"1", "true", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply AI Audience Markdown package specs.")
    parser.add_argument("specs", nargs="+", help="Markdown spec file(s)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only. This is the default.")
    parser.add_argument("--apply", action="store_true", help="Create or update package and version.")
    parser.add_argument("--publish", action="store_true", help="Publish the created/latest version.")
    parser.add_argument("--api-base", default="", help="Use admin API instead of local service.")
    parser.add_argument("--admin-session-cookie-from-env", action="store_true", help="Read admin cookie from AICRM_ADMIN_SESSION_COOKIE.")
    parser.add_argument("--package-key-prefix", default="", help="Prefix package_key, useful for prod_verify_ tests.")
    parser.add_argument("--operator", default="codex")
    parser.add_argument("--confirm-production", action="store_true")
    args = parser.parse_args(argv)

    if args.apply and _production_like(args.api_base) and not args.confirm_production:
        print(json.dumps({"ok": False, "error": "confirm_production_required"}, ensure_ascii=False))
        return 2

    cookie = os.getenv("AICRM_ADMIN_SESSION_COOKIE", "") if args.admin_session_cookie_from_env else ""
    reports: list[dict[str, Any]] = []
    for spec_path in args.specs:
        spec = parse_markdown_spec(spec_path)
        reports.append(
            apply_spec(
                spec,
                apply=bool(args.apply),
                publish=bool(args.publish),
                api_base=args.api_base,
                admin_session_cookie=cookie,
                package_key_prefix=args.package_key_prefix,
                operator=args.operator,
            )
        )
    payload = {"ok": all(item.get("ok") for item in reports), "reports": reports}
    print(_redact(json.dumps(payload, ensure_ascii=False, indent=2, default=str)))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
