import pytest

from app.domain.exceptions import LLMProviderError
from app.domain.models import (
    CandidateProfile,
    JobPosting,
    JobSite,
    MatchVerdict,
    WorkMode,
)
from app.services.match_engine import MatchEngine, MatchWeights
from tests.doubles import MockLLMAdapter

pytestmark = pytest.mark.unit


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Gil Jesus",
        headline="Backend Python Developer",
        skills=["Python", "FastAPI", "Docker", "Kubernetes"],
        years_of_experience=6,
        target_roles=["Backend Engineer"],
    )


@pytest.fixture
def job() -> JobPosting:
    return JobPosting(
        title="Senior Python Engineer",
        company="ACME",
        url="https://example.com/jobs/1",
        source=JobSite.LINKEDIN,
        location="São Paulo, SP",
        work_mode=WorkMode.REMOTE,
        description="Buscamos pessoa com experiência em python, FastAPI e docker.",
    )


def llm_response(score: float, **extra) -> dict:
    return {
        "score": score,
        "rationale": "Boa aderência técnica.",
        "strengths": ["Python"],
        "gaps": ["Kubernetes"],
        **extra,
    }


async def test_combines_keyword_and_llm_scores_with_default_weights(profile, job):
    engine = MatchEngine(MockLLMAdapter(llm_response(90)))

    result = await engine.evaluate(profile, job)

    # 3 de 4 skills citadas -> keyword 75; 0.4*75 + 0.6*90 = 84
    assert result.matched_skills == ("Python", "FastAPI", "Docker")
    assert result.keyword_score == 75.0
    assert result.llm_score == 90.0
    assert result.score == 84.0
    assert result.verdict is MatchVerdict.STRONG
    assert result.gaps == ("Kubernetes",)
    assert result.provider == "mock"
    assert result.job_key == job.dedup_key


@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        (MatchWeights(keyword=1.0, semantic=0.0), 75.0),
        (MatchWeights(keyword=0.0, semantic=1.0), 40.0),
        (MatchWeights(keyword=0.5, semantic=0.5), 57.5),
    ],
)
async def test_respects_custom_weights(profile, job, weights, expected):
    engine = MatchEngine(MockLLMAdapter(llm_response(40)), weights)

    result = await engine.evaluate(profile, job)

    assert result.score == expected


@pytest.mark.parametrize(("raw", "clamped"), [(150, 100.0), (-10, 0.0)])
async def test_clamps_out_of_range_llm_scores(profile, job, raw, clamped):
    engine = MatchEngine(MockLLMAdapter(llm_response(raw)))

    result = await engine.evaluate(profile, job)

    assert result.llm_score == clamped


async def test_falls_back_to_keyword_score_when_llm_fails(profile, job):
    engine = MatchEngine(MockLLMAdapter(error=LLMProviderError("timeout")))

    result = await engine.evaluate(profile, job)

    assert result.llm_score is None
    assert not result.used_llm
    assert result.score == result.keyword_score == 75.0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"score": "noventa"},
        {"score": True},
        {"score": float("nan")},
        llm_response(80, gaps="Kubernetes"),
        llm_response(80, rationale=42),
    ],
)
async def test_falls_back_when_llm_breaks_the_contract(profile, job, payload):
    engine = MatchEngine(MockLLMAdapter(payload))

    result = await engine.evaluate(profile, job)

    assert result.llm_score is None
    assert result.score == 75.0


async def test_skill_matching_ignores_case_and_accents_and_respects_word_boundaries():
    profile = CandidateProfile(
        full_name="Gil",
        headline="Dev",
        skills=["Java", "C#", "Integração Contínua", "Node.js"],
    )
    job = JobPosting(
        title="Dev Fullstack",
        company="ACME",
        url="https://example.com/jobs/2",
        source=JobSite.INDEED,
        description="Stack: JavaScript, c#, NODE.JS e integracao continua.",
    )

    matched = MatchEngine.matched_skills(profile, job)

    assert matched == ("C#", "Integração Contínua", "Node.js")  # "Java" != "JavaScript"


async def test_profile_without_skills_scores_zero_on_keywords(job):
    profile = CandidateProfile(full_name="Gil", headline="Dev", skills=[])
    engine = MatchEngine(MockLLMAdapter(llm_response(50)))

    result = await engine.evaluate(profile, job)

    assert result.keyword_score == 0.0
    assert result.score == 30.0  # 0.4*0 + 0.6*50


async def test_sends_profile_and_job_context_to_llm(profile, job):
    llm = MockLLMAdapter(llm_response(70))

    await MatchEngine(llm).evaluate(profile, job)

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert "Senior Python Engineer" in call["prompt"]
    assert "Python, FastAPI, Docker, Kubernetes" in call["prompt"]
    assert "JSON" in call["system_prompt"]


@pytest.mark.parametrize(
    ("keyword", "semantic"),
    [(0.5, 0.6), (-0.2, 1.2)],
)
def test_rejects_invalid_weights(keyword, semantic):
    with pytest.raises(ValueError):
        MatchWeights(keyword=keyword, semantic=semantic)
