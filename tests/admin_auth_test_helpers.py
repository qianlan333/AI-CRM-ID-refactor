from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from aicrm_next.admin_auth.browser_sessions import (
    ADMIN_AUDIENCE,
    ADMIN_BFF_CLIENT_ID,
    ADMIN_BFF_PRINCIPAL_ID,
    ADMIN_BFF_SUBJECT,
)
from aicrm_next.admin_auth.capabilities import ALL_CAPABILITIES, capabilities_for_roles
from aicrm_next.admin_auth.service import CSRF_COOKIE, SESSION_COOKIE
from aicrm_next.platform_foundation.auth_platform.context import AuthContext, PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.models import AuthSessionRecord, OAuthSubject
from aicrm_next.platform_foundation.auth_platform.sessions import AuthSessionService, IssuedSession


TEST_PEPPER = "pytest-admin-session-pepper-material-32-bytes"


class InMemoryAuthSessionRepository:
    def __init__(self) -> None:
        self.principals: dict[str, dict[str, Any]] = {}
        self.clients: dict[str, dict[str, Any]] = {}
        self.sessions: dict[str, AuthSessionRecord] = {}

    def upsert_principal(
        self,
        *,
        principal_id: str,
        principal_type: PrincipalType,
        subject: str,
        tenant_id: str,
        display_name: str,
        session_version: int = 1,
    ) -> None:
        existing = self.principals.get(principal_id)
        immutable = (principal_type, subject, tenant_id)
        if existing and existing["immutable"] != immutable:
            return
        self.principals[principal_id] = {
            "immutable": immutable,
            "display_name": display_name,
            "session_version": session_version,
            "status": "active",
        }

    def bootstrap_principal_and_client(self, **values: Any) -> None:
        self.upsert_principal(
            principal_id=values["principal_id"],
            principal_type=values["principal_type"],
            subject=values["subject"],
            tenant_id=values["tenant_id"],
            display_name=values["display_name"],
        )
        self.clients[values["client_id"]] = dict(values)

    def insert_auth_session(self, session: AuthSessionRecord) -> None:
        self.sessions[session.session_secret_hash] = session

    def auth_session_by_hash(self, session_hash: str) -> AuthSessionRecord | None:
        session = self.sessions.get(session_hash)
        if session is None or session.client_id not in self.clients:
            return None
        principal = self.principals.get(session.principal_id)
        if principal is None or principal["status"] != "active" or principal["session_version"] != session.session_version:
            return None
        return session

    def revoke_auth_session(self, session_hash: str, *, revoked_at: datetime, reason: str) -> bool:
        session = self.sessions.get(session_hash)
        if session is None:
            return False
        self.sessions[session_hash] = replace(session, revoked_at=revoked_at, revoked_reason=reason)
        return True


def install_admin_auth_service(client: TestClient) -> tuple[AuthSessionService, InMemoryAuthSessionRepository]:
    configured = getattr(client.app.state, "auth_session_service", None)
    if isinstance(configured, AuthSessionService) and isinstance(configured.repository, InMemoryAuthSessionRepository):
        return configured, configured.repository
    repository = InMemoryAuthSessionRepository()
    service = AuthSessionService(repository, CredentialHasher(TEST_PEPPER))
    client.app.state.auth_session_service = service
    return service, repository


def install_admin_session(
    client: TestClient,
    *roles: str,
    subject: str = "admin:test",
    principal_id: str = "admin-user:test",
    session_version: int = 1,
    set_csrf_header: bool = True,
) -> IssuedSession:
    actual_roles = roles or ("super_admin",)
    capabilities = tuple(sorted(capabilities_for_roles(actual_roles)))
    scopes = ("admin.read", "admin.write") if set(capabilities) - {"admin_read", "read_customer"} else ("admin.read",)
    service, _repository = install_admin_auth_service(client)
    service.provision_browser_client(
        principal_id=ADMIN_BFF_PRINCIPAL_ID,
        subject=ADMIN_BFF_SUBJECT,
        tenant_id="tenant:default",
        display_name="AI-CRM Admin BFF",
        client_id=ADMIN_BFF_CLIENT_ID,
        audience=ADMIN_AUDIENCE,
        scopes=("admin.read", "admin.write"),
        capabilities=tuple(sorted(ALL_CAPABILITIES)),
    )
    service.provision_principal(
        principal_id=principal_id,
        principal_type=PrincipalType.USER,
        subject=subject,
        tenant_id="tenant:default",
        display_name="Pytest Admin",
        session_version=session_version,
    )
    now = datetime.now(timezone.utc)
    issued = service.issue(
        subject=OAuthSubject(
            principal_id=principal_id,
            principal_type=PrincipalType.USER,
            subject=subject,
            tenant_id="tenant:default",
            acr="pytest",
            auth_time=now,
        ),
        client_id=ADMIN_BFF_CLIENT_ID,
        session_version=session_version,
        audience=ADMIN_AUDIENCE,
        scopes=scopes,
        capabilities=capabilities,
        now=now,
    )
    client.cookies.set(SESSION_COOKIE, issued.session_cookie)
    client.cookies.set(CSRF_COOKIE, issued.csrf_token)
    if set_csrf_header:
        client.headers["X-CSRF-Token"] = issued.csrf_token
    return issued


def admin_session_cookies(client: TestClient, *roles: str) -> dict[str, str]:
    issued = install_admin_session(client, *(roles or ("super_admin",)))
    return {
        SESSION_COOKIE: issued.session_cookie,
        CSRF_COOKIE: issued.csrf_token,
    }


def auth_context(
    *roles: str,
    subject: str = "admin:test",
    token_id: str = "session-test",
    now: datetime | None = None,
) -> AuthContext:
    issued_at = now or datetime.now(timezone.utc)
    capabilities = tuple(sorted(capabilities_for_roles(roles or ("super_admin",))))
    return AuthContext(
        principal_type=PrincipalType.USER,
        sub=subject,
        client_id=ADMIN_BFF_CLIENT_ID,
        tenant_id="tenant:default",
        audience=ADMIN_AUDIENCE,
        scopes=("admin.read", "admin.write"),
        capabilities=capabilities,
        resource_constraints={},
        token_id=token_id,
        actor="",
        acr="pytest",
        auth_time=issued_at,
        expires_at=issued_at + timedelta(hours=8),
    )
