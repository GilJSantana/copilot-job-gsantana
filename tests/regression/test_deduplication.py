"""Regressão da deduplicação: o que conta como "a mesma vaga" entre fontes."""

from datetime import date
from typing import Any

import pytest

from app.domain.models import JobListing, JobPosting, JobSite, SalaryRange, WorkMode, canonical_title
from app.services.deduplication import JobDeduplicator

pytestmark = pytest.mark.regression


def job(**overrides: Any) -> JobPosting:
    defaults: dict[str, Any] = {
        "title": "Senior Python Developer",
        "company": "ACME",
        "location": "São Paulo, SP, BR",
        "url": "https://www.linkedin.com/jobs/view/1",
        "source": JobSite.LINKEDIN,
    }
    return JobPosting(**defaults | overrides)


# --- Contrato da chave -------------------------------------------------------


def test_dedup_key_value_is_stable():
    """A chave é persistida: se este valor mudar, as chaves gravadas deixam de bater.

    Só atualize o valor esperado junto com uma migração dos dados existentes.
    """
    assert job().dedup_key == "0c88c4e44dff20fd"


@pytest.mark.parametrize(
    "variant",
    [
        # formatos de local de cada fonte
        {"location": "São Paulo, São Paulo, Brazil", "source": JobSite.INDEED},
        {"location": "Sao Paulo"},
        # sufixos societários
        {"company": "ACME Ltda."},
        {"company": "Acme S.A."},
        {"company": "ACME Inc"},
        # caixa, acentos, pontuação e espaços
        {"title": "senior  python developer"},
        {"title": "Senior Python Developer!"},
        {"location": "SÃO PAULO - SP"},
        {"location": "São Paulo – SP"},
        # campos que não fazem parte da identidade
        {"url": "https://br.indeed.com/viewjob?jk=abc", "source": JobSite.INDEED},
        {"description": "outra descrição", "work_mode": WorkMode.REMOTE},
    ],
)
def test_equivalent_postings_share_the_same_key(variant):
    assert job(**variant).dedup_key == job().dedup_key


@pytest.mark.parametrize(
    "variant",
    [
        {"title": "Junior Python Developer"},
        {"company": "ACME Labs"},
        {"location": "Campinas, SP, BR"},
        {"location": ""},
        {"location": "Embu-Guaçu, SP"},
        # senioridade distingue vagas
        {"title": "Pleno Python Developer"},
        {"title": "Python Developer"},
    ],
)
def test_distinct_postings_have_distinct_keys(variant):
    assert job(**variant).dedup_key != job().dedup_key


# --- Títulos com variações entre fontes -----------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Backend Engineer - Brazil", "Backend Engineer"),
        ("Backend Engineer | LATAM", "Backend Engineer"),
        ("Desenvolvedor(a) Python Sênior", "Desenvolvedor Python Sênior"),
        ("Desenvolvedor de Software Python", "Desenvolvedor Software Python"),
        ("Sênior Desenvolvedor Python", "Desenvolvedor Python Sênior"),
        ("Engenheiro de Dados - Híbrido", "Engenheiro de Dados"),
    ],
)
def test_equivalent_titles_share_the_same_key(a, b):
    assert canonical_title(a) == canonical_title(b)
    assert job(title=a).dedup_key == job(title=b).dedup_key


def test_remote_suffix_is_ignored_between_remote_copies():
    """Mesma vaga remota em regiões diferentes, uma delas com o sufixo no título."""
    marked = job(title="Staff Backend Engineer – Python - Trabalho Remoto", location="Recife")
    also_marked = job(title="Staff Backend Engineer (Python) - Remote", location="Curitiba")

    assert marked.dedup_key == also_marked.dedup_key


def test_flags_do_not_split_copies_of_the_same_job():
    """LinkedIn deixa o modo desconhecido, Indeed marca remoto: continua a mesma vaga."""
    linkedin = job(work_mode=WorkMode.UNKNOWN)
    indeed = job(work_mode=WorkMode.REMOTE, source=JobSite.INDEED, url="https://br.indeed.com/1")

    assert linkedin.dedup_key == indeed.dedup_key


def test_remote_suffix_vs_no_suffix_in_a_city_is_a_known_limitation():
    """Limitação conhecida: com uma única chave por vaga, "X - Remoto" (local
    ignorado) e "X" em São Paulo (local considerado) não se encontram."""
    marked = job(title="Senior Python Developer (Remote)")
    unmarked = job(title="Senior Python Developer", location="São Paulo, SP")

    assert canonical_title(marked.title) == canonical_title(unmarked.title)
    assert marked.dedup_key != unmarked.dedup_key


def test_dedup_key_is_stable_when_merging():
    remote = job(title="Python Developer - Remoto", location="Rio de Janeiro")
    other = job(title="Python Developer (Remote)", location="Recife", url="https://x/2")

    merged = remote.merged_with(other)

    assert merged.dedup_key == remote.dedup_key == other.dedup_key


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Senior Python Developer", "Junior Python Developer"),
        ("Software Engineer I", "Software Engineer II"),
        ("Python Developer", "Java Developer"),
        ("Engenheiro de Dados", "Analista de Dados"),
        ("Tech Lead", "Tech Lead Manager"),
    ],
)
def test_distinct_titles_keep_distinct_keys(a, b):
    assert job(title=a).dedup_key != job(title=b).dedup_key


def test_remote_job_posted_once_per_region_is_the_same_job():
    """Caso real: a BairesDev publicou a mesma vaga remota no RJ e no RS."""
    title = "Senior Backend Software Engineer – Python - Trabalho Remoto"
    rio = job(title=title, location="Rio de Janeiro, Brazil")
    rs = job(title=title, location="Rio Grande do Sul, Brazil", url="https://www.linkedin.com/jobs/view/2")

    assert rio.dedup_key == rs.dedup_key


def test_location_still_distinguishes_jobs_not_declared_remote():
    title = "Senior Backend Software Engineer – Python"

    assert job(title=title, location="Rio de Janeiro").dedup_key != job(title=title, location="Porto Alegre").dedup_key


def test_title_made_only_of_noise_words_is_kept():
    """Um título que seria esvaziado pela limpeza não pode colidir com todos os outros."""
    assert canonical_title("Remoto") == "remoto"


# --- Fusão de duplicatas -----------------------------------------------------


def test_keeps_first_occurrence_identity_and_order():
    linkedin = job()
    other = job(title="Backend Engineer")
    indeed = job(url="https://br.indeed.com/viewjob?jk=1", source=JobSite.INDEED)

    result = JobDeduplicator().deduplicate([linkedin, other, indeed])

    assert [(j.title, j.source) for j in result] == [
        ("Senior Python Developer", JobSite.LINKEDIN),
        ("Backend Engineer", JobSite.LINKEDIN),
    ]
    assert result[0].url == linkedin.url


def test_merge_fills_gaps_from_later_copies():
    salary = SalaryRange(min_amount=10000, max_amount=14000)
    linkedin = job(description="curta", skills=("Python", "Docker"))
    indeed = job(
        source=JobSite.INDEED,
        description="descrição bem mais completa da vaga",
        salary=salary,
        date_posted=date(2026, 9, 20),
        work_mode=WorkMode.HYBRID,
        job_type="fulltime",
        skills=("Docker", "AWS"),
    )

    [merged] = JobDeduplicator().deduplicate([linkedin, indeed])

    assert merged.source is JobSite.LINKEDIN
    assert merged.description == "descrição bem mais completa da vaga"
    assert merged.salary == salary
    assert merged.date_posted == date(2026, 9, 20)
    assert merged.work_mode is WorkMode.HYBRID
    assert merged.job_type == "fulltime"
    assert merged.skills == ("Python", "Docker", "AWS")


def test_merge_never_overwrites_known_values_of_the_primary():
    primary = job(
        salary=SalaryRange(min_amount=9000, max_amount=12000),
        work_mode=WorkMode.REMOTE,
        job_type="contract",
    )
    other = job(
        source=JobSite.INDEED,
        salary=SalaryRange(min_amount=1, max_amount=2),
        work_mode=WorkMode.ONSITE,
        job_type="fulltime",
    )

    [merged] = JobDeduplicator().deduplicate([primary, other])

    assert merged.salary == primary.salary
    assert merged.work_mode is WorkMode.REMOTE
    assert merged.job_type == "contract"


def test_merge_keeps_the_original_posting_date():
    first = job(date_posted=date(2026, 9, 25))
    republished = job(source=JobSite.INDEED, date_posted=date(2026, 9, 10))

    [merged] = JobDeduplicator().deduplicate([first, republished])

    assert merged.date_posted == date(2026, 9, 10)


def test_merges_more_than_two_copies():
    copies = [
        job(source=JobSite.LINKEDIN),
        job(source=JobSite.INDEED, skills=("Python",)),
        job(source=JobSite.GLASSDOOR, skills=("FastAPI",)),
    ]

    [merged] = JobDeduplicator().deduplicate(copies)

    assert merged.skills == ("Python", "FastAPI")


def test_empty_input():
    assert JobDeduplicator().deduplicate([]) == []


def test_refuses_to_merge_different_jobs():
    with pytest.raises(ValueError):
        job().merged_with(job(title="Outra vaga"))


# --- Anúncios da mesma vaga em outras fontes --------------------------------------

INDEED_URL = "https://br.indeed.com/viewjob?jk=1"
GLASSDOOR_URL = "https://www.glassdoor.com.br/job/1"


def test_merge_records_the_other_listings():
    linkedin = job()
    indeed = job(url=INDEED_URL, source=JobSite.INDEED)
    glassdoor = job(url=GLASSDOOR_URL, source=JobSite.GLASSDOOR)

    [merged] = JobDeduplicator().deduplicate([linkedin, indeed, glassdoor])

    assert merged.url == linkedin.url
    assert merged.other_listings == (
        JobListing(JobSite.INDEED, INDEED_URL),
        JobListing(JobSite.GLASSDOOR, GLASSDOOR_URL),
    )
    assert [listing.source for listing in merged.all_listings] == [
        JobSite.LINKEDIN,
        JobSite.INDEED,
        JobSite.GLASSDOOR,
    ]


def test_merge_carries_listings_already_known_by_the_other_copy():
    indeed = job(url=INDEED_URL, source=JobSite.INDEED)
    already_merged = indeed.merged_with(job(url=GLASSDOOR_URL, source=JobSite.GLASSDOOR))

    merged = job().merged_with(already_merged)

    assert [listing.url for listing in merged.other_listings] == [INDEED_URL, GLASSDOOR_URL]


def test_merge_never_repeats_a_listing_or_lists_the_primary_url():
    linkedin = job()
    indeed = job(url=INDEED_URL, source=JobSite.INDEED)

    merged = linkedin.merged_with(indeed).merged_with(indeed).merged_with(linkedin)

    assert merged.other_listings == (JobListing(JobSite.INDEED, INDEED_URL),)
