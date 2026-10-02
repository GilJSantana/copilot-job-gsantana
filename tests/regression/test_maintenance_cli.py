"""Comando `python -m app.maintenance prune-cvs` com banco e pasta reais."""

import pytest

from app.core.config import Settings
from app.domain.models import CVVersion
from app.maintenance import prune_cvs
from app.repositories.cv_version_store import SqlAlchemyCVVersionStore
from app.repositories.database import create_engine, create_session_factory
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.migrate import upgrade_to_head
from tests.cv_builders import JOB, tailored_cv

pytestmark = pytest.mark.regression

KEPT = f"Ana_CV_Acme_{'a' * 32}.pdf"
ORPHAN = f"Ana_CV_Acme_{'b' * 32}.pdf"


@pytest.fixture
async def settings(tmp_path) -> Settings:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
        cv_output_dir=tmp_path / "output_cvs",
    )
    settings.cv_output_dir.mkdir()
    for name in (KEPT, ORPHAN):
        (settings.cv_output_dir / name).write_bytes(b"%PDF")
    return settings


async def register_kept_version(settings: Settings) -> None:
    engine = create_engine(settings.database_url)
    await upgrade_to_head(engine)
    session_factory = create_session_factory(engine)
    await SqlAlchemyJobStore(session_factory).save_many([JOB])
    await SqlAlchemyCVVersionStore(session_factory).save(
        CVVersion(
            id="a" * 32,
            job_key=JOB.dedup_key,
            content=tailored_cv(),
            history_fingerprint="f" * 16,
            template="ats_base",
            pdf_path=KEPT,
        )
    )
    await engine.dispose()


async def test_dry_run_lists_and_keeps_files(settings, capsys):
    await register_kept_version(settings)

    assert await prune_cvs(settings, apply=False, force=False) == 0

    out = capsys.readouterr().out
    assert ORPHAN in out and KEPT not in out
    assert "Nada foi removido" in out
    assert (settings.cv_output_dir / ORPHAN).exists()


async def test_apply_removes_orphans(settings, capsys):
    await register_kept_version(settings)

    assert await prune_cvs(settings, apply=True, force=False) == 0

    assert not (settings.cv_output_dir / ORPHAN).exists()
    assert (settings.cv_output_dir / KEPT).exists()
    assert "1 arquivo(s) removido(s)" in capsys.readouterr().out


async def test_empty_database_blocks_removal_and_explains(settings, capsys):
    assert await prune_cvs(settings, apply=True, force=False) == 1

    out = capsys.readouterr().out
    assert "Confira se DATABASE_URL" in out
    assert (settings.cv_output_dir / ORPHAN).exists()
    assert (settings.cv_output_dir / KEPT).exists()
