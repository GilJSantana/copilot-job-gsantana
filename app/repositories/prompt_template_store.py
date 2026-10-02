"""Implementação SQLAlchemy da porta `IPromptTemplateStore`."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.domain.interfaces import IPromptTemplateStore
from app.domain.models import PromptName, PromptTemplate
from app.repositories.database import SessionFactory, write_transaction
from app.repositories.orm import PromptTemplateRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyPromptTemplateStore(IPromptTemplateStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def get(self, name: PromptName) -> PromptTemplate | None:
        query = select(PromptTemplateRow).where(PromptTemplateRow.name == name.value)
        async with self._session_factory() as session:
            row = await session.scalar(query)
            return _to_domain(row) if row else None

    async def save(self, template: PromptTemplate) -> PromptTemplate:
        saved = replace(template, updated_at=self._clock())
        async with write_transaction(self._session_factory) as session:
            query = select(PromptTemplateRow).where(PromptTemplateRow.name == saved.name.value)
            row = await session.scalar(query)
            if row is None:
                row = PromptTemplateRow(name=saved.name.value)
                session.add(row)
            row.template_text = saved.template_text
            row.is_active = saved.is_active
            row.updated_at = saved.updated_at
        return saved

    async def delete(self, name: PromptName) -> None:
        async with self._session_factory.begin() as session:
            await session.execute(delete(PromptTemplateRow).where(PromptTemplateRow.name == name.value))


def _to_domain(row: PromptTemplateRow) -> PromptTemplate:
    return PromptTemplate(
        name=PromptName(row.name),
        template_text=row.template_text,
        is_active=row.is_active,
        updated_at=row.updated_at.replace(tzinfo=UTC),
    )
