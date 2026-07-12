from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from .context import AuthContext, PrincipalType
from .credentials import CSRF_PREFIX, SESSION_PREFIX, CredentialHasher
from .models import AuthSessionRecord, OAuthSubject


SESSION_TTL = timedelta(hours=8)


class SessionRepository(Protocol):
    def upsert_principal(
        self,
        *,
        principal_id: str,
        principal_type: PrincipalType,
        subject: str,
        tenant_id: str,
        display_name: str,
        session_version: int = 1,
    ) -> None: ...

    def bootstrap_principal_and_client(
        self,
        *,
        principal_id: str,
        principal_type: PrincipalType,
        subject: str,
        tenant_id: str,
        display_name: str,
        client_id: str,
        client_type: str,
        token_endpoint_auth_method: str,
        client_secret_hash: str,
        redirect_uris: tuple[str, ...] = (),
        audiences: tuple[str, ...],
        scopes: tuple[str, ...],
        capabilities: tuple[str, ...],
        resource_constraints: dict[str, Any] | None = None,
        sender_constraint_type: str = "",
    ) -> None: ...

    def insert_auth_session(self, session: AuthSessionRecord) -> None: ...

    def auth_session_by_hash(self, session_hash: str) -> AuthSessionRecord | None: ...

    def revoke_auth_session(self, session_hash: str, *, revoked_at: datetime, reason: str) -> bool: ...


@dataclass(frozen=True)
class IssuedSession:
    session_cookie: str
    csrf_token: str
    session_id: str
    expires_at: datetime


@dataclass(frozen=True)
class SessionIntrospection:
    active: bool
    context: AuthContext | None = None
    record: AuthSessionRecord | None = None
    error: str = ""


class AuthSessionService:
    def __init__(self, repository: SessionRepository, hasher: CredentialHasher) -> None:
        self._repository = repository
        self._hasher = hasher

    @property
    def repository(self) -> SessionRepository:
        return self._repository

    def provision_principal(
        self,
        *,
        principal_id: str,
        principal_type: PrincipalType,
        subject: str,
        tenant_id: str,
        display_name: str,
        session_version: int,
    ) -> None:
        self._repository.upsert_principal(
            principal_id=principal_id,
            principal_type=principal_type,
            subject=subject,
            tenant_id=tenant_id,
            display_name=display_name,
            session_version=session_version,
        )

    def provision_browser_client(
        self,
        *,
        principal_id: str,
        subject: str,
        tenant_id: str,
        display_name: str,
        client_id: str,
        audience: str,
        scopes: tuple[str, ...],
        capabilities: tuple[str, ...],
    ) -> None:
        self._repository.bootstrap_principal_and_client(
            principal_id=principal_id,
            principal_type=PrincipalType.SERVICE,
            subject=subject,
            tenant_id=tenant_id,
            display_name=display_name,
            client_id=client_id,
            client_type="public",
            token_endpoint_auth_method="none",
            client_secret_hash="",
            audiences=(audience,),
            scopes=scopes,
            capabilities=capabilities,
        )

    def issue(
        self,
        *,
        subject: OAuthSubject,
        client_id: str,
        session_version: int,
        audience: str,
        scopes: tuple[str, ...],
        capabilities: tuple[str, ...],
        resource_constraints: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> IssuedSession:
        issued_at = _utc(now or datetime.now(timezone.utc))
        if session_version <= 0:
            raise ValueError("session version must be positive")
        session_credential = self._hasher.issue(SESSION_PREFIX)
        csrf_credential = self._hasher.issue(CSRF_PREFIX)
        session_id = f"session_{uuid4().hex}"
        expires_at = issued_at + SESSION_TTL
        self._repository.insert_auth_session(
            AuthSessionRecord(
                session_id=session_id,
                session_secret_hash=session_credential.digest,
                csrf_token_hash=csrf_credential.digest,
                principal_id=subject.principal_id,
                principal_type=subject.principal_type,
                subject=subject.subject,
                tenant_id=subject.tenant_id,
                client_id=client_id,
                session_version=session_version,
                audience=audience,
                scopes=tuple(sorted(set(scopes))),
                capabilities=tuple(sorted(set(capabilities))),
                resource_constraints=dict(resource_constraints or {}),
                actor=subject.actor,
                acr=subject.acr,
                auth_time=subject.auth_time or issued_at,
                expires_at=expires_at,
                revoked_at=None,
                revoked_reason="",
            )
        )
        return IssuedSession(
            session_cookie=session_credential.value,
            csrf_token=csrf_credential.value,
            session_id=session_id,
            expires_at=expires_at,
        )

    def introspect(self, session_cookie: str, *, now: datetime | None = None) -> SessionIntrospection:
        try:
            digest = self._hasher.digest(session_cookie)
        except ValueError:
            return SessionIntrospection(active=False, error="session_required")
        record = self._repository.auth_session_by_hash(digest)
        current = _utc(now or datetime.now(timezone.utc))
        if record is None or record.revoked_at is not None or current >= _utc(record.expires_at):
            return SessionIntrospection(active=False, error="session_expired_or_revoked")
        return SessionIntrospection(
            active=True,
            record=record,
            context=AuthContext(
                principal_type=record.principal_type,
                sub=record.subject,
                client_id=record.client_id,
                tenant_id=record.tenant_id,
                audience=record.audience,
                scopes=record.scopes,
                capabilities=record.capabilities,
                resource_constraints=record.resource_constraints,
                token_id=record.session_id,
                actor=record.actor,
                acr=record.acr,
                auth_time=record.auth_time,
                expires_at=record.expires_at,
            ),
        )

    def verify_csrf(self, introspection: SessionIntrospection, cookie_token: str, request_token: str) -> bool:
        record = introspection.record
        if not introspection.active or record is None or not cookie_token or not request_token:
            return False
        return self._hasher.verify(cookie_token, record.csrf_token_hash) and self._hasher.verify(request_token, record.csrf_token_hash)

    def revoke(self, session_cookie: str, *, reason: str, now: datetime | None = None) -> bool:
        try:
            digest = self._hasher.digest(session_cookie)
        except ValueError:
            return False
        return self._repository.revoke_auth_session(
            digest,
            revoked_at=_utc(now or datetime.now(timezone.utc)),
            reason=str(reason or "logout")[:128],
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("session timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)
