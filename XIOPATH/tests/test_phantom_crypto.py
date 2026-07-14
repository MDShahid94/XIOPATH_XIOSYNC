"""
Tests for phantom/crypto.py — XIOPATH Phantom Encryption Core (Fix 6.3)

Tests:
- AES-256-GCM encrypt/decrypt round-trip
- AES key derivation (HKDF)
- Shamir Secret Sharing (split + reconstruct)
- Password generation (length, character categories)
- UUIDv7 (format, sortability, RFC 9562 bits)
- Edge cases and validation errors
"""

import re
import time
import pytest
from phantom.crypto import (
    AESCipher,
    ShamirSecret,
    generate_master_key,
    generate_password,
    uuid7,
)


# ═══════════════════════════════════════════════════════════════════════════
# AESCipher
# ═══════════════════════════════════════════════════════════════════════════

class TestAESCipher:
    """Test AES-256-GCM encryption."""

    def test_encrypt_decrypt_roundtrip(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        plaintext = "Hello, XIOPATH!"
        token = cipher.encrypt(plaintext)
        assert cipher.decrypt(token) == plaintext

    def test_encrypt_decrypt_with_aad(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        plaintext = "secret data"
        aad = b"context-identifier"
        token = cipher.encrypt(plaintext, associated_data=aad)
        assert cipher.decrypt(token, associated_data=aad) == plaintext

    def test_wrong_aad_fails(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        token = cipher.encrypt("secret", associated_data=b"correct")
        with pytest.raises(Exception):  # InvalidTag from cryptography
            cipher.decrypt(token, associated_data=b"wrong")

    def test_wrong_key_fails(self):
        key1 = generate_master_key()
        key2 = generate_master_key()
        cipher1 = AESCipher(key1)
        cipher2 = AESCipher(key2)
        token = cipher1.encrypt("data")
        with pytest.raises(Exception):
            cipher2.decrypt(token)

    def test_invalid_key_length(self):
        with pytest.raises(ValueError, match="32 bytes"):
            AESCipher(b"too_short")

    def test_invalid_key_type(self):
        with pytest.raises(ValueError):
            AESCipher("not_bytes")

    def test_unicode_roundtrip(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        plaintext = "日本語テスト 🎯 العربية"
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_empty_string_roundtrip(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        assert cipher.decrypt(cipher.encrypt("")) == ""

    def test_large_plaintext(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        plaintext = "A" * 100_000
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_derive_key_produces_32_bytes(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        derived = cipher.derive_key("salt-context", "info-label")
        assert isinstance(derived, bytes)
        assert len(derived) == 32

    def test_derive_key_deterministic(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        d1 = cipher.derive_key("ctx", "info")
        d2 = cipher.derive_key("ctx", "info")
        assert d1 == d2

    def test_derive_key_different_contexts_differ(self):
        key = generate_master_key()
        cipher = AESCipher(key)
        d1 = cipher.derive_key("ctx-1", "info")
        d2 = cipher.derive_key("ctx-2", "info")
        assert d1 != d2


# ═══════════════════════════════════════════════════════════════════════════
# Shamir Secret Sharing
# ═══════════════════════════════════════════════════════════════════════════

class TestShamirSecret:
    """Test Shamir's Secret Sharing over GF(256)."""

    def test_split_and_reconstruct_3_of_5(self):
        secret = generate_master_key()  # 32 bytes
        shares = ShamirSecret.split(secret, threshold=3, shares=5)
        assert len(shares) == 5
        # Any 3 shares should reconstruct
        recovered = ShamirSecret.reconstruct(shares[:3])
        assert recovered == secret

    def test_different_share_subsets(self):
        secret = b"my_secret_data_1234567890123456"
        shares = ShamirSecret.split(secret, threshold=3, shares=5)
        # Test multiple subsets
        assert ShamirSecret.reconstruct(shares[0:3]) == secret
        assert ShamirSecret.reconstruct(shares[1:4]) == secret
        assert ShamirSecret.reconstruct(shares[2:5]) == secret
        # Non-contiguous
        assert ShamirSecret.reconstruct([shares[0], shares[2], shares[4]]) == secret

    def test_more_shares_than_threshold_works(self):
        secret = generate_master_key()
        shares = ShamirSecret.split(secret, threshold=2, shares=5)
        # All 5 shares should also work
        assert ShamirSecret.reconstruct(shares) == secret

    def test_threshold_2_minimum(self):
        secret = b"short"
        shares = ShamirSecret.split(secret, threshold=2, shares=3)
        assert ShamirSecret.reconstruct(shares[:2]) == secret

    def test_threshold_below_2_raises(self):
        with pytest.raises(ValueError, match="threshold must be ≥ 2"):
            ShamirSecret.split(b"x", threshold=1, shares=3)

    def test_shares_less_than_threshold_raises(self):
        with pytest.raises(ValueError, match="shares must be ≥ threshold"):
            ShamirSecret.split(b"x", threshold=5, shares=3)

    def test_shares_over_255_raises(self):
        with pytest.raises(ValueError, match="shares must be ≤ 255"):
            ShamirSecret.split(b"x", threshold=2, shares=256)

    def test_empty_secret_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            ShamirSecret.split(b"", threshold=2, shares=3)

    def test_reconstruct_too_few_shares_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            ShamirSecret.reconstruct([(1, b"x")])

    def test_single_byte_secret(self):
        secret = b"\x42"
        shares = ShamirSecret.split(secret, threshold=2, shares=3)
        assert ShamirSecret.reconstruct(shares[:2]) == secret


# ═══════════════════════════════════════════════════════════════════════════
# Password Generation
# ═══════════════════════════════════════════════════════════════════════════

class TestPasswordGeneration:
    """Test cryptographic password generation."""

    def test_default_length(self):
        pw = generate_password()
        assert len(pw) == 24

    def test_custom_length(self):
        pw = generate_password(length=32)
        assert len(pw) == 32

    def test_minimum_length_8(self):
        pw = generate_password(length=8)
        assert len(pw) == 8

    def test_below_minimum_raises(self):
        with pytest.raises(ValueError, match="at least 8"):
            generate_password(length=7)

    def test_contains_all_categories(self):
        # Generate many passwords and check category coverage
        pw = generate_password(length=100)
        assert any(c.islower() for c in pw), "No lowercase"
        assert any(c.isupper() for c in pw), "No uppercase"
        assert any(c.isdigit() for c in pw), "No digit"
        assert any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pw), "No special"

    def test_uniqueness(self):
        passwords = {generate_password() for _ in range(100)}
        assert len(passwords) == 100, "Password generation is not random enough"


# ═══════════════════════════════════════════════════════════════════════════
# UUIDv7
# ═══════════════════════════════════════════════════════════════════════════

class TestUUID7:
    """Test UUIDv7 generation (RFC 9562)."""

    UUID_PATTERN = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
    )

    def test_format(self):
        uid = uuid7()
        assert self.UUID_PATTERN.match(uid), f"Invalid UUIDv7 format: {uid}"

    def test_version_bits(self):
        uid = uuid7()
        # The 13th hex character should be '7' (version nibble)
        assert uid[14] == '7', f"Version nibble is not 7: {uid}"

    def test_variant_bits(self):
        uid = uuid7()
        # The 17th hex character should be 8, 9, a, or b (variant 10xx)
        assert uid[19] in '89ab', f"Variant bits incorrect: {uid}"

    def test_sortable_by_time(self):
        uid1 = uuid7()
        time.sleep(0.002)  # 2ms gap
        uid2 = uuid7()
        # Lexicographic ordering should reflect temporal ordering
        assert uid1 < uid2, f"UUIDs not time-sorted: {uid1} >= {uid2}"

    def test_uniqueness(self):
        uuids = {uuid7() for _ in range(1000)}
        assert len(uuids) == 1000, "UUID7 collision detected"

    def test_length(self):
        uid = uuid7()
        assert len(uid) == 36  # 8-4-4-4-12 with dashes


# ═══════════════════════════════════════════════════════════════════════════
# Master Key Generation
# ═══════════════════════════════════════════════════════════════════════════

class TestMasterKeyGeneration:
    """Test master key generation."""

    def test_key_length(self):
        key = generate_master_key()
        assert len(key) == 32

    def test_key_is_bytes(self):
        assert isinstance(generate_master_key(), bytes)

    def test_keys_are_unique(self):
        keys = {generate_master_key() for _ in range(100)}
        assert len(keys) == 100
