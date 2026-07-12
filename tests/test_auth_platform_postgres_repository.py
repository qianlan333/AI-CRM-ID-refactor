from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import psycopg

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.repository import PostgresAuthPlatformRepository
from aicrm_next.platform_foundation.auth_platform.service import AccessTokenRecord, AuthPlatformService


def test_postgres_repository_bootstraps_client_and_round_trips_access_token(next_pg_schema) -> None:
    suffix = uuid4().hex
    repository = PostgresAuthPlatformRepository(database_url=os.environ["DATABASE_URL"])
    principal_id = f"principal-{suffix}"
    client_id = f"client-{suffix}"
    repository.bootstrap_principal_and_client(
        principal_id=principal_id,
        principal_type=PrincipalType.SERVICE,
        subject=f"worker:{suffix}",
        tenant_id="tenant-default",
        display_name="Repository test worker",
        client_id=client_id,
        client_type="confidential",
        token_endpoint_auth_method="private_key_jwt",
        client_secret_hash="",
        audiences=("aicrm-internal",),
        scopes=("broadcast.read", "broadcast.write"),
        capabilities=("broadcast_execute",),
        resource_constraints={"corp_id": ["corp-1"]},
        sender_constraint_type="mtls",
    )

    grant = repository.client_grant(client_id)
    assert grant is not None
    assert grant.subject == f"worker:{suffix}"
    assert grant.scopes == ("broadcast.read", "broadcast.write")
    assert grant.resource_constraints == {"corp_id": ["corp-1"]}

    now = datetime.now(timezone.utc)
    token = AccessTokenRecord(
        token_id=f"tok-{suffix}",
        token_hash=("a" * 32) + suffix,
        principal_id=principal_id,
        principal_type=PrincipalType.SERVICE,
        subject=f"worker:{suffix}",
        client_id=client_id,
        tenant_id="tenant-default",
        audience="aicrm-internal",
        scopes=("broadcast.write",),
        capabilities=("broadcast_execute",),
        resource_constraints={"corp_id": ["corp-1"]},
        actor="",
        acr="client_credentials",
        sender_constraint="mtls:sha256:test",
        auth_time=now,
        expires_at=now + timedelta(minutes=5),
    )
    repository.insert_access_token(token)

    loaded = repository.access_token_by_hash(token.token_hash)
    assert loaded is not None
    assert loaded.token_id == token.token_id
    assert loaded.principal_type is PrincipalType.SERVICE
    assert loaded.resource_constraints == {"corp_id": ["corp-1"]}
    assert repository.revoke_access_token(token.token_hash, revoked_at=now + timedelta(seconds=1))
    revoked = repository.access_token_by_hash(token.token_hash)
    assert revoked is not None
    assert revoked.revoked_at is not None


def test_postgres_refresh_rotation_detects_reuse_and_revokes_family(next_pg_schema) -> None:
    suffix = uuid4().hex
    database_url = os.environ["DATABASE_URL"]
    repository = PostgresAuthPlatformRepository(database_url=database_url)
    client_id = f"admin-bff-{suffix}"
    repository.bootstrap_principal_and_client(
        principal_id=f"principal-admin-{suffix}",
        principal_type=PrincipalType.USER,
        subject=f"admin:{suffix}",
        tenant_id="tenant-default",
        display_name="Admin BFF test",
        client_id=client_id,
        client_type="confidential",
        token_endpoint_auth_method="private_key_jwt",
        client_secret_hash="",
        redirect_uris=("https://id-dev.example.test/oauth/callback",),
        audiences=("aicrm-admin",),
        scopes=("openid", "admin.read"),
        capabilities=("admin_read",),
    )
    service = AuthPlatformService(repository, CredentialHasher("postgres-pepper-material-32-bytes"))
    now = datetime.now(timezone.utc)
    initial = service.issue_user_token_pair(
        client_id=client_id,
        audience="aicrm-admin",
        requested_scopes=("openid", "admin.read"),
        sender_constraint="",
        now=now,
    )
    rotated = service.refresh_user_token_pair(
        initial.refresh_token,
        client_id=client_id,
        requested_scopes=("admin.read",),
        sender_constraint="",
        now=now + timedelta(minutes=1),
    )

    try:
        service.refresh_user_token_pair(
            initial.refresh_token,
            client_id=client_id,
            requested_scopes=("admin.read",),
            sender_constraint="",
            now=now + timedelta(minutes=2),
        )
    except PermissionError as exc:
        assert str(exc) == "refresh_token_reuse_detected"
    else:
        raise AssertionError("refresh token reuse was not rejected")
    assert not service.introspect_access_token(
        rotated.access_token,
        audience="aicrm-admin",
        sender_constraint="",
        now=now + timedelta(minutes=2),
    ).active
    with psycopg.connect(database_url) as connection:
        family = connection.execute(
            "SELECT status FROM auth_token_families WHERE client_id = %s",
            (client_id,),
        ).fetchone()
        assert family == ("reuse_detected",)
        active_tokens = connection.execute(
            "SELECT COUNT(*) FROM auth_tokens WHERE client_id = %s AND revoked_at IS NULL",
            (client_id,),
        ).fetchone()
        assert active_tokens == (0,)
