from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .application import ResolvePersonIdentityQuery
from .dto import ResolvePersonIdentityRequest

router = APIRouter()


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
