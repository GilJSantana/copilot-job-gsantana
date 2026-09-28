"""Contrato de `IOutreachStore`: roda contra o SQLite real e contra o dublê em memória."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import IOutreachStore
from app.domain.models import (
    JobPosting,
    JobSite,
    OutreachChannel,
    OutreachLanguage,
    OutreachMessage,
)
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.outreach_store import SqlAlchemyOutreachStore
from tests.doubles import InMemoryJobStore, InMemoryOutreachStore

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
async def store(request, session_factory) -> IOutreachStore:
    if request.param == "sqlite":
        await SqlAlchemyJobStore(session_factory).save_many([JOB, OTHER_JOB])
        return SqlAlchemyOutreachStore(session_factory, clock=TickingClock())
    jobs = InMemoryJobStore()
    await jobs.save_many([JOB, OTHER_JOB])
    return InMemoryOutreachStore(jobs)


def message(job: JobPosting = JOB, **overrides) -> OutreachMessage:
    values = {
        "job_key": job.dedup_key,
        "channel": OutreachChannel.EMAIL,
        "language": OutreachLanguage.EN,
        "subject": "Python Developer — FastAPI",
        "body": "Hi, ...",
        "provider": "ollama:llama3.1",
        "profile_fingerprint": "abc123abc123abc1",
    }
    return OutreachMessage(**values | overrides)


async def test_save_stamps_creation_time_and_round_trips(store):
    saved = await store.save(message())

    assert saved.created_at is not None
    assert saved.created_at.tzinfo is not None
    assert await store.list_for_job(JOB.dedup_key) == [saved]


async def test_round_trips_message_without_subject(store):
    saved = await store.save(
        message(channel=OutreachChannel.LINKEDIN_CONNECTION, subject=None, body="Olá!")
    )

    assert (await store.list_for_job(JOB.dedup_key))[0].subject is None
    assert saved.subject is None


async def test_keeps_every_draft_newest_first_per_job(store):
    first = await store.save(message(body="primeiro"))
    second = await store.save(message(body="segundo"))
    await store.save(message(OTHER_JOB, body="de outra vaga"))

    assert await store.list_for_job(JOB.dedup_key) == [second, first]


async def test_rejects_draft_for_unknown_job(store):
    with pytest.raises(JobNotFoundError):
        await store.save(message(job_key="0000000000000000"))


async def test_job_without_drafts(store):
    assert await store.list_for_job(JOB.dedup_key) == []
