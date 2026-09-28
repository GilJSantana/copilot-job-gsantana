"""Contrato de `IJobStore`: roda contra o SQLite real e contra o dublê em memória,
garantindo que os testes unitários (que usam o dublê) refletem o comportamento real."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from app.domain.interfaces import IJobStore
from app.domain.models import JobListing, JobPosting, JobSite, SalaryRange, WorkMode
from app.repositories.job_store import SqlAlchemyJobStore
from tests.doubles import InMemoryJobStore

pytestmark = pytest.mark.regression


class TickingClock:
    """Cada leitura avança 1s: buscas consecutivas têm horários distintos."""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture(params=["sqlite", "in_memory"])
def store(request, session_factory) -> IJobStore:
    if request.param == "sqlite":
        return SqlAlchemyJobStore(session_factory, clock=TickingClock())
    return InMemoryJobStore()


def job(**overrides: Any) -> JobPosting:
    defaults: dict[str, Any] = {
        "title": "Python Developer",
        "company": "ACME",
        "location": "São Paulo, SP",
        "url": "https://www.linkedin.com/jobs/view/1",
        "source": JobSite.LINKEDIN,
    }
    return JobPosting(**defaults | overrides)


async def test_round_trips_every_field(store):
    original = job(
        description="Python, FastAPI e Docker.",
        work_mode=WorkMode.HYBRID,
        salary=SalaryRange(min_amount=9000.0, max_amount=13000.0, currency="BRL", interval="monthly"),
        date_posted=date(2026, 9, 20),
        job_type="fulltime",
        skills=("Python", "FastAPI"),
        external_id="li-1",
        other_listings=(JobListing(JobSite.INDEED, "https://br.indeed.com/viewjob?jk=1"),),
    )

    await store.save_many([original])

    assert await store.get(original.dedup_key) == original


async def test_round_trips_partial_salary(store):
    original = job(salary=SalaryRange(min_amount=8000.0, currency="USD", interval="yearly"))

    await store.save_many([original])

    assert await store.get(original.dedup_key) == original


async def test_reports_only_never_seen_jobs_as_new(store):
    python, data = job(), job(title="Data Engineer")

    first = await store.save_many([python])
    second = await store.save_many([python, data])

    assert first == {python.dedup_key}
    assert second == {data.dedup_key}


async def test_known_job_keeps_identity_and_gains_new_information(store):
    stored = job(description="curta")
    seen_again = job(
        url="https://br.indeed.com/viewjob?jk=9",
        source=JobSite.INDEED,
        location="São Paulo, São Paulo, Brazil",
        description="descrição completa e bem mais longa",
        salary=SalaryRange(min_amount=10000.0, max_amount=12000.0),
    )

    await store.save_many([stored])
    await store.save_many([seen_again])

    result = await store.get(stored.dedup_key)
    assert result.url == stored.url
    assert result.source is JobSite.LINKEDIN
    assert result.description == "descrição completa e bem mais longa"
    assert result.salary == seen_again.salary


async def test_duplicates_inside_one_batch_are_merged(store):
    new_keys = await store.save_many([job(), job(source=JobSite.INDEED, skills=("AWS",))])

    assert len(new_keys) == 1
    assert (await store.get(job().dedup_key)).skills == ("AWS",)


async def test_lists_latest_search_first_keeping_search_order(store):
    await store.save_many([job(title="A"), job(title="B")])
    await store.save_many([job(title="C"), job(title="D")])

    titles = [j.title for j in await store.list_recent()]

    assert titles == ["C", "D", "A", "B"]


async def test_resaving_does_not_change_discovery_order(store):
    await store.save_many([job(title="A")])
    await store.save_many([job(title="B")])
    await store.save_many([job(title="A")])  # visto de novo, mas não é novo

    assert [j.title for j in await store.list_recent()] == ["B", "A"]


async def test_paginates(store):
    await store.save_many([job(title=t) for t in "ABCDE"])

    page = await store.list_recent(limit=2, offset=2)

    assert [j.title for j in page] == ["C", "D"]


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (10, -1)])
async def test_rejects_invalid_pagination(store, limit, offset):
    with pytest.raises(ValueError):
        await store.list_recent(limit=limit, offset=offset)


async def test_unknown_key_and_empty_batch(store):
    assert await store.get("inexistente") is None
    assert await store.save_many([]) == set()
    assert await store.list_recent() == []


async def test_listings_from_later_searches_accumulate(store):
    await store.save_many([job()])
    await store.save_many([job(url="https://br.indeed.com/viewjob?jk=1", source=JobSite.INDEED)])
    await store.save_many([job()])  # mesmo anúncio principal visto de novo

    stored = await store.get(job().dedup_key)
    assert stored.url == "https://www.linkedin.com/jobs/view/1"
    assert stored.other_listings == (JobListing(JobSite.INDEED, "https://br.indeed.com/viewjob?jk=1"),)
