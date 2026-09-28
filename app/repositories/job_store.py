"""Implementação SQLAlchemy da porta `IJobStore`."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces import IJobStore
from app.domain.models import JobListing, JobPosting, JobSite, SalaryRange, WorkMode
from app.repositories.database import SessionFactory, write_transaction
from app.repositories.orm import JobRow

# SQLite aceita até 32766 parâmetros por query; lotes pequenos ficam longe disso
_IN_CLAUSE_BATCH = 500


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyJobStore(IJobStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def save_many(self, jobs: list[JobPosting]) -> set[str]:
        incoming: dict[str, JobPosting] = {}
        for job in jobs:
            key = job.dedup_key
            incoming[key] = incoming[key].merged_with(job) if key in incoming else job
        if not incoming:
            return set()

        now = self._clock()
        new_keys: set[str] = set()
        async with write_transaction(self._session_factory) as session:
            existing = await self._load_rows(session, list(incoming))
            for key, job in incoming.items():
                row = existing.get(key)
                if row is None:
                    session.add(_to_row(job, seen_at=now))
                    new_keys.add(key)
                else:
                    # a cópia armazenada mantém a identidade; a nova só completa lacunas
                    _update_row(row, _to_domain(row).merged_with(job))
                    row.last_seen_at = now
        return new_keys

    async def get(self, dedup_key: str) -> JobPosting | None:
        async with self._session_factory() as session:
            row = await session.scalar(select(JobRow).where(JobRow.dedup_key == dedup_key))
            return _to_domain(row) if row else None

    async def list_recent(self, *, limit: int = 50, offset: int = 0) -> list[JobPosting]:
        if limit <= 0 or offset < 0:
            raise ValueError("exige limit > 0 e offset >= 0")
        query = (
            select(JobRow)
            .order_by(JobRow.first_seen_at.desc(), JobRow.id.asc())
            .limit(limit)
            .offset(offset)
        )
        async with self._session_factory() as session:
            return [_to_domain(row) for row in await session.scalars(query)]

    @staticmethod
    async def _load_rows(session: AsyncSession, keys: list[str]) -> dict[str, JobRow]:
        rows: dict[str, JobRow] = {}
        for start in range(0, len(keys), _IN_CLAUSE_BATCH):
            batch = keys[start : start + _IN_CLAUSE_BATCH]
            for row in await session.scalars(select(JobRow).where(JobRow.dedup_key.in_(batch))):
                rows[row.dedup_key] = row
        return rows


def _to_row(job: JobPosting, *, seen_at: datetime) -> JobRow:
    row = JobRow(dedup_key=job.dedup_key, first_seen_at=seen_at, last_seen_at=seen_at)
    _update_row(row, job)
    return row


def _update_row(row: JobRow, job: JobPosting) -> None:
    row.title = job.title
    row.company = job.company
    row.location = job.location
    row.url = job.url
    row.source = job.source.value
    row.description = job.description
    row.work_mode = job.work_mode.value
    row.job_type = job.job_type
    row.skills = list(job.skills)
    row.external_id = job.external_id
    row.other_listings = [
        {"source": listing.source.value, "url": listing.url} for listing in job.other_listings
    ]
    row.date_posted = job.date_posted
    salary = job.salary
    row.salary_min = salary.min_amount if salary else None
    row.salary_max = salary.max_amount if salary else None
    row.salary_currency = salary.currency if salary else None
    row.salary_interval = salary.interval if salary else None


def _to_domain(row: JobRow) -> JobPosting:
    salary = None
    if row.salary_currency is not None:
        salary = SalaryRange(
            min_amount=row.salary_min,
            max_amount=row.salary_max,
            currency=row.salary_currency,
            interval=row.salary_interval or "monthly",
        )
    return JobPosting(
        title=row.title,
        company=row.company,
        location=row.location,
        url=row.url,
        source=JobSite(row.source),
        description=row.description,
        work_mode=WorkMode(row.work_mode),
        job_type=row.job_type,
        skills=tuple(row.skills),
        external_id=row.external_id,
        other_listings=tuple(
            JobListing(JobSite(item["source"]), item["url"]) for item in row.other_listings
        ),
        date_posted=row.date_posted,
        salary=salary,
    )
