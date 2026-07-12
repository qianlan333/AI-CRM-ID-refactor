from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.service import (
    AccessTokenRecord,
    AuthPlatformService,
    ClientGrant,
    RefreshTokenRecord,
)


NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


class _Repository:
    def __init__(self) -> None:
        self.grants = {
            "broadcast-worker": ClientGrant(
                client_id="broadcast-worker",
                principal_id="principal-broadcast",
                principal_type=PrincipalType.SERVICE,
                subject="worker:broadcast",
                tenant_id="tenant-default",
                audiences=("aicrm-internal",),
                scopes=("broadcast.read", "broadcast.write"),
                capabilities=("broadcast_execute",),
                resource_constraints={"corp_id": ["corp-1"]},
                sender_constraint_type="mtls",
            ),
            "admin-bff": ClientGrant(
                client_id="admin-bff",
                principal_id="principal-admin",
                principal_type=PrincipalType.USER,
                subject="admin:1",
                tenant_id="tenant-default",
                audiences=("aicrm-admin",),
                scopes=("admin.read", "admin.write", "openid"),
                capabilities=("admin_read", "admin_write"),
                resource_constraints={},
                sender_constraint_type="",
            ),
        }
        self.tokens: dict[str, AccessTokenRecord] = {}
        self.refresh_tokens: dict[str, RefreshTokenRecord] = {}
        self.family_status: dict[str, str] = {}

    def client_grant(self, client_id: str):
        return self.grants.get(client_id)

    def insert_access_token(self, token: AccessTokenRecord) -> None:
        assert token.token_hash not in self.tokens
        self.tokens[token.token_hash] = token

    def access_token_by_hash(self, token_hash: str):
        return self.tokens.get(token_hash)

    def revoke_access_token(self, token_hash: str, *, revoked_at: datetime) -> bool:
        token = self.tokens.get(token_hash)
        if token is None:
            return False
        self.tokens[token_hash] = replace(token, revoked_at=revoked_at)
        return True

    def insert_token_pair(self, *, family_id, access_token, refresh_token) -> None:
        self.family_status[family_id] = "active"
        self.tokens[access_token.token_hash] = access_token
        self.refresh_tokens[refresh_token.token_hash] = refresh_token

    def refresh_token_by_hash(self, token_hash: str):
        token = self.refresh_tokens.get(token_hash)
        if token is None or self.family_status.get(token.family_id) != "active":
            return None
        return token

    def rotate_refresh_token(self, *, presented_hash, access_token, refresh_token, rotated_at) -> str:
        token = self.refresh_tokens.get(presented_hash)
        if token is None or self.family_status.get(token.family_id) != "active":
            return "invalid"
        if token.consumed_at is not None:
            self.family_status[token.family_id] = "reuse_detected"
            self.tokens = {
                key: replace(value, revoked_at=rotated_at) if value.family_id == token.family_id else value
                for key, value in self.tokens.items()
            }
            self.refresh_tokens = {
                key: replace(value, revoked_at=rotated_at) if value.family_id == token.family_id else value
                for key, value in self.refresh_tokens.items()
            }
            return "reuse_detected"
        self.refresh_tokens[presented_hash] = replace(token, consumed_at=rotated_at)
        self.tokens[access_token.token_hash] = access_token
        self.refresh_tokens[refresh_token.token_hash] = refresh_token
        return "rotated"


def test_client_credentials_issues_five_minute_sender_bound_high_risk_token() -> None:
    repo = _Repository()
    service = AuthPlatformService(repo, CredentialHasher("p" * 32))

    response = service.issue_client_credentials_access_token(
        client_id="broadcast-worker",
        audience="aicrm-internal",
        requested_scopes=("broadcast.write",),
        sender_constraint="mtls:sha256:worker-cert",
        high_risk_write=True,
        now=NOW,
    )

    assert response.token_type == "Bearer"
    assert response.expires_in == 300
    assert response.scope == "broadcast.write"
    stored = next(iter(repo.tokens.values()))
    assert response.access_token not in repr(stored)
    assert stored.sender_constraint == "mtls:sha256:worker-cert"


def test_introspection_returns_auth_context_only_for_bound_audience_and_sender() -> None:
    repo = _Repository()
    service = AuthPlatformService(repo, CredentialHasher("p" * 32))
    response = service.issue_client_credentials_access_token(
        client_id="broadcast-worker",
        audience="aicrm-internal",
        requested_scopes=("broadcast.read",),
        sender_constraint="mtls:sha256:worker-cert",
        now=NOW,
    )

    valid = service.introspect_access_token(
        response.access_token,
        audience="aicrm-internal",
        sender_constraint="mtls:sha256:worker-cert",
        now=NOW + timedelta(minutes=1),
    )
    assert valid.active
    assert valid.context is not None
    assert valid.context.sub == "worker:broadcast"
    assert not service.introspect_access_token(
        response.access_token,
        audience="aicrm-admin",
        sender_constraint="mtls:sha256:worker-cert",
        now=NOW,
    ).active
    assert not service.introspect_access_token(
        response.access_token,
        audience="aicrm-internal",
        sender_constraint="mtls:sha256:other-cert",
        now=NOW,
    ).active


def test_revocation_is_immediate_and_expired_tokens_are_inactive() -> None:
    repo = _Repository()
    service = AuthPlatformService(repo, CredentialHasher("p" * 32))
    response = service.issue_client_credentials_access_token(
        client_id="broadcast-worker",
        audience="aicrm-internal",
        requested_scopes=("broadcast.read",),
        sender_constraint="mtls:sha256:worker-cert",
        now=NOW,
    )

    assert service.revoke_access_token(response.access_token, now=NOW + timedelta(minutes=1))
    assert not service.introspect_access_token(
        response.access_token,
        audience="aicrm-internal",
        sender_constraint="mtls:sha256:worker-cert",
        now=NOW + timedelta(minutes=1),
    ).active


def test_user_refresh_token_rotates_and_reuse_revokes_the_entire_family() -> None:
    repo = _Repository()
    hasher = CredentialHasher("p" * 32)
    service = AuthPlatformService(repo, hasher)
    initial = service.issue_user_token_pair(
        client_id="admin-bff",
        audience="aicrm-admin",
        requested_scopes=("openid", "admin.read"),
        sender_constraint="",
        now=NOW,
    )

    rotated = service.refresh_user_token_pair(
        initial.refresh_token,
        client_id="admin-bff",
        requested_scopes=("admin.read",),
        sender_constraint="",
        now=NOW + timedelta(minutes=1),
    )
    assert rotated.refresh_token != initial.refresh_token
    assert rotated.expires_in == 600
    assert repo.family_status[next(iter(repo.family_status))] == "active"

    with pytest.raises(PermissionError, match="refresh_token_reuse_detected"):
        service.refresh_user_token_pair(
            initial.refresh_token,
            client_id="admin-bff",
            requested_scopes=("admin.read",),
            sender_constraint="",
            now=NOW + timedelta(minutes=2),
        )
    assert repo.family_status[next(iter(repo.family_status))] == "reuse_detected"
    assert not service.introspect_access_token(
        rotated.access_token,
        audience="aicrm-admin",
        sender_constraint="",
        now=NOW + timedelta(minutes=2),
    ).active


def test_refresh_cannot_expand_original_scope_or_change_client() -> None:
    repo = _Repository()
    service = AuthPlatformService(repo, CredentialHasher("p" * 32))
    initial = service.issue_user_token_pair(
        client_id="admin-bff",
        audience="aicrm-admin",
        requested_scopes=("openid", "admin.read"),
        sender_constraint="",
        now=NOW,
    )

    with pytest.raises(PermissionError, match="invalid_scope"):
        service.refresh_user_token_pair(
            initial.refresh_token,
            client_id="admin-bff",
            requested_scopes=("admin.write",),
            sender_constraint="",
            now=NOW + timedelta(minutes=1),
        )
    with pytest.raises(PermissionError, match="invalid_client"):
        service.refresh_user_token_pair(
            initial.refresh_token,
            client_id="different-client",
            requested_scopes=("admin.read",),
            sender_constraint="",
            now=NOW + timedelta(minutes=1),
        )


@pytest.mark.parametrize(
    ("audience", "scopes", "sender", "error"),
    [
        ("wrong", ("broadcast.read",), "mtls:sha256:worker-cert", "invalid_target"),
        ("aicrm-internal", ("admin.write",), "mtls:sha256:worker-cert", "invalid_scope"),
        ("aicrm-internal", ("broadcast.read",), "", "sender_constraint_required"),
    ],
)
def test_issuance_rejects_privilege_or_sender_constraint_escalation(audience, scopes, sender, error) -> None:
    service = AuthPlatformService(_Repository(), CredentialHasher("p" * 32))
    with pytest.raises(PermissionError, match=error):
        service.issue_client_credentials_access_token(
            client_id="broadcast-worker",
            audience=audience,
            requested_scopes=scopes,
            sender_constraint=sender,
            now=NOW,
        )
