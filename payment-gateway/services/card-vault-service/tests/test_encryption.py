from __future__ import annotations

import base64
import os

import pytest

from services.encryption import CardVaultEncryptor


@pytest.fixture
def two_key_encryptor() -> CardVaultEncryptor:
    return CardVaultEncryptor({
        1: os.urandom(32),
        2: os.urandom(32),
    })


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_encrypt_decrypt_roundtrip(encryptor: CardVaultEncryptor):
    pan = "4111111111111111"
    encrypted = encryptor.encrypt_pan(pan, key_version=1)
    assert encryptor.decrypt_pan(encrypted) == pan


def test_encrypted_value_is_not_plaintext(encryptor: CardVaultEncryptor):
    pan = "4111111111111111"
    encrypted = encryptor.encrypt_pan(pan, key_version=1)
    assert pan not in encrypted


def test_different_encryptions_are_unique(encryptor: CardVaultEncryptor):
    """AES-GCM with random nonce: same PAN → different ciphertext each time."""
    pan = "4111111111111111"
    c1 = encryptor.encrypt_pan(pan, key_version=1)
    c2 = encryptor.encrypt_pan(pan, key_version=1)
    assert c1 != c2


# ── Version prefix ────────────────────────────────────────────────────────────

def test_encrypted_has_version_prefix(encryptor: CardVaultEncryptor):
    encrypted = encryptor.encrypt_pan("4111111111111111", key_version=1)
    assert encrypted.startswith("v1:")


def test_version_prefix_correct_for_v2(two_key_encryptor: CardVaultEncryptor):
    encrypted = two_key_encryptor.encrypt_pan("4111111111111111", key_version=2)
    assert encrypted.startswith("v2:")


def test_decrypt_selects_correct_key(two_key_encryptor: CardVaultEncryptor):
    pan = "5105105105105100"
    enc_v1 = two_key_encryptor.encrypt_pan(pan, key_version=1)
    enc_v2 = two_key_encryptor.encrypt_pan(pan, key_version=2)
    assert two_key_encryptor.decrypt_pan(enc_v1) == pan
    assert two_key_encryptor.decrypt_pan(enc_v2) == pan


# ── Re-encryption / key rotation ─────────────────────────────────────────────

def test_reencrypt(two_key_encryptor: CardVaultEncryptor):
    pan = "4111111111111111"
    old_enc = two_key_encryptor.encrypt_pan(pan, key_version=1)
    new_enc = two_key_encryptor.re_encrypt(old_enc, new_version=2)
    assert new_enc.startswith("v2:")
    assert two_key_encryptor.decrypt_pan(new_enc) == pan


def test_reencrypt_produces_different_ciphertext(two_key_encryptor: CardVaultEncryptor):
    pan = "4111111111111111"
    old_enc = two_key_encryptor.encrypt_pan(pan, key_version=1)
    new_enc = two_key_encryptor.re_encrypt(old_enc, new_version=2)
    assert old_enc != new_enc


# ── Error cases ───────────────────────────────────────────────────────────────

def test_decrypt_unknown_version_raises(encryptor: CardVaultEncryptor):
    # Manually craft a v99 encrypted value
    fake = "v99:" + base64.b64encode(b"\x00" * 30).decode()
    with pytest.raises(ValueError, match="No key loaded for version"):
        encryptor.decrypt_pan(fake)


def test_decrypt_missing_separator_raises(encryptor: CardVaultEncryptor):
    with pytest.raises(ValueError, match="missing version prefix"):
        encryptor.decrypt_pan("invalidnocolon")


def test_decrypt_non_numeric_version_raises(encryptor: CardVaultEncryptor):
    with pytest.raises(ValueError):
        encryptor.decrypt_pan("vX:abc123==")


def test_init_wrong_key_length_raises():
    with pytest.raises(ValueError, match="32 bytes"):
        CardVaultEncryptor({1: b"tooshort"})


def test_init_empty_store_raises():
    with pytest.raises(ValueError, match="at least one key"):
        CardVaultEncryptor({})


def test_encrypt_unknown_version_raises(encryptor: CardVaultEncryptor):
    with pytest.raises(ValueError, match="Unknown key version"):
        encryptor.encrypt_pan("4111111111111111", key_version=99)
