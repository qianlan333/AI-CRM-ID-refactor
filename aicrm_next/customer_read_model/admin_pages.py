from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_shell import shell_context

from .application import ListCustomersQuery
from .dto import ListCustomersRequest

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

ADMIN_CUSTOMERS_UNAVAILABLE_MESSAGE = "客户列表暂不可用：生产客户读源正在同步或数据库连接繁忙，请稍后刷新。"


def _admin_customer_payload_from_list_result(
    *,
    result: dict,
    keyword: str,
    owner: str,
    mobile: str,
    tag: str,
    limit: int,
    offset: int,
) -> tuple[dict, str]:
    unavailable = not result.get("ok", True) or result.get("source_status") == "production_unavailable"
    page_error = ADMIN_CUSTOMERS_UNAVAILABLE_MESSAGE if unavailable else ""
    customers = [] if unavailable else list(result.get("customers") or result.get("items") or [])
    total = 0 if unavailable else int(result.get("total") or result.get("count") or len(customers))
    return (
        {
            "filters": {"keyword": keyword, "owner": owner, "mobile": mobile, "tag": tag},
            "customers": customers,
            "pagination": {
                "total": total,
                "has_prev": offset > 0,
                "has_next": offset + limit < total,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        },
        page_error,
    )


@router.get("/admin/customers", name="api.admin_console_customers")
def admin_customers(request: Request, keyword: str = "", owner: str = "", mobile: str = "", tag: str = "", offset: int = 0):
    limit = 50
    offset = max(int(offset or 0), 0)
    customer_query = ListCustomersRequest(
        owner_userid=owner or None,
        tag=tag or None,
        mobile=mobile or None,
        keyword=keyword or None,
        limit=limit,
        offset=offset,
    )
    result = ListCustomersQuery()(customer_query)
    customer_payload, page_error = _admin_customer_payload_from_list_result(
        result=result,
        keyword=keyword,
        owner=owner,
        mobile=mobile,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    context = shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="查看客户列表、筛选客户并打开客户档案。",
        active_endpoint="api.admin_console_customers",
    )
    context["page_error"] = page_error
    context["customer_payload"] = customer_payload
    return templates.TemplateResponse(request, "admin_console/customers.html", context)
