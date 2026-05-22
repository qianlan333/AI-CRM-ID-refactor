from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.integration_gateway.user_ops_adapters import (
    UserOpsBatchSendGateway,
    UserOpsDeferredJobGateway,
    UserOpsDndWriteGateway,
    WeComMessageDispatchAdapter,
    build_user_ops_batch_send_gateway,
    build_user_ops_deferred_job_gateway,
    build_user_ops_dnd_gateway,
    build_wecom_message_dispatch_adapter,
)
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import fixture_mode
from aicrm_next.shared.typing import JsonDict

from .dto import BatchSendRequest, DoNotDisturbRequest, UserOpsListRequest
from .repo import UserOpsRepository, build_user_ops_repository
from .user_ops import apply_filters, build_overview_cards, normalize_filters, resolve_batch_targets

_REPO: UserOpsRepository | None = None


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
    global _REPO
    if not fixture_mode():
        return
    if _REPO is None:
        _REPO = build_user_ops_repository()
    _REPO.reset()


def _default_repo() -> UserOpsRepository:
    global _REPO
    if _REPO is None:
        _REPO = build_user_ops_repository()
    return _REPO


def _media_refs_from_batch_request(request: BatchSendRequest) -> list[JsonDict]:
    refs: list[JsonDict] = []
    refs.extend({"kind": "image", "index": index} for index, _ in enumerate(request.images))
    refs.extend({"kind": "attachment", "index": index} for index, _ in enumerate(request.attachments))
    return refs


def _user_ops_side_effect_safety() -> JsonDict:
    return {
        "user_ops_dnd_mode": build_user_ops_dnd_gateway().mode,
        "user_ops_batch_send_mode": build_user_ops_batch_send_gateway().mode,
        "wecom_dispatch_mode": build_wecom_message_dispatch_adapter().mode,
        "user_ops_deferred_jobs_mode": build_user_ops_deferred_job_gateway().mode,
        "real_dnd_write_executed": False,
        "real_batch_send_executed": False,
        "real_wecom_dispatch_executed": False,
        "real_deferred_jobs_executed": False,
        "real_wecom_media_upload_executed": False,
        "side_effect_executed": False,
    }


class GetUserOpsOverviewQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _default_repo()

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
        self._repo = repo or _default_repo()

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
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        batch_gateway: UserOpsBatchSendGateway | None = None,
    ) -> None:
        self._repo = repo or _default_repo()
        self._batch_gateway = batch_gateway or build_user_ops_batch_send_gateway()

    def execute(self, request: BatchSendRequest) -> JsonDict:
        request.filters = normalize_filters(request.filters)
        rows = apply_filters(self._repo.list_rows(), request.filters)
        preview = resolve_batch_targets(rows, request)
        gateway_result = self._batch_gateway.build_batch_send_preview(
            selection_mode=request.selection_mode,
            filters=preview["filters"],
            selected_ids=request.selected_ids,
            excluded_ids=request.excluded_ids,
            content=request.content,
            targets=preview["final_targets"],
            owner_buckets=preview["owner_buckets"],
            include_do_not_disturb=preview["include_do_not_disturb"],
            media_refs=_media_refs_from_batch_request(request),
        )
        if not gateway_result["ok"]:
            raise ContractError(gateway_result["error_message"] or gateway_result["error_code"])
        return {
            "ok": True,
            **preview,
            "side_effect_safety": _user_ops_side_effect_safety(),
            "adapter_contract": {
                "batch_send": gateway_result,
            },
        }

    __call__ = execute


class ExecuteUserOpsBatchSendCommand:
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        batch_gateway: UserOpsBatchSendGateway | None = None,
        dispatch_adapter: WeComMessageDispatchAdapter | None = None,
    ) -> None:
        self._repo = repo or _default_repo()
        self._batch_gateway = batch_gateway or build_user_ops_batch_send_gateway()
        self._dispatch_adapter = dispatch_adapter or build_wecom_message_dispatch_adapter()

    def execute(self, request: BatchSendRequest) -> JsonDict:
        if not request.confirm:
            raise ContractError("confirm=true is required")
        preview = PreviewUserOpsBatchSendCommand(self._repo, batch_gateway=self._batch_gateway)(request)
        if not preview["has_body"]:
            raise ContractError("content is required")

        media_refs = _media_refs_from_batch_request(request)
        execute_gateway_result = self._batch_gateway.execute_batch_send(
            content=request.content,
            targets=preview["final_targets"],
            owner_buckets=preview["owner_buckets"],
            operator=request.operator,
            media_refs=media_refs,
        )
        if not execute_gateway_result["ok"]:
            raise ContractError(execute_gateway_result["error_message"] or execute_gateway_result["error_code"])

        task_results: list[JsonDict] = []
        sender_userids: list[str] = []
        for bucket in preview["owner_buckets"]:
            dispatch_result = self._dispatch_adapter.send_private_message(
                owner_userid=str(bucket.get("owner_userid") or ""),
                external_userids=list(bucket.get("external_userids") or []),
                content=request.content,
                media_refs=media_refs,
            )
            if not dispatch_result["ok"]:
                raise ContractError(dispatch_result["error_message"] or dispatch_result["error_code"])
            dispatch_payload = dispatch_result["result"]
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
                    "task_id": dispatch_payload["task_id"],
                    "status": dispatch_payload["status"],
                    "status_label": dispatch_payload["status_label"],
                    "error_message": dispatch_payload["error_message"],
                    "dispatch_adapter": dispatch_payload["dispatch_adapter"],
                    "adapter_contract": dispatch_result,
                }
            )

        sent_count = sum(result["target_count"] for result in task_results)
        record_payload = {
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
        record_gateway_result = self._batch_gateway.create_send_record(payload=record_payload)
        if not record_gateway_result["ok"]:
            raise ContractError(record_gateway_result["error_message"] or record_gateway_result["error_code"])
        record = self._repo.create_send_record(record_payload)
        summary_gateway_result = self._batch_gateway.build_send_result_summary(
            record_id=record["record_id"],
            task_results=task_results,
            sent_count=sent_count,
            skipped_count=preview["skipped_count"],
        )
        if not summary_gateway_result["ok"]:
            raise ContractError(summary_gateway_result["error_message"] or summary_gateway_result["error_code"])
        execution_summary = {
            "dispatch_adapter": "fake_wecom",
            "task_count": len(task_results),
            "sent_count": sent_count,
            "delivery_status_supported": False,
            "adapter_contract": summary_gateway_result,
            "side_effect_safety": _user_ops_side_effect_safety(),
        }
        return {
            "ok": True,
            **preview,
            "record_id": record["record_id"],
            "sent_count": sent_count,
            "execution_summary": execution_summary,
            "task_results": task_results,
            "side_effect_safety": _user_ops_side_effect_safety(),
            "adapter_contract": {
                "batch_send_execute": execute_gateway_result,
                "send_record": record_gateway_result,
            },
        }

    __call__ = execute


class ListUserOpsSendRecordsQuery:
    def __init__(self, repo: UserOpsRepository | None = None) -> None:
        self._repo = repo or _default_repo()

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
        self._repo = repo or _default_repo()

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
        self._repo = repo or _default_repo()

    def execute(self, record_id: str) -> JsonDict:
        detail = GetUserOpsSendRecordQuery(self._repo)(record_id)
        return {"ok": True, **detail, "refreshed": False}

    __call__ = execute


class EnqueueUserOpsDeferredJobCommand:
    def __init__(self, gateway: UserOpsDeferredJobGateway | None = None) -> None:
        self._gateway = gateway or build_user_ops_deferred_job_gateway()

    def execute(self, *, job_id: str = "", job_type: str = "", run_at: str = "", target: JsonDict | None = None, payload_summary: JsonDict | None = None) -> JsonDict:
        return self._gateway.enqueue_deferred_job(job_id=job_id, job_type=job_type, run_at=run_at, target=target or {}, payload_summary=payload_summary or {})

    __call__ = execute


class RunDueUserOpsDeferredJobsCommand:
    def __init__(self, gateway: UserOpsDeferredJobGateway | None = None) -> None:
        self._gateway = gateway or build_user_ops_deferred_job_gateway()

    def execute(self, *, now: str = "", limit: int = 100, job_ids: list[str] | None = None) -> JsonDict:
        return self._gateway.run_due_jobs(now=now, limit=limit, job_ids=job_ids or [])

    __call__ = execute


class SetUserOpsDoNotDisturbCommand:
    def __init__(
        self,
        repo: UserOpsRepository | None = None,
        dnd_gateway: UserOpsDndWriteGateway | None = None,
    ) -> None:
        self._repo = repo or _default_repo()
        self._dnd_gateway = dnd_gateway or build_user_ops_dnd_gateway()

    def execute(self, request: DoNotDisturbRequest) -> JsonDict:
        external_userid = request.external_userid.strip()
        mobile = request.mobile.strip()
        if not external_userid and not mobile:
            raise ContractError("external_userid or mobile is required")

        action = request.action.strip().lower()
        is_active = request.is_active
        if is_active is None:
            is_active = action not in {"disable", "cancel", "clear", "remove"}

        gateway_result = (
            self._dnd_gateway.enable_do_not_disturb(
                external_userid=external_userid,
                mobile=mobile,
                reason_code=request.reason_code.strip() or "manual_set",
                reason_text=request.reason_text.strip() or "运营设置",
                operator=request.operator,
            )
            if is_active
            else self._dnd_gateway.cancel_do_not_disturb(
                external_userid=external_userid,
                mobile=mobile,
                reason_code=request.reason_code.strip() or "manual_set",
                reason_text=request.reason_text.strip() or "运营设置",
                operator=request.operator,
            )
        )
        if not gateway_result["ok"]:
            raise ContractError(gateway_result["error_message"] or gateway_result["error_code"])

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
            "side_effect_safety": _user_ops_side_effect_safety(),
            "adapter_contract": {
                "dnd_write": gateway_result,
            },
        }

    __call__ = execute
