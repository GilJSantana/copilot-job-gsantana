"""Aplicação programática das migrações do Alembic (startup da aplicação e testes)."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config() -> Config:
    """Config independente do alembic.ini: funciona de qualquer diretório de trabalho."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


async def upgrade_to_head(engine: AsyncEngine) -> None:
    """Leva o banco à versão mais recente do esquema (idempotente)."""

    def _upgrade(connection: Connection) -> None:
        config = alembic_config()
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
