"""Regressão das migrações: o esquema criado pelo Alembic deve ser exatamente o do ORM."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect, text

from app.domain.models import JobSite
from app.repositories.database import create_engine, create_session_factory
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.migrate import alembic_config, upgrade_to_head
from app.repositories.orm import Base

pytestmark = pytest.mark.regression

INITIAL_REVISION = "51c5ef1d6760"


@pytest.fixture
async def engine(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'schema.db'}")
    yield engine
    await engine.dispose()


def _schema_diff(connection: Connection) -> list:
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return compare_metadata(context, Base.metadata)


async def test_migrations_match_orm_models(engine):
    """Falha quando um modelo muda sem a migração correspondente.

    Para corrigir: `uv run alembic revision --autogenerate -m "<descrição>"`.
    """
    await upgrade_to_head(engine)

    async with engine.connect() as connection:
        diff = await connection.run_sync(_schema_diff)

    assert diff == []


async def test_upgrade_is_idempotent(engine):
    await upgrade_to_head(engine)
    await upgrade_to_head(engine)

    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
    assert {"jobs", "match_results", "alembic_version"} <= set(tables)


async def test_downgrade_to_base_and_back(engine):
    def _run(connection: Connection, action) -> None:
        config = alembic_config()
        config.attributes["connection"] = connection
        action(config)

    await upgrade_to_head(engine)
    async with engine.begin() as connection:
        await connection.run_sync(_run, lambda cfg: command.downgrade(cfg, "base"))
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
    assert set(tables) == {"alembic_version"}

    await upgrade_to_head(engine)


def test_history_has_a_single_head():
    """Duas heads = migrações criadas em paralelo sem merge; o upgrade falharia."""
    assert len(ScriptDirectory.from_config(alembic_config()).get_heads()) == 1


async def test_upgrade_keeps_existing_rows_readable(engine):
    """Migrações novas devem funcionar sobre um banco com dados, não só vazio."""
    def _upgrade_to_initial(connection: Connection) -> None:
        config = alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, INITIAL_REVISION)

    async with engine.begin() as connection:
        await connection.run_sync(_upgrade_to_initial)
        await connection.execute(
            text(
                "INSERT INTO jobs (dedup_key, title, company, location, url, source, description,"
                " work_mode, skills, first_seen_at, last_seen_at) VALUES ('k1', 'Dev', 'ACME', '',"
                " 'https://x/1', 'linkedin', '', 'unknown', '[]', '2026-09-01', '2026-09-01')"
            )
        )

    await upgrade_to_head(engine)

    stored = await SqlAlchemyJobStore(create_session_factory(engine)).list_recent()
    assert [(j.title, j.source, j.other_listings) for j in stored] == [("Dev", JobSite.LINKEDIN, ())]
