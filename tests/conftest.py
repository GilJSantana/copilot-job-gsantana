import pytest

from app.repositories.database import SessionFactory, create_engine, create_session_factory
from app.repositories.migrate import upgrade_to_head


@pytest.fixture
async def session_factory() -> SessionFactory:
    """Banco SQLite em memória, criado pelas migrações reais, novo a cada teste."""
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await upgrade_to_head(engine)
    yield create_session_factory(engine)
    await engine.dispose()
