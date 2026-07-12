from aicrm_next.platform_foundation.auth_platform.credentials import (
    CredentialHasher,
    TOKEN_PREFIX,
    hash_client_secret,
    verify_client_secret,
)


def test_opaque_credentials_are_high_entropy_and_only_digests_are_stable() -> None:
    hasher = CredentialHasher("p" * 32)
    first = hasher.issue()
    second = hasher.issue()

    assert first.value.startswith(TOKEN_PREFIX)
    assert len(first.digest) == 64
    assert first.value != second.value
    assert first.digest != second.digest
    assert hasher.verify(first.value, first.digest)
    assert not hasher.verify(second.value, first.digest)


def test_client_secret_uses_scrypt_and_verifies_without_plaintext_storage() -> None:
    secret = "client-secret-material-at-least-32-bytes"
    encoded = hash_client_secret(secret, salt=b"0123456789abcdef")

    assert encoded.startswith("scrypt$16384$8$1$")
    assert secret not in encoded
    assert verify_client_secret(secret, encoded)
    assert not verify_client_secret("wrong-secret-material-at-least-32", encoded)
