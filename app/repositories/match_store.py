"""Implementação SQLAlchemy da porta `IMatchResultStore`."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import JobNotFoundError
from app.domain.interfaces import IMatchResultStore
from app.domain.models import MatchResult
from app.repositories.database import SessionFactory
from app.repositories.orm import MatchResultRow


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyMatchResultStore(IMatchResultStore):
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def save(self, result: MatchResult) -> None:
        values = {
            "job_key": result.job_key,
            "score": result.score,
            "keyword_score": result.keyword_score,
            "llm_score": result.llm_score,
            "matched_skills": list(result.matched_skills),
            "strengths": list(result.strengths),
            "gaps": list(result.gaps),
            "rationale": result.rationale,
            "provider": result.provider,
            "profile_fingerprint": result.profile_fingerprint,
            "evaluated_at": self._clock(),
        }
        # Upsert nativo: substituir o match é uma operação atômica, sem corrida
        # entre "já existe?" e "insere/atualiza".
        statement = insert(MatchResultRow).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[MatchResultRow.job_key],
            set_={key: statement.excluded[key] for key in values if key != "job_key"},
        )
        try:
            async with self._session_factory.begin() as session:
                await session.execute(statement)
        except IntegrityError as exc:
            # a única restrição que pode falhar aqui é a FK para jobs
            raise JobNotFoundError(f"vaga {result.job_key} não está armazenada") from exc

    async def get(self, job_key: str) -> MatchResult | None:
        async with self._session_factory() as session:
            row = await session.get(MatchResultRow, job_key)
            return _to_domain(row) if row else None

    async def get_many(self, job_keys: list[str]) -> dict[str, MatchResult]:
        if not job_keys:
            return {}
        query = select(MatchResultRow).where(MatchResultRow.job_key.in_(job_keys))
        async with self._session_factory() as session:
            return {row.job_key: _to_domain(row) for row in await session.scalars(query)}


def _to_domain(row: MatchResultRow) -> MatchResult:
    return MatchResult(
        job_key=row.job_key,
        score=row.score,
        keyword_score=row.keyword_score,
        llm_score=row.llm_score,
        matched_skills=tuple(row.matched_skills),
        strengths=tuple(row.strengths),
        gaps=tuple(row.gaps),
        rationale=row.rationale,
        provider=row.provider,
        profile_fingerprint=row.profile_fingerprint,
    )
