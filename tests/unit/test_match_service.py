from dataclasses import replace

import pytest

from app.domain.exceptions import JobNotFoundError, LLMProviderError
from app.domain.models import CandidateProfile, JobPosting, JobSite
from app.services.match_engine import MatchEngine
from app.services.match_service import MatchService
from tests.doubles import InMemoryJobStore, InMemoryMatchResultStore, MockLLMAdapter

pytestmark = pytest.mark.unit

PROFILE = CandidateProfile(full_name="Gil", headline="Backend Python", skills=("Python", "Docker"))
JOB = JobPosting(
    title="Python Developer",
    company="ACME",
    url="https://example.com/1",
    source=JobSite.LINKEDIN,
    description="Python e Docker.",
)
LLM_OK = {"score": 90, "rationale": "ok", "strengths": [], "gaps": []}


@pytest.fixture
async def job_store() -> InMemoryJobStore:
    store = InMemoryJobStore()
    await store.save_many([JOB])
    return store


def make_service(job_store: InMemoryJobStore, llm: MockLLMAdapter) -> tuple[MatchService, InMemoryMatchResultStore]:
    match_store = InMemoryMatchResultStore(job_store)
    return MatchService(MatchEngine(llm), match_store), match_store


async def test_evaluates_and_saves_on_first_request(job_store):
    llm = MockLLMAdapter(LLM_OK)
    service, match_store = make_service(job_store, llm)

    result = await service.match(PROFILE, JOB)

    assert result.profile_fingerprint == PROFILE.fingerprint
    assert await match_store.get(JOB.dedup_key) == result
    assert len(llm.calls) == 1


async def test_reuses_saved_match_for_the_same_profile(job_store):
    llm = MockLLMAdapter(LLM_OK)
    service, _ = make_service(job_store, llm)

    first = await service.match(PROFILE, JOB)
    second = await service.match(PROFILE, JOB)

    assert second == first
    assert len(llm.calls) == 1


async def test_recomputes_when_profile_changed(job_store):
    llm = MockLLMAdapter(LLM_OK)
    service, match_store = make_service(job_store, llm)
    await service.match(PROFILE, JOB)
    updated_profile = replace(PROFILE, skills=("Python", "Docker", "Kubernetes"))

    result = await service.match(updated_profile, JOB)

    assert len(llm.calls) == 2
    assert result.profile_fingerprint == updated_profile.fingerprint
    assert (await match_store.get(JOB.dedup_key)).is_current_for(updated_profile)


async def test_retries_llm_when_saved_match_was_a_fallback(job_store):
    match_store = InMemoryMatchResultStore(job_store)
    down = MatchService(MatchEngine(MockLLMAdapter(error=LLMProviderError("offline"))), match_store)
    fallback = await down.match(PROFILE, JOB)
    assert not fallback.used_llm

    llm = MockLLMAdapter(LLM_OK)
    result = await MatchService(MatchEngine(llm), match_store).match(PROFILE, JOB)

    assert result.used_llm
    assert len(llm.calls) == 1


async def test_force_recomputes_even_when_current(job_store):
    llm = MockLLMAdapter(LLM_OK)
    service, _ = make_service(job_store, llm)
    await service.match(PROFILE, JOB)

    await service.match(PROFILE, JOB, force=True)

    assert len(llm.calls) == 2


async def test_unknown_job_is_rejected():
    service, _ = make_service(InMemoryJobStore(), MockLLMAdapter(LLM_OK))

    with pytest.raises(JobNotFoundError):
        await service.match(PROFILE, JOB)


# --- Fingerprint do perfil -------------------------------------------------------


def test_fingerprint_is_deterministic():
    same = CandidateProfile(full_name="Gil", headline="Backend Python", skills=["Python", "Docker"])

    assert same.fingerprint == PROFILE.fingerprint


@pytest.mark.parametrize(
    "change",
    [
        {"headline": "Data Engineer"},
        {"skills": ("Python",)},
        {"summary": "novo resumo"},
        {"years_of_experience": 7},
        {"target_roles": ("Tech Lead",)},
        {"languages": ("Inglês",)},
    ],
)
def test_fingerprint_changes_with_any_field(change):
    assert replace(PROFILE, **change).fingerprint != PROFILE.fingerprint
