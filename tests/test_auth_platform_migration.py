from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "versions" / "0104_auth_platform.py"


def test_auth_platform_migration_uses_hash_only_credential_columns_and_required_security_tables() -> None:
    text = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "auth_principals",
        "auth_clients",
        "auth_client_keys",
        "auth_sessions",
        "auth_authorization_codes",
        "auth_token_families",
        "auth_tokens",
        "auth_replay_nonces",
        "auth_security_events",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text
    assert "client_secret TEXT" not in text
    assert "access_token TEXT" not in text
    assert "refresh_token TEXT" not in text
    assert "authorization_code TEXT" not in text
    assert "client_secret_hash TEXT" in text
    assert "token_hash TEXT" in text
    assert "code_hash TEXT" in text


def test_auth_platform_migration_follows_r10_head() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0104_auth_platform"' in text
    assert 'down_revision = "0103_broadcast_delivery_state_machine"' in text
