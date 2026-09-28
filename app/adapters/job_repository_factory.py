"""Fábrica da fonte de vagas: único ponto que conhece o adapter concreto."""

from app.adapters.jobspy_adapter import JobSpyAdapter
from app.adapters.rate_limit import RandomDelayThrottle
from app.core.config import Settings
from app.domain.interfaces import IJobRepository


def build_job_repository(settings: Settings) -> IJobRepository:
    return JobSpyAdapter(
        throttle=RandomDelayThrottle(
            settings.jobspy_min_delay_seconds,
            settings.jobspy_max_delay_seconds,
        ),
        linkedin_fetch_description=settings.jobspy_linkedin_fetch_description,
    )
