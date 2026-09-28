"""Engine e sessões assíncronas do SQLAlchemy para SQLite."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import Connection, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SessionFactory = async_sessionmaker[AsyncSession]

_WRITE_LOCK = "copilot_sqlite_write_lock"


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Cria o engine e assume o controle das transações e PRAGMAs do SQLite."""
    options: dict[str, Any] = {"echo": echo}
    if ":memory:" in url:
        # sem StaticPool cada conexão veria um banco em memória diferente (e vazio)
        options["poolclass"] = StaticPool
    engine = create_async_engine(url, **options)

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _: Any) -> None:
        # O driver sqlite3 abre transações por conta própria e sempre DEFERRED.
        # Desligando isso, o BEGIN passa a ser emitido por nós (ver _on_begin).
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")  # FKs são ignoradas sem isso
        cursor.execute("PRAGMA journal_mode=WAL")  # leitura não bloqueia escrita
        cursor.execute("PRAGMA busy_timeout=5000")  # espera a trava em vez de falhar
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _on_begin(connection: Connection) -> None:
        immediate = connection.get_execution_options().get(_WRITE_LOCK, False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    return engine


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    # expire_on_commit=False: objetos continuam legíveis após o commit
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def write_transaction(session_factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Transação que reserva a escrita no banco já no BEGIN (BEGIN IMMEDIATE).

    Use quando a transação lê e depois grava com base no que leu: sem a
    reserva, duas transações concorrentes leem o mesmo estado e ambas gravam
    (ex.: as duas inserem a mesma vaga "nova"). Com ela, a segunda espera a
    primeira terminar (até o busy_timeout) e já lê o estado atualizado.
    """
    async with session_factory() as session, session.begin():
        await session.connection(execution_options={_WRITE_LOCK: True})
        yield session
