from dataclasses import replace

import pytest

from app.domain.exceptions import CVIntegrityError, LLMProviderError, LLMResponseFormatError, ProfileError
from app.domain.models import OutreachLanguage
from app.services.cv_optimizer import LLMCVOptimizer
from tests.cv_builders import HISTORY, JOB, llm_cv
from tests.doubles import MockLLMAdapter, ScriptedLLMAdapter

pytestmark = pytest.mark.unit


async def optimize(llm, history=HISTORY, language=OutreachLanguage.PT):
    return await LLMCVOptimizer(llm).optimize_cv(JOB, history, language=language)


def highlights_of(cv, experience_id):
    return next(t.highlights for t in cv.experiences if t.experience_id == experience_id)


async def test_returns_faithful_cv_in_reverse_chronological_order():
    llm = MockLLMAdapter(llm_cv())

    cv = await optimize(llm)

    assert cv.violations_against(HISTORY) == []
    # o LLM devolveu logistica primeiro; a ordem cronológica é garantida pelo código
    assert [t.experience_id for t in cv.experiences] == ["pagamentos", "logistica"]
    assert cv.skills == ("Python", "FastAPI", "Kafka", "AWS", "Docker")
    assert cv.language is OutreachLanguage.PT
    assert len(llm.calls) == 1


async def test_prompt_exposes_ids_allowed_skills_and_rules():
    llm = MockLLMAdapter(llm_cv())

    await optimize(llm, language=OutreachLanguage.EN)

    prompt, system = llm.calls[0]["prompt"], llm.calls[0]["system_prompt"]
    assert "### id: pagamentos" in prompt and "### id: logistica" in prompt
    assert "Skills permitidas: Python, FastAPI, Django, PostgreSQL, Docker, Kafka, AWS" in prompt
    assert "Buscamos Python, FastAPI, Kafka e AWS" in prompt
    assert "inglês" in prompt
    assert "Nunca invente" in system
    assert "copiado exatamente" in system


async def test_experiences_omitted_by_the_llm_come_back_with_original_highlights():
    """Lacunas na trajetória prejudicam a candidatura: toda experiência entra."""
    llm = MockLLMAdapter(llm_cv(experiences=[{"id": "pagamentos", "highlights": ["Migrei o monólito para FastAPI."]}]))

    cv = await optimize(llm)

    assert highlights_of(cv, "logistica") == HISTORY.experience("logistica").highlights[:3]


async def test_limits_highlights_and_skills():
    many_skills = [f"Skill{i}" for i in range(25)]
    history = replace(HISTORY, skills=tuple(many_skills))
    llm = MockLLMAdapter(
        llm_cv(
            skills=many_skills,
            experiences=[
                {"id": "pagamentos", "highlights": [f"Migrei o monólito para FastAPI, etapa {chr(65 + i)}." for i in range(7)]}
            ],
        )
    )

    cv = await optimize(llm, history)

    assert len(cv.skills) == 20
    assert len(highlights_of(cv, "pagamentos")) == 5


async def test_keeps_only_keywords_actually_present_in_the_cv():
    llm = MockLLMAdapter(llm_cv(matched_keywords=["Python", "Kafka", "Kubernetes", "GraphQL"]))

    cv = await optimize(llm)

    assert cv.matched_keywords == ("Python", "Kafka")


async def test_asks_for_one_correction_listing_the_violations():
    llm = ScriptedLLMAdapter(llm_cv(skills=["Python", "Rust"]), llm_cv())

    cv = await optimize(llm)

    assert "Rust" not in cv.skills
    assert len(llm.calls) == 2
    assert "skills ausentes do histórico: Rust" in llm.calls[1]["prompt"]


async def test_removes_what_is_still_invented_after_the_correction():
    unfaithful = llm_cv(
        skills=["Python", "Rust"],
        experiences=[
            {
                "id": "pagamentos",
                "highlights": [
                    "Reduzi a latência p95 de 800 ms para 50 ms.",  # número alterado
                    "Processei 2 milhões de transações por dia com Kafka.",  # fiel
                ],
            },
            {"id": "google", "highlights": ["Trabalhei no Google."]},  # experiência inventada
            {"id": "logistica", "highlights": ["Liderei 15 pessoas."]},  # único highlight inventado
        ],
    )
    llm = ScriptedLLMAdapter(unfaithful, unfaithful)

    cv = await optimize(llm)

    assert cv.violations_against(HISTORY) == []
    assert cv.skills == ("Python",)
    assert highlights_of(cv, "pagamentos") == ("Processei 2 milhões de transações por dia com Kafka.",)
    assert highlights_of(cv, "logistica") == HISTORY.experience("logistica").highlights[:3]
    assert "google" not in [t.experience_id for t in cv.experiences]


async def test_invented_numbers_in_summary_and_headline_fall_back_to_the_history():
    unfaithful = llm_cv(headline="Backend | 12 anos", summary="Engenheira com 12 anos de experiência.")
    llm = ScriptedLLMAdapter(unfaithful, unfaithful)

    cv = await optimize(llm)

    assert (cv.headline, cv.summary) == (HISTORY.headline, HISTORY.summary)


async def test_fails_when_the_summary_cannot_be_repaired():
    unfaithful = llm_cv(summary="Engenheira com 12 anos de experiência.")
    llm = ScriptedLLMAdapter(unfaithful, unfaithful)

    with pytest.raises(CVIntegrityError, match="resumo"):
        await optimize(llm, replace(HISTORY, summary=""))


@pytest.mark.parametrize(
    "payload",
    [
        llm_cv(headline=""),
        llm_cv(summary=None),
        llm_cv(experiences=[]),
        llm_cv(experiences="pagamentos"),
        llm_cv(experiences=[{"highlights": []}]),
        llm_cv(skills="Python, FastAPI"),
        llm_cv(experiences=[{"id": "pagamentos", "highlights": "texto"}]),
    ],
)
async def test_rejects_responses_that_break_the_contract(payload):
    with pytest.raises(LLMResponseFormatError):
        await optimize(MockLLMAdapter(payload))


async def test_propagates_llm_outage():
    with pytest.raises(LLMProviderError):
        await optimize(MockLLMAdapter(error=LLMProviderError("offline")))


async def test_history_without_experiences_is_a_profile_problem():
    llm = MockLLMAdapter(llm_cv())

    with pytest.raises(ProfileError):
        await optimize(llm, replace(HISTORY, experiences=()))

    assert llm.calls == []



async def test_asks_again_when_the_format_is_broken():
    """Caso real (llama3.1): uma experiência veio sem 'id'."""
    llm = ScriptedLLMAdapter(llm_cv(experiences=[{"highlights": ["x"]}]), llm_cv())

    cv = await optimize(llm)

    assert cv.violations_against(HISTORY) == []
    assert "recusada: experiência sem 'id'" in llm.calls[1]["prompt"]


async def test_gives_up_when_the_format_is_broken_twice():
    broken = llm_cv(experiences=[{"highlights": ["x"]}])

    with pytest.raises(LLMResponseFormatError):
        await optimize(ScriptedLLMAdapter(broken, broken))


async def test_removes_highlights_copied_from_the_job_description():
    copied = "Apoiei a análise de requisitos técnicos e a definição de soluções para novas demandas."
    faithful = "Processei 2 milhões de transações por dia com eventos em Kafka."
    unfaithful = llm_cv(experiences=[{"id": "pagamentos", "highlights": [copied, faithful]}])
    llm = ScriptedLLMAdapter(unfaithful, unfaithful)

    cv = await optimize(llm)

    assert highlights_of(cv, "pagamentos") == (faithful,)
    assert "sem lastro no histórico" in llm.calls[1]["prompt"]


async def test_prompt_forbids_turning_job_duties_into_experience():
    llm = MockLLMAdapter(llm_cv())

    await optimize(llm)

    assert "Nunca transforme responsabilidades da vaga" in llm.calls[0]["system_prompt"]
