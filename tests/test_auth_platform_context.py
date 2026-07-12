from datetime import datetime, timedelta, timezone

import pytest

from aicrm_next.platform_foundation.auth_platform.context import AuthContext, PrincipalType


NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def test_auth_context_normalizes_permissions_and_enforces_resource_constraints() -> None:
    context = AuthContext(
        principal_type=PrincipalType.SERVICE,
        sub="worker:broadcast",
        client_id="broadcast-worker",
        tenant_id="tenant-default",
        audience="aicrm-internal",
        scopes=("broadcast.write", "broadcast.write"),
        capabilities=("broadcast_execute",),
        token_id="tok-1",
        expires_at=datetime(2099, 7, 12, tzinfo=timezone.utc),
        auth_time=NOW,
        resource_constraints={"corp_id": ["corp-1"], "channel": "wecom"},
        sender_constraint="mtls:sha256:abc",
    )
    assert context.scopes == ("broadcast.write",)
    assert context.permits(
        audience="aicrm-internal",
        capability="broadcast_execute",
        scope="broadcast.write",
        resource={"corp_id": "corp-1", "channel": "wecom"},
    )
    assert not context.permits(
        audience="aicrm-internal",
        capability="broadcast_execute",
        resource={"corp_id": "corp-2"},
    )
    assert not context.permits(
        audience="aicrm-internal",
        capability="broadcast_execute",
        scope="broadcast.write",
        resource={},
    )


def test_auth_context_rejects_missing_identity_or_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="client_id"):
        AuthContext(
            principal_type=PrincipalType.USER,
            sub="user-1",
            client_id="",
            tenant_id="tenant-default",
            audience="aicrm-admin",
            scopes=(),
            capabilities=(),
            token_id="tok-1",
            expires_at=NOW + timedelta(minutes=10),
            auth_time=NOW,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        AuthContext(
            principal_type=PrincipalType.USER,
            sub="user-1",
            client_id="admin-bff",
            tenant_id="tenant-default",
            audience="aicrm-admin",
            scopes=(),
            capabilities=(),
            token_id="tok-1",
            expires_at=datetime(2026, 7, 12, 1, 0),
            auth_time=datetime(2026, 7, 12, 0, 0),
        )
