import pytest

from app.domain.exceptions import (
    CVRenderError,
    CVVersionNotFoundError,
    JobNotFoundError,
    LLMProviderError,
    ProfileError,
)
from app.domain.interfaces import ICareerHistoryRepository, ICVGenerator
from app.domain.models import CareerHistory, JobPosting, JobSite, OutreachLanguage, TailoredCV
from app.services.cv_optimizer import LLMCVOptimizer
from app.services.cv_tailor_service import CVTailorService, file_name
from tests.cv_builders import HISTORY, JOB, llm_cv
from tests.doubles import InMemoryCVVersionStore, InMemoryFileStorage, InMemoryJobStore, MockLLMAdapter

pytestmark = pytest.mark.unit

PDF = b"%PDF-1.7 fake"


class StaticHistories(ICareerHistoryRepository):
    def __init__(self, history: CareerHistory | None = HISTORY, error: Exception | None = None) -> None:
        self._history, self._error = history, error

    async def get(self) -> CareerHistory:
        if self._error:
            raise self._error
        return self._history


class FakeGenerator(ICVGenerator):
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[TailoredCV] = []
        self._error = error

    @property
    def template(self) -> str:
        return "ats_base"

    async def generate_pdf(self, history: CareerHistory, cv: TailoredCV) -> bytes:
        self.calls.append(cv)
        if self._error:
            raise self._error
        return PDF


class Setup:
    def __init__(self, *, llm=None, histories=None, generator=None, jobs=(JOB,)) -> None:
        self.job_store = InMemoryJobStore()
        self.job_store.jobs.update({job.dedup_key: job for job in jobs})
        self.job_store._batch_of.update({job.dedup_key: 1 for job in jobs})
        self.llm = llm or MockLLMAdapter(llm_cv())
        self.generator = generator or FakeGenerator()
        self.storage = InMemoryFileStorage()
        self.store = InMemoryCVVersionStore(self.job_store)
        ids = iter(f"{n:032x}" for n in range(1, 100))
        self.service = CVTailorService(
            histories or StaticHistories(),
            LLMCVOptimizer(self.llm),
            self.generator,
            self.storage,
            self.store,
            id_factory=lambda: next(ids),
        )


async def test_tailor_generates_pdf_and_records_the_version():
    setup = Setup()

    version = await setup.service.tailor(JOB, language=OutreachLanguage.EN)

    assert version.job_key == JOB.dedup_key
    assert version.content.language is OutreachLanguage.EN
    assert version.history_fingerprint == HISTORY.fingerprint
    assert (version.template, version.provider) == ("ats_base", "mock")
    assert version.created_at is not None
    assert version.pdf_path == f"Ana-Souza_CV_Acme_{version.id}.pdf"
    assert setup.storage.files == {version.pdf_path: PDF}
    assert setup.generator.calls == [version.content]
    assert setup.store.versions == [version]


async def test_every_call_creates_a_new_version_newest_first():
    """Regressão: com ids de mesmo prefixo, a segunda versão sobrescrevia o PDF da primeira."""
    setup = Setup()

    first = await setup.service.tailor(JOB)
    second = await setup.service.tailor(JOB)

    assert await setup.service.versions(JOB) == [second, first]
    assert first.pdf_path != second.pdf_path
    assert len(setup.storage.files) == 2


async def test_removes_the_pdf_when_the_version_cannot_be_recorded():
    setup = Setup(jobs=())  # vaga não armazenada: o registro falha na FK

    with pytest.raises(JobNotFoundError):
        await setup.service.tailor(JOB)

    assert setup.storage.files == {}


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"histories": StaticHistories(error=ProfileError("sem histórico"))}, ProfileError),
        ({"llm": MockLLMAdapter(error=LLMProviderError("offline"))}, LLMProviderError),
        ({"generator": FakeGenerator(error=CVRenderError("template quebrado"))}, CVRenderError),
    ],
)
async def test_failures_before_the_pdf_leave_nothing_behind(kwargs, error):
    setup = Setup(**kwargs)

    with pytest.raises(error):
        await setup.service.tailor(JOB)

    assert setup.storage.files == {}
    assert setup.store.versions == []


async def test_reads_the_pdf_of_a_version():
    setup = Setup()
    version = await setup.service.tailor(JOB)

    found, pdf = await setup.service.read_pdf(version.id)

    assert (found, pdf) == (version, PDF)


async def test_unknown_version_is_not_found():
    with pytest.raises(CVVersionNotFoundError):
        await Setup().service.get("0" * 32)


async def test_version_whose_file_was_deleted_is_not_found():
    setup = Setup()
    version = await setup.service.tailor(JOB)
    setup.storage.files.clear()

    with pytest.raises(CVVersionNotFoundError, match="não está mais em disco"):
        await setup.service.read_pdf(version.id)


@pytest.mark.parametrize(
    ("name", "company", "expected"),
    [
        ("Ana Souza", "ACME", "Ana-Souza_CV_Acme_{id}.pdf"),
        ("José da Conceição", "Itaú Unibanco S.A.", "Jose-Da-Conceicao_CV_Itau-Unibanco-S-A_{id}.pdf"),
        ("Ana", "../../etc/passwd", "Ana_CV_Etc-Passwd_{id}.pdf"),
        ("Ana", "日本企業", "Ana_CV_sem-nome_{id}.pdf"),
    ],
)
def test_file_name_is_safe_and_readable(name, company, expected):
    job = JobPosting(title="Dev", company=company, url="https://x", source=JobSite.LINKEDIN)
    version_id = "1a2b3c4d" + "0" * 24

    assert file_name(name, job, version_id) == expected.format(id=version_id)


def test_file_name_is_bounded():
    job = JobPosting(title="Dev", company="C" * 200, url="https://x", source=JobSite.LINKEDIN)

    assert len(file_name("N" * 200, job, "0" * 32)) <= 120
