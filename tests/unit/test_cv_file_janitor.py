import pytest

from app.domain.models import CVVersion
from app.services.cv_file_janitor import CVFileJanitor
from tests.cv_builders import JOB, tailored_cv
from tests.doubles import InMemoryCVVersionStore, InMemoryFileStorage, InMemoryJobStore

pytestmark = pytest.mark.unit

KEPT = f"Ana_CV_Acme_{'a' * 32}.pdf"
ORPHAN = f"Ana_CV_Acme_{'b' * 32}.pdf"
USER_FILE = "meu-curriculo-antigo.pdf"


async def make(*, registered: bool = True) -> tuple[CVFileJanitor, InMemoryFileStorage]:
    jobs = InMemoryJobStore()
    await jobs.save_many([JOB])
    store = InMemoryCVVersionStore(jobs)
    if registered:
        await store.save(
            CVVersion(
                id="a" * 32,
                job_key=JOB.dedup_key,
                content=tailored_cv(),
                history_fingerprint="f" * 16,
                template="ats_base",
                pdf_path=KEPT,
            )
        )
    storage = InMemoryFileStorage()
    for name in (KEPT, ORPHAN, USER_FILE):
        await storage.save(name, b"%PDF")
    return CVFileJanitor(storage, store), storage


async def test_lists_orphans_without_deleting_by_default():
    janitor, storage = await make()

    report = await janitor.prune()

    assert report.orphans == (ORPHAN,)
    assert report.deleted == ()
    assert ORPHAN in storage.files


async def test_apply_deletes_only_orphan_cv_files():
    janitor, storage = await make()

    report = await janitor.prune(apply=True)

    assert report.deleted == (ORPHAN,)
    assert sorted(storage.files) == sorted([KEPT, USER_FILE])  # arquivo do usuário intacto


async def test_refuses_to_delete_when_the_database_has_no_versions():
    """Banco vazio + PDFs na pasta = provável DATABASE_URL errado: tudo pareceria órfão."""
    janitor, storage = await make(registered=False)

    report = await janitor.prune(apply=True)

    assert report.suspicious
    assert report.deleted == ()
    assert len(storage.files) == 3


async def test_force_overrides_the_empty_database_guard():
    janitor, storage = await make(registered=False)

    report = await janitor.prune(apply=True, force=True)

    assert set(report.deleted) == {KEPT, ORPHAN}
    assert list(storage.files) == [USER_FILE]
