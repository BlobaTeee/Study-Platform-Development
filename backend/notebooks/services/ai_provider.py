"""
Abstract AI provider interface for content generation.
Supports switching between Gemini and custom trained models.
"""

from abc import ABC, abstractmethod
from typing import Protocol


class AIProvider(ABC):
    """Abstract base class for AI content generation."""

    @abstractmethod
    def generate_json(self, prompt: str) -> dict:
        """Generate structured JSON from a prompt."""
        pass

    @abstractmethod
    def summarize(self, text: str, title: str = '') -> str:
        """Generate a summary of the given text."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'gemini', 'custom_model')."""
        pass


class GeminiProvider(AIProvider):
    """Google Gemini API provider."""

    def __init__(self):
        from .gemini_client import generate_json
        self._generate_json_fn = generate_json

    def generate_json(self, prompt: str) -> dict:
        return self._generate_json_fn(prompt)

    def summarize(self, text: str, title: str = '') -> str:
        from .gemini import summarize_with_gemini
        return summarize_with_gemini(text, title)

    @property
    def name(self) -> str:
        return 'gemini'


class CustomModelProvider(AIProvider):
    """Custom trained model provider (implement your own model here)."""

    def generate_json(self, prompt: str) -> dict:
        """
        Call your custom trained model for JSON generation.
        Example: Send to local inference server or cloud endpoint.
        """
        # TODO: Replace with your model endpoint
        raise NotImplementedError(
            'CustomModelProvider.generate_json() not implemented. '
            'Configure your model endpoint in settings.CUSTOM_MODEL_ENDPOINT'
        )

    def summarize(self, text: str, title: str = '') -> str:
        """
        Call your custom model for summarization.
        """
        # TODO: Replace with your model endpoint
        raise NotImplementedError(
            'CustomModelProvider.summarize() not implemented. '
            'Configure your model endpoint in settings.CUSTOM_MODEL_ENDPOINT'
        )

    @property
    def name(self) -> str:
        return 'custom_model'


def get_ai_provider() -> AIProvider:
    """
    Factory function to get the configured AI provider.
    
    Set AI_PROVIDER in settings:
    - 'gemini': Use Google Gemini API (default)
    - 'custom': Use your trained model
    
    Example .env:
        AI_PROVIDER=gemini
    
    When switching to custom model:
        AI_PROVIDER=custom
        CUSTOM_MODEL_ENDPOINT=http://localhost:5000
    """
    from django.conf import settings

    provider_name = getattr(settings, 'AI_PROVIDER', 'gemini').lower()

    if provider_name == 'custom':
        return CustomModelProvider()
    elif provider_name == 'gemini':
        return GeminiProvider()
    else:
        raise ValueError(f'Unknown AI provider: {provider_name}')
