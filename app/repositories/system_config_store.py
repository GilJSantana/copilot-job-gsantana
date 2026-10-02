"""Implementação SQLAlchemy da porta `ISystemConfigStore`."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.interfaces import ISystemConfigStore
from app.repositories.database import SessionFactory, write_transaction
from app.repositories.orm import SystemConfigRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemySystemConfigStore(ISystemConfigStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def get_many(self, prefix: str) -> dict[str, str]:
        # startswith escapa % e _ (comuns em chaves): o LIKE puro os trataria como curinga
        query = select(SystemConfigRow).where(SystemConfigRow.key.startswith(prefix, autoescape=True))
        async with self._session_factory() as session:
            return {row.key: row.value for row in await session.scalars(query)}

    async def set_many(self, values: dict[str, str], descriptions: dict[str, str] | None = None) -> None:
        if not values:
            return
        descriptions = descriptions or {}
        now = self._clock()
        # lê e depois grava: a reserva de escrita evita duas inserções da mesma chave
        async with write_transaction(self._session_factory) as session:
            query = select(SystemConfigRow).where(SystemConfigRow.key.in_(values))
            existing = {row.key: row for row in await session.scalars(query)}
            for key, value in values.items():
                row = existing.get(key)
                if row is None:
                    session.add(
                        SystemConfigRow(
                            key=key, value=value, description=descriptions.get(key), updated_at=now
                        )
                    )
                    continue
                if row.value != value:
                    row.value = value
                    row.updated_at = now
                if key in descriptions:
                    row.description = descriptions[key]
