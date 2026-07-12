from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from .context import AuthContext, PrincipalType
from .credentials import CredentialHasher, IssuedCredential, TOKEN_PREFIX


READ_ACCESS_TTL = timedelta(minutes=10)
HIGH_RISK_WRITE_ACCESS_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class ClientGrant:
    client_id: str
    principal_id: str
    principal_type: PrincipalType
    subject: str
    tenant_id: str
    audiences: tuple[str, ...]
    scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    resource_constraints: dict[str, Any]
    sender_constraint_type: str
    status: str = "active"


@dataclass(frozen=True)
class AccessTokenRecord:
    token_id: str
    token_hash: str
    principal_id: str
    principal_type: PrincipalType
    subject: str
    client_id: str
    tenant_id: str
    audience: str
    scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    resource_constraints: dict[str, Any]
    actor: str
    acr: str
    sender_constraint: str
    auth_time: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    token_id: str


@dataclass(frozen=True)
class IntrospectionResponse:
    active: bool
    context: AuthContext | None = None
    error: str = ""


class AuthPlatformRepository(Protocol):
    def client_grant(self, client_id: str) -> ClientGrant | None: ...

    def insert_access_token(self, token: AccessTokenRecord) -> None: ...

    def access_token_by_hash(self, token_hash: str) -> AccessTokenRecord | None: ...

    def revoke_access_token(self, token_hash: str, *, revoked_at: datetime) -> bool: ...


class AuthPlatformService:
    def __init__(self, repository: AuthPlatformRepository, hasher: CredentialHasher) -> None:
        self._repository = repository
        self._hasher = hasher

    def issue_client_credentials_access_token(
        self,
        *,
        client_id: str,
        audience: str,
        requested_scopes: tuple[str, ...],
        sender_constraint: str,
        high_risk_write: bool = False,
        now: datetime | None = None,
    ) -> TokenResponse:
        issued_at = _utc(now or datetime.now(timezone.utc))
        grant = self._repository.client_grant(client_id)
        if grant is None or grant.status != "active":
            raise PermissionError("invalid_client")
        normalized_audience = str(audience or "").strip()
        if normalized_audience not in grant.audiences:
            raise PermissionError("invalid_target")
        scopes = tuple(sorted({str(scope or "").strip() for scope in requested_scopes if str(scope or "").strip()}))
        if not scopes or not set(scopes).issubset(grant.scopes):
            raise PermissionError("invalid_scope")
        required_constraint = str(grant.sender_constraint_type or "").strip()
        actual_constraint = str(sender_constraint or "").strip()
        if required_constraint and not actual_constraint.startswith(f"{required_constraint}:"):
            raise PermissionError("sender_constraint_required")
        ttl = HIGH_RISK_WRITE_ACCESS_TTL if high_risk_write else READ_ACCESS_TTL
        issued = self._hasher.issue(TOKEN_PREFIX)
        token_id = f"tok_{uuid4().hex}"
        record = AccessTokenRecord(
            token_id=token_id,
            token_hash=issued.digest,
            principal_id=grant.principal_id,
            principal_type=grant.principal_type,
            subject=grant.subject,
            client_id=grant.client_id,
            tenant_id=grant.tenant_id,
            audience=normalized_audience,
            scopes=scopes,
            capabilities=grant.capabilities,
            resource_constraints=dict(grant.resource_constraints),
            actor="",
            acr="client_credentials",
            sender_constraint=actual_constraint,
            auth_time=issued_at,
            expires_at=issued_at + ttl,
        )
        self._repository.insert_access_token(record)
        return _token_response(issued, record)

    def introspect_access_token(
        self,
        credential: str,
        *,
        audience: str,
        sender_constraint: str,
        now: datetime | None = None,
    ) -> IntrospectionResponse:
        try:
            token_hash = self._hasher.digest(credential)
        except ValueError:
            return IntrospectionResponse(active=False, error="invalid_token")
        record = self._repository.access_token_by_hash(token_hash)
        current = _utc(now or datetime.now(timezone.utc))
        if record is None or record.revoked_at is not None or current >= _utc(record.expires_at):
            return IntrospectionResponse(active=False, error="invalid_token")
        if record.audience != str(audience or "").strip():
            return IntrospectionResponse(active=False, error="invalid_audience")
        if record.sender_constraint and record.sender_constraint != str(sender_constraint or "").strip():
            return IntrospectionResponse(active=False, error="sender_constraint_mismatch")
        return IntrospectionResponse(
            active=True,
            context=AuthContext(
                principal_type=record.principal_type,
                sub=record.subject,
                client_id=record.client_id,
                tenant_id=record.tenant_id,
                audience=record.audience,
                scopes=record.scopes,
                capabilities=record.capabilities,
                resource_constraints=record.resource_constraints,
                token_id=record.token_id,
                actor=record.actor,
                acr=record.acr,
                sender_constraint=record.sender_constraint,
                expires_at=record.expires_at,
                auth_time=record.auth_time,
            ),
        )

    def revoke_access_token(self, credential: str, *, now: datetime | None = None) -> bool:
        try:
            token_hash = self._hasher.digest(credential)
        except ValueError:
            return False
        return self._repository.revoke_access_token(token_hash, revoked_at=_utc(now or datetime.now(timezone.utc)))


def _token_response(issued: IssuedCredential, record: AccessTokenRecord) -> TokenResponse:
    return TokenResponse(
        access_token=issued.value,
        token_type="Bearer",
        expires_in=int((record.expires_at - record.auth_time).total_seconds()),
        scope=" ".join(record.scopes),
        token_id=record.token_id,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("auth platform timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
