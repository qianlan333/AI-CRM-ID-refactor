from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import Response

from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask

router = APIRouter()
wildcard_router = APIRouter()

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@wildcard_router.api_route("/api/admin/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/alipay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/h5/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/h5/alipay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/alipay/{path:path}", methods=_ALL_METHODS)
async def legacy_production_compat_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)
