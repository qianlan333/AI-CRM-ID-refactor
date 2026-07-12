from dataclasses import replace
from datetime import datetime, timedelta, timezone

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.models import OAuthSubject
from aicrm_next.platform_foundation.auth_platform.sessions import AuthSessionService


NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


class _Repository:
    def __init__(self):
        self.sessions = {}

    def insert_auth_session(self, session):
        self.sessions[session.session_secret_hash] = session

    def auth_session_by_hash(self, session_hash):
        return self.sessions.get(session_hash)

    def revoke_auth_session(self, session_hash, *, revoked_at, reason):
        session = self.sessions.get(session_hash)
        if session is None:
            return False
        self.sessions[session_hash] = replace(session, revoked_at=revoked_at, revoked_reason=reason)
        return True


def test_opaque_bff_session_yields_auth_context_and_hash_only_storage() -> None:
    repository = _Repository()
    service = AuthSessionService(repository, CredentialHasher("session-test-pepper-material-32-bytes"))
    issued = service.issue(
        subject=OAuthSubject(
            principal_id="principal-admin-1",
            principal_type=PrincipalType.USER,
            subject="admin:1",
            tenant_id="tenant-default",
            acr="wecom_sso",
            auth_time=NOW,
        ),
        client_id="admin-bff",
        session_version=3,
        audience="aicrm-admin",
        scopes=("admin.read",),
        capabilities=("admin_read",),
        now=NOW,
    )

    stored = next(iter(repository.sessions.values()))
    assert issued.session_cookie.startswith("ss_")
    assert issued.csrf_token.startswith("csrf_")
    assert issued.session_cookie not in repr(stored)
    assert issued.csrf_token not in repr(stored)
    introspection = service.introspect(issued.session_cookie, now=NOW + timedelta(hours=1))
    assert introspection.active
    assert introspection.context is not None
    assert introspection.context.sub == "admin:1"
    assert introspection.context.capabilities == ("admin_read",)
    assert service.verify_csrf(introspection, issued.csrf_token, issued.csrf_token)
    assert not service.verify_csrf(introspection, issued.csrf_token, "csrf_wrong")


def test_logout_revokes_session_immediately() -> None:
    repository = _Repository()
    service = AuthSessionService(repository, CredentialHasher("session-test-pepper-material-32-bytes"))
    issued = service.issue(
        subject=OAuthSubject(
            principal_id="principal-admin-2",
            principal_type=PrincipalType.USER,
            subject="admin:2",
            tenant_id="tenant-default",
            acr="wecom_sso",
        ),
        client_id="admin-bff",
        session_version=1,
        audience="aicrm-admin",
        scopes=("admin.read",),
        capabilities=("admin_read",),
        now=NOW,
    )
    assert service.revoke(issued.session_cookie, reason="logout", now=NOW + timedelta(minutes=1))
    result = service.introspect(issued.session_cookie, now=NOW + timedelta(minutes=1))
    assert not result.active
    assert result.error == "session_expired_or_revoked"
