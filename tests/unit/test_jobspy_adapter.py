from datetime import date
from typing import Any

import pandas as pd
import pytest

from app.adapters.jobspy_adapter import JobSpyAdapter
from app.adapters.rate_limit import RandomDelayThrottle
from app.domain.exceptions import JobSourceError
from app.domain.interfaces import IJobRepository
from app.domain.models import JobSearchCriteria, JobSite, WorkMode

pytestmark = pytest.mark.unit

NAN = float("nan")


def jobspy_row(**overrides: Any) -> dict[str, Any]:
    """Linha no formato do DataFrame do JobSpy (colunas ausentes viram NaN)."""
    return {
        "id": "li-123",
        "site": "linkedin",
        "job_url": "https://www.linkedin.com/jobs/view/123",
        "job_url_direct": NAN,
        "title": "Senior Python Developer",
        "company": "ACME",
        "location": "São Paulo, SP, BR",
        "date_posted": date(2026, 9, 25),
        "job_type": "fulltime",
        "interval": NAN,
        "min_amount": NAN,
        "max_amount": NAN,
        "currency": NAN,
        "is_remote": False,
        "description": "Python, FastAPI e Docker.",
        "skills": NAN,
        "work_from_home_type": NAN,
        **overrides,
    }


class FakeScraper:
    """Substitui `jobspy.scrape_jobs`: responde por site e registra os argumentos."""

    def __init__(self, responses: dict[str, pd.DataFrame | Exception]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> pd.DataFrame:
        self.calls.append(kwargs)
        response = self._responses[kwargs["site_name"][0]]
        if isinstance(response, Exception):
            raise response
        return response


class CountingThrottle(RandomDelayThrottle):
    def __init__(self) -> None:
        super().__init__(0.0, 0.0)
        self.entries = 0

    async def __aenter__(self) -> None:
        self.entries += 1
        await super().__aenter__()


def make_adapter(scraper: FakeScraper, throttle: RandomDelayThrottle | None = None) -> JobSpyAdapter:
    return JobSpyAdapter(throttle=throttle or CountingThrottle(), scrape_fn=scraper)


def criteria(**overrides: Any) -> JobSearchCriteria:
    defaults: dict[str, Any] = {
        "search_term": "python developer",
        "location": "São Paulo",
        "sites": (JobSite.LINKEDIN, JobSite.INDEED),
    }
    return JobSearchCriteria(**defaults | overrides)


def test_is_a_job_repository():
    assert isinstance(make_adapter(FakeScraper({})), IJobRepository)


async def test_scrapes_each_site_separately_through_the_throttle():
    scraper = FakeScraper(
        {
            "linkedin": pd.DataFrame([jobspy_row()]),
            "indeed": pd.DataFrame([jobspy_row(id="in-1", site="indeed", title="Backend Python")]),
        }
    )
    throttle = CountingThrottle()

    jobs = await make_adapter(scraper, throttle).search(criteria())

    assert [call["site_name"] for call in scraper.calls] == [["linkedin"], ["indeed"]]
    assert throttle.entries == 2
    assert [(j.source, j.title) for j in jobs] == [
        (JobSite.LINKEDIN, "Senior Python Developer"),
        (JobSite.INDEED, "Backend Python"),
    ]


async def test_maps_search_criteria_to_jobspy_arguments():
    scraper = FakeScraper({"linkedin": pd.DataFrame()})

    await make_adapter(scraper).search(
        criteria(sites=(JobSite.LINKEDIN,), results_wanted=5, hours_old=24, remote_only=True)
    )

    assert scraper.calls[0] == {
        "site_name": ["linkedin"],
        "search_term": "python developer",
        "location": "São Paulo",
        "is_remote": True,
        "results_wanted": 5,
        "hours_old": 24,
        "country_indeed": "brazil",
        "linkedin_fetch_description": True,
        "description_format": "markdown",
        "verbose": 1,
    }


async def test_normalizes_a_complete_row_into_job_posting():
    row = jobspy_row(
        min_amount=8000.0,
        max_amount=12000.0,
        currency="BRL",
        interval="monthly",
        is_remote=True,
        skills="Python, FastAPI , Docker",
    )
    scraper = FakeScraper({"linkedin": pd.DataFrame([row])})

    [job] = await make_adapter(scraper).search(criteria(sites=(JobSite.LINKEDIN,)))

    assert job.url == "https://www.linkedin.com/jobs/view/123"
    assert job.external_id == "li-123"
    assert job.location == "São Paulo, SP, BR"
    assert job.date_posted == date(2026, 9, 25)
    assert job.work_mode is WorkMode.REMOTE
    assert job.skills == ("Python", "FastAPI", "Docker")
    assert job.salary is not None
    assert (job.salary.min_amount, job.salary.max_amount) == (8000.0, 12000.0)


async def test_nan_columns_become_empty_values():
    scraper = FakeScraper(
        {"linkedin": pd.DataFrame([jobspy_row(description=NAN, location=NAN, date_posted=NAN)])}
    )

    [job] = await make_adapter(scraper).search(criteria(sites=(JobSite.LINKEDIN,)))

    assert job.description == ""
    assert job.location == ""
    assert job.date_posted is None
    assert job.salary is None
    assert job.skills == ()
    assert job.work_mode is WorkMode.UNKNOWN


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"work_from_home_type": "Hybrid"}, WorkMode.HYBRID),
        ({"work_from_home_type": "Remote"}, WorkMode.REMOTE),
        # caso real: LinkedIn com is_remote=False e "Trabalho Remoto" no título
        ({"title": "Staff Backend Engineer - Trabalho Remoto", "is_remote": False}, WorkMode.REMOTE),
        # o título declarado prevalece sobre a flag
        ({"title": "Dev Python - Híbrido", "is_remote": True}, WorkMode.HYBRID),
        ({"location": "Remote, Brazil"}, WorkMode.REMOTE),
        ({"title": "Dev Python Presencial", "work_from_home_type": "Remote"}, WorkMode.ONSITE),
        ({"date_posted": "2026-09-20"}, date(2026, 9, 20)),
        ({"date_posted": pd.Timestamp("2026-09-21 10:00")}, date(2026, 9, 21)),
    ],
)
async def test_handles_alternative_column_formats(row, expected):
    scraper = FakeScraper({"linkedin": pd.DataFrame([jobspy_row(**row)])})

    [job] = await make_adapter(scraper).search(criteria(sites=(JobSite.LINKEDIN,)))

    assert expected in (job.work_mode, job.date_posted)


async def test_description_is_not_used_to_infer_work_mode():
    row = jobspy_row(description="Benefícios: auxílio home office e VR.")
    scraper = FakeScraper({"linkedin": pd.DataFrame([row])})

    [job] = await make_adapter(scraper).search(criteria(sites=(JobSite.LINKEDIN,)))

    assert job.work_mode is WorkMode.UNKNOWN


async def test_drops_inconsistent_salary_but_keeps_the_job():
    scraper = FakeScraper(
        {"linkedin": pd.DataFrame([jobspy_row(min_amount=9000.0, max_amount=5000.0)])}
    )

    [job] = await make_adapter(scraper).search(criteria(sites=(JobSite.LINKEDIN,)))

    assert job.salary is None


async def test_skips_rows_missing_required_fields():
    rows = [
        jobspy_row(),
        jobspy_row(title=NAN),
        jobspy_row(company=""),
        jobspy_row(job_url=NAN, job_url_direct=NAN),
    ]
    scraper = FakeScraper({"linkedin": pd.DataFrame(rows)})

    jobs = await make_adapter(scraper).search(criteria(sites=(JobSite.LINKEDIN,)))

    assert len(jobs) == 1


async def test_one_failing_site_does_not_discard_the_others():
    scraper = FakeScraper(
        {
            "linkedin": RuntimeError("429 Too Many Requests"),
            "indeed": pd.DataFrame([jobspy_row(site="indeed")]),
        }
    )

    jobs = await make_adapter(scraper).search(criteria())

    assert [j.source for j in jobs] == [JobSite.INDEED]


async def test_raises_domain_error_when_every_site_fails():
    scraper = FakeScraper(
        {"linkedin": RuntimeError("429"), "indeed": ConnectionError("timeout")}
    )

    with pytest.raises(JobSourceError, match="linkedin.*429.*indeed.*timeout"):
        await make_adapter(scraper).search(criteria())


async def test_no_results_is_not_an_error():
    scraper = FakeScraper({"linkedin": pd.DataFrame(), "indeed": pd.DataFrame()})

    assert await make_adapter(scraper).search(criteria()) == []
