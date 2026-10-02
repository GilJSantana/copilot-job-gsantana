import math
from dataclasses import replace

import pytest

from app.adapters.configurable_job_repository import ConfigurableJobRepository
from app.adapters.configurable_llm import ConfigurableLLMProvider
from app.adapters.rate_limit import HourlyRequestBudget
from app.domain.exceptions import RateLimitExceededError, SourcesDisabledError
from app.domain.models import (
    CandidateProfile,
    JobSearchCriteria,
    JobSite,
    LLMProviderKind,
    LLMSettings,
    PromptName,
    PromptTemplate,
    ScraperSettings,
)
from app.services import match_engine
from app.services.cv_optimizer import LLMCVOptimizer
from app.services.match_engine import MatchEngine
from tests.cv_builders import HISTORY, JOB, llm_cv
from tests.doubles import FakeJobRepository, InMemoryPromptTemplateStore, MockLLMAdapter

pytestmark = pytest.mark.unit


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


# --- HourlyRequestBudget ---------------------------------------------------------------


def test_budget_accepts_requests_until_the_limit():
    clock = FakeClock()
    budget = HourlyRequestBudget(clock=clock)

    assert budget.try_acquire(2, limit=3) is None
    clock.now = 600
    assert budget.try_acquire(1, limit=3) is None
    # a janela só libera espaço quando a primeira requisição faz 1 hora
    assert budget.try_acquire(1, limit=3) == pytest.approx(3000)


def test_budget_frees_requests_older_than_one_hour():
    clock = FakeClock()
    budget = HourlyRequestBudget(clock=clock)
    budget.try_acquire(3, limit=3)

    clock.now = 3600

    assert budget.try_acquire(3, limit=3) is None


def test_budget_without_limit_still_counts_requests():
    clock = FakeClock()
    budget = HourlyRequestBudget(clock=clock)
    budget.try_acquire(5, limit=0)

    assert budget.try_acquire(1, limit=5) == pytest.approx(3600)


def test_a_search_larger_than_the_limit_never_fits():
    assert math.isinf(HourlyRequestBudget().try_acquire(4, limit=3))


# --- ConfigurableJobRepository ---------------------------------------------------------


def scrapers(**overrides) -> ScraperSettings:
    values = {
        "active_sites": (JobSite.LINKEDIN, JobSite.INDEED),
        "min_delay_seconds": 0.0,
        "max_delay_seconds": 0.0,
        "max_requests_per_hour": 0,
    }
    return ScraperSettings(**values | overrides)


class Settings:
    """Fonte de configurações mutável, como o banco editado pelo painel."""

    def __init__(self, value) -> None:
        self.value = value

    async def __call__(self):
        return self.value


CRITERIA = JobSearchCriteria(search_term="python", sites=(JobSite.LINKEDIN, JobSite.GLASSDOOR))


async def test_only_active_platforms_are_queried():
    inner = FakeJobRepository()
    repository = ConfigurableJobRepository(Settings(scrapers()), lambda _: inner)

    await repository.search(CRITERIA)

    assert inner.calls[0].sites == (JobSite.LINKEDIN,)


async def test_asking_only_for_inactive_platforms_is_an_error():
    repository = ConfigurableJobRepository(Settings(scrapers()), lambda _: FakeJobRepository())

    with pytest.raises(SourcesDisabledError, match="/settings/scrapers"):
        await repository.search(replace(CRITERIA, sites=(JobSite.GOOGLE,)))


async def test_the_hourly_limit_blocks_searches_before_calling_the_source():
    inner = FakeJobRepository()
    source = Settings(scrapers(max_requests_per_hour=1))
    repository = ConfigurableJobRepository(source, lambda _: inner)

    await repository.search(CRITERIA)
    with pytest.raises(RateLimitExceededError, match="Limite de 1 requisições por hora"):
        await repository.search(CRITERIA)
    assert len(inner.calls) == 1

    source.value = scrapers(max_requests_per_hour=2)  # o painel aumentou o limite
    await repository.search(CRITERIA)
    assert len(inner.calls) == 2


async def test_the_source_is_rebuilt_only_when_the_settings_change():
    built: list[ScraperSettings] = []
    source = Settings(scrapers())

    def build(settings: ScraperSettings) -> FakeJobRepository:
        built.append(settings)
        return FakeJobRepository()

    repository = ConfigurableJobRepository(source, build)
    await repository.search(CRITERIA)
    await repository.search(CRITERIA)
    source.value = scrapers(min_delay_seconds=1.0, max_delay_seconds=2.0)
    await repository.search(CRITERIA)

    assert [s.max_delay_seconds for s in built] == [0.0, 2.0]


# --- ConfigurableLLMProvider -----------------------------------------------------------

OLLAMA = LLMSettings(
    provider=LLMProviderKind.OLLAMA,
    gemini_model="gemini-2.5-flash",
    ollama_base_url="http://localhost:11434",
    ollama_model="llama3.1",
)


class ClosableMock(MockLLMAdapter):
    def __init__(self, label: str) -> None:
        super().__init__({"label": label})
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


async def test_the_llm_switches_provider_on_the_next_call():
    source = Settings(OLLAMA)
    built: list[ClosableMock] = []

    def build(settings: LLMSettings, timeout: float) -> ClosableMock:
        built.append(ClosableMock(f"{settings.provider}:{timeout}"))
        return built[-1]

    llm = ConfigurableLLMProvider(source, initial=OLLAMA, timeout_seconds=30, build=build)
    assert llm.name == "ollama:llama3.1"

    assert await llm.generate_json("a") == {"label": "ollama:30"}
    assert await llm.generate_json("b") == {"label": "ollama:30"}
    source.value = replace(OLLAMA, provider=LLMProviderKind.GEMINI, gemini_api_key="segredo")
    assert await llm.current_name() == "gemini:gemini-2.5-flash"
    assert await llm.generate_json("c") == {"label": "gemini:30"}

    assert llm.name == "gemini:gemini-2.5-flash"
    assert len(built) == 2
    # o adapter antigo só é fechado no fim: pode haver chamada em andamento nele
    assert not built[0].closed
    await llm.aclose()
    assert all(adapter.closed for adapter in built)


# --- Prompts customizados nos services -------------------------------------------------


async def test_match_engine_uses_the_custom_prompt_only_while_active():
    profile = CandidateProfile(
        full_name="Gil", headline="Dev", skills=("Python",), achievements=("Migração de 20TB no S3",)
    )
    prompts = InMemoryPromptTemplateStore()
    llm = MockLLMAdapter({"score": 50, "rationale": "", "strengths": [], "gaps": []})
    engine = MatchEngine(llm, prompts=prompts)

    await engine.evaluate(profile, JOB)
    await prompts.save(PromptTemplate(name=PromptName.MATCH_ENGINE, template_text="Seja rigoroso."))
    await engine.evaluate(profile, JOB)
    await prompts.save(PromptTemplate(name=PromptName.MATCH_ENGINE, template_text="Seja rigoroso.", is_active=False))
    await engine.evaluate(profile, JOB)

    assert "Conquista: Migração de 20TB no S3" in llm.calls[0]["prompt"]

    assert [call["system_prompt"] for call in llm.calls] == [
        match_engine.SYSTEM_PROMPT,
        "Seja rigoroso.",
        match_engine.SYSTEM_PROMPT,
    ]


async def test_cv_optimizer_uses_the_custom_prompt_and_lists_achievements():
    prompts = InMemoryPromptTemplateStore()
    await prompts.save(PromptTemplate(name=PromptName.CV_TAILOR, template_text="Prompt do CV."))
    llm = MockLLMAdapter(llm_cv())
    history = replace(HISTORY, achievements=("Migração de 20TB no S3",))

    await LLMCVOptimizer(llm, prompts=prompts).optimize_cv(JOB, history, language=history.language)

    assert llm.calls[0]["system_prompt"] == "Prompt do CV."
    assert "- Migração de 20TB no S3" in llm.calls[0]["prompt"]
