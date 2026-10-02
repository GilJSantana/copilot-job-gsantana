"""Dados de exemplo para os testes do CV Tailor."""

from typing import Any

from app.domain.models import (
    CareerHistory,
    Certification,
    ContactInfo,
    Education,
    Experience,
    JobPosting,
    JobSite,
    OutreachLanguage,
    TailoredCV,
    TailoredExperience,
)

HISTORY = CareerHistory(
    full_name="Ana Souza",
    headline="Engenheira de Software Backend",
    contact=ContactInfo(email="ana@email.com", linkedin="linkedin.com/in/ana", location="São Paulo, SP"),
    summary="Engenheira com 6 anos de experiência em backend Python.",
    skills=("Python", "FastAPI", "Django", "PostgreSQL", "Docker"),
    experiences=(
        # fora de ordem cronológica de propósito: a ordem final é responsabilidade do código
        Experience(
            id="logistica",
            title="Desenvolvedora Backend",
            company="Logística Ltda",
            location="Remoto",
            start="2019-01",
            end="2022-02",
            highlights=(
                "Desenvolvi APIs REST em Django e PostgreSQL.",
                "Automatizei o deploy com Docker, de 1 hora para 10 minutos.",
                "Mantive a documentação técnica do time.",
                "Participei de plantões de suporte.",
            ),
            technologies=("Django", "Docker"),
        ),
        Experience(
            id="pagamentos",
            title="Engenheira de Software Sênior",
            company="Pagamentos SA",
            location="São Paulo, SP",
            start="2022-03",
            highlights=(
                "Migrei o monólito para FastAPI, reduzindo a latência p95 de 800 ms para 120 ms.",
                "Implementei eventos com Kafka para 2 milhões de transações por dia.",
            ),
            technologies=("FastAPI", "Kafka", "AWS"),
        ),
    ),
    education=(
        Education(degree="Bacharelado em Ciência da Computação", institution="USP", start="2014-02", end="2018-12"),
    ),
    certifications=(Certification(name="AWS Developer Associate", issuer="AWS", year=2023),),
    languages=("Português (nativo)", "Inglês (avançado)"),
)

JOB = JobPosting(
    title="Senior Python Engineer",
    company="ACME",
    url="https://example.com/jobs/1",
    source=JobSite.LINKEDIN,
    description="Buscamos Python, FastAPI, Kafka e AWS para sistemas de alto volume.",
)


def llm_cv(**overrides: Any) -> dict[str, Any]:
    """Resposta do LLM fiel ao histórico."""
    payload: dict[str, Any] = {
        "headline": "Engenheira de Software Backend | Python, FastAPI e Kafka",
        "summary": "Engenheira com 6 anos de experiência em backend Python e sistemas de alto volume.",
        "skills": ["Python", "FastAPI", "Kafka", "AWS", "Docker"],
        "experiences": [
            {"id": "logistica", "highlights": ["Desenvolvi APIs REST em Django e PostgreSQL."]},
            {
                "id": "pagamentos",
                "highlights": [
                    "Reduzi a latência p95 de 800 ms para 120 ms migrando o monólito para FastAPI.",
                    "Processei 2 milhões de transações por dia com eventos em Kafka.",
                ],
            },
        ],
        "matched_keywords": ["Python", "FastAPI", "Kafka", "AWS"],
    }
    return payload | overrides


def tailored_cv(**overrides: Any) -> TailoredCV:
    values: dict[str, Any] = {
        "language": OutreachLanguage.PT,
        "headline": "Engenheira Backend | Python e Kafka",
        "summary": "Backend Python com 6 anos de experiência.",
        "skills": ("Python", "Kafka", "AWS"),
        "experiences": (
            TailoredExperience(
                experience_id="pagamentos",
                highlights=("Processei 2 milhões de transações por dia com Kafka.",),
            ),
            TailoredExperience(
                experience_id="logistica",
                highlights=("Desenvolvi APIs REST em Django e PostgreSQL.",),
            ),
        ),
        "matched_keywords": ("Python", "Kafka"),
    }
    return TailoredCV(**values | overrides)
