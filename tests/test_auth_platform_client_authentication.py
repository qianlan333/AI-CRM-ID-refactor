from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from aicrm_next.platform_foundation.auth_platform.client_authentication import (
    CLIENT_ASSERTION_TYPE,
    ClientAuthenticationError,
    jwk_thumbprint,
    mtls_sender_constraint,
    verify_dpop_proof,
    verify_private_key_jwt,
)
from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.models import ClientKeyRecord, OAuthClientRecord


NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)
TOKEN_ENDPOINT = "https://id-dev.example.test/oauth/token"


class _Repository:
    def __init__(self, client, key):
        self.client = client
        self.key = key
        self.nonces = set()

    def oauth_client(self, client_id):
        return self.client if client_id == self.client.client_id else None

    def client_key(self, client_id, key_id):
        return self.key if (client_id, key_id) == (self.client.client_id, self.key.key_id) else None

    def consume_replay_nonce(self, *, client_id, nonce_hash, purpose, expires_at):
        value = (client_id, nonce_hash, purpose)
        if value in self.nonces:
            return False
        self.nonces.add(value)
        return True


def test_private_key_jwt_verifies_registered_key_claims_and_replay_boundary() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    repository = _repository(public_jwk)
    assertion = jwt.encode(
        {
            "iss": "agent-client",
            "sub": "agent-client",
            "aud": TOKEN_ENDPOINT,
            "iat": int(NOW.timestamp()),
            "exp": int((NOW + timedelta(minutes=2)).timestamp()),
            "jti": "assertion-1",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )

    result = verify_private_key_jwt(
        assertion=assertion,
        assertion_type=CLIENT_ASSERTION_TYPE,
        token_endpoint=TOKEN_ENDPOINT,
        repository=repository,
        now=NOW,
    )
    assert result.client_id == "agent-client"
    assert result.method == "private_key_jwt"
    with pytest.raises(ClientAuthenticationError, match="client_assertion_replayed"):
        verify_private_key_jwt(
            assertion=assertion,
            assertion_type=CLIENT_ASSERTION_TYPE,
            token_endpoint=TOKEN_ENDPOINT,
            repository=repository,
            now=NOW,
        )


def test_private_key_jwt_rejects_wrong_audience_or_unregistered_algorithm() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    repository = _repository(public_jwk)
    assertion = jwt.encode(
        {
            "iss": "agent-client",
            "sub": "agent-client",
            "aud": "https://attacker.invalid/token",
            "iat": int(NOW.timestamp()),
            "exp": int((NOW + timedelta(minutes=2)).timestamp()),
            "jti": "assertion-2",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "key-1"},
    )
    with pytest.raises(ClientAuthenticationError, match="invalid_client_assertion_claims"):
        verify_private_key_jwt(
            assertion=assertion,
            assertion_type=CLIENT_ASSERTION_TYPE,
            token_endpoint=TOKEN_ENDPOINT,
            repository=repository,
            now=NOW,
        )


def test_dpop_binds_method_uri_key_and_access_token_and_rejects_replay() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    repository = _repository(jwt.algorithms.RSAAlgorithm.to_jwk(rsa.generate_private_key(65537, 2048).public_key(), as_dict=True))
    access_token = "at_test-token"
    ath = _base64url(__import__("hashlib").sha256(access_token.encode()).digest())
    proof = jwt.encode(
        {
            "htm": "POST",
            "htu": TOKEN_ENDPOINT,
            "iat": int(NOW.timestamp()),
            "jti": "dpop-1",
            "ath": ath,
        },
        private_key,
        algorithm="ES256",
        headers={"typ": "dpop+jwt", "jwk": jwk},
    )

    result = verify_dpop_proof(
        proof=proof,
        client_id="agent-client",
        method="POST",
        uri=TOKEN_ENDPOINT + "?ignored=query",
        repository=repository,
        access_token=access_token,
        now=NOW,
    )
    assert result.sender_constraint == f"dpop:{jwk_thumbprint(jwk)}"
    with pytest.raises(ClientAuthenticationError, match="dpop_proof_replayed"):
        verify_dpop_proof(
            proof=proof,
            client_id="agent-client",
            method="POST",
            uri=TOKEN_ENDPOINT,
            repository=repository,
            access_token=access_token,
            now=NOW,
        )


def test_mtls_thumbprint_is_strict_sha256() -> None:
    assert mtls_sender_constraint("AA:" * 31 + "AA") == f"mtls:{'aa' * 32}"
    with pytest.raises(ClientAuthenticationError, match="invalid_mtls_certificate_thumbprint"):
        mtls_sender_constraint("not-a-certificate-thumbprint")


def _repository(public_jwk):
    client = OAuthClientRecord(
        client_id="agent-client",
        principal_id="principal-agent",
        principal_type=PrincipalType.AGENT,
        subject="agent:copywriter",
        tenant_id="tenant-default",
        client_type="confidential",
        client_secret_hash="",
        token_endpoint_auth_method="private_key_jwt",
        redirect_uris=(),
        audiences=("aicrm-agent",),
        scopes=("audience.read",),
        capabilities=("external_read",),
        resource_constraints={},
        sender_constraint_type="dpop",
        status="active",
    )
    key = ClientKeyRecord(
        client_id=client.client_id,
        key_id="key-1",
        algorithm="RS256",
        public_jwk=dict(public_jwk),
        thumbprint=jwk_thumbprint(dict(public_jwk)),
        status="active",
        not_before=None,
        expires_at=None,
    )
    return _Repository(client, key)


def _base64url(value):
    import base64

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()
