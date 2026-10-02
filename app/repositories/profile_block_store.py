"""Implementação SQLAlchemy da porta `IProfileBlockStore`."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select

from app.domain.exceptions import ProfileBlockNotFoundError
from app.domain.interfaces import IProfileBlockStore
from app.domain.models import ProfileBlock, ProfileBlockCategory
from app.repositories.database import SessionFactory
from app.repositories.orm import ProfileCoreRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyProfileBlockStore(IProfileBlockStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def list_all(self, category: ProfileBlockCategory | None = None) -> list[ProfileBlock]:
        query = select(ProfileCoreRow).order_by(ProfileCoreRow.id)
        if category is not None:
            query = query.where(ProfileCoreRow.category == category.value)
        async with self._session_factory() as session:
            return [_to_domain(row) for row in await session.scalars(query)]

    async def get(self, block_id: int) -> ProfileBlock | None:
        async with self._session_factory() as session:
            row = await session.get(ProfileCoreRow, block_id)
            return _to_domain(row) if row else None

    async def save(self, block: ProfileBlock) -> ProfileBlock:
        saved = replace(block, updated_at=self._clock())
        async with self._session_factory.begin() as session:
            if saved.id is None:
                row = ProfileCoreRow()
                session.add(row)
            else:
                row = await session.get(ProfileCoreRow, saved.id)
                if row is None:
                    raise ProfileBlockNotFoundError(f"bloco {saved.id} não encontrado")
            _fill(row, saved)
            await session.flush()  # gera o id dos blocos novos
            return replace(saved, id=row.id)

    async def delete(self, block_id: int) -> None:
        async with self._session_factory.begin() as session:
            row = await session.get(ProfileCoreRow, block_id)
            if row is None:
                raise ProfileBlockNotFoundError(f"bloco {block_id} não encontrado")
            await session.delete(row)

    async def add_many(self, blocks: list[ProfileBlock]) -> None:
        now = self._clock()
        async with self._session_factory.begin() as session:
            for block in blocks:
                row = ProfileCoreRow()
                _fill(row, replace(block, updated_at=now))
                session.add(row)


def _fill(row: ProfileCoreRow, block: ProfileBlock) -> None:
    row.category = block.category.value
    row.title = block.title
    row.content = block.content
    row.is_active = block.is_active
    row.updated_at = block.updated_at


def _to_domain(row: ProfileCoreRow) -> ProfileBlock:
    return ProfileBlock(
        id=row.id,
        category=ProfileBlockCategory(row.category),
        title=row.title,
        content=row.content,
        is_active=row.is_active,
        # SQLite devolve datetime sem fuso; o valor gravado é sempre UTC
        updated_at=row.updated_at.replace(tzinfo=UTC),
    )
