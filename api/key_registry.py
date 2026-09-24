from typing import Dict, List, Optional

from .models import APIKey


class APIKeyRegistry:
    """
    Central registry for all API keys available to the application.

    The registry is intentionally provider-agnostic. It stores keys
    from Groq, Gemini, or any future provider in one expandable pool.
    """

    def __init__(self):
        self._keys: Dict[str, APIKey] = {}

    # ------------------------------------------------------------
    # ADD / REMOVE
    # ------------------------------------------------------------

    def add_key(self, api_key: APIKey) -> None:
        """
        Add an API key to the registry.

        Raises:
            ValueError: if a key with the same ID already exists.
        """

        if api_key.id in self._keys:
            raise ValueError(
                f"API key with ID '{api_key.id}' already exists."
            )

        self._keys[api_key.id] = api_key

    def remove_key(self, key_id: str) -> APIKey:
        """
        Remove and return an API key from the registry.

        Raises:
            KeyError: if the key does not exist.
        """

        if key_id not in self._keys:
            raise KeyError(
                f"API key with ID '{key_id}' does not exist."
            )

        return self._keys.pop(key_id)

    # ------------------------------------------------------------
    # LOOKUP
    # ------------------------------------------------------------

    def get_key(self, key_id: str) -> APIKey:
        """
        Return a specific API key.

        Raises:
            KeyError: if the key does not exist.
        """

        if key_id not in self._keys:
            raise KeyError(
                f"API key with ID '{key_id}' does not exist."
            )

        return self._keys[key_id]

    def get_all_keys(self) -> List[APIKey]:
        """
        Return all registered API keys.
        """

        return list(self._keys.values())

    # ------------------------------------------------------------
    # FILTERING
    # ------------------------------------------------------------

    def get_enabled_keys(self) -> List[APIKey]:
        """
        Return all keys currently enabled.
        """

        return [
            api_key
            for api_key in self._keys.values()
            if api_key.enabled
        ]

    def get_keys_by_provider(
        self,
        provider: str,
    ) -> List[APIKey]:
        """
        Return all enabled keys belonging to a provider.
        """

        return [
            api_key
            for api_key in self._keys.values()
            if api_key.enabled
            and api_key.provider == provider
        ]

    def get_keys_by_model(
        self,
        model: str,
    ) -> List[APIKey]:
        """
        Return all enabled keys supporting a specific model.
        """

        return [
            api_key
            for api_key in self._keys.values()
            if api_key.enabled
            and api_key.model == model
        ]

    # ------------------------------------------------------------
    # ENABLE / DISABLE
    # ------------------------------------------------------------

    def enable_key(self, key_id: str) -> None:
        """
        Enable a key so the scheduler can use it.
        """

        self.get_key(key_id).enabled = True

    def disable_key(self, key_id: str) -> None:
        """
        Disable a key so the scheduler will not use it.
        """

        self.get_key(key_id).enabled = False

    # ------------------------------------------------------------
    # REGISTRY INFORMATION
    # ------------------------------------------------------------

    def __len__(self) -> int:
        """
        Return the total number of registered keys.
        """

        return len(self._keys)

    def __contains__(self, key_id: str) -> bool:
        """
        Allow:

            if "groq_001" in registry:
        """

        return key_id in self._keys