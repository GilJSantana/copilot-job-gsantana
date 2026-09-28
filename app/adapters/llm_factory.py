"""Fábrica de provedores de LLM: único ponto que conhece os adapters concretos."""

from collections.abc import Callable

from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.ollama_adapter import OllamaAdapter
from app.core.config import LLMProviderName, Settings
from app.domain.interfaces import ILLMProvider


def _build_gemini(settings: Settings) -> ILLMProvider:
    assert settings.gemini_api_key is not None  # garantido pela validação de Settings
    return GeminiAdapter(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


def _build_ollama(settings: Settings) -> ILLMProvider:
    return OllamaAdapter(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


# Novo provedor = novo adapter + uma entrada aqui (OCP)
_BUILDERS: dict[LLMProviderName, Callable[[Settings], ILLMProvider]] = {
    "gemini": _build_gemini,
    "ollama": _build_ollama,
}


def build_llm_provider(settings: Settings) -> ILLMProvider:
    return _BUILDERS[settings.llm_provider](settings)
