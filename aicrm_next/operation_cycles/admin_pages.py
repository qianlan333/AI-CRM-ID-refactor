from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell.navigation import admin_path_for, shell_context

from .application import get_run, get_strategy, list_strategies, list_strategy_runs


router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "admin_shell" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _detail_href(strategy_key: object, run_key: object | None = None) -> str:
    params = {"strategy_key": str(strategy_key or "")}
    if run_key is None:
        return admin_path_for("api.admin_operation_cycle_strategy_page", **params)
    return admin_path_for("api.admin_operation_cycle_run_page", run_key=str(run_key or ""), **params)


def _strategy_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {**item, "detail_href": _detail_href(item.get("strategy_key"))}
        for item in _plain(payload.get("items") or [])
        if isinstance(item, dict)
    ]


def _run_summaries(payload: dict[str, Any], strategy_key: str) -> list[dict[str, Any]]:
    return [
        {**item, "detail_href": _detail_href(strategy_key, item.get("run_key"))}
        for item in _plain(payload.get("items") or [])
        if isinstance(item, dict)
    ]


def _run_view(run: dict[str, Any]) -> dict[str, Any]:
    funnel = run.get("funnel") or {}
    planned = funnel.get("planned_target_count") or {}
    sent = funnel.get("effective_sent_count") or {}
    failed = funnel.get("failed_count") or {}
    failure_classification = str(failed.get("classification") or "").strip().lower()
    retryable_failure = failure_classification == "failed_retryable"
    completion_rate = None
    if planned.get("status") == "observed" and sent.get("status") == "observed" and planned.get("value"):
        completion_rate = round(float(sent["value"]) * 100 / float(planned["value"]), 2)
    return {
        **run,
        "plan": {
            "version_label": run.get("plan_version") or "",
            "status": run.get("plan_status") or "",
            "source": run.get("plan_source") or "",
            "plan_source": run.get("plan_source") or "",
            "review_status": run.get("review_status") or "",
            "target_count": planned.get("value") if planned.get("status") in {"observed", "partial_lower_bound"} else None,
            "target_count_state": planned.get("status") or "unknown",
            "conflict_notice": "计划元数据与实际发送事实存在冲突" if run.get("fact_conflict") else "",
        },
        "delivery": {
            "status": run.get("delivery_status") or "",
            "source": sent.get("data_source") or failed.get("data_source") or "",
            "source_label": sent.get("data_source") or failed.get("data_source") or "",
            "effective_sent_count": sent.get("value"),
            "effective_sent_state": sent.get("status") or "unknown",
            "failed_count": failed.get("value"),
            "failed_state": failed.get("status") or "unknown",
            "failure_classification": failure_classification,
            "retryable_failed_count": failed.get("value") if retryable_failure else None,
            "retryable_failed_state": failed.get("status") if retryable_failure else "unknown",
            "completion_rate": completion_rate,
            "completion_rate_state": "observed" if completion_rate is not None else "unknown",
            "failure_summary": failed.get("limitation") or "",
        },
    }


def _observation_windows(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for raw_metric in metrics:
        metric = {
            **raw_metric,
            "value_state": raw_metric.get("value_state") or raw_metric.get("value_status") or "unknown",
            "limitation": raw_metric.get("limitation") or "；".join(raw_metric.get("limitations") or []),
        }
        window = str(metric.get("observation_window") or "未指定窗口")
        group = grouped.setdefault(
            window,
            {
                "label": window,
                "window_label": window,
                "status": metric.get("value_state") or "unknown",
                "value_state": metric.get("value_state") or "unknown",
                "data_quality": metric.get("data_quality") or "unknown",
                "window_start": metric.get("window_start"),
                "window_end": metric.get("window_end"),
                "limitation": metric.get("limitation") or metric.get("limitations") or "",
                "metrics": [],
            },
        )
        group["metrics"].append(metric)
        if group["status"] != "observed" and metric.get("value_state") == "observed":
            group["status"] = "observed"
            group["value_state"] = "observed"
    return list(grouped.values())


def _attempt_view(item: dict[str, Any]) -> dict[str, Any]:
    summary = item.get("summary")
    if isinstance(summary, dict):
        summary = summary.get("summary") or summary.get("note") or summary.get("detail") or ""
    return {**item, "summary": summary or "", "finished_at": item.get("finished_at") or item.get("ended_at")}


def _stage_view(item: dict[str, Any]) -> dict[str, Any]:
    summary = item.get("summary")
    if isinstance(summary, dict):
        summary = summary.get("summary") or summary.get("note") or summary.get("detail") or ""
    return {**item, "label": item.get("label") or item.get("stage"), "summary": summary or ""}


def _retrospective_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "findings": payload.get("findings") or payload.get("observations") or []}


def _next_iteration_view(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "changes": payload.get("changes") or payload.get("actions") or [],
        "rationale": payload.get("rationale") or payload.get("hypothesis") or "",
        "applied_version": payload.get("applied_version") or payload.get("applied_strategy_version"),
    }


@router.get("/admin/operation-cycles", name="api.admin_operation_cycles_page", response_class=HTMLResponse)
def admin_operation_cycles_page(request: Request):
    payload = _plain(list_strategies(limit=100, offset=0))
    context = shell_context(
        request=request,
        page_title="运营闭环",
        page_summary="按策略查看每一次真实执行、结果复盘与下一轮优化。页面只读，不触发任何外部动作。",
        active_endpoint="api.admin_operation_cycles_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "运营闭环", "href": ""},
            ],
            "strategy_summaries": _strategy_summaries(payload),
        }
    )
    return templates.TemplateResponse(request, "admin_shell/operation_cycles_list.html", context)


@router.get(
    "/admin/operation-cycles/{strategy_key}/runs/{run_key}",
    name="api.admin_operation_cycle_run_page",
    response_class=HTMLResponse,
)
def admin_operation_cycle_run_page(request: Request, strategy_key: str, run_key: str):
    payload = _plain(get_run(run_key))
    if not payload:
        return _not_found(request, "未找到这次运行")
    run = _run_view(payload.get("run") or {})
    if str(run.get("strategy_key") or strategy_key) != strategy_key:
        return _not_found(request, "这次运行不属于当前策略")
    strategy_payload = _plain(get_strategy(strategy_key)) or {}
    strategy = strategy_payload.get("strategy") or {"strategy_key": strategy_key, "title": strategy_key}
    metrics = [item for item in payload.get("metrics") or [] if isinstance(item, dict)]
    context = shell_context(
        request=request,
        page_title=str(run.get("label") or run_key),
        page_summary="逐步还原任务目标、尝试、人审、发送事实、分窗口结果、复盘与优化采纳。",
        active_endpoint="api.admin_operation_cycles_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "运营闭环", "href": admin_path_for("api.admin_operation_cycles_page")},
                {"label": str(strategy.get("title") or strategy_key), "href": _detail_href(strategy_key)},
                {"label": str(run.get("label") or run_key), "href": ""},
            ],
            "strategy": {**strategy, "detail_href": _detail_href(strategy_key)},
            "run": {**run, "detail_href": _detail_href(strategy_key, run_key)},
            "attempts": [_attempt_view(item) for item in payload.get("attempts") or []],
            "stages": [_stage_view(item) for item in payload.get("stages") or []],
            "funnel": run.get("funnel") or {},
            "observation_windows": _observation_windows(metrics),
            "retrospective": _retrospective_view(payload.get("retrospective") or {}),
            "next_iteration": _next_iteration_view(payload.get("next_iteration") or {}),
            "references": payload.get("references") or [],
            "snapshot": payload.get("snapshot") or {},
        }
    )
    return templates.TemplateResponse(request, "admin_shell/operation_cycles_run.html", context)


@router.get(
    "/admin/operation-cycles/{strategy_key}",
    name="api.admin_operation_cycle_strategy_page",
    response_class=HTMLResponse,
)
def admin_operation_cycle_strategy_page(request: Request, strategy_key: str):
    payload = _plain(get_strategy(strategy_key))
    if not payload:
        return _not_found(request, "未找到这个运营策略")
    strategy = payload.get("strategy") or {}
    runs_payload = _plain(list_strategy_runs(strategy_key, limit=100, offset=0))
    context = shell_context(
        request=request,
        page_title=str(strategy.get("title") or strategy_key),
        page_summary="先看本轮结论和核心漏斗，再追溯历史运行、策略版本、口径与数据源。",
        active_endpoint="api.admin_operation_cycles_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "运营闭环", "href": admin_path_for("api.admin_operation_cycles_page")},
                {"label": str(strategy.get("title") or strategy_key), "href": ""},
            ],
            "strategy": {**strategy, "detail_href": _detail_href(strategy_key)},
            "runs": _run_summaries(runs_payload, strategy_key),
            "strategy_versions": payload.get("versions") or [],
            "trend_windows": payload.get("trend") or [],
            "sources": payload.get("sources") or [],
        }
    )
    return templates.TemplateResponse(request, "admin_shell/operation_cycles_strategy.html", context)


def _not_found(request: Request, message: str):
    context = shell_context(
        request=request,
        page_title="运营闭环",
        page_summary=message,
        active_endpoint="api.admin_operation_cycles_page",
    )
    context.update({"strategy_summaries": [], "page_error": message})
    return templates.TemplateResponse(
        request,
        "admin_shell/operation_cycles_list.html",
        context,
        status_code=404,
    )
