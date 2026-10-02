"""Configurações de LLM e de conectores, gravadas no banco (tabela system_configs).

O `.env` fornece os valores iniciais: uma chave que nunca foi salva pelo painel
continua valendo o que está nas variáveis de ambiente.
"""

import logging
from collections.abc import Callable

from app.domain.interfaces import ISystemConfigStore
from app.domain.models import JobSite, LLMProviderKind, LLMSettings, ScraperSettings

logger = logging.getLogger(__name__)

_LLM_DESCRIPTIONS = {
    "llm.provider": "Provedor de LLM padrão (gemini | ollama)",
    "llm.gemini_api_key": "API key do Google Gemini",
    "llm.gemini_model": "Modelo do Gemini",
    "llm.ollama_base_url": "URL do servidor Ollama",
    "llm.ollama_model": "Modelo do Ollama",
}
_SCRAPER_DESCRIPTIONS = {
    "scrapers.active_sites": "Plataformas de vagas ativas (separadas por vírgula)",
    "scrapers.min_delay_seconds": "Pausa mínima entre requisições (s)",
    "scrapers.max_delay_seconds": "Pausa máxima entre requisições (s)",
    "scrapers.max_requests_per_hour": "Limite de requisições por hora (0 = sem limite)",
    "scrapers.linkedin_fetch_description": "Busca a descrição completa no LinkedIn",
}


def _llm_to_values(settings: LLMSettings) -> dict[str, str]:
    return {
        "llm.provider": settings.provider.value,
        "llm.gemini_api_key": settings.gemini_api_key or "",
        "llm.gemini_model": settings.gemini_model,
        "llm.ollama_base_url": settings.ollama_base_url,
        "llm.ollama_model": settings.ollama_model,
    }


def _llm_from_values(values: dict[str, str]) -> LLMSettings:
    return LLMSettings(
        provider=LLMProviderKind(values["llm.provider"]),
        gemini_api_key=values["llm.gemini_api_key"] or None,
        gemini_model=values["llm.gemini_model"],
        ollama_base_url=values["llm.ollama_base_url"],
        ollama_model=values["llm.ollama_model"],
    )


def _scrapers_to_values(settings: ScraperSettings) -> dict[str, str]:
    return {
        "scrapers.active_sites": ",".join(site.value for site in settings.active_sites),
        "scrapers.min_delay_seconds": repr(settings.min_delay_seconds),
        "scrapers.max_delay_seconds": repr(settings.max_delay_seconds),
        "scrapers.max_requests_per_hour": str(settings.max_requests_per_hour),
        "scrapers.linkedin_fetch_description": "true" if settings.linkedin_fetch_description else "false",
    }


def _scrapers_from_values(values: dict[str, str]) -> ScraperSettings:
    return ScraperSettings(
        active_sites=tuple(JobSite(site) for site in values["scrapers.active_sites"].split(",") if site),
        min_delay_seconds=float(values["scrapers.min_delay_seconds"]),
        max_delay_seconds=float(values["scrapers.max_delay_seconds"]),
        max_requests_per_hour=int(values["scrapers.max_requests_per_hour"]),
        linkedin_fetch_description=values["scrapers.linkedin_fetch_description"] == "true",
    )


class SystemSettingsService:
    def __init__(
        self,
        configs: ISystemConfigStore,
        *,
        llm_defaults: LLMSettings,
        scraper_defaults: ScraperSettings,
    ) -> None:
        self._configs = configs
        self._llm_defaults = llm_defaults
        self._scraper_defaults = scraper_defaults

    async def llm(self) -> LLMSettings:
        return await self._load("llm.", _llm_to_values(self._llm_defaults), _llm_from_values, self._llm_defaults)

    async def save_llm(self, settings: LLMSettings) -> None:
        await self._configs.set_many(_llm_to_values(settings), _LLM_DESCRIPTIONS)

    async def scrapers(self) -> ScraperSettings:
        return await self._load(
            "scrapers.",
            _scrapers_to_values(self._scraper_defaults),
            _scrapers_from_values,
            self._scraper_defaults,
        )

    async def save_scrapers(self, settings: ScraperSettings) -> None:
        await self._configs.set_many(_scrapers_to_values(settings), _SCRAPER_DESCRIPTIONS)

    async def _load[T](
        self,
        prefix: str,
        defaults: dict[str, str],
        parse: Callable[[dict[str, str]], T],
        fallback: T,
    ) -> T:
        stored = await self._configs.get_many(prefix)
        try:
            return parse(defaults | stored)
        except (ValueError, KeyError) as exc:
            # só acontece se alguém editar a tabela à mão: o sistema segue com o .env
            logger.warning("Configuração '%s*' inválida no banco (%s); usando o .env", prefix, exc)
            return fallback
