"""Fábrica de provedores de LLM: único ponto que conhece os adapters concretos."""

from collections.abc import Callable

from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.ollama_adapter import OllamaAdapter
from app.core.config import Settings
from app.domain.interfaces import ILLMProvider
from app.domain.models import LLMProviderKind, LLMSettings


def _build_gemini(settings: LLMSettings, timeout_seconds: float) -> ILLMProvider:
    assert settings.gemini_api_key is not None  # garantido pela validação de LLMSettings
    return GeminiAdapter(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=timeout_seconds,
    )


def _build_ollama(settings: LLMSettings, timeout_seconds: float) -> ILLMProvider:
    return OllamaAdapter(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout_seconds=timeout_seconds,
    )


# Novo provedor = novo adapter + uma entrada aqui (OCP)
_BUILDERS: dict[LLMProviderKind, Callable[[LLMSettings, float], ILLMProvider]] = {
    LLMProviderKind.GEMINI: _build_gemini,
    LLMProviderKind.OLLAMA: _build_ollama,
}


def llm_settings_from_env(settings: Settings) -> LLMSettings:
    """Valores do `.env`: os padrões enquanto o painel não salvar outros."""
    return LLMSettings(
        provider=LLMProviderKind(settings.llm_provider),
        gemini_api_key=settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else None,
        gemini_model=settings.gemini_model,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
    )


def build_llm_adapter(settings: LLMSettings, timeout_seconds: float) -> ILLMProvider:
    return _BUILDERS[settings.provider](settings, timeout_seconds)


def build_llm_provider(settings: Settings, *, timeout_seconds: float | None = None) -> ILLMProvider:
    """Adapter fixo a partir do `.env`. `timeout_seconds` sobrescreve
    LLM_TIMEOUT_SECONDS (ex.: o CV Tailor gera respostas bem maiores que a análise de match)."""
    timeout = timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
    return build_llm_adapter(llm_settings_from_env(settings), timeout)
