from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from aicrm_next.platform_foundation.auth_platform.context import PrincipalType
from aicrm_next.platform_foundation.auth_platform.credentials import CredentialHasher
from aicrm_next.platform_foundation.auth_platform.service import (
    AccessTokenRecord,
    AuthPlatformService,
    ClientGrant,
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
            )
        }
        self.tokens: dict[str, AccessTokenRecord] = {}

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
