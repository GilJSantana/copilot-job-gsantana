"""Fonte de vagas que segue a configuração do painel (plataformas ativas, ritmo e limite)."""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import replace

from app.adapters.rate_limit import HourlyRequestBudget
from app.domain.exceptions import RateLimitExceededError, SourcesDisabledError
from app.domain.interfaces import IJobRepository
from app.domain.models import JobPosting, JobSearchCriteria, ScraperSettings

ScraperSettingsSource = Callable[[], Awaitable[ScraperSettings]]
RepositoryBuilder = Callable[[ScraperSettings], IJobRepository]


class ConfigurableJobRepository(IJobRepository):
    """Proxy que aplica as regras de conexão antes de delegar à fonte concreta.

    * só consulta plataformas ativas;
    * cada plataforma consultada conta uma requisição no limite por hora;
    * recria a fonte concreta quando o ritmo (delays) muda.
    """

    def __init__(
        self,
        source: ScraperSettingsSource,
        build: RepositoryBuilder,
        *,
        budget: HourlyRequestBudget | None = None,
    ) -> None:
        self._source = source
        self._build = build
        self._budget = budget or HourlyRequestBudget()
        self._settings: ScraperSettings | None = None
        self._repository: IJobRepository | None = None
        self._lock = asyncio.Lock()

    async def search(self, criteria: JobSearchCriteria) -> list[JobPosting]:
        settings = await self._source()
        sites = tuple(site for site in criteria.sites if site in settings.active_sites)
        if not sites:
            raise SourcesDisabledError(
                "Nenhuma das plataformas escolhidas está ativa. Ative-as em /settings/scrapers"
            )

        async with self._lock:
            wait = self._budget.try_acquire(len(sites), settings.max_requests_per_hour)
            if wait is not None:
                raise RateLimitExceededError(_limit_message(len(sites), settings.max_requests_per_hour, wait))
            if self._repository is None or settings != self._settings:
                self._repository = self._build(settings)
                self._settings = settings
            repository = self._repository

        return await repository.search(replace(criteria, sites=sites))


def _limit_message(count: int, limit: int, wait: float) -> str:
    if math.isinf(wait):
        return (
            f"A busca consulta {count} plataformas, mais que o limite de {limit} "
            "requisições por hora. Escolha menos plataformas ou aumente o limite em /settings/scrapers"
        )
    minutes = max(1, math.ceil(wait / 60))
    return (
        f"Limite de {limit} requisições por hora atingido. "
        f"Tente novamente em {minutes} min ou ajuste o limite em /settings/scrapers"
    )
