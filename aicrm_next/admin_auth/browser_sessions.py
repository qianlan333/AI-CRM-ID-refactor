from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from starlette.responses import Response

from aicrm_next.platform_foundation.auth_platform.api import auth_session_service
from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.models import OAuthSubject
from aicrm_next.platform_foundation.auth_platform.sessions import IssuedSession

from .capabilities import ALL_CAPABILITIES, capabilities_for_roles, normalize_roles
from .service import CSRF_COOKIE, SESSION_COOKIE, SESSION_MAX_AGE_SECONDS, admin_cookie_secure, normalize_text


ADMIN_BFF_CLIENT_ID = "aicrm-admin-bff"
ADMIN_BFF_PRINCIPAL_ID = "service:aicrm-admin-bff"
ADMIN_BFF_SUBJECT = "service:aicrm-admin-bff"
ADMIN_AUDIENCE = "aicrm-admin"
DEFAULT_TENANT_ID = "tenant:default"


@dataclass(frozen=True)
class BrowserSessionIdentity:
    principal_id: str
    subject: str
    display_name: str
    session_version: int
    roles: tuple[str, ...]
    acr: str
    actor: str = ""
    tenant_id: str = DEFAULT_TENANT_ID

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(capabilities_for_roles(self.roles)))

    @property
    def scopes(self) -> tuple[str, ...]:
        scopes = {"admin.read"}
        if set(self.capabilities) - {"admin_read", "read_customer"}:
            scopes.add("admin.write")
        return tuple(sorted(scopes))


def browser_session_identity(claims: dict[str, Any]) -> BrowserSessionIdentity:
    roles = normalize_roles(claims.get("roles") or ())
    if not roles:
        raise ValueError("admin identity has no roles")
    admin_user_id = normalize_text(claims.get("admin_user_id"))
    username = normalize_text(claims.get("username") or claims.get("wecom_userid"))
    login_type = normalize_text(claims.get("login_type") or claims.get("auth_source")) or "admin_login"
    if admin_user_id:
        principal_id = f"admin-user:{admin_user_id}"
        subject = f"admin:{admin_user_id}"
    elif login_type == "break_glass" and username:
        principal_id = "admin-break-glass"
        subject = "admin:break-glass"
    else:
        raise ValueError("admin identity is missing a stable subject")
    session_version = int(claims.get("session_version") or 1)
    if session_version <= 0:
        raise ValueError("admin identity session version must be positive")
    return BrowserSessionIdentity(
        principal_id=principal_id,
        subject=subject,
        display_name=normalize_text(claims.get("display_name")) or username or subject,
        session_version=session_version,
        roles=roles,
        acr=login_type,
        actor=normalize_text(claims.get("actor")),
    )


def issue_browser_session(request: Request, claims: dict[str, Any]) -> IssuedSession:
    identity = browser_session_identity(claims)
    service = auth_session_service(request)
    service.provision_browser_client(
        principal_id=ADMIN_BFF_PRINCIPAL_ID,
        subject=ADMIN_BFF_SUBJECT,
        tenant_id=identity.tenant_id,
        display_name="AI-CRM Admin BFF",
        client_id=ADMIN_BFF_CLIENT_ID,
        audience=ADMIN_AUDIENCE,
        scopes=("admin.read", "admin.write"),
        capabilities=tuple(sorted(ALL_CAPABILITIES)),
    )
    service.provision_principal(
        principal_id=identity.principal_id,
        principal_type=PrincipalType.USER,
        subject=identity.subject,
        tenant_id=identity.tenant_id,
        display_name=identity.display_name,
        session_version=identity.session_version,
    )
    now = datetime.now(timezone.utc)
    return service.issue(
        subject=OAuthSubject(
            principal_id=identity.principal_id,
            principal_type=PrincipalType.USER,
            subject=identity.subject,
            tenant_id=identity.tenant_id,
            actor=identity.actor,
            acr=identity.acr,
            auth_time=now,
        ),
        client_id=ADMIN_BFF_CLIENT_ID,
        session_version=identity.session_version,
        audience=ADMIN_AUDIENCE,
        scopes=identity.scopes,
        capabilities=identity.capabilities,
        now=now,
    )


def set_browser_session_cookies(response: Response, issued: IssuedSession) -> None:
    secure_cookie = admin_cookie_secure()
    response.set_cookie(
        SESSION_COOKIE,
        issued.session_cookie,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=False,
        samesite="lax",
        secure=secure_cookie,
        path="/",
    )


def revoke_browser_session(request: Request, *, reason: str = "logout") -> bool:
    session_cookie = normalize_text(request.cookies.get(SESSION_COOKIE))
    if not session_cookie:
        return False
    return auth_session_service(request).revoke(session_cookie, reason=reason)
