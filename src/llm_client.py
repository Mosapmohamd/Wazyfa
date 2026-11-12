"""Unified LLM client for multiple API providers.

This module provides a single interface to interact with various LLM providers
including NVIDIA, OpenAI, Anthropic, Google, Azure, and custom OpenAI-compatible APIs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from config import Settings

logger = logging.getLogger(__name__)


_TIMEOUT_SECONDS = 60.0


def _build_openai_compatible(api_key: str, base_url: str | None, label: str) -> Any:
    """Create an OpenAI-compatible client (NVIDIA/OpenAI/custom providers)."""

    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": api_key, "timeout": _TIMEOUT_SECONDS}
    if base_url:
        kwargs["base_url"] = base_url
    client = OpenAI(**kwargs)
    logger.info("Initialized %s client", label)
    return client


def _require_openai_package(label: str) -> None:
    logger.warning("openai package not installed; cannot use %s", label)


def _nvidia_client(settings: Settings) -> Any | None:
    if not settings.nvidia_api_key:
        logger.warning("NVIDIA API key not configured")
        return None
    try:
        return _build_openai_compatible(
            settings.nvidia_api_key, settings.nvidia_base_url, "NVIDIA NIM"
        )
    except ImportError:
        _require_openai_package("NVIDIA NIM")
        return None


def _openai_client(settings: Settings) -> Any | None:
    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured")
        return None
    try:
        return _build_openai_compatible(settings.openai_api_key, None, "OpenAI")
    except ImportError:
        _require_openai_package("OpenAI")
        return None


def _anthropic_client(settings: Settings) -> Any | None:
    if not settings.anthropic_api_key:
        logger.warning("Anthropic API key not configured")
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=_TIMEOUT_SECONDS,
        )
        logger.info("Initialized Anthropic client")
        return client
    except ImportError:
        logger.warning("anthropic package not installed; cannot use Anthropic")
        return None


def _google_client(settings: Settings) -> Any | None:
    if not settings.google_api_key:
        logger.warning("Google API key not configured")
        return None
    try:
        import google.generativeai as genai

        genai.configure(api_key=settings.google_api_key)
        logger.info("Initialized Google Gemini client")
        return genai
    except ImportError:
        logger.warning(
            "google-generativeai package not installed; cannot use Google Gemini"
        )
        return None


def _azure_client(settings: Settings) -> Any | None:
    if not settings.azure_api_key or not settings.azure_endpoint:
        logger.warning("Azure OpenAI credentials not configured")
        return None
    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=settings.azure_endpoint,
            api_key=settings.azure_api_key,
            api_version=settings.azure_api_version,
            timeout=_TIMEOUT_SECONDS,
        )
        logger.info("Initialized Azure OpenAI client")
        return client
    except ImportError:
        _require_openai_package("Azure OpenAI")
        return None


def _custom_client(settings: Settings) -> Any | None:
    if not settings.custom_base_url or not settings.custom_api_key:
        logger.warning("Custom API credentials not configured")
        return None
    try:
        return _build_openai_compatible(
            settings.custom_api_key, settings.custom_base_url, "custom OpenAI-compatible"
        )
    except ImportError:
        _require_openai_package("custom API")
        return None


# Provider builders: return a ready client, or None when credentials/package
# are missing. Model getters resolve the provider's model/deployment name.
_PROVIDER_BUILDERS: dict[str, Callable[[Settings], Any | None]] = {
    "nvidia": _nvidia_client,
    "openai": _openai_client,
    "anthropic": _anthropic_client,
    "google": _google_client,
    "azure": _azure_client,
    "custom": _custom_client,
}

_PROVIDER_MODELS: dict[str, Callable[[Settings], str]] = {
    "nvidia": lambda s: s.nvidia_fallback_model,
    "openai": lambda s: s.openai_model,
    "anthropic": lambda s: s.anthropic_model,
    "google": lambda s: s.google_model,
    "azure": lambda s: s.azure_deployment,
    "custom": lambda s: s.custom_model,
}


class LLMClient:
    """Unified client for multiple LLM API providers.
    
    Supports:
    - NVIDIA NIM
    - OpenAI
    - Anthropic
    - Google Gemini
    - Azure OpenAI
    - Custom OpenAI-compatible APIs
    """
    
    def __init__(self, settings: Settings):
        """Initialize the LLM client with application settings.
        
        Args:
            settings: Application settings containing API credentials and configurations.
        """
        self.settings = settings
        self._client: Any | None = None
        self._provider: str = settings.llm_provider.lower()
        
    def _get_client(self) -> Any | None:
        """Get or create the appropriate client for the configured provider.

        Returns:
            The client instance for the configured provider, or None if unavailable.
        """
        if self._client is not None:
            return self._client

        # Unknown providers fall back to the NVIDIA/OpenAI-compatible path.
        builder = _PROVIDER_BUILDERS.get(self._provider, _nvidia_client)

        try:
            client = builder(self.settings)
        except Exception as e:
            logger.warning("Failed to initialize LLM client for %s: %s", self._provider, e)
            return None

        if client is not None:
            self._client = client
        return client

    def _setup_nvidia(self) -> Any | None:
        """Set up NVIDIA NIM client."""
        if not self.settings.nvidia_api_key:
            logger.warning("NVIDIA API key not configured")
            return None
            
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=self.settings.nvidia_base_url,
                api_key=self.settings.nvidia_api_key,
                timeout=60.0,
            )
            self._client = client
            logger.info("Initialized NVIDIA NIM client")
            return client
        except ImportError:
            logger.warning("openai package not installed; cannot use NVIDIA NIM")
            return None
    
    def _setup_openai(self) -> Any | None:
        """Set up OpenAI client."""
        if not self.settings.openai_api_key:
            logger.warning("OpenAI API key not configured")
            return None
            
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.settings.openai_api_key,
                timeout=60.0,
            )
            self._client = client
            logger.info("Initialized OpenAI client")
            return client
        except ImportError:
            logger.warning("openai package not installed; cannot use OpenAI")
            return None
    
    def _setup_anthropic(self) -> Any | None:
        """Set up Anthropic client."""
        if not self.settings.anthropic_api_key:
            logger.warning("Anthropic API key not configured")
            return None
            
        try:
            import anthropic
            client = anthropic.Anthropic(
                api_key=self.settings.anthropic_api_key,
                timeout=60.0,
            )
            self._client = client
            logger.info("Initialized Anthropic client")
            return client
        except ImportError:
            logger.warning("anthropic package not installed; cannot use Anthropic")
            return None
    
    def _setup_google(self) -> Any | None:
        """Set up Google Gemini client."""
        if not self.settings.google_api_key:
            logger.warning("Google API key not configured")
            return None
            
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.settings.google_api_key)
            self._client = genai
            logger.info("Initialized Google Gemini client")
            return genai
        except ImportError:
            logger.warning("google-generativeai package not installed; cannot use Google Gemini")
            return None
    
    def _setup_azure(self) -> Any | None:
        """Set up Azure OpenAI client."""
        if not self.settings.azure_api_key or not self.settings.azure_endpoint:
            logger.warning("Azure OpenAI credentials not configured")
            return None
            
        try:
            from openai import AzureOpenAI
            client = AzureOpenAI(
                azure_endpoint=self.settings.azure_endpoint,
                api_key=self.settings.azure_api_key,
                api_version=self.settings.azure_api_version,
                timeout=60.0,
            )
            self._client = client
            logger.info("Initialized Azure OpenAI client")
            return client
        except ImportError:
            logger.warning("openai package not installed; cannot use Azure OpenAI")
            return None
    
    def _setup_custom(self) -> Any | None:
        """Set up custom OpenAI-compatible API client."""
        if not self.settings.custom_base_url or not self.settings.custom_api_key:
            logger.warning("Custom API credentials not configured")
            return None
            
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=self.settings.custom_base_url,
                api_key=self.settings.custom_api_key,
                timeout=60.0,
            )
            self._client = client
            logger.info("Initialized custom OpenAI-compatible client")
            return client
        except ImportError:
            logger.warning("openai package not installed; cannot use custom API")
            return None
    
    def get_model_name(self) -> str:
        """Get the model name for the configured provider.

        Returns:
            The model name string.
        """
        getter = _PROVIDER_MODELS.get(self._provider, _PROVIDER_MODELS["nvidia"])
        return getter(self.settings)

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2560,
    ) -> str | None:
        """Generate a chat completion using the configured provider.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens to generate.
            
        Returns:
            The generated text response, or None if generation failed.
        """
        client = self._get_client()
        if client is None:
            return None
            
        model = self.get_model_name()
        
        try:
            if self._provider == "anthropic":
                # Anthropic uses different API format
                system_message = ""
                user_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                    else:
                        user_messages.append(msg)
                
                response = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system_message,
                    messages=user_messages,
                )
                return response.content[0].text
                
            elif self._provider == "google":
                # Google Gemini uses different API format
                import google.generativeai as genai
                gemini_model = genai.GenerativeModel(model)
                
                # Convert messages to Gemini format
                prompt = ""
                for msg in messages:
                    if msg["role"] == "system":
                        prompt += f"System: {msg['content']}\n"
                    elif msg["role"] == "user":
                        prompt += f"User: {msg['content']}\n"
                    elif msg["role"] == "assistant":
                        prompt += f"Assistant: {msg['content']}\n"
                
                response = gemini_model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                return response.text
                
            else:
                # OpenAI-compatible APIs (NVIDIA, OpenAI, Azure, Custom)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return response.choices[0].message.content or None
                
        except Exception as e:
            logger.exception("%s chat completion failed", self._provider)
            return None
    
    def is_available(self) -> bool:
        """Check if the configured provider is available.
        
        Returns:
            True if the client can be initialized, False otherwise.
        """
        return self._get_client() is not None


# Global instance for backward compatibility
_llm_client: LLMClient | None = None


def get_llm_client(settings: Settings) -> LLMClient:
    """Get or create the global LLM client instance.
    
    Args:
        settings: Application settings.
        
    Returns:
        The global LLM client instance.
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(settings)
    return _llm_client


def reset_llm_client() -> None:
    """Reset the global LLM client instance.
    
    Useful for testing or reconfiguration.
    """
    global _llm_client
    _llm_client = None
