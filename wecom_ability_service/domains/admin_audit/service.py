from __future__ import annotations

import json
from math import ceil
from typing import Any
from urllib.parse import urlencode

from . import repo

LEGACY_ADMIN_PATH_ROWS = [
    {
        "legacy_path": "/admin/user-ops/ui",
        "strategy": "redirect",
        "replacement": "/admin/user-ops",
        "status": "deprecated",
        "notes": "旧入口已收口到统一运营看板；保留 302 兼容，不再单独维护 legacy 页面。",
    },
    {
        "legacy_path": "/admin/questionnaires/ui",
        "strategy": "redirect",
        "replacement": "/admin/questionnaires",
        "status": "deprecated",
        "notes": "统一跳到问卷中心；问卷 admin 不再是孤立页面。",
    },
    {
        "legacy_path": "/admin/class-user-management/ui",
        "strategy": "redirect",
        "replacement": "/admin/class-users?tab=class-users",
        "status": "deprecated",
        "notes": "统一纳入运营模块，旧入口只保留兼容跳转。",
    },
    {
        "legacy_path": "/admin/class-user-backoffice/ui",
        "strategy": "redirect",
        "replacement": "/admin/class-users?tab=class-users",
        "status": "deprecated",
        "notes": "统一纳入运营模块，旧入口只保留兼容跳转。",
    },
]

RISK_CONTROL_ROWS = [
    {
        "scope": "Customer Tags",
        "risk_level": "high",
        "strategy": "preview first",
        "confirmation": "checkbox confirm",
        "notes": "客户详情页默认 dry-run 预览；勾选确认才执行真实打标/去标。",
    },
    {
        "scope": "Customer Tasks",
        "risk_level": "high",
        "strategy": "preview first",
        "confirmation": "checkbox confirm",
        "notes": "private/group/moment task 默认先生成 preview payload。",
    },
    {
        "scope": "Operations Imports / Backfill / Deferred Jobs",
        "risk_level": "high",
        "strategy": "confirm required",
        "confirmation": "checkbox confirm",
        "notes": "导入、回填、跑作业统一要求确认；backfill 支持 dry-run。",
    },
    {
        "scope": "App Settings",
        "risk_level": "high",
        "strategy": "confirm required",
        "confirmation": "confirm=true",
        "notes": "secret 仅 masked 展示；保存必须显式确认并落审计。",
    },
    {
        "scope": "MCP High-Risk Sample Call",
        "risk_level": "high",
        "strategy": "preview or second confirm",
        "confirmation": "confirm_high_risk",
        "notes": "高风险 MCP 写工具默认不 live run；无 native dry-run 的只展示 request preview。",
    },
]

RUNBOOK_ROWS = [
    {"label": "服务状态", "href": "/api/ops/status", "description": "服务 runtime 快照与健康摘要。"},
    {"label": "Archive 健康检查", "href": "/api/archive/health", "description": "Archive SDK / 配置检查。"},
    {"label": "MCP 控制台", "href": "/admin/mcp", "description": "查看 `/mcp` runtime、preflight 和 sample call。"},
    {"label": "问卷中心", "href": "/admin/questionnaires", "description": "执行 questionnaire preflight 并检查提交 / apply。"},
    {"label": "审计中心", "href": "/admin/audit", "description": "查询后台写操作、预览和配置变更。"},
]

TARGET_ROUTE_MAP = {
    "customer_tag_action": lambda target_id: f"/admin/customers/{target_id}?tab=tags",
    "customer_task_action": lambda target_id: f"/admin/customers/{target_id}?tab=tasks",
    "questionnaire_console_action": lambda target_id: f"/admin/questionnaires/{target_id}",
    "operations_console_action": lambda target_id: "/admin/user-ops",
    "owner_role_map": lambda target_id: f"/admin/config/routing?edit_owner={target_id}",
    "routing_rule_config": lambda target_id: f"/admin/config/routing?edit_rule={target_id}",
    "signup_tag_rule": lambda target_id: f"/admin/config/signup-tags?edit_tag={target_id}",
    "class_term_tag_mapping": lambda target_id: f"/admin/config/class-term-tags?edit_mapping={target_id}",
    "app_setting": lambda target_id: "/admin/config/app-settings",
    "mcp_tool_setting": lambda target_id: f"/admin/config/mcp-tools?edit_tool={target_id}",
    "mcp_preflight": lambda target_id: "/admin/mcp",
    "mcp_sample_call": lambda target_id: f"/admin/mcp?tool={target_id}",
    "jobs_console_action": lambda target_id: "/admin/jobs",
}

SORTABLE_COLUMNS = (
    {"key": "created_at", "label": "时间"},
    {"key": "operator", "label": "Operator"},
    {"key": "action_type", "label": "Action"},
    {"key": "target_type", "label": "Target Type"},
    {"key": "target_id", "label": "Target"},
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _sort_dir(value: Any) -> str:
    return "asc" if _normalized_text(value).lower() == "asc" else "desc"


def _build_href(base_path: str, params: dict[str, Any]) -> str:
    filtered = {key: value for key, value in params.items() if value not in ("", None, False)}
    if not filtered:
        return base_path
    return f"{base_path}?{urlencode(filtered, doseq=True)}"


def _target_href(target_type: str, target_id: str) -> str:
    builder = TARGET_ROUTE_MAP.get(_normalized_text(target_type))
    if builder:
        return builder(_normalized_text(target_id))
    return _build_href("/admin/audit", {"target_type": target_type, "target_id": target_id})


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _log_preview_text(value: Any) -> str:
    text = _pretty_json(value)
    if len(text) <= 200:
        return text
    return text[:200] + "..."


def build_admin_audit_payload(args: Any) -> dict[str, Any]:
    filters = {
        "q": _normalized_text(args.get("q")),
        "target_type": _normalized_text(args.get("target_type")),
        "action_type": _normalized_text(args.get("action_type")),
        "operator": _normalized_text(args.get("operator")),
        "target_id": _normalized_text(args.get("target_id")),
        "page": _normalized_int(args.get("page"), default=1, minimum=1, maximum=100000),
        "page_size": _normalized_int(args.get("page_size"), default=20, minimum=10, maximum=100),
        "sort_by": _normalized_text(args.get("sort_by")) or "created_at",
        "sort_dir": _sort_dir(args.get("sort_dir")),
    }
    query_result = repo.list_admin_operation_logs(
        q=filters["q"],
        target_type=filters["target_type"],
        action_type=filters["action_type"],
        operator=filters["operator"],
        target_id=filters["target_id"],
        page=filters["page"],
        page_size=filters["page_size"],
        sort_by=filters["sort_by"],
        sort_dir=filters["sort_dir"],
    )
    total = int(query_result["total"] or 0)
    total_pages = max(1, ceil(total / filters["page_size"])) if filters["page_size"] else 1
    if filters["page"] > total_pages:
        filters["page"] = total_pages
        query_result = repo.list_admin_operation_logs(
            q=filters["q"],
            target_type=filters["target_type"],
            action_type=filters["action_type"],
            operator=filters["operator"],
            target_id=filters["target_id"],
            page=filters["page"],
            page_size=filters["page_size"],
            sort_by=filters["sort_by"],
            sort_dir=filters["sort_dir"],
        )
    items = []
    for row in query_result["items"]:
        items.append(
            {
                **row,
                "target_href": _target_href(_normalized_text(row.get("target_type")), _normalized_text(row.get("target_id"))),
                "detail_href": _build_href("/admin/audit", {**filters, "log_id": row["id"]}),
                "before_preview": _log_preview_text(row.get("before_json") or {}),
                "after_preview": _log_preview_text(row.get("after_json") or {}),
                "before_pretty": _pretty_json(row.get("before_json") or {}),
                "after_pretty": _pretty_json(row.get("after_json") or {}),
            }
        )
    selected_log_id = _normalized_int(args.get("log_id"), default=0, minimum=0, maximum=10**9)
    selected_entry = next((item for item in items if int(item["id"]) == selected_log_id), None) if selected_log_id else None
    if not selected_entry and selected_log_id:
        row = repo.get_admin_operation_log(selected_log_id)
        if row:
            selected_entry = {
                **row,
                "target_href": _target_href(_normalized_text(row.get("target_type")), _normalized_text(row.get("target_id"))),
                "before_pretty": _pretty_json(row.get("before_json") or {}),
                "after_pretty": _pretty_json(row.get("after_json") or {}),
            }
    base_params = {key: value for key, value in filters.items() if key != "page"}
    page_numbers = []
    window_start = max(1, filters["page"] - 2)
    window_end = min(total_pages, filters["page"] + 2)
    for page_number in range(window_start, window_end + 1):
        page_numbers.append(
            {
                "label": str(page_number),
                "href": _build_href("/admin/audit", {**base_params, "page": page_number}),
                "active": page_number == filters["page"],
            }
        )
    sort_links = {
        item["key"]: _build_href(
            "/admin/audit",
            {
                **filters,
                "sort_by": item["key"],
                "sort_dir": "asc" if filters["sort_by"] == item["key"] and filters["sort_dir"] == "desc" else "desc",
                "page": 1,
            },
        )
        for item in SORTABLE_COLUMNS
    }
    return {
        "filters": filters,
        "items": items,
        "selected_entry": selected_entry or {},
        "summary_cards": [
            {"label": "Audit Logs", "value": total, "description": "当前筛选结果总数"},
            {"label": "Operators", "value": len({item["operator"] for item in items if _normalized_text(item.get("operator"))}), "description": "当前页涉及操作人"},
            {"label": "Targets", "value": len({item["target_type"] for item in items if _normalized_text(item.get("target_type"))}), "description": "当前页 target type 数量"},
            {
                "label": "High Risk",
                "value": sum(
                    1
                    for item in items
                    if any(token in _normalized_text(item.get("action_type")) for token in ("execute_", "run_", "save_", "disable_", "enable_", "import_", "apply_"))
                ),
                "description": "当前页高风险动作数量",
            },
        ],
        "pagination": {
            "page": filters["page"],
            "page_size": filters["page_size"],
            "total": total,
            "total_pages": total_pages,
            "prev_href": _build_href("/admin/audit", {**base_params, "page": filters["page"] - 1}) if filters["page"] > 1 else "",
            "next_href": _build_href("/admin/audit", {**base_params, "page": filters["page"] + 1}) if filters["page"] < total_pages else "",
            "page_links": page_numbers,
        },
        "sort_columns": SORTABLE_COLUMNS,
        "sort_links": sort_links,
        "operator_options": repo.list_distinct_values("operator"),
        "action_type_options": repo.list_distinct_values("action_type"),
        "target_type_options": repo.list_distinct_values("target_type"),
        "shareable_href": _build_href("/admin/audit", filters),
    }


def build_risk_control_rows() -> list[dict[str, str]]:
    return [dict(item) for item in RISK_CONTROL_ROWS]


def build_legacy_admin_path_rows() -> list[dict[str, str]]:
    return [dict(item) for item in LEGACY_ADMIN_PATH_ROWS]


def build_runbook_rows() -> list[dict[str, str]]:
    return [dict(item) for item in RUNBOOK_ROWS]
