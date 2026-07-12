from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass


TOKEN_PREFIX = "at_"
REFRESH_PREFIX = "rt_"
CODE_PREFIX = "ac_"


@dataclass(frozen=True)
class IssuedCredential:
    value: str
    digest: str
    prefix: str


class CredentialHasher:
    """Keyed one-way storage for opaque credentials.

    The pepper is deployment key material and must come from the secret-store
    boundary. Only the digest is persisted; the credential value is returned
    exactly once to the caller.
    """

    def __init__(self, pepper: str | bytes) -> None:
        raw = pepper.encode("utf-8") if isinstance(pepper, str) else bytes(pepper)
        if len(raw) < 32:
            raise ValueError("credential hashing pepper must contain at least 32 bytes")
        self._pepper = raw

    def issue(self, prefix: str = TOKEN_PREFIX, *, entropy_bytes: int = 32) -> IssuedCredential:
        if prefix not in {TOKEN_PREFIX, REFRESH_PREFIX, CODE_PREFIX}:
            raise ValueError("unsupported opaque credential prefix")
        if entropy_bytes < 32:
            raise ValueError("opaque credentials require at least 256 bits of entropy")
        token = prefix + base64.urlsafe_b64encode(secrets.token_bytes(entropy_bytes)).rstrip(b"=").decode("ascii")
        return IssuedCredential(value=token, digest=self.digest(token), prefix=prefix)

    def digest(self, credential: str) -> str:
        value = str(credential or "").strip()
        if not value:
            raise ValueError("credential is required")
        return hmac.new(self._pepper, value.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify(self, credential: str, expected_digest: str) -> bool:
        candidate = str(credential or "").strip()
        expected = str(expected_digest or "").strip()
        if not candidate or len(expected) != 64:
            return False
        return hmac.compare_digest(self.digest(candidate), expected)


def hash_client_secret(secret: str, *, salt: bytes | None = None) -> str:
    value = str(secret or "")
    if len(value.encode("utf-8")) < 32:
        raise ValueError("client secret must contain at least 32 bytes")
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(value.encode("utf-8"), salt=actual_salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(actual_salt).decode("ascii") + "$" + base64.urlsafe_b64encode(digest).decode("ascii")


def verify_client_secret(secret: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = str(encoded or "").split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        candidate = hashlib.scrypt(
            str(secret or "").encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)
