import pytest
from pydantic import ValidationError

from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.llm_factory import build_llm_provider
from app.adapters.ollama_adapter import OllamaAdapter
from app.core.config import Settings

pytestmark = pytest.mark.unit

_ENV_VARS = (
    "LLM_PROVIDER",
    "LLM_TIMEOUT_SECONDS",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "JOBSPY_MIN_DELAY_SECONDS",
    "JOBSPY_MAX_DELAY_SECONDS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Isola os testes das variáveis de ambiente da máquina."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def load_settings() -> Settings:
    return Settings(_env_file=None)  # ignora o .env local


def test_defaults_to_local_ollama_without_credentials():
    settings = load_settings()

    assert settings.llm_provider == "ollama"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.gemini_api_key is None


def test_reads_values_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "segredo")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")

    settings = load_settings()

    assert settings.llm_provider == "gemini"
    assert settings.gemini_api_key.get_secret_value() == "segredo"
    assert settings.gemini_model == "gemini-2.5-pro"
    assert settings.llm_timeout_seconds == 30.0


def test_api_key_is_not_leaked_in_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "segredo")

    assert "segredo" not in repr(load_settings())


@pytest.mark.parametrize("api_key", [None, ""])
def test_gemini_provider_requires_api_key(monkeypatch, api_key):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    if api_key is not None:
        monkeypatch.setenv("GEMINI_API_KEY", api_key)

    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        load_settings()


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("LLM_PROVIDER", "openai"),
        ("LLM_TIMEOUT_SECONDS", "0"),
        ("JOBSPY_MIN_DELAY_SECONDS", "-1"),
        ("JOBSPY_MIN_DELAY_SECONDS", "10"),  # > max padrão (6)
    ],
)
def test_rejects_invalid_values(monkeypatch, var, value):
    monkeypatch.setenv(var, value)

    with pytest.raises(ValidationError):
        load_settings()


def test_factory_builds_ollama_adapter(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:7b")

    provider = build_llm_provider(load_settings())

    assert isinstance(provider, OllamaAdapter)
    assert provider.name == "ollama:qwen2.5:7b"


def test_factory_builds_gemini_adapter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "segredo")

    provider = build_llm_provider(load_settings())

    assert isinstance(provider, GeminiAdapter)
    assert provider.name == "gemini:gemini-2.5-flash"
