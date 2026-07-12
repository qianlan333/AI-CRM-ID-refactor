from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import psycopg

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.models import OAuthSubject
from aicrm_next.platform_foundation.auth_platform.repository import PostgresAuthPlatformRepository
from aicrm_next.platform_foundation.auth_platform.sessions import AuthSessionService


def test_postgres_session_is_invalidated_by_principal_session_version(next_pg_schema) -> None:
    suffix = uuid4().hex
    database_url = os.environ["DATABASE_URL"]
    repository = PostgresAuthPlatformRepository(database_url=database_url)
    principal_id = f"session-principal-{suffix}"
    client_id = f"session-client-{suffix}"
    repository.bootstrap_principal_and_client(
        principal_id=principal_id,
        principal_type=PrincipalType.USER,
        subject=f"admin:{suffix}",
        tenant_id="tenant-default",
        display_name="Session admin",
        client_id=client_id,
        client_type="public",
        token_endpoint_auth_method="none",
        client_secret_hash="",
        audiences=("aicrm-admin",),
        scopes=("admin.read",),
        capabilities=("admin_read",),
    )
    service = AuthSessionService(repository, CredentialHasher("postgres-session-pepper-32-bytes"))
    now = datetime.now(timezone.utc)
    issued = service.issue(
        subject=OAuthSubject(
            principal_id=principal_id,
            principal_type=PrincipalType.USER,
            subject=f"admin:{suffix}",
            tenant_id="tenant-default",
            acr="wecom_sso",
        ),
        client_id=client_id,
        session_version=1,
        audience="aicrm-admin",
        scopes=("admin.read",),
        capabilities=("admin_read",),
        now=now,
    )
    assert service.introspect(issued.session_cookie, now=now + timedelta(minutes=1)).active

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "UPDATE auth_principals SET session_version = session_version + 1 WHERE principal_id = %s",
            (principal_id,),
        )
        connection.commit()
    result = service.introspect(issued.session_cookie, now=now + timedelta(minutes=2))
    assert not result.active
    assert result.error == "session_expired_or_revoked"
