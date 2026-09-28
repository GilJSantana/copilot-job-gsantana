"""Caso de uso de busca de vagas."""

import logging
from dataclasses import dataclass

from app.domain.interfaces import IJobRepository, IJobStore
from app.domain.models import JobPosting, JobSearchCriteria
from app.services.deduplication import JobDeduplicator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSearchResult:
    jobs: tuple[JobPosting, ...]
    total_fetched: int
    new_keys: frozenset[str] = frozenset()

    @property
    def duplicates_removed(self) -> int:
        return self.total_fetched - len(self.jobs)

    @property
    def new_jobs(self) -> tuple[JobPosting, ...]:
        """Vagas nunca vistas em buscas anteriores, na ordem da busca."""
        return tuple(job for job in self.jobs if job.dedup_key in self.new_keys)


class JobService:
    def __init__(
        self,
        repository: IJobRepository,
        store: IJobStore,
        deduplicator: JobDeduplicator | None = None,
    ) -> None:
        self._repository = repository
        self._store = store
        self._deduplicator = deduplicator or JobDeduplicator()

    async def search(self, criteria: JobSearchCriteria) -> JobSearchResult:
        """Busca vagas na fonte, remove duplicatas entre sites e as persiste.

        Propaga `JobSourceError` quando todas as fontes falham.
        """
        fetched = await self._repository.search(criteria)
        unique = self._deduplicator.deduplicate(fetched)
        new_keys = await self._store.save_many(unique)
        result = JobSearchResult(
            jobs=tuple(unique),
            total_fetched=len(fetched),
            new_keys=frozenset(new_keys),
        )
        logger.info(
            "Busca '%s': %d vagas (%d novas), %d duplicatas removidas",
            criteria.search_term,
            len(result.jobs),
            len(result.new_keys),
            result.duplicates_removed,
        )
        return result
