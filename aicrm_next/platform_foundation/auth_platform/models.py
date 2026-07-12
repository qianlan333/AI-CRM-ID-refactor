from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .context import PrincipalType


@dataclass(frozen=True)
class OAuthClientRecord:
    client_id: str
    principal_id: str
    principal_type: PrincipalType
    subject: str
    tenant_id: str
    client_type: str
    client_secret_hash: str
    token_endpoint_auth_method: str
    redirect_uris: tuple[str, ...]
    audiences: tuple[str, ...]
    scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    resource_constraints: dict[str, Any]
    sender_constraint_type: str
    status: str


@dataclass(frozen=True)
class OAuthSubject:
    principal_id: str
    principal_type: PrincipalType
    subject: str
    tenant_id: str
    actor: str = ""
    acr: str = ""
    auth_time: datetime | None = None


@dataclass(frozen=True)
class AuthorizationCodeRecord:
    code_hash: str
    principal_id: str
    principal_type: PrincipalType
    subject: str
    tenant_id: str
    client_id: str
    redirect_uri: str
    audience: str
    scopes: tuple[str, ...]
    code_challenge: str
    code_challenge_method: str
    nonce: str
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True)
class ClientKeyRecord:
    client_id: str
    key_id: str
    algorithm: str
    public_jwk: dict[str, Any]
    thumbprint: str
    status: str
    not_before: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True)
class AuthSessionRecord:
    session_id: str
    session_secret_hash: str
    csrf_token_hash: str
    principal_id: str
    principal_type: PrincipalType
    subject: str
    tenant_id: str
    client_id: str
    session_version: int
    audience: str
    scopes: tuple[str, ...]
    capabilities: tuple[str, ...]
    resource_constraints: dict[str, Any]
    actor: str
    acr: str
    auth_time: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_reason: str
