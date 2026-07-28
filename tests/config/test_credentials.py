"""
Unit tests for CredentialManager.

All tests mock the keyring library to avoid touching the real OS credential store.

Covers:
    - save stores the key via keyring
    - load retrieves the key via keyring
    - delete removes the key via keyring
    - load returns None when no credential exists
    - delete is silent when no credential exists
"""

from unittest.mock import MagicMock, patch

import keyring.errors
import pytest

from src.config.credentials import CredentialManager, _SERVICE_NAME
from src.config.models import ProviderType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cred_manager():
    return CredentialManager()


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------


class TestSave:
    def test_save_calls_keyring_set_password(self, cred_manager):
        with patch("src.config.credentials.keyring.set_password") as mock_set:
            cred_manager.save(ProviderType.OPENAI, "sk-test-key")
            mock_set.assert_called_once_with(
                _SERVICE_NAME, ProviderType.OPENAI.value, "sk-test-key"
            )

    def test_save_uses_provider_value_as_username(self, cred_manager):
        with patch("src.config.credentials.keyring.set_password") as mock_set:
            cred_manager.save(ProviderType.ANTHROPIC, "ant-key")
            _, username, _ = mock_set.call_args.args
            assert username == "anthropic"

    def test_save_all_providers(self, cred_manager):
        with patch("src.config.credentials.keyring.set_password") as mock_set:
            for provider in ProviderType:
                cred_manager.save(provider, "some-key")
            assert mock_set.call_count == len(ProviderType)


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_returns_stored_key(self, cred_manager):
        with patch(
            "src.config.credentials.keyring.get_password", return_value="sk-test-key"
        ) as mock_get:
            result = cred_manager.load(ProviderType.OPENAI)
            assert result == "sk-test-key"
            mock_get.assert_called_once_with(_SERVICE_NAME, ProviderType.OPENAI.value)

    def test_load_returns_none_when_missing(self, cred_manager):
        with patch(
            "src.config.credentials.keyring.get_password", return_value=None
        ):
            result = cred_manager.load(ProviderType.GEMINI)
            assert result is None

    def test_load_uses_provider_value_as_username(self, cred_manager):
        with patch(
            "src.config.credentials.keyring.get_password", return_value="key"
        ) as mock_get:
            cred_manager.load(ProviderType.ANTHROPIC)
            _, username = mock_get.call_args.args
            assert username == "anthropic"


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_calls_keyring_delete_password(self, cred_manager):
        with patch("src.config.credentials.keyring.delete_password") as mock_del:
            cred_manager.delete(ProviderType.OPENAI)
            mock_del.assert_called_once_with(_SERVICE_NAME, ProviderType.OPENAI.value)

    def test_delete_is_silent_when_credential_missing(self, cred_manager):
        with patch(
            "src.config.credentials.keyring.delete_password",
            side_effect=keyring.errors.PasswordDeleteError("not found"),
        ):
            # Should not raise
            cred_manager.delete(ProviderType.OPENAI)

    def test_delete_uses_provider_value_as_username(self, cred_manager):
        with patch("src.config.credentials.keyring.delete_password") as mock_del:
            cred_manager.delete(ProviderType.GEMINI)
            _, username = mock_del.call_args.args
            assert username == "gemini"
