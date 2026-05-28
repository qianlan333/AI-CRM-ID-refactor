from __future__ import annotations

from typing import Any

from .legacy_flask_facade import _legacy_app, _legacy_import_module


def _text(value: Any) -> str:
    return str(value or "").strip()


def sidebar_lead_pool_status(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    queries = _legacy_import_module(".application.user_ops.queries")

    with _legacy_app().app_context():
        return queries.GetSidebarLeadPoolStatusQuery()(
            queries.GetSidebarLeadPoolStatusQueryDTO(
                external_userid=_text(external_userid),
                owner_userid=_text(owner_userid),
            )
        )


def sidebar_signup_tag_status(*, external_userid: str) -> dict[str, Any]:
    dto = _legacy_import_module(".application.class_user.dto")
    queries = _legacy_import_module(".application.class_user.queries")
    admin_support = _legacy_import_module(".http.admin_support")
    marketing_support = _legacy_import_module(".http.sidebar_marketing_support")

    with _legacy_app().app_context():
        current_status = queries.GetClassUserStatusCurrentQuery()(
            dto.GetClassUserStatusCurrentQueryDTO(external_userid=_text(external_userid))
        ) or {}
        configured = admin_support._configured_signup_tag_rules_payload()
        return {
            "definitions": configured.get("definitions") or [],
            "initialized": bool(configured.get("initialized")),
            "missing_statuses": configured.get("missing_statuses") or [],
            "current_signup_status": _text(current_status.get("signup_status")),
            "current_tag": _text(current_status.get("signup_label_name")),
            "wecom_tag_sync_status": _text(current_status.get("wecom_tag_sync_status")),
            "wecom_tag_sync_error": _text(current_status.get("wecom_tag_sync_error")),
            "marketing_profile": marketing_support.get_customer_marketing_profile(_text(external_userid)),
        }


def sidebar_marketing_status(*, external_userid: str) -> dict[str, Any]:
    marketing_support = _legacy_import_module(".http.sidebar_marketing_support")

    normalized_external_userid = _text(external_userid)
    with _legacy_app().app_context():
        if not marketing_support.sidebar_marketing_target_exists(normalized_external_userid):
            raise LookupError("customer not found")
        preview = marketing_support.preview_signup_conversion_customer(external_userid=normalized_external_userid)
        return {"marketing_status": marketing_support.marketing_status_payload(preview)}


def sidebar_v2_workbench_readonly(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    sidebar_v2 = _legacy_import_module(".domains.sidebar_v2")
    sidebar_v2_service = _legacy_import_module(".domains.sidebar_v2.service")

    normalized_external_userid = _text(external_userid)
    normalized_owner = _text(owner_userid)
    with _legacy_app().app_context():
        context = sidebar_v2_service._context(normalized_external_userid)
        binding = dict(context.get("binding") or {}) or sidebar_v2_service._binding_status(
            normalized_external_userid,
            normalized_owner,
        )
        customer = sidebar_v2_service._customer_payload(
            context,
            binding,
            normalized_external_userid,
            normalized_owner,
        )
        questionnaires = sidebar_v2.get_questionnaires(external_userid=normalized_external_userid)["questionnaires"]
        sidebar_context = dict((context.get("customer") or {}).get("sidebar_context") or {})
        workflow_title = (
            _text(sidebar_context.get("workflow_title"))
            or _text(sidebar_context.get("sop_title"))
            or _text(sidebar_context.get("program_name"))
            or sidebar_v2_service.repo.get_workflow_title_for_customer(normalized_external_userid)
        )
        return {
            "customer": customer,
            "workflow": {"title": workflow_title},
            "profile": sidebar_v2_service._profile_payload(normalized_external_userid, context, questionnaires),
            "modules": list(sidebar_v2_service.MODULES),
        }


def sidebar_v2_questionnaires(*, external_userid: str) -> dict[str, Any]:
    sidebar_v2 = _legacy_import_module(".domains.sidebar_v2")

    with _legacy_app().app_context():
        return sidebar_v2.get_questionnaires(external_userid=_text(external_userid))


def sidebar_v2_materials(*, material_type: str, limit: int = 50) -> dict[str, Any]:
    sidebar_v2 = _legacy_import_module(".domains.sidebar_v2")

    with _legacy_app().app_context():
        return sidebar_v2.list_materials(material_type=_text(material_type), limit=limit)


def sidebar_v2_image_thumbnail(image_id: int) -> dict[str, Any]:
    sidebar_v2 = _legacy_import_module(".domains.sidebar_v2")

    with _legacy_app().app_context():
        return sidebar_v2.get_image_thumbnail(int(image_id))


def sidebar_v2_other_staff_messages(
    *,
    external_userid: str,
    current_userid: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    sidebar_v2 = _legacy_import_module(".domains.sidebar_v2")

    with _legacy_app().app_context():
        return sidebar_v2.get_other_staff_messages(
            external_userid=_text(external_userid),
            current_userid=_text(current_userid),
            limit=limit,
        )


def sidebar_v2_products(*, external_userid: str) -> dict[str, Any]:
    sidebar_v2 = _legacy_import_module(".domains.sidebar_v2")

    with _legacy_app().app_context():
        return sidebar_v2.get_products(external_userid=_text(external_userid))


def sidebar_v2_orders_readonly(*, external_userid: str) -> dict[str, Any]:
    sidebar_v2_service = _legacy_import_module(".domains.sidebar_v2.service")

    normalized_external_userid = _text(external_userid)
    with _legacy_app().app_context():
        context = sidebar_v2_service._context(normalized_external_userid)
        binding = dict(context.get("binding") or {}) or sidebar_v2_service._binding_status(
            normalized_external_userid,
            "",
        )
        customer = sidebar_v2_service._customer_payload(context, binding, normalized_external_userid, "")
        rows = sidebar_v2_service.repo.list_customer_wechat_pay_orders(
            external_userid=normalized_external_userid,
            mobile=_text(customer.get("mobile")),
            limit=20,
        )
        return {"orders": [sidebar_v2_service._order_item(dict(item)) for item in rows]}


def signup_conversion_batch_list(*, limit: int = 20, cursor: str = "") -> list[dict[str, Any]]:
    dto = _legacy_import_module(".application.automation_engine.dto")
    queries = _legacy_import_module(".application.automation_engine.queries")

    with _legacy_app().app_context():
        return queries.ListSignupConversionBatchesQuery()(
            dto.SignupConversionBatchListQueryDTO(limit=int(limit), cursor=_text(cursor))
        )


def signup_conversion_batch_detail(batch_id: int) -> dict[str, Any] | None:
    dto = _legacy_import_module(".application.automation_engine.dto")
    queries = _legacy_import_module(".application.automation_engine.queries")
    customer_automation = _legacy_import_module(".http.customer_automation")

    with _legacy_app().app_context():
        payload = queries.GetSignupConversionBatchQuery()(
            dto.SignupConversionBatchDetailQueryDTO(batch_id=int(batch_id))
        )
        if not payload:
            return None
        candidates = []
        for item in payload.get("candidates") or []:
            candidate = dict(item)
            external_userid = _text(candidate.get("external_userid"))
            candidate["customer_context"] = customer_automation._candidate_context(external_userid) if external_userid else {}
            candidates.append(candidate)
        payload["candidates"] = candidates
        return payload


def webhook_delivery_list(*, event_type: str = "", status: str = "", limit: int = 50) -> list[dict[str, Any]]:
    dto = _legacy_import_module(".application.automation_engine.dto")
    queries = _legacy_import_module(".application.automation_engine.queries")

    with _legacy_app().app_context():
        return queries.ListOutboundWebhookDeliveriesQuery()(
            dto.OutboundWebhookListQueryDTO(
                event_type=_text(event_type),
                status=_text(status),
                limit=int(limit),
            )
        )
