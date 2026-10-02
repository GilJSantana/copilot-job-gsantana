"""Fábrica da fonte de vagas: único ponto que conhece o adapter concreto."""

from app.adapters.jobspy_adapter import JobSpyAdapter
from app.adapters.rate_limit import RandomDelayThrottle
from app.core.config import Settings
from app.domain.interfaces import IJobRepository
from app.domain.models import JobSite, ScraperSettings


def scraper_settings_from_env(settings: Settings) -> ScraperSettings:
    """Valores do `.env`: os padrões enquanto o painel não salvar outros."""
    return ScraperSettings(
        active_sites=tuple(JobSite),
        min_delay_seconds=settings.jobspy_min_delay_seconds,
        max_delay_seconds=settings.jobspy_max_delay_seconds,
        max_requests_per_hour=settings.jobspy_max_requests_per_hour,
        linkedin_fetch_description=settings.jobspy_linkedin_fetch_description,
    )


def build_jobspy_repository(settings: ScraperSettings) -> IJobRepository:
    return JobSpyAdapter(
        throttle=RandomDelayThrottle(settings.min_delay_seconds, settings.max_delay_seconds),
        linkedin_fetch_description=settings.linkedin_fetch_description,
    )
