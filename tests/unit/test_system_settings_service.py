from dataclasses import replace

import pytest

from app.domain.models import JobSite, LLMProviderKind, LLMSettings, PromptName, ScraperSettings
from app.services import cv_optimizer, match_engine
from app.services.prompt_service import PromptService
from app.services.system_settings_service import SystemSettingsService
from tests.doubles import InMemoryPromptTemplateStore, InMemorySystemConfigStore

pytestmark = pytest.mark.unit

LLM_DEFAULTS = LLMSettings(
    provider=LLMProviderKind.OLLAMA,
    gemini_model="gemini-2.5-flash",
    ollama_base_url="http://localhost:11434",
    ollama_model="llama3.1",
)
SCRAPER_DEFAULTS = ScraperSettings(
    active_sites=tuple(JobSite), min_delay_seconds=2.0, max_delay_seconds=6.0, max_requests_per_hour=60
)


@pytest.fixture
def configs() -> InMemorySystemConfigStore:
    return InMemorySystemConfigStore()


@pytest.fixture
def service(configs) -> SystemSettingsService:
    return SystemSettingsService(configs, llm_defaults=LLM_DEFAULTS, scraper_defaults=SCRAPER_DEFAULTS)


async def test_env_values_apply_until_the_panel_saves(service):
    assert await service.llm() == LLM_DEFAULTS
    assert await service.scrapers() == SCRAPER_DEFAULTS


async def test_saved_llm_settings_round_trip(service, configs):
    gemini = LLMSettings(
        provider=LLMProviderKind.GEMINI,
        gemini_api_key="segredo",
        gemini_model="gemini-2.5-pro",
        ollama_base_url="http://ollama:11434",
        ollama_model="qwen2.5",
    )

    await service.save_llm(gemini)

    assert await service.llm() == gemini
    assert configs.values["llm.provider"] == "gemini"
    assert configs.descriptions["llm.gemini_api_key"] == "API key do Google Gemini"


async def test_saved_scraper_settings_round_trip(service):
    custom = ScraperSettings(
        active_sites=(JobSite.INDEED, JobSite.LINKEDIN),
        min_delay_seconds=0.5,
        max_delay_seconds=1.5,
        max_requests_per_hour=0,
        linkedin_fetch_description=False,
    )

    await service.save_scrapers(custom)

    assert await service.scrapers() == custom


async def test_partially_saved_keys_fall_back_to_env(service, configs):
    configs.values["llm.ollama_model"] = "mistral"

    assert await service.llm() == replace(LLM_DEFAULTS, ollama_model="mistral")


async def test_invalid_values_in_the_table_fall_back_to_env(service, configs):
    configs.values["llm.provider"] = "openai"
    configs.values["scrapers.max_requests_per_hour"] = "muitas"

    assert await service.llm() == LLM_DEFAULTS
    assert await service.scrapers() == SCRAPER_DEFAULTS


# --- Prompts ---------------------------------------------------------------------------


@pytest.fixture
def prompts() -> PromptService:
    return PromptService(InMemoryPromptTemplateStore())


async def test_prompts_default_to_the_code(prompts):
    views = {view.name: view for view in await prompts.list_all()}

    assert set(views) == set(PromptName)
    assert views[PromptName.MATCH_ENGINE].text == match_engine.SYSTEM_PROMPT
    assert views[PromptName.CV_TAILOR].text == cv_optimizer.SYSTEM_PROMPT
    assert not any(view.is_custom for view in views.values())


async def test_customizing_and_resetting_a_prompt(prompts):
    saved = await prompts.save(PromptName.MATCH_ENGINE, "Avalie com rigor.\r\nResponda em JSON.  ")

    assert (saved.text, saved.is_custom) == ("Avalie com rigor.\nResponda em JSON.", True)
    assert saved.updated_at is not None

    reset = await prompts.reset(PromptName.MATCH_ENGINE)
    assert (reset.text, reset.is_custom) == (match_engine.SYSTEM_PROMPT, False)


async def test_saving_the_default_text_removes_the_customization(prompts):
    await prompts.save(PromptName.CV_TAILOR, "outro")

    view = await prompts.save(PromptName.CV_TAILOR, cv_optimizer.SYSTEM_PROMPT + "\n")

    assert view.is_custom is False
