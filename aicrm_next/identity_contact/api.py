from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from aicrm_next.integration_gateway.legacy_customer_read_facade import get_customer_via_legacy
from aicrm_next.customer_read_model.dto import CustomerDetailRequest
from aicrm_next.shared.runtime import legacy_production_facade_enabled, production_data_ready

from .application import ResolvePersonIdentityQuery
from .dto import ResolvePersonIdentityRequest

router = APIRouter()


def _use_production_customer_facade() -> bool:
    return production_data_ready() and legacy_production_facade_enabled()


@router.get("/api/identity/resolve")
def resolve_identity(
    external_userid: str | None = None,
    mobile: str | None = None,
    openid: str | None = None,
    unionid: str | None = None,
) -> dict:
    result = ResolvePersonIdentityQuery()(
        ResolvePersonIdentityRequest(
            external_userid=external_userid,
            mobile=mobile,
            openid=openid,
            unionid=unionid,
        )
    )
    if result is None:
        raise HTTPException(status_code=404, detail="identity not found")
    return {"ok": True, "identity": result.model_dump()}


@router.get("/api/sidebar/contact-binding-status")
def sidebar_contact_binding_status(
    external_userid: str | None = None,
    owner_userid: str | None = None,
):
    resolved_external_userid = str(external_userid or "").strip()
    if not resolved_external_userid:
        return JSONResponse(
            {"ok": False, "error": "external_userid is required", "source_status": "input_error"},
            status_code=400,
        )
    if _use_production_customer_facade():
        try:
            customer = get_customer_via_legacy(CustomerDetailRequest(external_userid=resolved_external_userid)) or {}
        except Exception as exc:
            return JSONResponse(
                {
                    "ok": False,
                    "degraded": True,
                    "source_status": "production_unavailable",
                    "error_code": "contact_binding_status_unavailable",
                    "page_error": str(exc),
                    "route_owner": "ai_crm_next",
                },
                status_code=503,
            )
        binding = dict(customer.get("binding") or {})
        identity = dict(customer.get("identity") or {})
        is_bound = bool(binding.get("is_bound") or customer.get("mobile") or identity.get("mobile"))
        return {
            "ok": True,
            "is_bound": is_bound,
            "external_userid": resolved_external_userid,
            "owner_userid": owner_userid or customer.get("owner_userid") or "",
            "customer_name": customer.get("customer_name") or "",
            "remark": customer.get("remark") or "",
            "display_name": customer.get("customer_name") or customer.get("remark") or f"客户 {resolved_external_userid[-6:]}",
            "person_id": identity.get("person_id") or binding.get("person_id"),
            "mobile": binding.get("mobile") or identity.get("mobile") or customer.get("mobile"),
            "third_party_user_id": binding.get("third_party_user_id") or identity.get("third_party_user_id"),
            "detail_url": customer.get("sidebar_context", {}).get("customer_profile_url")
            or f"/admin/customers/{resolved_external_userid}",
            "source_status": "legacy_production_facade",
            "route_owner": "ai_crm_next",
        }
    result = ResolvePersonIdentityQuery()(
        ResolvePersonIdentityRequest(
            external_userid=resolved_external_userid,
        )
    )
    if result is None:
        return {
            "ok": True,
            "is_bound": False,
            "external_userid": resolved_external_userid,
            "owner_userid": owner_userid or "",
            "customer_name": "",
            "remark": "",
            "display_name": f"客户 {resolved_external_userid[-6:]}",
            "source_status": "identity_contact",
            "route_owner": "ai_crm_next",
        }
    return {
        "ok": True,
        "is_bound": bool(result.mobile),
        "external_userid": resolved_external_userid,
        "owner_userid": owner_userid or result.owner_userid or "",
        "customer_name": "",
        "remark": "",
        "display_name": f"客户 {resolved_external_userid[-6:]}",
        "person_id": result.person_id,
        "mobile": result.mobile,
        "detail_url": f"/admin/customers/{resolved_external_userid}",
        "source_status": "identity_contact",
        "route_owner": "ai_crm_next",
    }
