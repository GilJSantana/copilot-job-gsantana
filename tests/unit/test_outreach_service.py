import pytest

from app.domain.exceptions import (
    JobNotFoundError,
    LLMProviderError,
    LLMResponseFormatError,
    OutreachGenerationError,
)
from app.domain.models import (
    CandidateProfile,
    JobPosting,
    JobSite,
    MatchResult,
    OutreachChannel,
    OutreachLanguage,
    OutreachMessage,
)
from app.services.outreach_service import OutreachService
from tests.doubles import InMemoryJobStore, InMemoryOutreachStore, MockLLMAdapter, ScriptedLLMAdapter

pytestmark = pytest.mark.unit

PROFILE = CandidateProfile(
    full_name="Gil Jesus",
    headline="Backend Python Developer",
    skills=("Python", "FastAPI"),
    years_of_experience=6,
    summary="Construo APIs de alto volume.",
)
JOB = JobPosting(
    title="Senior Python Engineer",
    company="ACME",
    url="https://example.com/1",
    source=JobSite.LINKEDIN,
    description="Buscamos Python e FastAPI.",
)
EMAIL = {"subject": "Senior Python Engineer — APIs com FastAPI", "body": "Olá, tudo bem? ..."}
NOTE = {"subject": None, "body": "Olá! Vi a vaga de Senior Python Engineer na ACME e gostaria de conectar."}


def match(fingerprint: str = PROFILE.fingerprint) -> MatchResult:
    return MatchResult(
        job_key=JOB.dedup_key,
        score=85.0,
        keyword_score=100.0,
        llm_score=75.0,
        matched_skills=("Python", "FastAPI"),
        strengths=("APIs de alto volume",),
        gaps=("Kubernetes",),
        profile_fingerprint=fingerprint,
    )


@pytest.fixture
async def outreach_store() -> InMemoryOutreachStore:
    jobs = InMemoryJobStore()
    await jobs.save_many([JOB])
    return InMemoryOutreachStore(jobs)


async def draft(llm, store, **kwargs) -> OutreachMessage:
    options = {"channel": OutreachChannel.LINKEDIN_CONNECTION} | kwargs
    return await OutreachService(llm, store).draft(PROFILE, JOB, **options)


async def test_drafts_and_saves_an_email(outreach_store):
    llm = MockLLMAdapter(EMAIL)

    message = await draft(llm, outreach_store, channel=OutreachChannel.EMAIL)

    assert (message.subject, message.body) == (EMAIL["subject"], EMAIL["body"])
    assert message.provider == "mock"
    assert message.profile_fingerprint == PROFILE.fingerprint
    assert message.created_at is not None
    assert outreach_store.messages == [message]


async def test_channels_without_subject_ignore_one_sent_by_mistake(outreach_store):
    llm = MockLLMAdapter(NOTE | {"subject": "Assunto indevido"})

    message = await draft(llm, outreach_store)

    assert message.subject is None


async def test_prompt_carries_channel_rules_and_only_profile_facts(outreach_store):
    llm = MockLLMAdapter(NOTE)

    await draft(llm, outreach_store, language=OutreachLanguage.EN, recipient_name="Ana")

    prompt = llm.calls[0]["prompt"]
    assert "inglês" in prompt
    assert "no máximo 300 caracteres" in prompt
    assert "Destinatário: Ana" in prompt
    assert "Python, FastAPI" in prompt
    assert "Senior Python Engineer" in prompt and "ACME" in prompt
    assert "Nunca invente" in llm.calls[0]["system_prompt"]


async def test_unknown_recipient_is_explicit_in_the_prompt(outreach_store):
    llm = MockLLMAdapter(NOTE)

    await draft(llm, outreach_store, recipient_name="   ")

    assert "Destinatário: nome desconhecido" in llm.calls[0]["prompt"]


async def test_uses_strengths_of_a_current_match_but_never_its_gaps(outreach_store):
    llm = MockLLMAdapter(NOTE)

    await draft(llm, outreach_store, match=match())

    prompt = llm.calls[0]["prompt"]
    assert "Pontos de conexão com a vaga" in prompt
    assert "Pontos fortes: APIs de alto volume" in prompt
    assert "Kubernetes" not in prompt


async def test_ignores_a_match_made_for_an_older_profile(outreach_store):
    llm = MockLLMAdapter(NOTE)

    await draft(llm, outreach_store, match=match(fingerprint="0000000000000000"))

    assert "Pontos de conexão com a vaga" not in llm.calls[0]["prompt"]


async def test_asks_for_one_rewrite_when_too_long(outreach_store):
    llm = ScriptedLLMAdapter({"body": "x" * 450}, NOTE)

    message = await draft(llm, outreach_store)

    assert message.body == NOTE["body"]
    assert len(llm.calls) == 2
    assert "450 caracteres" in llm.calls[1]["prompt"]


async def test_gives_up_after_the_rewrite_is_still_too_long(outreach_store):
    llm = ScriptedLLMAdapter({"body": "x" * 450}, {"body": "y" * 320})

    with pytest.raises(OutreachGenerationError, match="320"):
        await draft(llm, outreach_store)

    assert outreach_store.messages == []


@pytest.mark.parametrize(
    ("channel", "payload"),
    [
        (OutreachChannel.LINKEDIN_MESSAGE, {}),
        (OutreachChannel.LINKEDIN_MESSAGE, {"body": "   "}),
        (OutreachChannel.LINKEDIN_MESSAGE, {"body": 42}),
        (OutreachChannel.EMAIL, {"body": "Olá"}),
        (OutreachChannel.EMAIL, {"subject": "", "body": "Olá"}),
    ],
)
async def test_rejects_drafts_that_break_the_contract(outreach_store, channel, payload):
    with pytest.raises(LLMResponseFormatError):
        await draft(MockLLMAdapter(payload), outreach_store, channel=channel)

    assert outreach_store.messages == []


async def test_propagates_llm_outage(outreach_store):
    with pytest.raises(LLMProviderError):
        await draft(MockLLMAdapter(error=LLMProviderError("offline")), outreach_store)


async def test_unknown_job_is_rejected():
    store = InMemoryOutreachStore(InMemoryJobStore())

    with pytest.raises(JobNotFoundError):
        await draft(MockLLMAdapter(NOTE), store)


async def test_history_lists_newest_first(outreach_store):
    service = OutreachService(ScriptedLLMAdapter(NOTE, EMAIL), outreach_store)
    await service.draft(PROFILE, JOB, channel=OutreachChannel.LINKEDIN_CONNECTION)
    await service.draft(PROFILE, JOB, channel=OutreachChannel.EMAIL)

    history = await service.history(JOB)

    assert [m.channel for m in history] == [OutreachChannel.EMAIL, OutreachChannel.LINKEDIN_CONNECTION]


# --- Regras do domínio ----------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"channel": OutreachChannel.LINKEDIN_CONNECTION, "body": "x" * 301},
        {"channel": OutreachChannel.LINKEDIN_CONNECTION, "body": " "},
        {"channel": OutreachChannel.LINKEDIN_CONNECTION, "body": "Olá", "subject": "Oi"},
        {"channel": OutreachChannel.EMAIL, "body": "Olá"},
        {"channel": OutreachChannel.EMAIL, "body": "x" * 1501, "subject": "Oi"},
    ],
)
def test_outreach_message_enforces_channel_rules(fields):
    with pytest.raises(ValueError):
        OutreachMessage(job_key="k", language=OutreachLanguage.PT, **fields)


def test_linkedin_connection_limit_is_the_platform_limit():
    assert OutreachChannel.LINKEDIN_CONNECTION.max_length == 300
