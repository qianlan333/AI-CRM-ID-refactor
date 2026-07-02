from __future__ import annotations

from .dto import DeliveryLineageDetail, DeliveryLineageItem, DeliveryLineageList
from .repository import DeliveryLineageRepository, build_delivery_lineage_repository


def list_delivery_lineage(
    *,
    repo: DeliveryLineageRepository | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    repository = repo or build_delivery_lineage_repository()
    safe_limit = _safe_limit(limit)
    safe_offset = max(0, int(offset or 0))
    items = repository.list_items(limit=safe_limit, offset=safe_offset)
    return DeliveryLineageList(items=items, limit=safe_limit, offset=safe_offset).model_dump()


def get_delivery_lineage(lineage_id: str, *, repo: DeliveryLineageRepository | None = None) -> dict:
    repository = repo or build_delivery_lineage_repository()
    item = repository.get_item(str(lineage_id or "").strip())
    if item is None:
        return {"ok": False, "status_code": 404, "error_code": "delivery_lineage_not_found"}
    return DeliveryLineageDetail(item=item).model_dump()


def list_delivery_lineage_by_unionid(
    unionid: str,
    *,
    repo: DeliveryLineageRepository | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    repository = repo or build_delivery_lineage_repository()
    safe_limit = _safe_limit(limit)
    safe_offset = max(0, int(offset or 0))
    items = repository.list_by_unionid(str(unionid or "").strip(), limit=safe_limit, offset=safe_offset)
    return DeliveryLineageList(items=items, limit=safe_limit, offset=safe_offset).model_dump()


def list_delivery_lineage_by_trace(
    trace_id: str,
    *,
    repo: DeliveryLineageRepository | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    repository = repo or build_delivery_lineage_repository()
    safe_limit = _safe_limit(limit)
    safe_offset = max(0, int(offset or 0))
    items = repository.list_by_trace(str(trace_id or "").strip(), limit=safe_limit, offset=safe_offset)
    return DeliveryLineageList(items=items, limit=safe_limit, offset=safe_offset).model_dump()


def _safe_limit(limit: int) -> int:
    return max(1, min(int(limit or 50), 100))
