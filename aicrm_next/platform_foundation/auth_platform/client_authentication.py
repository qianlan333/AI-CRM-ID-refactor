from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import jwt

from .models import ClientKeyRecord, OAuthClientRecord


CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
ALLOWED_ASYMMETRIC_ALGORITHMS = frozenset({"RS256", "ES256"})
PROOF_CLOCK_SKEW = timedelta(seconds=60)
MAX_ASSERTION_LIFETIME = timedelta(minutes=5)
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


class ClientAuthenticationRepository(Protocol):
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


@dataclass(frozen=True)
class ClientAuthenticationResult:
    client_id: str
    sender_constraint: str
    method: str


class ClientAuthenticationError(ValueError):
    def __init__(self, error: str) -> None:
        self.error = error
        super().__init__(error)


def verify_private_key_jwt(
    *,
    assertion: str,
    assertion_type: str,
    token_endpoint: str,
    repository: ClientAuthenticationRepository,
    now: datetime | None = None,
) -> ClientAuthenticationResult:
    if assertion_type != CLIENT_ASSERTION_TYPE:
        raise ClientAuthenticationError("invalid_client_assertion_type")
    current = _utc(now or datetime.now(timezone.utc))
    try:
        header = jwt.get_unverified_header(assertion)
        unverified = jwt.decode(assertion, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise ClientAuthenticationError("invalid_client_assertion") from exc
    algorithm = str(header.get("alg") or "")
    key_id = str(header.get("kid") or "")
    client_id = str(unverified.get("iss") or "")
    if algorithm not in ALLOWED_ASYMMETRIC_ALGORITHMS or not key_id or not client_id:
        raise ClientAuthenticationError("invalid_client_assertion")
    if unverified.get("sub") != client_id or unverified.get("aud") != token_endpoint:
        raise ClientAuthenticationError("invalid_client_assertion_claims")
    client = repository.oauth_client(client_id)
    key = repository.client_key(client_id, key_id)
    if (
        client is None
        or client.status != "active"
        or client.token_endpoint_auth_method != "private_key_jwt"
        or key is None
        or key.status != "active"
        or key.algorithm != algorithm
        or (key.not_before is not None and current < _utc(key.not_before))
        or (key.expires_at is not None and current >= _utc(key.expires_at))
    ):
        raise ClientAuthenticationError("invalid_client")
    try:
        claims = jwt.decode(
            assertion,
            jwt.PyJWK.from_dict(key.public_jwk).key,
            algorithms=[algorithm],
            audience=token_endpoint,
            options={
                "require": ["iss", "sub", "aud", "iat", "exp", "jti"],
                "verify_exp": False,
                "verify_iat": False,
            },
            leeway=int(PROOF_CLOCK_SKEW.total_seconds()),
        )
    except jwt.PyJWTError as exc:
        raise ClientAuthenticationError("invalid_client_assertion") from exc
    issued_at = datetime.fromtimestamp(int(claims["iat"]), tz=timezone.utc)
    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
    if (
        issued_at > current + PROOF_CLOCK_SKEW
        or expires_at <= current - PROOF_CLOCK_SKEW
        or expires_at <= issued_at
        or expires_at - issued_at > MAX_ASSERTION_LIFETIME
    ):
        raise ClientAuthenticationError("invalid_client_assertion_time")
    if not repository.consume_replay_nonce(
        client_id=client_id,
        nonce_hash=_digest(str(claims["jti"])),
        purpose="private_key_jwt",
        expires_at=expires_at + PROOF_CLOCK_SKEW,
    ):
        raise ClientAuthenticationError("client_assertion_replayed")
    return ClientAuthenticationResult(client_id=client_id, sender_constraint="", method="private_key_jwt")


def verify_dpop_proof(
    *,
    proof: str,
    client_id: str,
    method: str,
    uri: str,
    repository: ClientAuthenticationRepository,
    access_token: str = "",
    now: datetime | None = None,
) -> ClientAuthenticationResult:
    current = _utc(now or datetime.now(timezone.utc))
    try:
        header = jwt.get_unverified_header(proof)
        jwk = dict(header.get("jwk") or {})
        algorithm = str(header.get("alg") or "")
        if str(header.get("typ") or "").lower() != "dpop+jwt":
            raise ClientAuthenticationError("invalid_dpop_typ")
        if algorithm not in ALLOWED_ASYMMETRIC_ALGORITHMS or not jwk or any(name in jwk for name in ("d", "p", "q", "dp", "dq", "qi")):
            raise ClientAuthenticationError("invalid_dpop_key")
        claims = jwt.decode(
            proof,
            jwt.PyJWK.from_dict(jwk).key,
            algorithms=[algorithm],
            options={
                "verify_aud": False,
                "require": ["htm", "htu", "iat", "jti"],
            },
            leeway=int(PROOF_CLOCK_SKEW.total_seconds()),
        )
    except ClientAuthenticationError:
        raise
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise ClientAuthenticationError("invalid_dpop_proof") from exc
    if str(claims["htm"]).upper() != str(method or "").upper() or _normalized_uri(str(claims["htu"])) != _normalized_uri(uri):
        raise ClientAuthenticationError("dpop_target_mismatch")
    issued_at = datetime.fromtimestamp(int(claims["iat"]), tz=timezone.utc)
    if abs((current - issued_at).total_seconds()) > PROOF_CLOCK_SKEW.total_seconds():
        raise ClientAuthenticationError("dpop_proof_expired")
    if access_token:
        expected_ath = _base64url(hashlib.sha256(access_token.encode("ascii")).digest())
        if claims.get("ath") != expected_ath:
            raise ClientAuthenticationError("dpop_access_token_mismatch")
    thumbprint = jwk_thumbprint(jwk)
    if not repository.consume_replay_nonce(
        client_id=client_id,
        nonce_hash=_digest(str(claims["jti"])),
        purpose="dpop",
        expires_at=current + PROOF_CLOCK_SKEW,
    ):
        raise ClientAuthenticationError("dpop_proof_replayed")
    return ClientAuthenticationResult(
        client_id=client_id,
        sender_constraint=f"dpop:{thumbprint}",
        method="dpop",
    )


def mtls_sender_constraint(certificate_thumbprint: str) -> str:
    normalized = str(certificate_thumbprint or "").strip().lower().replace(":", "")
    if not _SHA256_HEX.fullmatch(normalized):
        raise ClientAuthenticationError("invalid_mtls_certificate_thumbprint")
    return f"mtls:{normalized}"


def jwk_thumbprint(jwk: dict[str, Any]) -> str:
    kty = str(jwk.get("kty") or "")
    if kty == "RSA":
        names = ("e", "kty", "n")
    elif kty == "EC":
        names = ("crv", "kty", "x", "y")
    else:
        raise ClientAuthenticationError("unsupported_jwk_type")
    if any(not str(jwk.get(name) or "") for name in names):
        raise ClientAuthenticationError("invalid_jwk")
    canonical = json.dumps({name: jwk[name] for name in names}, sort_keys=True, separators=(",", ":"))
    return _base64url(hashlib.sha256(canonical.encode("utf-8")).digest())


def _normalized_uri(uri: str) -> str:
    parsed = urlsplit(uri)
    if parsed.scheme.lower() not in {"https", "http"} or not parsed.netloc:
        raise ClientAuthenticationError("invalid_dpop_uri")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", ""))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ClientAuthenticationError("authentication_time_must_be_timezone_aware")
    return value.astimezone(timezone.utc)
