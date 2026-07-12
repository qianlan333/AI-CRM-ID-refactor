from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from .context import AuthContext, PrincipalType
from .credentials import CredentialHasher, IssuedCredential, REFRESH_PREFIX, TOKEN_PREFIX


READ_ACCESS_TTL = timedelta(minutes=10)
HIGH_RISK_WRITE_ACCESS_TTL = timedelta(minutes=5)
REFRESH_TOKEN_TTL = timedelta(days=30)


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
    family_id: str = ""


@dataclass(frozen=True)
class RefreshTokenRecord:
    token_id: str
    token_hash: str
    family_id: str
    parent_token_id: str
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
    consumed_at: datetime | None = None


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    token_type: str
    expires_in: int
    scope: str
    token_id: str


@dataclass(frozen=True)
class TokenPairResponse(TokenResponse):
    refresh_token: str
    refresh_token_id: str


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

    def insert_token_pair(
        self,
        *,
        family_id: str,
        access_token: AccessTokenRecord,
        refresh_token: RefreshTokenRecord,
    ) -> None: ...

    def refresh_token_by_hash(self, token_hash: str) -> RefreshTokenRecord | None: ...

    def rotate_refresh_token(
        self,
        *,
        presented_hash: str,
        access_token: AccessTokenRecord,
        refresh_token: RefreshTokenRecord,
        rotated_at: datetime,
    ) -> str: ...


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

    def issue_user_token_pair(
        self,
        *,
        client_id: str,
        audience: str,
        requested_scopes: tuple[str, ...],
        sender_constraint: str,
        actor: str = "",
        acr: str = "wecom_sso",
        high_risk_write: bool = False,
        now: datetime | None = None,
    ) -> TokenPairResponse:
        issued_at = _utc(now or datetime.now(timezone.utc))
        grant = self._validated_grant(
            client_id=client_id,
            audience=audience,
            requested_scopes=requested_scopes,
            sender_constraint=sender_constraint,
        )
        family_id = f"family_{uuid4().hex}"
        access_issued, access = self._new_access_record(
            grant=grant,
            audience=audience,
            scopes=requested_scopes,
            sender_constraint=sender_constraint,
            actor=actor,
            acr=acr,
            auth_time=issued_at,
            issued_at=issued_at,
            high_risk_write=high_risk_write,
            family_id=family_id,
        )
        refresh_issued = self._hasher.issue(REFRESH_PREFIX)
        refresh = RefreshTokenRecord(
            token_id=f"tok_{uuid4().hex}",
            token_hash=refresh_issued.digest,
            family_id=family_id,
            parent_token_id="",
            principal_id=grant.principal_id,
            principal_type=grant.principal_type,
            subject=grant.subject,
            client_id=grant.client_id,
            tenant_id=grant.tenant_id,
            audience=audience,
            scopes=tuple(sorted(set(requested_scopes))),
            capabilities=grant.capabilities,
            resource_constraints=dict(grant.resource_constraints),
            actor=actor,
            acr=acr,
            sender_constraint=sender_constraint,
            auth_time=issued_at,
            expires_at=issued_at + REFRESH_TOKEN_TTL,
        )
        self._repository.insert_token_pair(family_id=family_id, access_token=access, refresh_token=refresh)
        return _token_pair_response(access_issued, access, refresh_issued, refresh, issued_at=issued_at)

    def refresh_user_token_pair(
        self,
        refresh_credential: str,
        *,
        client_id: str,
        requested_scopes: tuple[str, ...],
        sender_constraint: str,
        high_risk_write: bool = False,
        now: datetime | None = None,
    ) -> TokenPairResponse:
        current = _utc(now or datetime.now(timezone.utc))
        try:
            presented_hash = self._hasher.digest(refresh_credential)
        except ValueError as exc:
            raise PermissionError("invalid_grant") from exc
        previous = self._repository.refresh_token_by_hash(presented_hash)
        if previous is None or previous.revoked_at is not None or current >= _utc(previous.expires_at):
            raise PermissionError("invalid_grant")
        if previous.client_id != str(client_id or "").strip():
            raise PermissionError("invalid_client")
        scopes = tuple(sorted({str(scope or "").strip() for scope in requested_scopes if str(scope or "").strip()}))
        if not scopes:
            scopes = previous.scopes
        if not set(scopes).issubset(previous.scopes):
            raise PermissionError("invalid_scope")
        if previous.sender_constraint and previous.sender_constraint != str(sender_constraint or "").strip():
            raise PermissionError("sender_constraint_mismatch")
        grant = ClientGrant(
            client_id=previous.client_id,
            principal_id=previous.principal_id,
            principal_type=previous.principal_type,
            subject=previous.subject,
            tenant_id=previous.tenant_id,
            audiences=(previous.audience,),
            scopes=previous.scopes,
            capabilities=previous.capabilities,
            resource_constraints=previous.resource_constraints,
            sender_constraint_type=previous.sender_constraint.split(":", 1)[0] if previous.sender_constraint else "",
        )
        access_issued, access = self._new_access_record(
            grant=grant,
            audience=previous.audience,
            scopes=scopes,
            sender_constraint=sender_constraint,
            actor=previous.actor,
            acr=previous.acr,
            auth_time=previous.auth_time,
            issued_at=current,
            high_risk_write=high_risk_write,
            family_id=previous.family_id,
        )
        refresh_issued = self._hasher.issue(REFRESH_PREFIX)
        replacement = RefreshTokenRecord(
            token_id=f"tok_{uuid4().hex}",
            token_hash=refresh_issued.digest,
            family_id=previous.family_id,
            parent_token_id=previous.token_id,
            principal_id=previous.principal_id,
            principal_type=previous.principal_type,
            subject=previous.subject,
            client_id=previous.client_id,
            tenant_id=previous.tenant_id,
            audience=previous.audience,
            scopes=scopes,
            capabilities=previous.capabilities,
            resource_constraints=previous.resource_constraints,
            actor=previous.actor,
            acr=previous.acr,
            sender_constraint=previous.sender_constraint,
            auth_time=previous.auth_time,
            expires_at=current + REFRESH_TOKEN_TTL,
        )
        outcome = self._repository.rotate_refresh_token(
            presented_hash=presented_hash,
            access_token=access,
            refresh_token=replacement,
            rotated_at=current,
        )
        if outcome == "reuse_detected":
            raise PermissionError("refresh_token_reuse_detected")
        if outcome != "rotated":
            raise PermissionError("invalid_grant")
        return _token_pair_response(access_issued, access, refresh_issued, replacement, issued_at=current)

    def revoke_access_token(self, credential: str, *, now: datetime | None = None) -> bool:
        try:
            token_hash = self._hasher.digest(credential)
        except ValueError:
            return False
        return self._repository.revoke_access_token(token_hash, revoked_at=_utc(now or datetime.now(timezone.utc)))

    def _validated_grant(
        self,
        *,
        client_id: str,
        audience: str,
        requested_scopes: tuple[str, ...],
        sender_constraint: str,
    ) -> ClientGrant:
        grant = self._repository.client_grant(client_id)
        if grant is None or grant.status != "active":
            raise PermissionError("invalid_client")
        if audience not in grant.audiences:
            raise PermissionError("invalid_target")
        scopes = {str(scope or "").strip() for scope in requested_scopes if str(scope or "").strip()}
        if not scopes or not scopes.issubset(grant.scopes):
            raise PermissionError("invalid_scope")
        required = str(grant.sender_constraint_type or "").strip()
        if required and not str(sender_constraint or "").strip().startswith(f"{required}:"):
            raise PermissionError("sender_constraint_required")
        return grant

    def _new_access_record(
        self,
        *,
        grant: ClientGrant,
        audience: str,
        scopes: tuple[str, ...],
        sender_constraint: str,
        actor: str,
        acr: str,
        auth_time: datetime,
        issued_at: datetime,
        high_risk_write: bool,
        family_id: str,
    ) -> tuple[IssuedCredential, AccessTokenRecord]:
        ttl = HIGH_RISK_WRITE_ACCESS_TTL if high_risk_write else READ_ACCESS_TTL
        issued = self._hasher.issue(TOKEN_PREFIX)
        return issued, AccessTokenRecord(
            token_id=f"tok_{uuid4().hex}",
            token_hash=issued.digest,
            principal_id=grant.principal_id,
            principal_type=grant.principal_type,
            subject=grant.subject,
            client_id=grant.client_id,
            tenant_id=grant.tenant_id,
            audience=audience,
            scopes=tuple(sorted(set(scopes))),
            capabilities=grant.capabilities,
            resource_constraints=dict(grant.resource_constraints),
            actor=actor,
            acr=acr,
            sender_constraint=sender_constraint,
            auth_time=auth_time,
            expires_at=issued_at + ttl,
            family_id=family_id,
        )


def _token_response(issued: IssuedCredential, record: AccessTokenRecord) -> TokenResponse:
    return TokenResponse(
        access_token=issued.value,
        token_type="Bearer",
        expires_in=int((record.expires_at - record.auth_time).total_seconds()),
        scope=" ".join(record.scopes),
        token_id=record.token_id,
    )


def _token_pair_response(
    access_issued: IssuedCredential,
    access: AccessTokenRecord,
    refresh_issued: IssuedCredential,
    refresh: RefreshTokenRecord,
    *,
    issued_at: datetime,
) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=access_issued.value,
        token_type="Bearer",
        expires_in=int((access.expires_at - issued_at).total_seconds()),
        scope=" ".join(access.scopes),
        token_id=access.token_id,
        refresh_token=refresh_issued.value,
        refresh_token_id=refresh.token_id,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("auth platform timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
