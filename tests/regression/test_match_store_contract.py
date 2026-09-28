"""Contrato de `IMatchResultStore`: roda contra o SQLite real e contra o dublê em memória."""

from typing import Any

import pytest

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import IJobStore, IMatchResultStore
from app.domain.models import JobPosting, JobSite, MatchResult
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.match_store import SqlAlchemyMatchResultStore
from tests.doubles import InMemoryJobStore, InMemoryMatchResultStore

pytestmark = pytest.mark.regression

JOB = JobPosting(
    title="Python Developer",
    company="ACME",
    location="São Paulo, SP",
    url="https://www.linkedin.com/jobs/view/1",
    source=JobSite.LINKEDIN,
)


@pytest.fixture(params=["sqlite", "in_memory"])
async def stores(request, session_factory) -> tuple[IJobStore, IMatchResultStore]:
    if request.param == "sqlite":
        job_store: IJobStore = SqlAlchemyJobStore(session_factory)
        match_store: IMatchResultStore = SqlAlchemyMatchResultStore(session_factory)
    else:
        job_store = InMemoryJobStore()
        match_store = InMemoryMatchResultStore(job_store)
    await job_store.save_many([JOB])
    return job_store, match_store


@pytest.fixture
def match_store(stores) -> IMatchResultStore:
    return stores[1]


def match(**overrides: Any) -> MatchResult:
    values: dict[str, Any] = {
        "job_key": JOB.dedup_key,
        "score": 84.0,
        "keyword_score": 75.0,
        "llm_score": 90.0,
        "matched_skills": ("Python", "Docker"),
        "strengths": ("Experiência sólida",),
        "gaps": ("Kubernetes",),
        "rationale": "Boa aderência.",
        "provider": "ollama:llama3.1",
        "profile_fingerprint": "abc123abc123abc1",
    }
    return MatchResult(**values | overrides)


async def test_round_trips_every_field(match_store):
    await match_store.save(match())

    assert await match_store.get(JOB.dedup_key) == match()


async def test_round_trips_fallback_match(match_store):
    fallback = match(llm_score=None, score=75.0, strengths=(), gaps=(), rationale="")

    await match_store.save(fallback)

    assert await match_store.get(JOB.dedup_key) == fallback


async def test_saving_again_replaces_every_field(match_store):
    await match_store.save(match())
    replacement = match(
        score=60.0,
        llm_score=None,
        gaps=(),
        provider="gemini:gemini-2.5-flash",
        profile_fingerprint="0000000000000000",
    )

    await match_store.save(replacement)

    assert await match_store.get(JOB.dedup_key) == replacement


async def test_rejects_match_for_unknown_job(match_store):
    with pytest.raises(JobNotFoundError):
        await match_store.save(match(job_key="0000000000000000"))

    assert await match_store.get("0000000000000000") is None


async def test_missing_match(match_store):
    assert await match_store.get(JOB.dedup_key) is None


async def test_get_many_returns_only_existing_matches(stores):
    job_store, match_store = stores
    other = JobPosting(
        title="Data Engineer", company="ACME", url="https://x/2", source=JobSite.INDEED
    )
    await job_store.save_many([other])
    await match_store.save(match())

    found = await match_store.get_many([JOB.dedup_key, other.dedup_key, "0000000000000000"])

    assert found == {JOB.dedup_key: match()}
    assert await match_store.get_many([]) == {}
