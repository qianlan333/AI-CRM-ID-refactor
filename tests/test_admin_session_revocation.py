from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.models import OAuthSubject
from aicrm_next.platform_foundation.auth_platform.sessions import AuthSessionService
from tests.admin_auth_test_helpers import InMemoryAuthSessionRepository


ROOT = Path(__file__).resolve().parents[1]


def test_server_side_principal_version_revokes_existing_admin_session() -> None:
    repository = InMemoryAuthSessionRepository()
    repository.bootstrap_principal_and_client(
        principal_id="service:aicrm-admin-bff",
        principal_type=PrincipalType.SERVICE,
        subject="service:aicrm-admin-bff",
        tenant_id="tenant:default",
        display_name="Admin BFF",
        client_id="aicrm-admin-bff",
        client_type="public",
        token_endpoint_auth_method="none",
        client_secret_hash="",
        audiences=("aicrm-admin",),
        scopes=("admin.read",),
        capabilities=("admin_read",),
    )
    repository.upsert_principal(
        principal_id="admin-user:17",
        principal_type=PrincipalType.USER,
        subject="admin:17",
        tenant_id="tenant:default",
        display_name="Admin 17",
        session_version=4,
    )
    service = AuthSessionService(repository, CredentialHasher("admin-revocation-pepper-material-32-bytes"))
    now = datetime.now(timezone.utc)
    issued = service.issue(
        subject=OAuthSubject(
            principal_id="admin-user:17",
            principal_type=PrincipalType.USER,
            subject="admin:17",
            tenant_id="tenant:default",
            acr="wecom_sso",
            auth_time=now,
        ),
        client_id="aicrm-admin-bff",
        session_version=4,
        audience="aicrm-admin",
        scopes=("admin.read",),
        capabilities=("admin_read",),
        now=now,
    )
    assert service.introspect(issued.session_cookie, now=now + timedelta(minutes=1)).active

    repository.upsert_principal(
        principal_id="admin-user:17",
        principal_type=PrincipalType.USER,
        subject="admin:17",
        tenant_id="tenant:default",
        display_name="Admin 17",
        session_version=5,
    )

    result = service.introspect(issued.session_cookie, now=now + timedelta(minutes=2))
    assert not result.active
    assert result.error == "session_expired_or_revoked"


def test_auth_migration_syncs_admin_disable_role_and_version_changes() -> None:
    source = (ROOT / "migrations" / "versions" / "0104_auth_platform.py").read_text(encoding="utf-8")

    assert "sync_admin_auth_principal_state" in source
    assert "AFTER UPDATE OF session_version, is_active, login_enabled ON admin_users" in source
    assert "WHERE principal_id = 'admin-user:' || NEW.id::text" in source
