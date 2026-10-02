"""Contrato de `ICVVersionStore`: roda contra o SQLite real e contra o dublê em memória."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import ICVVersionStore
from app.domain.models import CVVersion, JobPosting, JobSite
from app.repositories.cv_version_store import SqlAlchemyCVVersionStore
from app.repositories.job_store import SqlAlchemyJobStore
from tests.cv_builders import tailored_cv
from tests.doubles import InMemoryCVVersionStore, InMemoryJobStore

pytestmark = pytest.mark.regression

JOB = JobPosting(title="Python Developer", company="ACME", url="https://x/1", source=JobSite.LINKEDIN)
OTHER_JOB = JobPosting(title="Data Engineer", company="ACME", url="https://x/2", source=JobSite.INDEED)


class TickingClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture(params=["sqlite", "in_memory"])
async def store(request, session_factory) -> ICVVersionStore:
    if request.param == "sqlite":
        await SqlAlchemyJobStore(session_factory).save_many([JOB, OTHER_JOB])
        return SqlAlchemyCVVersionStore(session_factory, clock=TickingClock())
    jobs = InMemoryJobStore()
    await jobs.save_many([JOB, OTHER_JOB])
    return InMemoryCVVersionStore(jobs)


def version(n: int = 1, job: JobPosting = JOB, **overrides) -> CVVersion:
    values = {
        "id": f"{n:032x}",
        "job_key": job.dedup_key,
        "content": tailored_cv(),
        "history_fingerprint": "abc123abc123abc1",
        "template": "ats_base",
        "pdf_path": f"Ana_CV_Acme_{n:08x}.pdf",
        "provider": "ollama:llama3.1",
    }
    return CVVersion(**values | overrides)


async def test_round_trips_every_field_including_the_tailored_content(store):
    saved = await store.save(version())

    assert saved.created_at is not None and saved.created_at.tzinfo is not None
    assert await store.get(saved.id) == saved
    # a ordem das experiências e dos highlights é parte do CV
    assert [t.experience_id for t in saved.content.experiences] == ["pagamentos", "logistica"]


async def test_lists_versions_of_a_job_newest_first(store):
    first = await store.save(version(1))
    second = await store.save(version(2))
    await store.save(version(3, OTHER_JOB))

    assert await store.list_for_job(JOB.dedup_key) == [second, first]


async def test_rejects_version_for_unknown_job(store):
    with pytest.raises(JobNotFoundError):
        await store.save(version(job_key="0000000000000000"))


async def test_unknown_version_and_job_without_versions(store):
    assert await store.get("f" * 32) is None
    assert await store.list_for_job(JOB.dedup_key) == []



async def test_lists_every_referenced_file(store):
    await store.save(version(1))
    await store.save(version(2, OTHER_JOB))

    assert await store.referenced_files() == {version(1).pdf_path, version(2).pdf_path}
