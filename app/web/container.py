"""Raiz de composição: o único lugar que conhece as implementações concretas.

Controllers recebem o `Container` já montado e só falam com services e portas.
Testes trocam as dependências externas (fonte de vagas, LLM, perfil) por
dublês via `Overrides`, mantendo o resto da montagem real.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.adapters.job_repository_factory import build_job_repository
from app.adapters.llm_factory import build_llm_provider
from app.core.config import Settings
from app.domain.interfaces import (
    IJobRepository,
    IJobStore,
    ILLMProvider,
    IMatchResultStore,
    IProfileRepository,
)
from app.repositories.database import create_engine, create_session_factory
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.match_store import SqlAlchemyMatchResultStore
from app.repositories.migrate import upgrade_to_head
from app.repositories.outreach_store import SqlAlchemyOutreachStore
from app.repositories.profile_repository import JsonProfileRepository
from app.services.job_service import JobService
from app.services.match_engine import MatchEngine
from app.services.match_service import MatchService
from app.services.outreach_service import OutreachService


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    job_service: JobService
    match_service: MatchService
    outreach_service: OutreachService
    job_store: IJobStore
    match_store: IMatchResultStore
    profiles: IProfileRepository
    llm: ILLMProvider


@dataclass(frozen=True, slots=True, kw_only=True)
class Overrides:
    job_repository: IJobRepository | None = None
    llm: ILLMProvider | None = None
    profiles: IProfileRepository | None = None


@asynccontextmanager
async def build_container(
    settings: Settings, overrides: Overrides | None = None
) -> AsyncIterator[Container]:
    """Monta as dependências e as libera ao sair (conexões HTTP e do banco)."""
    overrides = overrides or Overrides()
    engine = create_engine(settings.database_url)
    try:
        await upgrade_to_head(engine)
        session_factory = create_session_factory(engine)
        job_store = SqlAlchemyJobStore(session_factory)
        match_store = SqlAlchemyMatchResultStore(session_factory)
        llm = overrides.llm or build_llm_provider(settings)
        try:
            yield Container(
                settings=settings,
                job_service=JobService(
                    overrides.job_repository or build_job_repository(settings), job_store
                ),
                match_service=MatchService(MatchEngine(llm), match_store),
                outreach_service=OutreachService(llm, SqlAlchemyOutreachStore(session_factory)),
                job_store=job_store,
                match_store=match_store,
                profiles=overrides.profiles or JsonProfileRepository(settings.profile_path),
                llm=llm,
            )
        finally:
            await llm.aclose()
    finally:
        await engine.dispose()
