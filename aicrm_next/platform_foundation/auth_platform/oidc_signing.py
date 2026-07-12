from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization


ID_TOKEN_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class OIDCSigner:
    issuer: str
    private_key_pem: str
    key_id: str
    algorithm: str = "RS256"

    def __post_init__(self) -> None:
        if self.algorithm != "RS256":
            raise ValueError("RAUTH OIDC signer only permits RS256")
        if not self.issuer.startswith("https://"):
            raise ValueError("OIDC issuer must use https")
        if not self.key_id:
            raise ValueError("OIDC signing key id is required")
        serialization.load_pem_private_key(self.private_key_pem.encode("utf-8"), password=None)

    def sign(self, claims: dict[str, Any]) -> str:
        required = {"sub", "aud", "iat"}
        if not required.issubset(claims):
            raise ValueError("OIDC ID token is missing required claims")
        payload = dict(claims)
        issued_at = _timestamp(payload["iat"])
        payload.update(
            {
                "iss": self.issuer,
                "iat": int(issued_at.timestamp()),
                "exp": int((issued_at + ID_TOKEN_TTL).timestamp()),
            }
        )
        return jwt.encode(
            payload,
            self.private_key_pem,
            algorithm=self.algorithm,
            headers={"kid": self.key_id, "typ": "JWT"},
        )

    def verify(self, token: str, *, audience: str) -> dict[str, Any]:
        return dict(
            jwt.decode(
                token,
                self.public_key_pem(),
                algorithms=[self.algorithm],
                audience=audience,
                issuer=self.issuer,
                options={"require": ["iss", "sub", "aud", "iat", "exp"]},
            )
        )

    def public_key_pem(self) -> str:
        private_key = serialization.load_pem_private_key(self.private_key_pem.encode("utf-8"), password=None)
        return (
            private_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )

    def jwks(self) -> dict[str, list[dict[str, Any]]]:
        public_key = serialization.load_pem_public_key(self.public_key_pem().encode("ascii"))
        key = dict(jwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True))
        key.update({"kid": self.key_id, "use": "sig", "alg": self.algorithm})
        return {"keys": [key]}


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("OIDC issued-at must be timezone-aware")
        return value.astimezone(timezone.utc)
    return datetime.fromtimestamp(int(value), tz=timezone.utc)
