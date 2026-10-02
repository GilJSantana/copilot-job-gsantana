"""Implementação SQLAlchemy da porta `ICVVersionStore`."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import ICVVersionStore
from app.domain.models import CVVersion, OutreachLanguage, TailoredCV, TailoredExperience
from app.repositories.database import SessionFactory
from app.repositories.orm import CVVersionRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyCVVersionStore(ICVVersionStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def save(self, version: CVVersion) -> CVVersion:
        saved = replace(version, created_at=self._clock())
        cv = saved.content
        row = CVVersionRow(
            id=saved.id,
            job_key=saved.job_key,
            language=cv.language.value,
            headline=cv.headline,
            summary=cv.summary,
            skills=list(cv.skills),
            experiences=[
                {"experience_id": t.experience_id, "highlights": list(t.highlights)}
                for t in cv.experiences
            ],
            matched_keywords=list(cv.matched_keywords),
            history_fingerprint=saved.history_fingerprint,
            template=saved.template,
            pdf_path=saved.pdf_path,
            provider=saved.provider,
            created_at=saved.created_at,
        )
        try:
            async with self._session_factory.begin() as session:
                session.add(row)
        except IntegrityError as exc:
            # ids são uuid4: a restrição que falha na prática é a FK para jobs
            raise JobNotFoundError(f"vaga {saved.job_key} não está armazenada") from exc
        return saved

    async def get(self, version_id: str) -> CVVersion | None:
        async with self._session_factory() as session:
            row = await session.get(CVVersionRow, version_id)
            return _to_domain(row) if row else None

    async def list_for_job(self, job_key: str) -> list[CVVersion]:
        query = (
            select(CVVersionRow)
            .where(CVVersionRow.job_key == job_key)
            .order_by(CVVersionRow.created_at.desc(), CVVersionRow.id.desc())
        )
        async with self._session_factory() as session:
            return [_to_domain(row) for row in await session.scalars(query)]


    async def referenced_files(self) -> set[str]:
        async with self._session_factory() as session:
            return set(await session.scalars(select(CVVersionRow.pdf_path)))


def _to_domain(row: CVVersionRow) -> CVVersion:
    return CVVersion(
        id=row.id,
        job_key=row.job_key,
        content=TailoredCV(
            language=OutreachLanguage(row.language),
            headline=row.headline,
            summary=row.summary,
            skills=tuple(row.skills),
            experiences=tuple(
                TailoredExperience(experience_id=e["experience_id"], highlights=tuple(e["highlights"]))
                for e in row.experiences
            ),
            matched_keywords=tuple(row.matched_keywords),
        ),
        history_fingerprint=row.history_fingerprint,
        template=row.template,
        pdf_path=row.pdf_path,
        provider=row.provider,
        # SQLite devolve datetime sem fuso; o valor gravado é sempre UTC
        created_at=row.created_at.replace(tzinfo=UTC),
    )
