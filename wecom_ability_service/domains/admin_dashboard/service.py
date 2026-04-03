from __future__ import annotations

from typing import Any

from flask import current_app

from ..admin_jobs import build_jobs_dashboard_groups, build_jobs_runtime_snapshot
from . import repo

ADMIN_NAV_ITEMS = (
    {"key": "workbench", "label": "工作台", "endpoint": "api.admin_console_home"},
    {"key": "customers", "label": "客户", "endpoint": "api.admin_console_customers"},
    {"key": "operations", "label": "运营", "endpoint": "api.admin_console_user_ops"},
    {"key": "questionnaires", "label": "问卷", "endpoint": "api.admin_console_questionnaires"},
    {"key": "mcp", "label": "MCP", "endpoint": "api.admin_console_mcp"},
    {"key": "config", "label": "配置", "endpoint": "api.admin_config_home"},
    {"key": "jobs", "label": "同步与任务", "endpoint": "api.admin_console_jobs"},
    {"key": "audit", "label": "审计", "endpoint": "api.admin_audit_logs"},
    {"key": "system", "label": "系统", "endpoint": "api.admin_console_system"},
)


def list_admin_navigation(active_nav: str) -> list[dict[str, Any]]:
    normalized_active_nav = str(active_nav or "").strip() or "workbench"
    return [
        {**item, "active": item["key"] == normalized_active_nav}
        for item in ADMIN_NAV_ITEMS
    ]


def build_admin_shell_status() -> dict[str, Any]:
    environment = repo.detect_environment(current_app.config)
    health = repo.get_admin_health_snapshot(current_app.config)
    return {
        "environment": environment,
        "release_sha": repo.get_release_sha(current_app.config),
        "health": health,
    }


def _bool_label(value: bool) -> str:
    return "Enabled" if value else "Disabled"


def _empty_value(value: str, *, fallback: str = "Never") -> str:
    text = str(value or "").strip()
    return text or fallback


def build_system_status_payload() -> dict[str, Any]:
    snapshot = repo.get_system_snapshot(current_app.config)
    jobs_snapshot = build_jobs_runtime_snapshot(include_archive_health=False)
    health = snapshot["health"]
    last_sync_run = dict(jobs_snapshot.get("last_sync_run") or {})
    callback_enabled = bool(jobs_snapshot.get("callback_enabled"))
    background_async_enabled = bool(jobs_snapshot.get("background_async_enabled"))
    deferred_counts = dict(jobs_snapshot.get("deferred_counts") or {})
    pending_jobs = int(deferred_counts.get("pending_count") or 0)
    running_jobs = int(deferred_counts.get("running_count") or 0)
    failed_jobs = int(deferred_counts.get("failed_count") or 0)
    total_attention_jobs = pending_jobs + running_jobs + failed_jobs
    last_archive_sync = {
        "run_id": last_sync_run.get("id"),
        "status": str(last_sync_run.get("status") or "").strip() or "never",
        "time": (
            str(last_sync_run.get("finished_at") or "").strip()
            or str(last_sync_run.get("created_at") or "").strip()
            or str(last_sync_run.get("finished_or_created_at") or "").strip()
        ),
        "error_message": str(last_sync_run.get("error_message") or "").strip(),
    }
    snapshot = {
        **snapshot,
        "callback_enabled": callback_enabled,
        "background_async_enabled": background_async_enabled,
        "last_archive_sync": last_archive_sync,
        "deferred_counts": deferred_counts,
    }
    cards = [
        {
            "key": "service_health",
            "label": "Service Health",
            "value": health["label"],
            "description": health["detail"],
            "tone": health["state"],
        },
        {
            "key": "release_sha",
            "label": "Release SHA",
            "value": snapshot["release_sha"],
            "description": "当前部署版本",
            "tone": "neutral",
        },
        {
            "key": "database_backend",
            "label": "Database Backend",
            "value": snapshot["database_backend"],
            "description": "当前运行数据库后端",
            "tone": "neutral",
        },
        {
            "key": "callback_enabled",
            "label": "Callback",
            "value": _bool_label(callback_enabled),
            "description": "企业微信回调开关状态",
            "tone": "healthy" if callback_enabled else "degraded",
        },
        {
            "key": "background_async_enabled",
            "label": "Background Async",
            "value": _bool_label(background_async_enabled),
            "description": "后台异步处理开关",
            "tone": "healthy" if background_async_enabled else "unknown",
        },
        {
            "key": "last_archive_sync",
            "label": "Recent Archive Sync",
            "value": str(last_archive_sync["status"] or "").upper() or "NEVER",
            "description": _empty_value(last_archive_sync["time"]),
            "tone": "degraded" if last_archive_sync["status"] == "failed" else "neutral",
        },
        {
            "key": "deferred_jobs",
            "label": "Deferred Jobs",
            "value": total_attention_jobs,
            "description": f"pending {pending_jobs} · running {running_jobs} · failed {failed_jobs}",
            "tone": "degraded" if failed_jobs else ("unknown" if total_attention_jobs else "healthy"),
        },
        {
            "key": "last_contacts_sync_time",
            "label": "Recent Contacts Sync",
            "value": _empty_value(snapshot["last_contacts_sync_time"]),
            "description": "contacts 表最近更新时间",
            "tone": "neutral",
        },
    ]
    return {**snapshot, "cards": cards}


def build_dashboard_summary() -> dict[str, Any]:
    counts = repo.get_business_summary_counts()
    cards = [
        {
            "key": "archived_messages_total",
            "label": "Archived Messages",
            "value": counts["archived_messages_total"],
            "description": "archived_messages 总量",
            "href": "/admin/jobs",
        },
        {
            "key": "contacts_total",
            "label": "Contacts",
            "value": counts["contacts_total"],
            "description": "contacts 快照总量",
            "href": "/admin/customers",
        },
        {
            "key": "group_chats_total",
            "label": "Group Chats",
            "value": counts["group_chats_total"],
            "description": "group_chats 总量",
            "href": "/admin/jobs",
        },
        {
            "key": "customers_total",
            "label": "Customers",
            "value": counts["customers_total"],
            "description": "基于 customer scope 聚合",
            "href": "/admin/customers",
        },
        {
            "key": "questionnaire_total",
            "label": "Questionnaires",
            "value": counts["questionnaire_total"],
            "description": (
                f"最近提交 {_empty_value(counts['questionnaire_latest_submission'], fallback='暂无提交')}"
            ),
            "href": "/admin/questionnaires",
        },
        {
            "key": "user_ops_lead_pool_total",
            "label": "User Ops Lead Pool",
            "value": counts["user_ops_lead_pool_total"],
            "description": "user_ops_lead_pool_current 总量",
            "href": "/admin/user-ops",
        },
        {
            "key": "class_user_current_total",
            "label": "Class Users",
            "value": counts["class_user_current_total"],
            "description": "class_user_status_current 总量",
            "href": "/admin/class-users",
        },
    ]
    return {
        **counts,
        "cards": cards,
    }


def _build_failed_apply_group() -> dict[str, Any]:
    rows = repo.list_recent_failed_questionnaire_apply_logs(limit=5)
    items = [
        {
            "title": f"Submission #{row['submission_id']}",
            "meta": _empty_value(str(row.get("created_at") or "").strip()),
            "detail": str(row.get("error_message") or "").strip() or "questionnaire apply failed",
        }
        for row in rows
    ]
    return {
        "key": "failed_questionnaire_apply",
        "title": "Failed Questionnaire Apply",
        "count": len(rows),
        "description": "最近失败的问卷 SCRM apply 记录。",
        "tone": "danger" if rows else "ok",
        "items": items,
        "empty_title": "最近没有问卷 apply 失败",
        "href": "/admin/questionnaires",
    }


def _build_questionnaire_preflight_group() -> dict[str, Any]:
    snapshot = repo.get_questionnaire_preflight_snapshot(current_app.config)
    anomaly_items: list[dict[str, Any]] = []

    if not snapshot.get("wechat_oauth_configured"):
        anomaly_items.append(
            {
                "title": "WeChat OAuth 未配置",
                "meta": "问卷身份匹配能力不完整",
                "detail": "WECHAT_MP_APP_ID / WECHAT_MP_APP_SECRET / SECRET_KEY 需要完整配置。",
            }
        )
    if not snapshot.get("wecom_contact_configured"):
        anomaly_items.append(
            {
                "title": "WeCom Contact 凭证缺失",
                "meta": "问卷 SCRM 侧无法完整工作",
                "detail": "WECOM_CORP_ID / WECOM_CONTACT_SECRET 需要完整配置。",
            }
        )
    if not snapshot.get("wecom_tags_api_available"):
        anomaly_items.append(
            {
                "title": "Tag Probe 未通过",
                "meta": "首页只做轻量预检",
                "detail": str(snapshot.get("wecom_tags_api_error") or "").strip() or "tag readiness check failed",
            }
        )
    if not snapshot.get("identity_map_available"):
        anomaly_items.append(
            {
                "title": "Identity Map 不可用",
                "meta": "external contact identity 读模型不可用",
                "detail": str(snapshot.get("identity_map_error") or "").strip() or "identity map query failed",
            }
        )

    return {
        "key": "questionnaire_preflight",
        "title": "Questionnaire Preflight",
        "count": len(anomaly_items),
        "description": "首页展示轻量预检摘要，深度检查仍在问卷中心。",
        "tone": "warn" if anomaly_items else "ok",
        "items": anomaly_items,
        "empty_title": "问卷轻量预检正常",
        "href": "/admin/questionnaires",
    }


def _build_mcp_runtime_group() -> dict[str, Any]:
    snapshot = repo.get_mcp_runtime_snapshot(current_app.config)
    items: list[dict[str, Any]] = []
    if not snapshot["bearer_token_configured"]:
        items.append(
            {
                "title": "MCP Bearer Token 缺失",
                "meta": "MCP runtime config",
                "detail": "MCP_BEARER_TOKEN 未配置，后台只能显示异常摘要。",
            }
        )
    return {
        "key": "mcp_runtime",
        "title": "MCP Runtime",
        "count": len(items),
        "description": "MCP 运行时配置异常摘要。",
        "tone": "warn" if items else "ok",
        "items": items,
        "empty_title": "MCP runtime 配置正常",
        "href": "/admin/mcp",
    }


def build_dashboard_todos() -> dict[str, Any]:
    groups = [
        *build_jobs_dashboard_groups(),
        _build_failed_apply_group(),
        _build_questionnaire_preflight_group(),
        _build_mcp_runtime_group(),
    ]
    return {
        "groups": groups,
        "total_pending": sum(int(group["count"]) for group in groups),
    }


def build_dashboard_cards() -> list[dict[str, Any]]:
    return build_dashboard_summary()["cards"]
