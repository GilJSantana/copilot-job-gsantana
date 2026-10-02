import pytest

from app.adapters.configurable_llm import ConfigurableLLMProvider
from app.core.config import Settings
from app.domain.models import LLMProviderKind, LLMSettings
from app.web.container import Overrides, build_container
from tests.doubles import MockLLMAdapter

pytestmark = pytest.mark.unit


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, database_url="sqlite+aiosqlite:///:memory:", **overrides)


async def test_cv_tailor_uses_its_own_llm_with_a_longer_timeout():
    async with build_container(settings(llm_timeout_seconds=90, cv_llm_timeout_seconds=700)) as container:
        cv_llm = container.cv_tailor_service._optimizer._llm

        assert isinstance(container.llm, ConfigurableLLMProvider)
        assert cv_llm is not container.llm
        assert cv_llm.name == container.llm.name  # mesmo provedor e modelo
        assert container.llm.timeout_seconds == 90.0
        assert cv_llm.timeout_seconds == 700.0


async def test_the_llm_follows_the_provider_saved_in_the_panel():
    async with build_container(settings(llm_provider="ollama", ollama_model="llama3.1")) as container:
        current = await container.system_settings.llm()
        assert await container.llm.current_name() == "ollama:llama3.1"

        await container.system_settings.save_llm(
            LLMSettings(
                provider=LLMProviderKind.GEMINI,
                gemini_api_key="segredo",
                gemini_model="gemini-2.5-flash",
                ollama_base_url=current.ollama_base_url,
                ollama_model=current.ollama_model,
            )
        )

        assert await container.llm.current_name() == "gemini:gemini-2.5-flash"


async def test_an_injected_llm_is_shared():
    llm = MockLLMAdapter()

    async with build_container(settings(), Overrides(llm=llm)) as container:
        assert container.cv_tailor_service._optimizer._llm is llm
