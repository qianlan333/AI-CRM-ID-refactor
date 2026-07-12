from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from aicrm_next.shared.db_session import get_session_factory

from .context import PrincipalType
from .service import AccessTokenRecord, ClientGrant, RefreshTokenRecord


def _json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return default
        return parsed
    return value


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class PostgresAuthPlatformRepository:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        database_url: str | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory(database_url)

    def client_grant(self, client_id: str) -> ClientGrant | None:
        with self._session_factory() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT c.client_id, c.status, c.audiences_json, c.scopes_json,
                               c.capabilities_json, c.resource_constraints_json,
                               c.sender_constraint_type, p.principal_id, p.principal_type,
                               p.subject, p.tenant_id
                        FROM auth_clients c
                        JOIN auth_principals p ON p.principal_id = c.principal_id
                        WHERE c.client_id = :client_id
                          AND p.status = 'active'
                        """
                    ),
                    {"client_id": str(client_id or "").strip()},
                )
                .mappings()
                .first()
            )
        return _client_grant(dict(row)) if row else None

    def insert_access_token(self, token: AccessTokenRecord) -> None:
        with self._session_factory.begin() as session:
            _insert_access_token(session, token)

    def access_token_by_hash(self, token_hash: str) -> AccessTokenRecord | None:
        with self._session_factory() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT t.token_id, t.token_hash, t.family_id, t.principal_id,
                               p.principal_type, p.subject, p.tenant_id,
                               t.client_id, t.audience, t.scopes_json,
                               t.capabilities_json, t.resource_constraints_json,
                               t.actor, t.acr, t.sender_constraint, t.auth_time,
                               t.expires_at, t.revoked_at
                        FROM auth_tokens t
                        JOIN auth_principals p ON p.principal_id = t.principal_id
                        JOIN auth_clients c ON c.client_id = t.client_id
                        WHERE t.token_hash = :token_hash
                          AND t.token_type = 'access'
                          AND p.status = 'active'
                          AND c.status = 'active'
                        """
                    ),
                    {"token_hash": str(token_hash or "").strip()},
                )
                .mappings()
                .first()
            )
        return _access_token(dict(row)) if row else None

    def revoke_access_token(self, token_hash: str, *, revoked_at: datetime) -> bool:
        with self._session_factory.begin() as session:
            result = session.execute(
                text(
                    """
                    UPDATE auth_tokens
                    SET revoked_at = COALESCE(revoked_at, :revoked_at)
                    WHERE token_hash = :token_hash AND token_type = 'access'
                    """
                ),
                {"token_hash": str(token_hash or "").strip(), "revoked_at": revoked_at},
            )
            return bool(result.rowcount)

    def insert_token_pair(
        self,
        *,
        family_id: str,
        access_token: AccessTokenRecord,
        refresh_token: RefreshTokenRecord,
    ) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                text(
                    """
                    INSERT INTO auth_token_families (
                        family_id, principal_id, client_id, status
                    ) VALUES (:family_id, :principal_id, :client_id, 'active')
                    """
                ),
                {
                    "family_id": family_id,
                    "principal_id": refresh_token.principal_id,
                    "client_id": refresh_token.client_id,
                },
            )
            _insert_access_token(session, access_token)
            _insert_refresh_token(session, refresh_token)

    def refresh_token_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        with self._session_factory() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT t.token_id, t.token_hash, t.family_id,
                               COALESCE(t.parent_token_id, '') AS parent_token_id,
                               t.principal_id, p.principal_type, p.subject,
                               p.tenant_id, t.client_id, t.audience, t.scopes_json,
                               t.capabilities_json, t.resource_constraints_json,
                               t.actor, t.acr, t.sender_constraint, t.auth_time,
                               t.expires_at, t.revoked_at, t.consumed_at
                        FROM auth_tokens t
                        JOIN auth_principals p ON p.principal_id = t.principal_id
                        JOIN auth_clients c ON c.client_id = t.client_id
                        JOIN auth_token_families f ON f.family_id = t.family_id
                        WHERE t.token_hash = :token_hash
                          AND t.token_type = 'refresh'
                          AND p.status = 'active'
                          AND c.status = 'active'
                          AND f.status = 'active'
                        """
                    ),
                    {"token_hash": str(token_hash or "").strip()},
                )
                .mappings()
                .first()
            )
        return _refresh_token(dict(row)) if row else None

    def rotate_refresh_token(
        self,
        *,
        presented_hash: str,
        access_token: AccessTokenRecord,
        refresh_token: RefreshTokenRecord,
        rotated_at: datetime,
    ) -> str:
        with self._session_factory.begin() as session:
            row = (
                session.execute(
                    text(
                        """
                        SELECT t.token_id, t.family_id, t.expires_at,
                               t.revoked_at, t.consumed_at, f.status AS family_status
                        FROM auth_tokens t
                        JOIN auth_token_families f ON f.family_id = t.family_id
                        WHERE t.token_hash = :token_hash
                          AND t.token_type = 'refresh'
                        FOR UPDATE OF t, f
                        """
                    ),
                    {"token_hash": presented_hash},
                )
                .mappings()
                .first()
            )
            if row is None or row["family_status"] != "active":
                return "invalid"
            if row["consumed_at"] is not None:
                session.execute(
                    text(
                        """
                        UPDATE auth_token_families
                        SET status = 'reuse_detected', revoked_at = :rotated_at,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE family_id = :family_id
                        """
                    ),
                    {"family_id": row["family_id"], "rotated_at": rotated_at},
                )
                session.execute(
                    text(
                        """
                        UPDATE auth_tokens
                        SET revoked_at = COALESCE(revoked_at, :rotated_at)
                        WHERE family_id = :family_id
                        """
                    ),
                    {"family_id": row["family_id"], "rotated_at": rotated_at},
                )
                return "reuse_detected"
            if row["revoked_at"] is not None or row["expires_at"] <= rotated_at:
                return "invalid"
            session.execute(
                text(
                    """
                    UPDATE auth_tokens
                    SET consumed_at = :rotated_at
                    WHERE token_hash = :token_hash AND consumed_at IS NULL
                    """
                ),
                {"token_hash": presented_hash, "rotated_at": rotated_at},
            )
            _insert_access_token(session, access_token)
            _insert_refresh_token(session, refresh_token)
            session.execute(
                text(
                    """
                    UPDATE auth_token_families
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE family_id = :family_id
                    """
                ),
                {"family_id": row["family_id"]},
            )
            return "rotated"

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
    ) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                text(
                    """
                    INSERT INTO auth_principals (
                        principal_id, principal_type, tenant_id, subject,
                        display_name, status
                    ) VALUES (
                        :principal_id, :principal_type, :tenant_id, :subject,
                        :display_name, 'active'
                    )
                    ON CONFLICT (principal_id) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE auth_principals.principal_type = EXCLUDED.principal_type
                      AND auth_principals.tenant_id = EXCLUDED.tenant_id
                      AND auth_principals.subject = EXCLUDED.subject
                    """
                ),
                {
                    "principal_id": principal_id,
                    "principal_type": principal_type.value,
                    "tenant_id": tenant_id,
                    "subject": subject,
                    "display_name": display_name,
                },
            )
            session.execute(
                text(
                    """
                    INSERT INTO auth_clients (
                        client_id, principal_id, client_type, client_secret_hash,
                        token_endpoint_auth_method, redirect_uris_json,
                        audiences_json, scopes_json, capabilities_json,
                        resource_constraints_json, sender_constraint_type, status
                    ) VALUES (
                        :client_id, :principal_id, :client_type,
                        :client_secret_hash, :token_endpoint_auth_method,
                        CAST(:redirect_uris_json AS JSONB),
                        CAST(:audiences_json AS JSONB), CAST(:scopes_json AS JSONB),
                        CAST(:capabilities_json AS JSONB),
                        CAST(:resource_constraints_json AS JSONB),
                        :sender_constraint_type, 'active'
                    )
                    ON CONFLICT (client_id) DO UPDATE SET
                        redirect_uris_json = EXCLUDED.redirect_uris_json,
                        audiences_json = EXCLUDED.audiences_json,
                        scopes_json = EXCLUDED.scopes_json,
                        capabilities_json = EXCLUDED.capabilities_json,
                        resource_constraints_json = EXCLUDED.resource_constraints_json,
                        sender_constraint_type = EXCLUDED.sender_constraint_type,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE auth_clients.principal_id = EXCLUDED.principal_id
                      AND auth_clients.client_type = EXCLUDED.client_type
                      AND auth_clients.token_endpoint_auth_method = EXCLUDED.token_endpoint_auth_method
                    """
                ),
                {
                    "client_id": client_id,
                    "principal_id": principal_id,
                    "client_type": client_type,
                    "client_secret_hash": client_secret_hash,
                    "token_endpoint_auth_method": token_endpoint_auth_method,
                    "redirect_uris_json": _json_text(list(redirect_uris)),
                    "audiences_json": _json_text(list(audiences)),
                    "scopes_json": _json_text(list(scopes)),
                    "capabilities_json": _json_text(list(capabilities)),
                    "resource_constraints_json": _json_text(resource_constraints or {}),
                    "sender_constraint_type": sender_constraint_type,
                },
            )


def _client_grant(row: dict[str, Any]) -> ClientGrant:
    return ClientGrant(
        client_id=str(row["client_id"]),
        principal_id=str(row["principal_id"]),
        principal_type=PrincipalType(str(row["principal_type"])),
        subject=str(row["subject"]),
        tenant_id=str(row["tenant_id"]),
        audiences=tuple(str(value) for value in _json(row.get("audiences_json"), [])),
        scopes=tuple(str(value) for value in _json(row.get("scopes_json"), [])),
        capabilities=tuple(str(value) for value in _json(row.get("capabilities_json"), [])),
        resource_constraints=dict(_json(row.get("resource_constraints_json"), {})),
        sender_constraint_type=str(row.get("sender_constraint_type") or ""),
        status=str(row.get("status") or ""),
    )


def _access_token(row: dict[str, Any]) -> AccessTokenRecord:
    return AccessTokenRecord(
        token_id=str(row["token_id"]),
        token_hash=str(row["token_hash"]),
        principal_id=str(row["principal_id"]),
        principal_type=PrincipalType(str(row["principal_type"])),
        subject=str(row["subject"]),
        client_id=str(row["client_id"]),
        tenant_id=str(row["tenant_id"]),
        audience=str(row["audience"]),
        scopes=tuple(str(value) for value in _json(row.get("scopes_json"), [])),
        capabilities=tuple(str(value) for value in _json(row.get("capabilities_json"), [])),
        resource_constraints=dict(_json(row.get("resource_constraints_json"), {})),
        actor=str(row.get("actor") or ""),
        acr=str(row.get("acr") or ""),
        sender_constraint=str(row.get("sender_constraint") or ""),
        auth_time=row["auth_time"],
        expires_at=row["expires_at"],
        revoked_at=row.get("revoked_at"),
        family_id=str(row.get("family_id") or ""),
    )


def _refresh_token(row: dict[str, Any]) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        token_id=str(row["token_id"]),
        token_hash=str(row["token_hash"]),
        family_id=str(row["family_id"]),
        parent_token_id=str(row.get("parent_token_id") or ""),
        principal_id=str(row["principal_id"]),
        principal_type=PrincipalType(str(row["principal_type"])),
        subject=str(row["subject"]),
        client_id=str(row["client_id"]),
        tenant_id=str(row["tenant_id"]),
        audience=str(row["audience"]),
        scopes=tuple(str(value) for value in _json(row.get("scopes_json"), [])),
        capabilities=tuple(str(value) for value in _json(row.get("capabilities_json"), [])),
        resource_constraints=dict(_json(row.get("resource_constraints_json"), {})),
        actor=str(row.get("actor") or ""),
        acr=str(row.get("acr") or ""),
        sender_constraint=str(row.get("sender_constraint") or ""),
        auth_time=row["auth_time"],
        expires_at=row["expires_at"],
        revoked_at=row.get("revoked_at"),
        consumed_at=row.get("consumed_at"),
    )


def _insert_access_token(session: Session, token: AccessTokenRecord) -> None:
    session.execute(
        text(
            """
            INSERT INTO auth_tokens (
                token_id, token_hash, token_type, family_id, principal_id,
                client_id, audience, scopes_json, capabilities_json,
                resource_constraints_json, actor, acr, sender_constraint,
                auth_time, expires_at
            ) VALUES (
                :token_id, :token_hash, 'access', NULLIF(:family_id, ''),
                :principal_id, :client_id, :audience,
                CAST(:scopes_json AS JSONB), CAST(:capabilities_json AS JSONB),
                CAST(:resource_constraints_json AS JSONB), :actor, :acr,
                :sender_constraint, :auth_time, :expires_at
            )
            """
        ),
        _token_parameters(token),
    )


def _insert_refresh_token(session: Session, token: RefreshTokenRecord) -> None:
    parameters = _token_parameters(token)
    parameters["parent_token_id"] = token.parent_token_id
    session.execute(
        text(
            """
            INSERT INTO auth_tokens (
                token_id, token_hash, token_type, family_id, parent_token_id,
                principal_id, client_id, audience, scopes_json,
                capabilities_json, resource_constraints_json, actor, acr,
                sender_constraint, auth_time, expires_at
            ) VALUES (
                :token_id, :token_hash, 'refresh', :family_id,
                NULLIF(:parent_token_id, ''), :principal_id, :client_id,
                :audience, CAST(:scopes_json AS JSONB),
                CAST(:capabilities_json AS JSONB),
                CAST(:resource_constraints_json AS JSONB), :actor, :acr,
                :sender_constraint, :auth_time, :expires_at
            )
            """
        ),
        parameters,
    )


def _token_parameters(token: AccessTokenRecord | RefreshTokenRecord) -> dict[str, Any]:
    return {
        "token_id": token.token_id,
        "token_hash": token.token_hash,
        "family_id": token.family_id,
        "principal_id": token.principal_id,
        "client_id": token.client_id,
        "audience": token.audience,
        "scopes_json": _json_text(list(token.scopes)),
        "capabilities_json": _json_text(list(token.capabilities)),
        "resource_constraints_json": _json_text(token.resource_constraints),
        "actor": token.actor,
        "acr": token.acr,
        "sender_constraint": token.sender_constraint,
        "auth_time": token.auth_time,
        "expires_at": token.expires_at,
    }
