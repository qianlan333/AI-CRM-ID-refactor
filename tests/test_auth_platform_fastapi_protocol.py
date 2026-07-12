import base64
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt

from aicrm_next.main import create_app
from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.client_authentication import CLIENT_ASSERTION_TYPE, jwk_thumbprint
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher, hash_client_secret
from aicrm_next.platform_foundation.auth_platform.oauthlib_provider import OAuthLibProvider, OAuthLibRequestValidator
from aicrm_next.platform_foundation.auth_platform.oidc_signing import OIDCSigner
from aicrm_next.platform_foundation.auth_platform.repository import PostgresAuthPlatformRepository


def test_fastapi_oauth_metadata_token_userinfo_introspection_and_revocation(next_pg_schema) -> None:
    suffix = uuid4().hex
    database_url = os.environ["DATABASE_URL"]
    repository = PostgresAuthPlatformRepository(database_url=database_url)
    client_id = f"fastapi-worker-{suffix}"
    secret = f"fastapi-client-{suffix}-secret-material"
    repository.bootstrap_principal_and_client(
        principal_id=f"fastapi-principal-{suffix}",
        principal_type=PrincipalType.SERVICE,
        subject=f"worker:{suffix}",
        tenant_id="tenant-default",
        display_name="FastAPI protocol worker",
        client_id=client_id,
        client_type="confidential",
        token_endpoint_auth_method="client_secret_basic",
        client_secret_hash=hash_client_secret(secret),
        audiences=("aicrm-internal",),
        scopes=("runtime.read",),
        capabilities=("internal_read",),
    )
    provider = _provider(repository)
    app = create_app()
    app.state.auth_platform_provider = provider
    basic = "Basic " + base64.b64encode(f"{client_id}:{secret}".encode()).decode()

    with TestClient(app) as client:
        metadata = client.get("/.well-known/openid-configuration")
        assert metadata.status_code == 200
        assert metadata.json()["issuer"] == "https://id-dev.example.test/oauth"
        assert metadata.json()["code_challenge_methods_supported"] == ["S256"]
        assert client.get("/oauth/jwks").json()["keys"][0]["use"] == "sig"

        token_response = client.post(
            "/oauth/token",
            headers={"Authorization": basic},
            data={
                "grant_type": "client_credentials",
                "scope": "runtime.read",
                "audience": "aicrm-internal",
            },
        )
        assert token_response.status_code == 200, token_response.text
        token = token_response.json()["access_token"]
        assert token_response.headers["cache-control"] == "no-store"

        introspection = client.post(
            "/oauth/introspect",
            headers={"Authorization": basic},
            data={"token": token},
        )
        assert introspection.status_code == 200
        assert introspection.json()["active"] is True

        revocation = client.post(
            "/oauth/revoke",
            headers={"Authorization": basic},
            data={"token": token, "token_type_hint": "access_token"},
        )
        assert revocation.status_code == 200
        assert client.post(
            "/oauth/introspect",
            headers={"Authorization": basic},
            data={"token": token},
        ).json() == {"active": False}


def test_fastapi_external_agent_requires_private_key_jwt_and_dpop(next_pg_schema) -> None:
    suffix = uuid4().hex
    repository = PostgresAuthPlatformRepository(database_url=os.environ["DATABASE_URL"])
    client_id = f"agent-{suffix}"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = dict(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True))
    repository.bootstrap_principal_and_client(
        principal_id=f"agent-principal-{suffix}",
        principal_type=PrincipalType.AGENT,
        subject=f"agent:{suffix}",
        tenant_id="tenant-default",
        display_name="External agent",
        client_id=client_id,
        client_type="confidential",
        token_endpoint_auth_method="private_key_jwt",
        client_secret_hash="",
        audiences=("aicrm-agent",),
        scopes=("audience.read",),
        capabilities=("external_read",),
        sender_constraint_type="dpop",
    )
    repository.register_client_public_key(
        client_id=client_id,
        key_id="agent-key",
        algorithm="RS256",
        public_jwk=public_jwk,
        thumbprint=jwk_thumbprint(public_jwk),
    )
    provider = _provider(repository)
    app = create_app()
    app.state.auth_platform_provider = provider
    now = datetime.now(timezone.utc)
    token_endpoint = "https://id-dev.example.test/oauth/token"
    assertion = jwt.encode(
        {
            "iss": client_id,
            "sub": client_id,
            "aud": token_endpoint,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=2)).timestamp()),
            "jti": f"assertion-{suffix}",
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "agent-key"},
    )
    dpop_public_jwk = public_jwk
    dpop = jwt.encode(
        {
            "htm": "POST",
            "htu": token_endpoint,
            "iat": int(now.timestamp()),
            "jti": f"dpop-{suffix}",
        },
        private_key,
        algorithm="RS256",
        headers={"typ": "dpop+jwt", "jwk": dpop_public_jwk},
    )
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "scope": "audience.read",
        "audience": "aicrm-agent",
        "client_assertion_type": CLIENT_ASSERTION_TYPE,
        "client_assertion": assertion,
    }

    with TestClient(app) as client:
        response = client.post("/oauth/token", data=payload, headers={"DPoP": dpop})
        assert response.status_code == 200, response.text
        access_token = response.json()["access_token"]
        record = repository.access_token_by_hash(provider.validator.hasher.digest(access_token))
        assert record is not None
        assert record.sender_constraint == f"dpop:{jwk_thumbprint(public_jwk)}"

        replay = client.post("/oauth/token", data=payload, headers={"DPoP": dpop})
        assert replay.status_code == 401
        assert replay.json()["error_description"] == "client_assertion_replayed"


def test_fastapi_internal_worker_uses_trusted_proxy_mtls_identity(next_pg_schema) -> None:
    suffix = uuid4().hex
    repository = PostgresAuthPlatformRepository(database_url=os.environ["DATABASE_URL"])
    client_id = f"mtls-worker-{suffix}"
    repository.bootstrap_principal_and_client(
        principal_id=f"mtls-principal-{suffix}",
        principal_type=PrincipalType.SERVICE,
        subject=f"worker:mtls:{suffix}",
        tenant_id="tenant-default",
        display_name="mTLS worker",
        client_id=client_id,
        client_type="confidential",
        token_endpoint_auth_method="tls_client_auth",
        client_secret_hash="",
        audiences=("aicrm-internal",),
        scopes=("runtime.read",),
        capabilities=("internal_read",),
        sender_constraint_type="mtls",
    )
    provider = _provider(repository)
    app = create_app()
    app.state.auth_platform_provider = provider
    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "scope": "runtime.read",
        "audience": "aicrm-internal",
    }

    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        missing_certificate = client.post("/oauth/token", data=payload)
        assert missing_certificate.status_code == 401
        assert missing_certificate.json()["error_description"] == "mtls_client_certificate_required"

        response = client.post(
            "/oauth/token",
            data=payload,
            headers={
                "X-AICRM-mTLS-Verified": "SUCCESS",
                "X-AICRM-mTLS-Client-Cert-SHA256": "ab" * 32,
            },
        )
        assert response.status_code == 200, response.text
        record = repository.access_token_by_hash(provider.validator.hasher.digest(response.json()["access_token"]))
        assert record is not None
        assert record.sender_constraint == f"mtls:{'ab' * 32}"


def _provider(repository):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    signer = OIDCSigner(
        issuer="https://id-dev.example.test/oauth",
        private_key_pem=pem,
        key_id="fastapi-test-key",
    )
    validator = OAuthLibRequestValidator(
        repository,
        CredentialHasher("fastapi-oauth-provider-pepper-32-bytes"),
        signer,
    )
    return OAuthLibProvider(validator)
