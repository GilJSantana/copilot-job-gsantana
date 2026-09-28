"""Ambiente do Alembic.

Dois modos de execução:
  * CLI (`uv run alembic upgrade head`): conecta em `Settings.database_url`.
  * Programático (`app.repositories.migrate.upgrade_to_head`): recebe uma
    conexão já aberta em `config.attributes["connection"]` e a reutiliza —
    é assim que a aplicação e os testes (inclusive com banco em memória)
    aplicam as migrações.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from app.core.config import Settings
from app.repositories.database import create_engine
from app.repositories.orm import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        # SQLite não suporta a maioria dos ALTER TABLE: "batch" recria a tabela
        render_as_batch=True,
        compare_type=True,
        literal_binds=connection is None,
    )


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or Settings().database_url


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar (`alembic upgrade head --sql`)."""
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_engine(_database_url())
    async with engine.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
