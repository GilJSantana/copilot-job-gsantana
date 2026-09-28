"""Implementação SQLAlchemy da porta `IOutreachStore`."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import IOutreachStore
from app.domain.models import OutreachChannel, OutreachLanguage, OutreachMessage
from app.repositories.database import SessionFactory
from app.repositories.orm import OutreachRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyOutreachStore(IOutreachStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def save(self, message: OutreachMessage) -> OutreachMessage:
        saved = replace(message, created_at=self._clock())
        row = OutreachRow(
            job_key=saved.job_key,
            channel=saved.channel.value,
            language=saved.language.value,
            subject=saved.subject,
            body=saved.body,
            provider=saved.provider,
            profile_fingerprint=saved.profile_fingerprint,
            created_at=saved.created_at,
        )
        try:
            async with self._session_factory.begin() as session:
                session.add(row)
        except IntegrityError as exc:
            # a única restrição que pode falhar aqui é a FK para jobs
            raise JobNotFoundError(f"vaga {saved.job_key} não está armazenada") from exc
        return saved

    async def list_for_job(self, job_key: str) -> list[OutreachMessage]:
        # id desc: desempata rascunhos gravados no mesmo instante
        query = (
            select(OutreachRow)
            .where(OutreachRow.job_key == job_key)
            .order_by(OutreachRow.created_at.desc(), OutreachRow.id.desc())
        )
        async with self._session_factory() as session:
            return [_to_domain(row) for row in await session.scalars(query)]


def _to_domain(row: OutreachRow) -> OutreachMessage:
    return OutreachMessage(
        job_key=row.job_key,
        channel=OutreachChannel(row.channel),
        language=OutreachLanguage(row.language),
        subject=row.subject,
        body=row.body,
        provider=row.provider,
        profile_fingerprint=row.profile_fingerprint,
        # SQLite devolve datetime sem fuso; o valor gravado é sempre UTC
        created_at=row.created_at.replace(tzinfo=UTC),
    )
