"""
Credential manager for Resume Tailor.

Isolates all interaction with the OS credential store (keyring).
API keys are never written to disk or stored in config.toml.

The keyring library automatically selects the appropriate backend:
    - macOS Keychain
    - Windows Credential Manager
    - Linux Secret Service / Keyring
"""

from typing import Optional

import keyring
import keyring.errors

from .models import ProviderType

_SERVICE_NAME = "resume-tailor"


class CredentialManager:
    """
    Manages API key storage and retrieval via the OS credential store.

    All operations are scoped to the ``resume-tailor`` service name
    so they do not conflict with other applications.
    """

    def save(self, provider: ProviderType, api_key: str) -> None:
        """
        Store *api_key* for *provider* in the OS credential store.

        Parameters
        ----------
        provider : ProviderType
            The provider whose API key is being stored.
        api_key : str
            The API key to store.
        """
        keyring.set_password(_SERVICE_NAME, provider.value, api_key)

    def load(self, provider: ProviderType) -> Optional[str]:
        """
        Retrieve the API key for *provider* from the OS credential store.

        Parameters
        ----------
        provider : ProviderType
            The provider whose API key is being retrieved.

        Returns
        -------
        str | None
            The stored API key, or ``None`` if no key has been saved.
        """
        return keyring.get_password(_SERVICE_NAME, provider.value)

    def delete(self, provider: ProviderType) -> None:
        """
        Remove the API key for *provider* from the OS credential store.

        Does nothing if no key exists for the given provider.

        Parameters
        ----------
        provider : ProviderType
            The provider whose API key should be deleted.
        """
        try:
            keyring.delete_password(_SERVICE_NAME, provider.value)
        except keyring.errors.PasswordDeleteError:
            pass
