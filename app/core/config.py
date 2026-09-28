"""Configuração da aplicação, lida de variáveis de ambiente e do arquivo `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "copilot-job-gil"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: str = "sqlite+aiosqlite:///./copilot_job.db"
    profile_path: Path = Path("profile_data/profile.json")

    # --- LLM ---
    llm_provider: LLMProviderName = "ollama"
    llm_timeout_seconds: float = Field(default=120.0, gt=0)

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # --- Ingestão de vagas (JobSpy) ---
    jobspy_min_delay_seconds: float = Field(default=2.0, ge=0)
    jobspy_max_delay_seconds: float = Field(default=6.0, ge=0)
    jobspy_linkedin_fetch_description: bool = True

    @model_validator(mode="after")
    def _require_credentials_for_selected_provider(self) -> Self:
        if self.llm_provider == "gemini" and not (
            self.gemini_api_key and self.gemini_api_key.get_secret_value()
        ):
            raise ValueError("GEMINI_API_KEY é obrigatória quando LLM_PROVIDER=gemini")
        return self

    @model_validator(mode="after")
    def _validate_delay_range(self) -> Self:
        if self.jobspy_min_delay_seconds > self.jobspy_max_delay_seconds:
            raise ValueError("JOBSPY_MIN_DELAY_SECONDS não pode ser maior que JOBSPY_MAX_DELAY_SECONDS")
        return self


@lru_cache
def get_settings() -> Settings:
    """Instância única de `Settings` (use `get_settings.cache_clear()` nos testes)."""
    return Settings()
