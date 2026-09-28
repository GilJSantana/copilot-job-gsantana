from dataclasses import replace

import pytest

from app.domain.exceptions import JobSourceError
from app.domain.models import JobPosting, JobSearchCriteria, JobSite, WorkMode
from app.services.job_service import JobService
from tests.doubles import FakeJobRepository, InMemoryJobStore

pytestmark = pytest.mark.unit


def job(title: str, source: JobSite = JobSite.LINKEDIN, location: str = "São Paulo, SP") -> JobPosting:
    return JobPosting(
        title=title,
        company="ACME",
        location=location,
        url=f"https://example.com/{source}/{title}",
        source=source,
    )


CRITERIA = JobSearchCriteria(search_term="python")


async def test_returns_unique_jobs_and_counts_removed_duplicates():
    repository = FakeJobRepository(
        [
            job("Python Dev"),
            job("Data Engineer"),
            job("Python Dev", JobSite.INDEED, "São Paulo, São Paulo, Brazil"),
        ]
    )

    result = await JobService(repository, InMemoryJobStore()).search(CRITERIA)

    assert [j.title for j in result.jobs] == ["Python Dev", "Data Engineer"]
    assert result.total_fetched == 3
    assert result.duplicates_removed == 1


async def test_persists_unique_jobs():
    store = InMemoryJobStore()
    repository = FakeJobRepository([job("Python Dev"), job("Python Dev", JobSite.INDEED)])

    await JobService(repository, store).search(CRITERIA)

    assert list(store.jobs) == [job("Python Dev").dedup_key]


async def test_flags_jobs_not_seen_in_previous_searches():
    store = InMemoryJobStore()
    await store.save_many([job("Python Dev")])
    repository = FakeJobRepository([job("Python Dev"), job("Data Engineer")])

    result = await JobService(repository, store).search(CRITERIA)

    assert [j.title for j in result.new_jobs] == ["Data Engineer"]
    assert result.new_keys == {job("Data Engineer").dedup_key}


async def test_forwards_criteria_to_the_repository():
    repository = FakeJobRepository()

    await JobService(repository, InMemoryJobStore()).search(CRITERIA)

    assert repository.calls == [CRITERIA]


async def test_no_jobs_found():
    result = await JobService(FakeJobRepository(), InMemoryJobStore()).search(CRITERIA)

    assert result.jobs == ()
    assert result.new_jobs == ()
    assert result.duplicates_removed == 0


async def test_propagates_source_errors_without_touching_the_store():
    store = InMemoryJobStore()
    service = JobService(FakeJobRepository(error=JobSourceError("todas falharam")), store)

    with pytest.raises(JobSourceError):
        await service.search(CRITERIA)

    assert store.jobs == {}


async def test_merged_job_exposes_every_listing():
    repository = FakeJobRepository(
        [
            job("Python Dev"),
            replace(
                job("Python Dev", JobSite.INDEED, "São Paulo, São Paulo, Brazil"),
                work_mode=WorkMode.REMOTE,  # só o Indeed marcou is_remote
            ),
        ]
    )

    result = await JobService(repository, InMemoryJobStore()).search(CRITERIA)

    [merged] = result.jobs
    assert [listing.source for listing in merged.all_listings] == [JobSite.LINKEDIN, JobSite.INDEED]
