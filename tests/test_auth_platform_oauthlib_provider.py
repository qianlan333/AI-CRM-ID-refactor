from __future__ import annotations

import base64
import hashlib
import json
import os
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher, hash_client_secret
from aicrm_next.platform_foundation.auth_platform.models import OAuthSubject
from aicrm_next.platform_foundation.auth_platform.oauthlib_provider import (
    OAuthLibProvider,
    OAuthLibRequestValidator,
)
from aicrm_next.platform_foundation.auth_platform.oidc_signing import OIDCSigner
from aicrm_next.platform_foundation.auth_platform.repository import PostgresAuthPlatformRepository


ISSUER = "https://id-dev.example.test/oauth"


def test_oauthlib_client_credentials_introspection_and_revocation(next_pg_schema) -> None:
    suffix = uuid4().hex
    repository = PostgresAuthPlatformRepository(database_url=os.environ["DATABASE_URL"])
    client_id = f"worker-{suffix}"
    secret = f"client-secret-{suffix}-material-32-bytes"
    repository.bootstrap_principal_and_client(
        principal_id=f"principal-{suffix}",
        principal_type=PrincipalType.SERVICE,
        subject=f"worker:{suffix}",
        tenant_id="tenant-default",
        display_name="OAuthLib worker",
        client_id=client_id,
        client_type="confidential",
        token_endpoint_auth_method="client_secret_basic",
        client_secret_hash=hash_client_secret(secret),
        audiences=("aicrm-internal",),
        scopes=("broadcast.read", "broadcast.write"),
        capabilities=("broadcast_execute",),
    )
    provider, _signer = _provider(repository)
    headers = {"Authorization": _basic(client_id, secret), "Content-Type": "application/x-www-form-urlencoded"}

    response_headers, response_body, status = provider.server.create_token_response(
        f"{ISSUER}/token",
        body=urlencode({"grant_type": "client_credentials", "scope": "broadcast.write"}),
        headers=headers,
        credentials={"audience": "aicrm-internal", "sender_constraint": ""},
    )

    assert status == 200, response_body
    token = json.loads(response_body)
    assert token["token_type"] == "Bearer"
    assert token["expires_in"] == 300
    assert "refresh_token" not in token
    assert response_headers["Cache-Control"] == "no-store"

    _, introspection_body, introspection_status = provider.server.create_introspect_response(
        f"{ISSUER}/introspect",
        body=urlencode({"token": token["access_token"], "token_type_hint": "access_token"}),
        headers=headers,
    )
    introspection = json.loads(introspection_body)
    assert introspection_status == 200
    assert introspection["active"] is True
    assert introspection["client_id"] == client_id
    assert introspection["sub"] == f"worker:{suffix}"
    assert introspection["aud"] == "aicrm-internal"

    _, _, revoke_status = provider.server.create_revocation_response(
        f"{ISSUER}/revoke",
        body=urlencode({"token": token["access_token"], "token_type_hint": "access_token"}),
        headers=headers,
    )
    assert revoke_status == 200
    _, revoked_body, _ = provider.server.create_introspect_response(
        f"{ISSUER}/introspect",
        body=urlencode({"token": token["access_token"]}),
        headers=headers,
    )
    assert json.loads(revoked_body) == {"active": False}


def test_oauthlib_oidc_authorization_code_pkce_is_one_time_and_rotating(next_pg_schema) -> None:
    suffix = uuid4().hex
    repository = PostgresAuthPlatformRepository(database_url=os.environ["DATABASE_URL"])
    client_id = f"admin-bff-{suffix}"
    principal_id = f"admin-principal-{suffix}"
    redirect_uri = f"https://id-dev.example.test/callback/{suffix}"
    repository.bootstrap_principal_and_client(
        principal_id=principal_id,
        principal_type=PrincipalType.USER,
        subject=f"admin:{suffix}",
        tenant_id="tenant-default",
        display_name="OIDC admin",
        client_id=client_id,
        client_type="public",
        token_endpoint_auth_method="none",
        client_secret_hash="",
        redirect_uris=(redirect_uri,),
        audiences=("aicrm-admin",),
        scopes=("openid", "admin.read"),
        capabilities=("admin_read",),
    )
    provider, signer = _provider(repository)
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    subject = OAuthSubject(
        principal_id=principal_id,
        principal_type=PrincipalType.USER,
        subject=f"admin:{suffix}",
        tenant_id="tenant-default",
        acr="wecom_sso",
    )
    authorization_uri = f"{ISSUER}/authorize?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid admin.read",
            "state": "state-1",
            "nonce": "nonce-1",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )

    auth_headers, _auth_body, auth_status = provider.server.create_authorization_response(
        authorization_uri,
        scopes=["openid", "admin.read"],
        credentials={"user": subject, "audience": "aicrm-admin"},
    )

    assert auth_status == 302
    location = auth_headers["Location"]
    params = parse_qs(urlparse(location).query)
    assert "code" in params, location
    code = params["code"][0]
    assert params["state"] == ["state-1"]
    token_body = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
    )
    _, response_body, status = provider.server.create_token_response(
        f"{ISSUER}/token",
        body=token_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        credentials={"audience": "aicrm-admin", "sender_constraint": ""},
    )

    assert status == 200, response_body
    tokens = json.loads(response_body)
    assert tokens["expires_in"] == 600
    assert tokens["refresh_token"].startswith("rt_")
    claims = signer.verify(tokens["id_token"], audience=client_id)
    assert claims["sub"] == f"admin:{suffix}"
    assert claims["nonce"] == "nonce-1"
    assert claims["acr"] == "wecom_sso"

    refresh_body = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "scope": "admin.read",
        }
    )
    _, refreshed_body, refreshed_status = provider.server.create_token_response(
        f"{ISSUER}/token",
        body=refresh_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        credentials={"audience": "aicrm-admin", "sender_constraint": ""},
    )
    assert refreshed_status == 200, refreshed_body
    refreshed = json.loads(refreshed_body)
    assert refreshed["refresh_token"] != tokens["refresh_token"]

    _, reused_body, reused_status = provider.server.create_token_response(
        f"{ISSUER}/token",
        body=refresh_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        credentials={"audience": "aicrm-admin", "sender_constraint": ""},
    )
    assert reused_status == 400
    assert json.loads(reused_body)["error"] == "invalid_grant"
    revoked_access = repository.access_token_by_hash(provider.validator.hasher.digest(refreshed["access_token"]))
    assert revoked_access is not None
    assert revoked_access.revoked_at is not None

    _, replay_body, replay_status = provider.server.create_token_response(
        f"{ISSUER}/token",
        body=token_body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        credentials={"audience": "aicrm-admin", "sender_constraint": ""},
    )
    assert replay_status == 400
    assert json.loads(replay_body)["error"] == "invalid_grant"


def _provider(repository):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    signer = OIDCSigner(issuer=ISSUER, private_key_pem=private_key_pem, key_id="test-key")
    validator = OAuthLibRequestValidator(repository, CredentialHasher("oauthlib-provider-test-pepper-32-bytes"), signer)
    return OAuthLibProvider(validator), signer


def _basic(client_id: str, secret: str) -> str:
    encoded = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    return f"Basic {encoded}"
