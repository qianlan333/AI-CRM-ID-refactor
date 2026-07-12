"""add unified AI-CRM authorization platform schema.

Revision ID: 0104_auth_platform
Revises: 0103_broadcast_delivery_state_machine
"""

from __future__ import annotations

from alembic import op


revision = "0104_auth_platform"
down_revision = "0103_broadcast_delivery_state_machine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_principals (
            id BIGSERIAL PRIMARY KEY,
            principal_id TEXT NOT NULL UNIQUE,
            principal_type TEXT NOT NULL CHECK (principal_type IN ('user','service','agent','partner')),
            tenant_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','revoked')),
            session_version BIGINT NOT NULL DEFAULT 1 CHECK (session_version > 0),
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (tenant_id, subject, principal_type)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_clients (
            id BIGSERIAL PRIMARY KEY,
            client_id TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES auth_principals(principal_id),
            client_type TEXT NOT NULL CHECK (client_type IN ('confidential','public')),
            client_secret_hash TEXT NOT NULL DEFAULT '',
            token_endpoint_auth_method TEXT NOT NULL,
            redirect_uris_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            audiences_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            resource_constraints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            sender_constraint_type TEXT NOT NULL DEFAULT '' CHECK (sender_constraint_type IN ('','mtls','dpop')),
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','revoked')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((client_type = 'public' AND client_secret_hash = '') OR client_type = 'confidential')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_client_keys (
            id BIGSERIAL PRIMARY KEY,
            client_id TEXT NOT NULL REFERENCES auth_clients(client_id) ON DELETE CASCADE,
            key_id TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            public_jwk_json JSONB NOT NULL,
            thumbprint TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','retiring','revoked')),
            not_before TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (client_id, key_id),
            UNIQUE (client_id, thumbprint)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES auth_principals(principal_id),
            client_id TEXT NOT NULL REFERENCES auth_clients(client_id),
            session_secret_hash TEXT NOT NULL,
            session_version BIGINT NOT NULL CHECK (session_version > 0),
            acr TEXT NOT NULL DEFAULT '',
            auth_time TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (expires_at > auth_time)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_authorization_codes (
            id BIGSERIAL PRIMARY KEY,
            code_hash TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES auth_principals(principal_id),
            client_id TEXT NOT NULL REFERENCES auth_clients(client_id),
            redirect_uri TEXT NOT NULL,
            audience TEXT NOT NULL,
            scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            code_challenge TEXT NOT NULL,
            code_challenge_method TEXT NOT NULL CHECK (code_challenge_method = 'S256'),
            nonce_hash TEXT NOT NULL DEFAULT '',
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_token_families (
            id BIGSERIAL PRIMARY KEY,
            family_id TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL REFERENCES auth_principals(principal_id),
            client_id TEXT NOT NULL REFERENCES auth_clients(client_id),
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked','reuse_detected')),
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id BIGSERIAL PRIMARY KEY,
            token_id TEXT NOT NULL UNIQUE,
            token_hash TEXT NOT NULL UNIQUE,
            token_type TEXT NOT NULL CHECK (token_type IN ('access','refresh')),
            family_id TEXT REFERENCES auth_token_families(family_id),
            parent_token_id TEXT,
            principal_id TEXT NOT NULL REFERENCES auth_principals(principal_id),
            client_id TEXT NOT NULL REFERENCES auth_clients(client_id),
            audience TEXT NOT NULL,
            scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            capabilities_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            resource_constraints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            actor TEXT NOT NULL DEFAULT '',
            acr TEXT NOT NULL DEFAULT '',
            sender_constraint TEXT NOT NULL DEFAULT '',
            auth_time TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            revoked_at TIMESTAMPTZ,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (expires_at > auth_time),
            CHECK ((token_type = 'refresh' AND family_id IS NOT NULL) OR token_type = 'access')
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_active_lookup ON auth_tokens (token_hash, expires_at) WHERE revoked_at IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_family ON auth_tokens (family_id) WHERE family_id IS NOT NULL")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_replay_nonces (
            id BIGSERIAL PRIMARY KEY,
            client_id TEXT NOT NULL REFERENCES auth_clients(client_id),
            nonce_hash TEXT NOT NULL,
            purpose TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (client_id, nonce_hash, purpose)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_auth_replay_nonces_expiry ON auth_replay_nonces (expires_at)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_security_events (
            id BIGSERIAL PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE,
            event_type TEXT NOT NULL,
            principal_id TEXT NOT NULL DEFAULT '',
            client_id TEXT NOT NULL DEFAULT '',
            token_id TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL CHECK (outcome IN ('allowed','denied','revoked','failed')),
            reason TEXT NOT NULL DEFAULT '',
            request_fingerprint TEXT NOT NULL DEFAULT '',
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_security_events")
    op.execute("DROP TABLE IF EXISTS auth_replay_nonces")
    op.execute("DROP TABLE IF EXISTS auth_tokens")
    op.execute("DROP TABLE IF EXISTS auth_token_families")
    op.execute("DROP TABLE IF EXISTS auth_authorization_codes")
    op.execute("DROP TABLE IF EXISTS auth_sessions")
    op.execute("DROP TABLE IF EXISTS auth_client_keys")
    op.execute("DROP TABLE IF EXISTS auth_clients")
    op.execute("DROP TABLE IF EXISTS auth_principals")
