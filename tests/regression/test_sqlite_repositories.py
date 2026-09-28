"""Detalhes específicos do SQLite: timestamps, PRAGMAs, persistência em arquivo,
cascata e concorrência entre conexões."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.domain.models import JobPosting, JobSite, MatchResult
from app.repositories.database import create_engine, create_session_factory
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.match_store import SqlAlchemyMatchResultStore
from app.repositories.migrate import upgrade_to_head
from app.repositories.orm import JobRow, MatchResultRow

pytestmark = pytest.mark.regression

JOB = JobPosting(
    title="Python Developer",
    company="ACME",
    location="São Paulo, SP",
    url="https://www.linkedin.com/jobs/view/1",
    source=JobSite.LINKEDIN,
)


def job(title: str, source: JobSite = JobSite.LINKEDIN) -> JobPosting:
    return JobPosting(
        title=title, company="ACME", location="SP", url=f"https://x/{source}/{title}", source=source
    )


def match(score: float = 80.0) -> MatchResult:
    return MatchResult(
        job_key=JOB.dedup_key, score=score, keyword_score=70.0, llm_score=score, matched_skills=()
    )


class FixedClock:
    def __init__(self, *moments: datetime) -> None:
        self._moments = list(moments)

    def __call__(self) -> datetime:
        return self._moments.pop(0)


async def test_tracks_first_and_last_seen(session_factory):
    first, second = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 5, tzinfo=UTC)
    store = SqlAlchemyJobStore(session_factory, clock=FixedClock(first, second))

    await store.save_many([JOB])
    await store.save_many([JOB])

    async with session_factory() as session:
        row = await session.scalar(select(JobRow))
    # SQLite não guarda fuso: os valores voltam como UTC "naive"
    assert row.first_seen_at == first.replace(tzinfo=None)
    assert row.last_seen_at == second.replace(tzinfo=None)


async def test_foreign_keys_are_enforced(session_factory):
    async with session_factory() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar() == 1


async def test_match_is_deleted_with_its_job(session_factory):
    await SqlAlchemyJobStore(session_factory).save_many([JOB])
    await SqlAlchemyMatchResultStore(session_factory).save(match())

    async with session_factory.begin() as session:
        await session.execute(text("DELETE FROM jobs"))

    async with session_factory() as session:
        assert await session.scalar(select(MatchResultRow)) is None


async def test_persists_across_connections(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}"

    for _ in range(2):  # a segunda passada simula reiniciar a aplicação
        engine = create_engine(url)
        await upgrade_to_head(engine)
        store = SqlAlchemyJobStore(create_session_factory(engine))
        new_keys = await store.save_many([JOB])
        await engine.dispose()

    assert new_keys == set()  # já existia no arquivo


# --- Concorrência ----------------------------------------------------------------


@pytest.fixture
async def two_connections(tmp_path):
    """Dois engines independentes no mesmo arquivo: simula dois processos/requisições."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'race.db'}"
    engines = [create_engine(url) for _ in range(2)]
    await upgrade_to_head(engines[0])
    yield [create_session_factory(engine) for engine in engines]
    for engine in engines:
        await engine.dispose()


async def test_concurrent_saves_of_overlapping_batches(two_connections):
    """Regressão: sem BEGIN IMMEDIATE, ambas as transações liam "vaga nova" e a
    segunda falhava com UNIQUE constraint failed (30 de 30 rodadas)."""
    stores = [SqlAlchemyJobStore(factory) for factory in two_connections]

    for round_ in range(10):
        batch_a = [job(f"Vaga r{round_} n{i}") for i in range(20)]
        batch_b = [job(f"Vaga r{round_} n{i}", JobSite.INDEED) for i in range(10, 30)]  # 10 em comum

        new_a, new_b = await asyncio.gather(
            stores[0].save_many(batch_a), stores[1].save_many(batch_b)
        )

        assert not new_a & new_b, "a mesma vaga foi reportada como nova duas vezes"
        assert len(new_a | new_b) == 30


async def test_concurrent_match_saves_keep_one_row(two_connections):
    await SqlAlchemyJobStore(two_connections[0]).save_many([JOB])
    stores = [SqlAlchemyMatchResultStore(factory) for factory in two_connections]

    await asyncio.gather(*(stores[i % 2].save(match(score=float(i))) for i in range(20)))

    async with two_connections[0]() as session:
        rows = (await session.scalars(select(MatchResultRow))).all()
    assert len(rows) == 1
