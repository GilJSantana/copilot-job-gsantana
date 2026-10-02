"""Vagas simuladas para a pré-visualização da página de busca (`/preview/search`).

Cobrem os estados visuais do JobCard: os quatro vereditos de match, vaga sem análise,
vaga nova, anúncio em mais de uma plataforma, salário e modelos de trabalho distintos.
"""

from datetime import date, timedelta

from app.domain.models import JobSite, MatchVerdict, WorkMode
from app.web.schemas import JobSummaryOut, ListingOut, MatchOut, SalaryOut


def _match(score: float, verdict: MatchVerdict, skills: list[str], *, used_llm: bool = True) -> MatchOut:
    return MatchOut(
        score=score,
        verdict=verdict,
        keyword_score=score,
        llm_score=score if used_llm else None,
        used_llm=used_llm,
        matched_skills=skills,
        strengths=[],
        gaps=[],
        rationale="",
        provider="preview",
        is_current=True,
    )


def mock_jobs(today: date | None = None) -> list[JobSummaryOut]:
    today = today or date.today()
    return [
        JobSummaryOut(
            key="preview000000001",
            title="Senior Python Engineer",
            company="Acme Fintech",
            location="São Paulo, SP",
            work_mode=WorkMode.REMOTE,
            source=JobSite.LINKEDIN,
            url="https://www.linkedin.com/jobs/",
            other_listings=[ListingOut(source=JobSite.INDEED, url="https://br.indeed.com/")],
            date_posted=today,
            salary=SalaryOut(min_amount=18000, max_amount=24000, currency="BRL", interval="monthly"),
            job_type="fulltime",
            is_new=True,
            match=_match(88, MatchVerdict.STRONG, ["Python", "FastAPI", "PostgreSQL"]),
        ),
        JobSummaryOut(
            key="preview000000002",
            title="Backend Developer Pleno (Django)",
            company="Sabor Delivery",
            location="Campinas, SP",
            work_mode=WorkMode.HYBRID,
            source=JobSite.INDEED,
            url="https://br.indeed.com/",
            other_listings=[],
            date_posted=today - timedelta(days=1),
            salary=None,
            job_type="fulltime",
            match=_match(71, MatchVerdict.GOOD, ["Python", "Docker"]),
        ),
        JobSummaryOut(
            key="preview000000003",
            title="Tech Lead — Plataforma de Dados",
            company="PagaBem Pagamentos",
            location="Rio de Janeiro, RJ",
            work_mode=WorkMode.ONSITE,
            source=JobSite.GLASSDOOR,
            url="https://www.glassdoor.com.br/",
            other_listings=[],
            date_posted=today - timedelta(days=3),
            salary=None,
            job_type="contract",
            match=_match(54, MatchVerdict.WEAK, ["Airflow"], used_llm=False),
        ),
        JobSummaryOut(
            key="preview000000004",
            title="Desenvolvedor Java Júnior",
            company="Banco Horizonte",
            location="São Paulo, SP",
            work_mode=WorkMode.UNKNOWN,
            source=JobSite.LINKEDIN,
            url="https://www.linkedin.com/jobs/",
            other_listings=[],
            date_posted=today - timedelta(days=6),
            salary=None,
            job_type=None,
            match=_match(23, MatchVerdict.POOR, []),
        ),
        JobSummaryOut(
            key="preview000000005",
            title="Engenheiro de Machine Learning",
            company="CasaLar Imóveis",
            location="Remoto — Brasil",
            work_mode=WorkMode.REMOTE,
            source=JobSite.LINKEDIN,
            url="https://www.linkedin.com/jobs/",
            other_listings=[],
            date_posted=today - timedelta(days=2),
            salary=None,
            job_type="fulltime",
            match=None,
        ),
    ]
