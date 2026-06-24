from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService
from aicrm_next.platform_foundation.internal_events import InternalEventService

from .event_types import DAILY_TICK_EVENT, INCREMENTAL_TICK_EVENT, SOURCE_CHANGED_EVENT
from .repository import AudienceRepository, build_audience_repository, _text
from .schemas import PackageCreateRequest, PackageVersionCreateRequest, PreviewRequest
from .sql_executor import build_execution_plan


class AudiencePackageService:
    def __init__(
        self,
        repository: AudienceRepository | None = None,
        internal_events: InternalEventService | None = None,
    ):
        self._repo = repository or build_audience_repository()
        self._events = internal_events or InternalEventService()

    def list_packages(self) -> dict[str, Any]:
        return {"ok": True, "packages": self._repo.list_packages()}

    def list_admin_package_summaries(self, *, limit: int = 200) -> dict[str, Any]:
        rows = self._repo.list_package_summaries(limit=limit)
        items = [_admin_package_item(row) for row in rows]
        total = int(rows[0].get("total_count") or len(items)) if rows else 0
        return {
            "ok": True,
            "items": items,
            "total": total,
            "generated_at": _admin_datetime(datetime.now(timezone.utc)),
        }

    def list_admin_packages(self, *, limit: int = 200) -> dict[str, Any]:
        return self.list_admin_package_summaries(limit=limit)

    def create_package(self, request: PackageCreateRequest) -> dict[str, Any]:
        payload = request.model_dump()
        package = self._repo.create_package(payload)
        version = None
        incremental_sql = _text(payload.get("incremental_sql_text"))
        snapshot_sql = _text(payload.get("snapshot_sql_text"))
        if _text(payload.get("sql_text")):
            if _text(payload.get("query_mode")) == "snapshot_current":
                snapshot_sql = _text(payload.get("sql_text"))
            else:
                incremental_sql = _text(payload.get("sql_text"))
        if incremental_sql or snapshot_sql:
            version = self.create_version(int(package["id"]), PackageVersionCreateRequest(**{**payload, "incremental_sql_text": incremental_sql, "snapshot_sql_text": snapshot_sql}))["version"]
        return {"ok": True, "package": package, "version": version}

    def get_package(self, package_id: int) -> dict[str, Any]:
        package = self._repo.get_package(int(package_id))
        if not package:
            return {"ok": False, "error": "package_not_found"}
        return {"ok": True, "package": package, "current_version": self._repo.get_current_version(int(package_id))}

    def create_version(self, package_id: int, request: PackageVersionCreateRequest) -> dict[str, Any]:
        payload = request.model_dump()
        if _text(payload.get("sql_text")) and not _text(payload.get("incremental_sql_text")) and not _text(payload.get("snapshot_sql_text")):
            payload["incremental_sql_text"] = _text(payload.get("sql_text"))
        dependencies: list[str] = []
        validation_errors: list[str] = []
        for sql_text in (_text(payload.get("incremental_sql_text")), _text(payload.get("snapshot_sql_text"))):
            if not sql_text:
                continue
            plan = build_execution_plan(sql_text)
            dependencies.extend(plan.dependencies)
            validation_errors.extend(plan.validation.errors)
        payload["dependencies"] = sorted(set(dependencies))
        payload["validation_errors"] = sorted(set(validation_errors))
        version = self._repo.create_version(package_id, payload)
        self._repo.replace_dependencies(package_id, int(version["id"]), sorted(set(dependencies)))
        return {"ok": not validation_errors, "version": version, "validation_errors": sorted(set(validation_errors))}

    def publish(self, package_id: int, *, version_id: int | None = None) -> dict[str, Any]:
        package = self._repo.get_package(package_id)
        if not package:
            return {"ok": False, "error": "package_not_found"}
        if version_id is not None:
            version = self._repo.get_version(int(version_id))
            if not version or int(version.get("package_id") or 0) != int(package_id):
                return {"ok": False, "error": "version_not_found"}
        else:
            version = self._repo.get_latest_version(package_id)
        if not version:
            return {"ok": False, "error": "version_not_found"}
        errors = []
        dependencies: list[str] = []
        if bool(package.get("incremental_enabled", True)) and not _text(version.get("incremental_sql_text")):
            errors.append("incremental_sql_required")
        if bool(package.get("daily_enabled", False)) and not _text(version.get("snapshot_sql_text")):
            errors.append("snapshot_sql_required")
        for sql_text in (_text(version.get("incremental_sql_text")), _text(version.get("snapshot_sql_text"))):
            if not sql_text:
                continue
            plan = build_execution_plan(sql_text)
            errors.extend(plan.validation.errors)
            dependencies.extend(plan.dependencies)
        if errors:
            self._repo.update_version_validation(int(version["id"]), dependencies=sorted(set(dependencies)), validation_errors=sorted(set(errors)))
            return {"ok": False, "error": "sql_validation_failed", "validation_errors": sorted(set(errors))}
        self._repo.update_version_validation(int(version["id"]), dependencies=sorted(set(dependencies)), validation_errors=[])
        self._repo.replace_dependencies(package_id, int(version["id"]), sorted(set(dependencies)))
        published = self._repo.publish_version(package_id, int(version["id"]))
        return {"ok": True, "package": self._repo.get_package(package_id), "version": published}

    def pause(self, package_id: int, *, reason: str = "") -> dict[str, Any]:
        package = self._repo.update_package_status(package_id, "paused", reason=reason)
        return {"ok": bool(package), "package": package, "error": "" if package else "package_not_found"}

    def archive(self, package_id: int, *, reason: str = "") -> dict[str, Any]:
        package = self._repo.update_package_status(package_id, "archived", reason=reason)
        return {"ok": bool(package), "package": package, "error": "" if package else "package_not_found"}

    def preview(self, package_id: int, request: PreviewRequest) -> dict[str, Any]:
        sql_text = request.sql_text
        if not sql_text:
            version = self._repo.get_current_version(package_id)
            sql_text = _text((version or {}).get("snapshot_sql_text" if request.sql_kind == "daily" else "incremental_sql_text"))
        from .refresh_service import AudienceRefreshService

        return AudienceRefreshService(repository=self._repo, internal_events=self._events).preview_sql(sql_text, request.params, limit=request.limit)

    def list_subscriptions(self, package_id: int) -> dict[str, Any]:
        return {"ok": True, "subscriptions": self._repo.list_subscriptions(package_id)}

    def create_subscription(self, package_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        subscription = self._repo.create_subscription(package_id, payload)
        return {"ok": True, "subscription": subscription, "deduplicated": bool(subscription.get("deduplicated"))}

    def update_subscription(self, subscription_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        subscription = self._repo.update_subscription(subscription_id, payload)
        return {"ok": bool(subscription), "subscription": subscription, "error": "" if subscription else "subscription_not_found"}

    def emit_tick(self, tick_type: str, *, actor_id: str = "ai_audience_scheduler") -> dict[str, Any]:
        event_type = DAILY_TICK_EVENT if tick_type == "daily" else INCREMENTAL_TICK_EVENT
        bucket = _tick_bucket(tick_type)
        result = self._events.emit_event(
            event_type=event_type,
            aggregate_type="ai_audience_scheduler",
            aggregate_id=bucket,
            subject_type="ai_audience",
            subject_id=tick_type,
            idempotency_key=f"ai_audience:{tick_type}:{bucket}",
            source_module="ai_audience_ops.service",
            payload={"tick_type": tick_type, "bucket": bucket},
            payload_summary={"tick_type": tick_type, "bucket": bucket},
            context=CommandContext(actor_id=actor_id, actor_type="system", source_route=f"ai_audience.ticks.{tick_type}"),
        )
        return {"ok": True, **result}

    def emit_source_changed(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_type = _text(payload.get("source_type"))
        source_key = _text(payload.get("source_key"))
        identity_type = _text(payload.get("identity_type"))
        identity_value = _text(payload.get("identity_value"))
        result = self._events.emit_event(
            event_type=SOURCE_CHANGED_EVENT,
            aggregate_type="ai_audience_source",
            aggregate_id=f"{source_type}:{source_key}",
            subject_type=identity_type,
            subject_id=identity_value,
            idempotency_key=f"ai_audience:source:{source_type}:{source_key}:{identity_type}:{identity_value}:{_text(payload.get('occurred_at'))}",
            source_module="ai_audience_ops.service",
            payload=dict(payload or {}),
            payload_summary={"source_type": source_type, "source_key": source_key, "identity_type": identity_type},
            context=CommandContext(actor_id="ai_audience_source_dirty", actor_type="system", source_route="ai_audience.source_dirty"),
        )
        return {"ok": True, **result}

    def diagnostics(self, package_id: int, kind: str) -> dict[str, Any]:
        if kind == "runs":
            return {"ok": True, "runs": self._repo.list_runs(package_id)}
        if kind == "members":
            return {"ok": True, "members": self._repo.list_members(package_id)}
        if kind == "events":
            return {"ok": True, "events": self._repo.list_events(package_id)}
        return {"ok": False, "error": "unknown_diagnostic_kind"}

    def external_effects(self, package_id: int) -> dict[str, Any]:
        member_events = self._repo.list_events(package_id, limit=500)
        member_event_ids = {str(item.get("id")) for item in member_events}
        jobs, total = ExternalEffectService().list_jobs({"business_type": "ai_audience_member_event"}, limit=200)
        items = [job.to_dict() for job in jobs if str(job.business_id) in member_event_ids]
        return {"ok": True, "total_scanned": total, "external_effect_jobs": items}

    def health(self) -> dict[str, Any]:
        return {"ok": True, **self._repo.health()}


def _tick_bucket(tick_type: str) -> str:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if tick_type == "daily":
        return now.strftime("%Y-%m-%d")
    minute = (now.minute // 3) * 3
    return now.replace(minute=minute, second=0, microsecond=0).isoformat()


def _admin_package_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "package_key": _text(row.get("package_key")),
        "name": _text(row.get("name")) or _text(row.get("package_key")) or "未命名人群包",
        "member_count": int(row.get("member_count") or 0),
        "last_refreshed_at": _admin_datetime(row.get("last_refreshed_at")) if row.get("last_refreshed_at") else None,
        "refresh_mode_label": _refresh_mode_label(row),
    }


def _refresh_mode_label(row: dict[str, Any]) -> str:
    labels: list[str] = []
    if bool(row.get("incremental_enabled")):
        seconds = max(1, int(row.get("incremental_interval_seconds") or 180))
        if seconds >= 60 and seconds % 60 == 0:
            labels.append(f"每 {max(1, seconds // 60)} 分钟")
        else:
            labels.append(f"每 {seconds} 秒")
    if bool(row.get("daily_enabled")):
        labels.append(f"每日 {_text(row.get('daily_refresh_time')) or '02:00'}")
    return " + ".join(labels) if labels else "手动"


def _admin_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
