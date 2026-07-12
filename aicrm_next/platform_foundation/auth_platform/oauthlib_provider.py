from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
from typing import Any, Protocol
from urllib.parse import unquote
from uuid import uuid4

from oauthlib.common import Request
from oauthlib.openid import RequestValidator, Server

from .context import PrincipalType
from .credentials import CODE_PREFIX, CredentialHasher, REFRESH_PREFIX, TOKEN_PREFIX, verify_client_secret
from .models import AuthorizationCodeRecord, ClientKeyRecord, OAuthClientRecord, OAuthSubject
from .oidc_signing import OIDCSigner
from .service import AccessTokenRecord, RefreshTokenRecord


AUTHORIZATION_CODE_TTL = timedelta(minutes=2)


class OAuthProviderRepository(Protocol):
    def oauth_client(self, client_id: str) -> OAuthClientRecord | None: ...

    def client_key(self, client_id: str, key_id: str) -> ClientKeyRecord | None: ...

    def consume_replay_nonce(
        self,
        *,
        client_id: str,
        nonce_hash: str,
        purpose: str,
        expires_at: datetime,
    ) -> bool: ...

    def insert_authorization_code(self, code: AuthorizationCodeRecord) -> None: ...

    def authorization_code_by_hash(self, code_hash: str) -> AuthorizationCodeRecord | None: ...

    def consume_authorization_code(self, code_hash: str, *, consumed_at: datetime) -> bool: ...

    def insert_access_token(self, token: AccessTokenRecord) -> None: ...

    def insert_token_pair(
        self,
        *,
        family_id: str,
        access_token: AccessTokenRecord,
        refresh_token: RefreshTokenRecord,
    ) -> None: ...

    def access_token_by_hash(self, token_hash: str) -> AccessTokenRecord | None: ...

    def refresh_token_by_hash(self, token_hash: str) -> RefreshTokenRecord | None: ...

    def rotate_refresh_token(
        self,
        *,
        presented_hash: str,
        access_token: AccessTokenRecord,
        refresh_token: RefreshTokenRecord,
        rotated_at: datetime,
    ) -> str: ...

    def revoke_access_token(self, token_hash: str, *, revoked_at: datetime) -> bool: ...

    def revoke_refresh_family_by_hash(self, token_hash: str, *, revoked_at: datetime) -> bool: ...


class OAuthLibRequestValidator(RequestValidator):
    def __init__(
        self,
        repository: OAuthProviderRepository,
        hasher: CredentialHasher,
        signer: OIDCSigner,
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        self.signer = signer

    def authenticate_client(self, request: Request, *args, **kwargs) -> bool:
        basic_client_id, basic_secret = _basic_credentials(request)
        client_id = _authenticated_client_id(request) or basic_client_id or str(request.client_id or "").strip()
        client = self.repository.oauth_client(client_id)
        if client is None or client.status != "active" or client.client_type != "confidential":
            return False
        preauthenticated = _authenticated_client_id(request)
        if preauthenticated:
            valid = preauthenticated == client.client_id
        elif client.token_endpoint_auth_method in {"client_secret_basic", "client_secret_post"}:
            provided_secret = basic_secret or str(request.client_secret or "")
            valid = verify_client_secret(provided_secret, client.client_secret_hash)
        else:
            valid = False
        if valid:
            request.client = client
            request.client_id = client.client_id
        return valid

    def authenticate_client_id(self, client_id: str, request: Request, *args, **kwargs) -> bool:
        client = self.repository.oauth_client(client_id)
        if client is None or client.status != "active" or client.client_type != "public":
            return False
        request.client = client
        request.client_id = client.client_id
        return True

    def client_authentication_required(self, request: Request, *args, **kwargs) -> bool:
        client = self.repository.oauth_client(str(request.client_id or "").strip())
        return client is None or client.client_type != "public"

    def validate_client_id(self, client_id: str, request: Request, *args, **kwargs) -> bool:
        client = self.repository.oauth_client(client_id)
        if client is None or client.status != "active":
            return False
        request.client = client
        return True

    def validate_redirect_uri(self, client_id: str, redirect_uri: str, request: Request, *args, **kwargs) -> bool:
        client = self.repository.oauth_client(client_id)
        return bool(client and redirect_uri in client.redirect_uris)

    def get_default_redirect_uri(self, client_id: str, request: Request, *args, **kwargs) -> str:
        client = self.repository.oauth_client(client_id)
        return client.redirect_uris[0] if client and len(client.redirect_uris) == 1 else ""

    def validate_response_type(self, client_id: str, response_type: str, client, request, *args, **kwargs) -> bool:
        return response_type == "code"

    def validate_grant_type(self, client_id: str, grant_type: str, client, request, *args, **kwargs) -> bool:
        if not isinstance(client, OAuthClientRecord):
            client = self.repository.oauth_client(client_id)
        if client is None or client.status != "active":
            return False
        if grant_type == "client_credentials":
            return client.client_type == "confidential" and client.principal_type in {
                PrincipalType.SERVICE,
                PrincipalType.AGENT,
                PrincipalType.PARTNER,
            }
        return grant_type in {"authorization_code", "refresh_token"}

    def validate_scopes(self, client_id: str, scopes: list[str], client, request, *args, **kwargs) -> bool:
        record = client if isinstance(client, OAuthClientRecord) else self.repository.oauth_client(client_id)
        return bool(record and scopes and set(scopes).issubset(record.scopes))

    def get_default_scopes(self, client_id: str, request: Request, *args, **kwargs) -> list[str]:
        client = self.repository.oauth_client(client_id)
        return list(client.scopes) if client else []

    def is_pkce_required(self, client_id: str, request: Request) -> bool:
        return True

    def save_authorization_code(self, client_id: str, code: dict[str, Any], request: Request, *args, **kwargs) -> None:
        subject = request.user
        if not isinstance(subject, OAuthSubject):
            raise ValueError("OAuth authorization requires an Auth Platform subject")
        now = datetime.now(timezone.utc)
        raw_code = str(code["code"])
        credentials = dict(getattr(request, "extra_credentials", None) or {})
        self.repository.insert_authorization_code(
            AuthorizationCodeRecord(
                code_hash=self.hasher.digest(CODE_PREFIX + raw_code if not raw_code.startswith(CODE_PREFIX) else raw_code),
                principal_id=subject.principal_id,
                principal_type=subject.principal_type,
                subject=subject.subject,
                tenant_id=subject.tenant_id,
                client_id=client_id,
                redirect_uri=str(request.redirect_uri or ""),
                audience=str(credentials.get("audience") or getattr(request, "audience", "") or "aicrm-admin"),
                scopes=tuple(request.scopes or ()),
                code_challenge=str(request.code_challenge or ""),
                code_challenge_method=str(request.code_challenge_method or ""),
                nonce=str(code.get("nonce") or request.nonce or ""),
                expires_at=now + AUTHORIZATION_CODE_TTL,
                consumed_at=None,
            )
        )

    def validate_code(self, client_id: str, code: str, client, request: Request, *args, **kwargs) -> bool:
        record = self._authorization_code(code)
        now = datetime.now(timezone.utc)
        if (
            record is None
            or record.client_id != client_id
            or record.consumed_at is not None
            or record.expires_at <= now
            or not self.repository.consume_authorization_code(record.code_hash, consumed_at=now)
        ):
            return False
        request.user = _subject_from_code(record)
        request.scopes = list(record.scopes)
        request.redirect_uri = record.redirect_uri
        request.code_challenge = record.code_challenge
        request.code_challenge_method = record.code_challenge_method
        request.rauth_authorization_code = record
        return True

    def confirm_redirect_uri(self, client_id: str, code: str, redirect_uri: str, client, request: Request, *args, **kwargs) -> bool:
        record = getattr(request, "rauth_authorization_code", None) or self._authorization_code(code)
        return bool(record and record.client_id == client_id and record.redirect_uri == redirect_uri)

    def invalidate_authorization_code(self, client_id: str, code: str, request: Request, *args, **kwargs) -> None:
        # The code is consumed with a row-level conditional update in validate_code
        # before token material is generated, closing concurrent replay.
        return None

    def get_code_challenge(self, code: str, request: Request) -> str:
        record = getattr(request, "rauth_authorization_code", None) or self._authorization_code(code)
        return record.code_challenge if record else ""

    def get_code_challenge_method(self, code: str, request: Request) -> str:
        record = getattr(request, "rauth_authorization_code", None) or self._authorization_code(code)
        return record.code_challenge_method if record else "S256"

    def get_authorization_code_scopes(self, client_id: str, code: str, redirect_uri: str, request: Request) -> list[str]:
        record = self._authorization_code(code)
        return list(record.scopes) if record and record.client_id == client_id else []

    def get_authorization_code_nonce(self, client_id: str, code: str, redirect_uri: str, request: Request) -> str:
        record = self._authorization_code(code)
        return record.nonce if record and record.client_id == client_id else ""

    def save_bearer_token(self, token: dict[str, Any], request: Request, *args, **kwargs) -> None:
        client = request.client
        if not isinstance(client, OAuthClientRecord):
            raise ValueError("OAuth client context is missing")
        now = datetime.now(timezone.utc)
        credentials = dict(getattr(request, "extra_credentials", None) or {})
        audience = str(credentials.get("audience") or _request_audience(request) or "").strip()
        if audience not in client.audiences:
            raise ValueError("OAuth token audience is not granted to this client")
        sender_constraint = str(credentials.get("sender_constraint") or "").strip()
        if client.sender_constraint_type and not sender_constraint.startswith(f"{client.sender_constraint_type}:"):
            raise ValueError("OAuth token sender constraint is missing")
        subject = request.user if isinstance(request.user, OAuthSubject) else _subject_from_client(client, now)
        scopes = tuple(str(token.get("scope") or "").split()) or tuple(request.scopes or ())
        expires_in = int(token.get("expires_in") or _token_expires_in(request))
        previous = None
        family_id = ""
        if request.grant_type == "refresh_token":
            previous = self.repository.refresh_token_by_hash(self.hasher.digest(str(request.refresh_token or "")))
            if previous is None:
                raise ValueError("refresh token context is missing")
            family_id = previous.family_id
        elif token.get("refresh_token"):
            family_id = f"family_{uuid4().hex}"
        access = _access_record(
            raw_token=str(token["access_token"]),
            hasher=self.hasher,
            client=client,
            subject=subject,
            audience=audience,
            scopes=scopes,
            sender_constraint=sender_constraint,
            expires_at=now + timedelta(seconds=expires_in),
            family_id=family_id,
        )
        if not token.get("refresh_token"):
            self.repository.insert_access_token(access)
            return
        refresh = _refresh_record(
            raw_token=str(token["refresh_token"]),
            hasher=self.hasher,
            client=client,
            subject=subject,
            audience=audience,
            scopes=scopes,
            sender_constraint=sender_constraint,
            family_id=family_id,
            parent_token_id=previous.token_id if previous else "",
            now=now,
        )
        if previous is None:
            self.repository.insert_token_pair(family_id=family_id, access_token=access, refresh_token=refresh)
            return
        outcome = self.repository.rotate_refresh_token(
            presented_hash=previous.token_hash,
            access_token=access,
            refresh_token=refresh,
            rotated_at=now,
        )
        if outcome != "rotated":
            raise ValueError(f"refresh rotation failed: {outcome}")

    def validate_refresh_token(self, refresh_token: str, client, request: Request, *args, **kwargs) -> bool:
        digest = self.hasher.digest(refresh_token)
        record = self.repository.refresh_token_by_hash(digest)
        if record is None or record.revoked_at is not None:
            return False
        if record.consumed_at is not None:
            self.repository.revoke_refresh_family_by_hash(digest, revoked_at=datetime.now(timezone.utc))
            return False
        if record.expires_at <= datetime.now(timezone.utc) or record.client_id != request.client_id:
            return False
        request.user = _subject_from_refresh(record)
        request.scopes = list(record.scopes)
        request.rauth_refresh_token = record
        return True

    def get_original_scopes(self, refresh_token: str, request: Request, *args, **kwargs) -> list[str]:
        record = getattr(request, "rauth_refresh_token", None)
        if record is None:
            record = self.repository.refresh_token_by_hash(self.hasher.digest(refresh_token))
        return list(record.scopes) if record else []

    def rotate_refresh_token(self, request: Request) -> bool:
        return True

    def introspect_token(self, token: str, token_type_hint: str, request: Request, *args, **kwargs):
        record = self.repository.access_token_by_hash(self.hasher.digest(token))
        now = datetime.now(timezone.utc)
        if record is None or record.revoked_at is not None or record.expires_at <= now:
            return None
        return {
            "client_id": record.client_id,
            "sub": record.subject,
            "username": record.subject,
            "scope": " ".join(record.scopes),
            "token_type": "Bearer",
            "aud": record.audience,
            "iss": self.signer.issuer,
            "iat": int(record.auth_time.timestamp()),
            "exp": int(record.expires_at.timestamp()),
        }

    def revoke_token(self, token: str, token_type_hint: str, request: Request, *args, **kwargs) -> None:
        digest = self.hasher.digest(token)
        now = datetime.now(timezone.utc)
        if token_type_hint == "refresh_token" and self.repository.revoke_refresh_family_by_hash(digest, revoked_at=now):
            return
        if self.repository.revoke_access_token(digest, revoked_at=now):
            return
        self.repository.revoke_refresh_family_by_hash(digest, revoked_at=now)

    def validate_bearer_token(self, token: str, scopes: list[str], request: Request) -> bool:
        record = self.repository.access_token_by_hash(self.hasher.digest(token))
        if record is None or record.revoked_at is not None or record.expires_at <= datetime.now(timezone.utc):
            return False
        if scopes and not set(scopes).issubset(record.scopes):
            return False
        request.user = OAuthSubject(
            principal_id=record.principal_id,
            principal_type=record.principal_type,
            subject=record.subject,
            tenant_id=record.tenant_id,
            actor=record.actor,
            acr=record.acr,
            auth_time=record.auth_time,
        )
        request.client = self.repository.oauth_client(record.client_id)
        request.scopes = list(record.scopes)
        return True

    def validate_user(self, username: str, password: str, client, request: Request, *args, **kwargs) -> bool:
        return False

    def finalize_id_token(self, id_token, token, token_handler, request: Request) -> str:
        subject = request.user
        if not isinstance(subject, OAuthSubject):
            raise ValueError("OIDC subject context is missing")
        claims = dict(id_token)
        claims.update(
            {
                "sub": subject.subject,
                "auth_time": int((subject.auth_time or datetime.now(timezone.utc)).timestamp()),
                "acr": subject.acr,
            }
        )
        if subject.actor:
            claims["act"] = {"sub": subject.actor}
        return self.signer.sign(claims)

    def validate_silent_authorization(self, request: Request) -> bool:
        return False

    def validate_silent_login(self, request: Request) -> bool:
        return False

    def validate_user_match(self, id_token_hint, scopes, claims, request: Request) -> bool:
        if not id_token_hint:
            return isinstance(request.user, OAuthSubject)
        return bool(isinstance(request.user, OAuthSubject) and request.user.subject == id_token_hint)

    def get_jwt_bearer_token(self, token, token_handler, request: Request):
        return self.finalize_id_token(token, token, token_handler, request)

    def validate_jwt_bearer_token(self, token: str, scopes: list[str], request: Request) -> bool:
        return False

    def validate_id_token(self, token: str, scopes: list[str], request: Request) -> bool:
        try:
            self.signer.verify(token, audience=str(request.client_id or ""))
        except Exception:
            return False
        return True

    def get_userinfo_claims(self, request: Request) -> dict[str, Any]:
        subject = request.user
        if not isinstance(subject, OAuthSubject):
            return {}
        claims: dict[str, Any] = {"sub": subject.subject}
        if subject.actor:
            claims["act"] = {"sub": subject.actor}
        return claims

    def _authorization_code(self, code: str) -> AuthorizationCodeRecord | None:
        raw = str(code or "")
        return self.repository.authorization_code_by_hash(self.hasher.digest(CODE_PREFIX + raw if not raw.startswith(CODE_PREFIX) else raw))


class OAuthLibProvider:
    def __init__(self, validator: OAuthLibRequestValidator) -> None:
        self.validator = validator
        self.server = Server(
            validator,
            token_expires_in=_token_expires_in,
            token_generator=lambda request: validator.hasher.issue(TOKEN_PREFIX).value,
            refresh_token_generator=lambda request: validator.hasher.issue(REFRESH_PREFIX).value,
        )


def _token_expires_in(request: Request) -> int:
    scopes = set(request.scopes or ())
    return 300 if any(scope.endswith(".write") or scope.endswith(":write") for scope in scopes) else 600


def _basic_credentials(request: Request) -> tuple[str, str]:
    authorization = str((request.headers or {}).get("Authorization") or (request.headers or {}).get("authorization") or "")
    if not authorization.startswith("Basic "):
        return "", ""
    try:
        decoded = base64.b64decode(authorization[6:].strip(), validate=True).decode("utf-8")
        client_id, secret = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return "", ""
    return unquote(client_id), unquote(secret)


def _authenticated_client_id(request: Request) -> str:
    return str(dict(getattr(request, "extra_credentials", None) or {}).get("authenticated_client_id") or "").strip()


def _request_audience(request: Request) -> str:
    code = getattr(request, "rauth_authorization_code", None)
    refresh = getattr(request, "rauth_refresh_token", None)
    return str(
        getattr(request, "audience", "") or getattr(request, "resource", "") or getattr(code, "audience", "") or getattr(refresh, "audience", "") or ""
    ).strip()


def _subject_from_client(client: OAuthClientRecord, now: datetime) -> OAuthSubject:
    return OAuthSubject(
        principal_id=client.principal_id,
        principal_type=client.principal_type,
        subject=client.subject,
        tenant_id=client.tenant_id,
        acr="client_credentials",
        auth_time=now,
    )


def _subject_from_code(code: AuthorizationCodeRecord) -> OAuthSubject:
    return OAuthSubject(
        principal_id=code.principal_id,
        principal_type=code.principal_type,
        subject=code.subject,
        tenant_id=code.tenant_id,
        acr="wecom_sso",
        auth_time=datetime.now(timezone.utc),
    )


def _subject_from_refresh(token: RefreshTokenRecord) -> OAuthSubject:
    return OAuthSubject(
        principal_id=token.principal_id,
        principal_type=token.principal_type,
        subject=token.subject,
        tenant_id=token.tenant_id,
        actor=token.actor,
        acr=token.acr,
        auth_time=token.auth_time,
    )


def _access_record(
    *,
    raw_token: str,
    hasher: CredentialHasher,
    client: OAuthClientRecord,
    subject: OAuthSubject,
    audience: str,
    scopes: tuple[str, ...],
    sender_constraint: str,
    expires_at: datetime,
    family_id: str,
) -> AccessTokenRecord:
    return AccessTokenRecord(
        token_id=f"tok_{uuid4().hex}",
        token_hash=hasher.digest(raw_token),
        principal_id=subject.principal_id,
        principal_type=subject.principal_type,
        subject=subject.subject,
        client_id=client.client_id,
        tenant_id=subject.tenant_id,
        audience=audience,
        scopes=scopes,
        capabilities=client.capabilities,
        resource_constraints=dict(client.resource_constraints),
        actor=subject.actor,
        acr=subject.acr,
        sender_constraint=sender_constraint,
        auth_time=subject.auth_time or datetime.now(timezone.utc),
        expires_at=expires_at,
        family_id=family_id,
    )


def _refresh_record(
    *,
    raw_token: str,
    hasher: CredentialHasher,
    client: OAuthClientRecord,
    subject: OAuthSubject,
    audience: str,
    scopes: tuple[str, ...],
    sender_constraint: str,
    family_id: str,
    parent_token_id: str,
    now: datetime,
) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        token_id=f"tok_{uuid4().hex}",
        token_hash=hasher.digest(raw_token),
        family_id=family_id,
        parent_token_id=parent_token_id,
        principal_id=subject.principal_id,
        principal_type=subject.principal_type,
        subject=subject.subject,
        client_id=client.client_id,
        tenant_id=subject.tenant_id,
        audience=audience,
        scopes=scopes,
        capabilities=client.capabilities,
        resource_constraints=dict(client.resource_constraints),
        actor=subject.actor,
        acr=subject.acr,
        sender_constraint=sender_constraint,
        auth_time=subject.auth_time or now,
        expires_at=now + timedelta(days=30),
    )
