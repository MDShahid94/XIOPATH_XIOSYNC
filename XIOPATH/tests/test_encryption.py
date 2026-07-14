"""Tests for Fernet encryption at rest — SecretManager and ApiManager."""
import json
import os


class TestSecretManagerEncryption:
    """SecretManager encryption round-trips and auto-migration."""

    def test_set_and_get_round_trip(self, secret_mgr):
        """Write a secret and read it back correctly."""
        secret_mgr.set_secret("db_password", "super_secret_123")
        assert secret_mgr.get_secret("db_password") == "super_secret_123"

    def test_multiple_secrets(self, secret_mgr):
        """Multiple secrets should coexist without overwriting each other."""
        secret_mgr.set_secret("key_a", "value_a")
        secret_mgr.set_secret("key_b", "value_b")
        assert secret_mgr.get_secret("key_a") == "value_a"
        assert secret_mgr.get_secret("key_b") == "value_b"

    def test_list_keys_returns_names_only(self, secret_mgr):
        """list_keys should return key names without revealing values."""
        secret_mgr.set_secret("api_key", "hidden_value")
        secret_mgr.set_secret("token", "hidden_token")
        keys = secret_mgr.list_keys()
        assert "api_key" in keys
        assert "token" in keys
        assert "hidden_value" not in keys

    def test_nonexistent_key_returns_empty(self, secret_mgr):
        """Getting a non-existent key should return empty string."""
        assert secret_mgr.get_secret("no_such_key") == ""

    def test_file_is_encrypted_on_disk(self, secret_mgr):
        """The raw secrets file should NOT be readable JSON if encryption is active."""
        secret_mgr.set_secret("test", "encrypted_data")
        with open(secret_mgr.secrets_path, "rb") as f:
            raw = f.read()
        if secret_mgr._fernet:
            # Should not be parseable as JSON
            try:
                json.loads(raw.decode("utf-8"))
                assert False, "File is readable plaintext JSON — encryption failed"
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # Expected — file is encrypted
        else:
            # No encryption available, skip this assertion
            pass

    def test_auto_migration_from_plaintext(self, tmp_data_dir):
        """An existing plaintext secrets file should be auto-migrated to encrypted format."""
        secrets_path = tmp_data_dir / "migrate_secrets.json"
        key_path = tmp_data_dir / ".vault_key"

        # Write a plaintext file first
        with open(secrets_path, "w") as f:
            json.dump({"old_secret": "old_value"}, f)

        # Now create SecretManager pointing at this file — it should auto-migrate
        from core.secret_manager import SecretManager
        mgr = SecretManager(secrets_file=str(secrets_path), key_file=str(key_path))

        # Should still be able to read the old value
        assert mgr.get_secret("old_secret") == "old_value"

        # And the file should now be encrypted (if cryptography is available)
        if mgr._fernet:
            with open(secrets_path, "rb") as f:
                raw = f.read()
            try:
                json.loads(raw.decode("utf-8"))
                assert False, "File is still plaintext after migration"
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass  # Successfully migrated


class TestApiManagerEncryption:
    """ApiManager encryption and key rotation."""

    def test_add_and_retrieve_key(self, api_mgr):
        """Add an API key and retrieve it via get_next_key."""
        api_mgr.add_key("AIzaSyTest1234567890")
        key = api_mgr.get_next_key()
        assert key == "AIzaSyTest1234567890"

    def test_no_keys_raises_exception(self, api_mgr):
        """get_next_key with no keys should raise Exception."""
        import pytest
        with pytest.raises(Exception, match="No API keys configured"):
            api_mgr.get_next_key()

    def test_cooling_and_recovery(self, api_mgr):
        """A cooling key with expired cooldown should become active again."""
        api_mgr.add_key("test_key_cool")
        api_mgr.mark_cooling("test_key_cool", reason="rate limit")

        # Key is cooling — manually expire its cooldown
        for k in api_mgr.keys:
            if k["key"] == "test_key_cool":
                k["cooling_until"] = 0  # Expired
                break

        key = api_mgr.get_next_key()
        assert key == "test_key_cool"

    def test_status_report(self, api_mgr):
        """Status report should contain masked key info."""
        api_mgr.add_key("AIzaSyTestKey12345678")
        report = api_mgr.get_status_report()
        assert "AIzaSyTe" in report  # First 8 chars
        assert "5678" in report  # Last 4 chars
        assert "ACTIVE" in report
