from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.integration_gateway.dispatch import DispatchGateway
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.typing import JsonDict

from .dto import BatchSendRequest, DoNotDisturbRequest, UserOpsListRequest
from .repo import UserOpsRepository, build_user_ops_repository
from .user_ops import apply_filters, build_overview_cards, normalize_filters, resolve_batch_targets

_REPO = build_user_ops_repository()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _filter_options(rows: list[JsonDict]) -> JsonDict:
    return {
        "class_term_no": sorted({row["class_term_no"] for row in rows if row.get("class_term_no")}),
        "owner_userid": sorted({row["owner_userid"] for row in rows if row.get("owner_userid")}),
        "wecom_status": ["all", "added", "not_added"],
        "mobile_binding_status": ["all", "bound", "unbound"],
        "activation_bucket": ["all", "activated", "not_activated", "pending_input"],
    }


def reset_user_ops_fixture_state() -> None:
    _REPO.reset()


class GetUserOpsOverviewQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, request: UserOpsListRequest) -> JsonDict:
        normalized_filters = normalize_filters(request.filters)
        base_rows = self._repo.list_rows()
        rows = apply_filters(base_rows, normalized_filters)
        return {
            "ok": True,
            "filters": normalized_filters.model_dump(),
            "cards": build_overview_cards(rows),
            "metrics": {"lead_pool_total_count": len(base_rows), "filtered_total": len(rows)},
            "generated_at": _now_iso(),
            "class_term_options": sorted({row["class_term_no"] for row in base_rows if row.get("class_term_no")}),
        }

    __call__ = execute


class ListLeadPoolQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, request: UserOpsListRequest) -> JsonDict:
        normalized_filters = normalize_filters(request.filters)
        base_rows = self._repo.list_rows()
        rows = apply_filters(base_rows, normalized_filters)
        total = len(rows)
        page = rows[request.offset : request.offset + request.limit]
        return {
            "ok": True,
            "items": page,
            "total": total,
            "count": len(page),
            "limit": request.limit,
            "offset": request.offset,
            "filters": normalized_filters.model_dump(),
            "filter_options": _filter_options(base_rows),
            "meta": {"source": "aicrm_next", "generated_at": _now_iso()},
        }

    __call__ = execute


class PreviewUserOpsBatchSendCommand:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, request: BatchSendRequest) -> JsonDict:
        request.filters = normalize_filters(request.filters)
        rows = apply_filters(self._repo.list_rows(), request.filters)
        return {"ok": True, **resolve_batch_targets(rows, request)}

    __call__ = execute


class ExecuteUserOpsBatchSendCommand:
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        dispatch_gateway: DispatchGateway | None = None,
    ) -> None:
        self._repo = repo or _REPO
        self._dispatch_gateway = dispatch_gateway or DispatchGateway()

    def execute(self, request: BatchSendRequest) -> JsonDict:
        if not request.confirm:
            raise ContractError("confirm=true is required")
        preview = PreviewUserOpsBatchSendCommand(self._repo)(request)
        if not preview["has_body"]:
            raise ContractError("content is required")

        task_results: list[JsonDict] = []
        sender_userids: list[str] = []
        for bucket in preview["owner_buckets"]:
            dispatch_result = self._dispatch_gateway.dispatch_user_ops_private_message_batch(
                owner_bucket=bucket,
                content=request.content,
                images=request.images,
                attachments=request.attachments,
            )
            sender_userid = str(bucket.get("sender_userid") or bucket.get("owner_userid") or "")
            sender_userids.append(sender_userid)
            task_results.append(
                {
                    "owner_userid": bucket["owner_userid"],
                    "sender_userid": sender_userid,
                    "owner_display_name": bucket.get("owner_display_name") or sender_userid,
                    "external_userids": bucket["external_userids"],
                    "external_userid_count": len(bucket["external_userids"]),
                    "target_count": bucket["target_count"],
                    "task_id": dispatch_result["task_id"],
                    "status": dispatch_result["status"],
                    "status_label": dispatch_result["status_label"],
                    "error_message": dispatch_result["error_message"],
                    "dispatch_adapter": dispatch_result["dispatch_adapter"],
                }
            )

        sent_count = sum(result["target_count"] for result in task_results)
        record = self._repo.create_send_record(
            {
                "selected_count": preview["selected_count"],
                "eligible_count": preview["eligible_count"],
                "sent_count": sent_count,
                "skipped_count": preview["skipped_count"],
                "skipped_reasons": preview["skipped_by_reason"],
                "skipped_by_reason": preview["skipped_by_reason"],
                "skipped_summary": preview["skipped_summary"],
                "skip_summary": preview["skip_summary"],
                "include_do_not_disturb": preview["include_do_not_disturb"],
                "content_preview": preview["content_preview"],
                "image_count": preview["image_count"],
                "sender_userids": sorted(set(sender_userids)),
                "filter_snapshot": preview["filters"],
                "operator": request.operator,
                "status": "created",
                "status_label": "已创建任务",
                "task_results": task_results,
            }
        )
        execution_summary = {
            "dispatch_adapter": "fake_wecom",
            "task_count": len(task_results),
            "sent_count": sent_count,
            "delivery_status_supported": False,
        }
        return {
            "ok": True,
            **preview,
            "record_id": record["record_id"],
            "sent_count": sent_count,
            "execution_summary": execution_summary,
            "task_results": task_results,
        }

    __call__ = execute


class ListUserOpsSendRecordsQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, limit: int = 20, offset: int = 0) -> JsonDict:
        records = self._repo.list_send_records()
        page = records[offset : offset + limit]
        summaries = [{key: value for key, value in record.items() if key != "task_results"} for record in page]
        return {
            "ok": True,
            "items": summaries,
            "records": summaries,
            "count": len(summaries),
            "total": len(records),
            "limit": limit,
            "offset": offset,
        }

    __call__ = execute


class GetUserOpsSendRecordQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, record_id: str) -> JsonDict:
        record = self._repo.get_send_record(record_id)
        if record is None:
            raise NotFoundError("send record not found")
        task_results = record.get("task_results", [])
        record_summary = {key: value for key, value in record.items() if key != "task_results"}
        return {
            "ok": True,
            "record": record_summary,
            "task_results": task_results,
            "delivery_status_supported": False,
            "status_note": "当前只支持 fake dispatch 任务创建结果，不轮询企业微信送达状态。",
        }

    __call__ = execute


class RefreshUserOpsSendRecordStatusCommand:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, record_id: str) -> JsonDict:
        detail = GetUserOpsSendRecordQuery(self._repo)(record_id)
        return {"ok": True, **detail, "refreshed": False}

    __call__ = execute


class SetUserOpsDoNotDisturbCommand:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _REPO

    def execute(self, request: DoNotDisturbRequest) -> JsonDict:
        external_userid = request.external_userid.strip()
        mobile = request.mobile.strip()
        if not external_userid and not mobile:
            raise ContractError("external_userid or mobile is required")

        action = request.action.strip().lower()
        is_active = request.is_active
        if is_active is None:
            is_active = action not in {"disable", "cancel", "clear", "remove"}

        row = self._repo.set_do_not_disturb(
            external_userid=external_userid,
            mobile=mobile,
            reason_code=request.reason_code.strip() or "manual_set",
            reason_text=request.reason_text.strip() or "运营设置",
            is_active=bool(is_active),
            operator=request.operator,
        )
        if row is None:
            raise NotFoundError("target is not in user_ops_pool_current")
        return {
            "ok": True,
            "target": {
                "id": row["id"],
                "external_userid": row["external_userid"],
                "mobile": row["mobile"],
            },
            "do_not_disturb": row["do_not_disturb"],
            "do_not_disturb_reasons": row["do_not_disturb_reasons"],
        }

    __call__ = execute
