import copy
import pickle
from dataclasses import replace

import pytest

from app.domain.exceptions import CVIntegrityError
from app.domain.models import (
    CareerHistory,
    ContactInfo,
    CVVersion,
    Education,
    Experience,
    OutreachLanguage,
    TailoredCV,
    TailoredExperience,
)

pytestmark = pytest.mark.unit

HISTORY = CareerHistory(
    full_name="Ana Souza",
    headline="Backend Python",
    summary="Engenheira com 6 anos de experiência.",
    contact=ContactInfo(email="ana@email.com"),
    skills=["Python", "FastAPI", "PostgreSQL"],
    experiences=[
        Experience(
            id="pagamentos",
            title="Engenheira Sênior",
            company="Pagamentos SA",
            start="2022-03",
            highlights=[
                "Reduzi a latência p95 de 800 ms para 120 ms.",
                "Liderei um time de 5 pessoas.",
            ],
            technologies=["Kafka", "AWS"],
        ),
        Experience(
            id="logistica",
            title="Desenvolvedora Backend",
            company="Logística Ltda",
            start="2019-01",
            end="2022-02",
            highlights=["Desenvolvi APIs REST em Django."],
        ),
    ],
)


def tailored(**overrides) -> TailoredCV:
    values = {
        "language": OutreachLanguage.PT,
        "headline": "Engenheira Backend Python",
        "summary": "Backend com foco em performance.",
        "skills": ("Python", "Kafka"),
        "experiences": (
            TailoredExperience(
                experience_id="pagamentos",
                highlights=("Levei a latência p95 de 800 ms a 120 ms com FastAPI.",),
            ),
        ),
    }
    return TailoredCV(**values | overrides)


# --- Histórico -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [("2022-13", None), ("2022-3", None), ("03/2022", None), ("2022-03", "2021-12")],
)
def test_experience_rejects_invalid_periods(start, end):
    with pytest.raises(ValueError):
        Experience(id="x", title="Dev", company="ACME", start=start, end=end)


def test_education_rejects_invalid_periods():
    with pytest.raises(ValueError):
        Education(degree="BCC", institution="USP", start="2018-01", end="2017-12")


def test_history_rejects_repeated_experience_ids():
    experience = Experience(id="x", title="Dev", company="ACME", start="2020-01")

    with pytest.raises(ValueError, match="repetidos"):
        CareerHistory(full_name="A", headline="B", contact=ContactInfo(), experiences=[experience, experience])


def test_known_skills_include_technologies_of_experiences():
    assert HISTORY.known_skills == {"python", "fastapi", "postgresql", "kafka", "aws"}


def test_fingerprint_changes_when_history_changes():
    assert replace(HISTORY, summary="novo").fingerprint != HISTORY.fingerprint


# --- Integridade do CV otimizado ------------------------------------------------------


def test_faithful_rewrite_has_no_violations():
    assert tailored().violations_against(HISTORY) == []


def test_skill_comparison_ignores_case_and_accents():
    assert tailored(skills=("PYTHON", "fastapi")).violations_against(HISTORY) == []


def test_detects_invented_experience():
    cv = tailored(experiences=(TailoredExperience(experience_id="google", highlights=()),))

    assert cv.violations_against(HISTORY) == ["experiência inexistente: google"]


def test_detects_repeated_experience():
    same = TailoredExperience(experience_id="logistica", highlights=())

    assert "experiência repetida: logistica" in tailored(experiences=(same, same)).violations_against(HISTORY)


def test_detects_invented_skill():
    violations = tailored(skills=("Python", "Rust", "Go")).violations_against(HISTORY)

    assert violations == ["skills ausentes do histórico: Rust, Go"]


@pytest.mark.parametrize(
    "highlight",
    [
        "Reduzi a latência p95 de 800 ms para 90 ms.",  # métrica alterada
        "Liderei um time de 12 pessoas.",  # tamanho de equipe inventado
        "Aumentei a receita em 30%.",  # métrica inexistente
    ],
)
def test_detects_invented_numbers_in_highlights(highlight):
    cv = tailored(experiences=(TailoredExperience(experience_id="pagamentos", highlights=(highlight,)),))

    [violation] = cv.violations_against(HISTORY)
    assert violation.startswith("pagamentos: números ausentes do histórico")


def test_numbers_must_come_from_the_same_experience():
    """'5' existe em 'pagamentos', mas não em 'logistica'."""
    cv = tailored(
        experiences=(
            TailoredExperience(experience_id="logistica", highlights=("Liderei 5 pessoas em Django.",)),
        )
    )

    assert cv.violations_against(HISTORY) == ["logistica: números ausentes do histórico: 5"]


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("summary", "Engenheira com 10 anos de experiência."),
        ("headline", "Engenheira Backend | 8 anos"),
    ],
)
def test_detects_invented_numbers_in_summary_and_headline(field, text):
    [violation] = tailored(**{field: text}).violations_against(HISTORY)

    assert violation.startswith("números ausentes do histórico no resumo")


def test_summary_may_cite_numbers_from_anywhere_in_history():
    cv = tailored(summary="6 anos de backend; reduzi a latência de 800 ms para 120 ms.")

    assert cv.violations_against(HISTORY) == []


@pytest.mark.parametrize("field", ["headline", "summary"])
def test_tailored_cv_requires_headline_and_summary(field):
    with pytest.raises(ValueError):
        tailored(**{field: " "})


def test_tailored_cv_requires_an_experience():
    with pytest.raises(ValueError):
        tailored(experiences=())


def test_cv_version_knows_when_history_changed():
    version = CVVersion(
        id="v1",
        job_key="k",
        content=tailored(),
        history_fingerprint=HISTORY.fingerprint,
        template="ats_base",
        pdf_path="cv.pdf",
    )

    assert version.is_current_for(HISTORY)
    assert not version.is_current_for(replace(HISTORY, headline="Outro"))



# --- Lastro dos highlights --------------------------------------------------------------


def with_highlight(highlight: str, **overrides) -> TailoredCV:
    return tailored(
        experiences=(TailoredExperience(experience_id="pagamentos", highlights=(highlight,)),),
        **overrides,
    )


@pytest.mark.parametrize(
    "highlight",
    [
        # caso real (llama3.1): responsabilidades copiadas da descrição da vaga
        "Apoiei a análise de requisitos técnicos e a definição de soluções para novas demandas.",
        "Colaborei com a equipe técnica em revisões de código e resolução de problemas.",
    ],
)
def test_detects_highlights_without_support_in_the_experience(highlight):
    [violation] = with_highlight(highlight).violations_against(HISTORY)

    assert violation.startswith("pagamentos: sem lastro no histórico")


@pytest.mark.parametrize(
    "highlight",
    [
        "Reduzi a latência p95 de 800 ms para 120 ms.",  # cópia
        "Latência p95 reduzida de 800 ms para 120 ms.",  # reordenado
        "Reduzindo a latência p95 de 800 ms para 120 ms com Kafka e AWS.",  # flexão + tecnologias
    ],
)
def test_faithful_rewrites_have_support(highlight):
    assert with_highlight(highlight).violations_against(HISTORY) == []


def test_support_is_not_checked_across_languages():
    """Comparação por palavras não funciona entre idiomas: a tradução é aceita
    (números e skills continuam verificados)."""
    cv = with_highlight("Cut p95 latency from 800 ms to 120 ms.", language=OutreachLanguage.EN)

    assert cv.violations_against(HISTORY) == []



@pytest.mark.parametrize(
    ("pdf_path", "expected"),
    [
        ("Ana-Souza_CV_Acme_v1.pdf", "Ana-Souza_CV_Acme.pdf"),
        ("arquivo-antigo.pdf", "arquivo-antigo.pdf"),  # sem o sufixo do id: mantém
    ],
)
def test_download_name_hides_the_internal_id(pdf_path, expected):
    version = CVVersion(
        id="v1",
        job_key="k",
        content=tailored(),
        history_fingerprint=HISTORY.fingerprint,
        template="ats_base",
        pdf_path=pdf_path,
    )

    assert version.download_name == expected



def test_integrity_error_survives_being_recreated_from_its_args():
    """Regressão: recriada a partir de args, a mensagem virava uma lista de caracteres."""
    original = CVIntegrityError(["skills ausentes do histórico: Rust"])

    for clone in (copy.copy(original), pickle.loads(pickle.dumps(original)), type(original)(*original.args)):
        assert str(clone) == "CV otimizado diverge do histórico: skills ausentes do histórico: Rust"
        assert clone.violations == ["skills ausentes do histórico: Rust"]
