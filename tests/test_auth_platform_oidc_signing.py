from datetime import datetime, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from aicrm_next.platform_foundation.auth_platform.oidc_signing import OIDCSigner


def test_oidc_signer_emits_asymmetric_required_claims_and_public_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    signer = OIDCSigner(
        issuer="https://id-dev.example.test/oauth",
        private_key_pem=pem,
        key_id="kid-1",
    )

    token = signer.sign(
        {
            "sub": "admin:1",
            "aud": "admin-bff",
            "iat": datetime.now(timezone.utc),
            "nonce": "nonce-1",
        }
    )
    claims = signer.verify(token, audience="admin-bff")
    header = jwt.get_unverified_header(token)

    assert claims["iss"] == "https://id-dev.example.test/oauth"
    assert claims["sub"] == "admin:1"
    assert claims["exp"] - claims["iat"] == 300
    assert header == {"alg": "RS256", "kid": "kid-1", "typ": "JWT"}
    jwk = signer.jwks()["keys"][0]
    assert jwk["kid"] == "kid-1"
    assert jwk["kty"] == "RSA"
    assert "d" not in jwk
