"""Raiz de composição: o único lugar que conhece as implementações concretas.

Controllers recebem o `Container` já montado e só falam com services e portas.
Testes trocam as dependências externas (fonte de vagas, LLM, perfil) por
dublês via `Overrides`, mantendo o resto da montagem real.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from app.adapters.configurable_job_repository import ConfigurableJobRepository
from app.adapters.configurable_llm import ConfigurableLLMProvider
from app.adapters.job_repository_factory import build_jobspy_repository, scraper_settings_from_env
from app.adapters.llm_factory import build_llm_adapter, llm_settings_from_env
from app.adapters.local_file_storage import LocalFileStorage
from app.adapters.typst_pdf_adapter import TypstPdfAdapter
from app.core.config import Settings
from app.domain.interfaces import (
    ICareerHistoryRepository,
    IJobRepository,
    IJobStore,
    ILLMProvider,
    IMatchResultStore,
    IProfileRepository,
)
from app.repositories.career_history_repository import JsonCareerHistoryRepository
from app.repositories.cv_version_store import SqlAlchemyCVVersionStore
from app.repositories.database import create_engine, create_session_factory
from app.repositories.job_store import SqlAlchemyJobStore
from app.repositories.match_store import SqlAlchemyMatchResultStore
from app.repositories.migrate import upgrade_to_head
from app.repositories.outreach_store import SqlAlchemyOutreachStore
from app.repositories.profile_block_store import SqlAlchemyProfileBlockStore
from app.repositories.profile_repository import JsonProfileRepository
from app.repositories.prompt_template_store import SqlAlchemyPromptTemplateStore
from app.repositories.system_config_store import SqlAlchemySystemConfigStore
from app.services.cv_optimizer import LLMCVOptimizer
from app.services.cv_tailor_service import CVTailorService
from app.services.job_service import JobService
from app.services.match_engine import MatchEngine
from app.services.match_service import MatchService
from app.services.outreach_service import OutreachService
from app.services.profile_service import ProfileService, StoredCandidateProfiles, StoredCareerHistories
from app.services.prompt_service import PromptService
from app.services.system_settings_service import SystemSettingsService


@dataclass(frozen=True, slots=True)
class Container:
    settings: Settings
    job_service: JobService
    match_service: MatchService
    outreach_service: OutreachService
    cv_tailor_service: CVTailorService
    profile_service: ProfileService
    system_settings: SystemSettingsService
    prompt_service: PromptService
    career_histories: ICareerHistoryRepository
    job_store: IJobStore
    match_store: IMatchResultStore
    profiles: IProfileRepository
    llm: ILLMProvider


@dataclass(frozen=True, slots=True, kw_only=True)
class Overrides:
    job_repository: IJobRepository | None = None
    llm: ILLMProvider | None = None
    profiles: IProfileRepository | None = None
    career_histories: ICareerHistoryRepository | None = None


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
        configs = SqlAlchemySystemConfigStore(session_factory)
        prompts = SqlAlchemyPromptTemplateStore(session_factory)

        profile_service = ProfileService(configs, SqlAlchemyProfileBlockStore(session_factory))
        # migração única: os JSON de perfil viram dados do banco se ele ainda não tiver perfil
        await profile_service.import_legacy(
            JsonProfileRepository(settings.profile_path),
            JsonCareerHistoryRepository(settings.career_history_path),
        )
        career_histories = overrides.career_histories or StoredCareerHistories(profile_service)

        system_settings = SystemSettingsService(
            configs,
            llm_defaults=llm_settings_from_env(settings),
            scraper_defaults=scraper_settings_from_env(settings),
        )
        llm_settings = await system_settings.llm()

        def configurable_llm(timeout_seconds: float) -> ILLMProvider:
            return ConfigurableLLMProvider(
                system_settings.llm,
                initial=llm_settings,
                timeout_seconds=timeout_seconds,
                build=build_llm_adapter,
            )

        llm = overrides.llm or configurable_llm(settings.llm_timeout_seconds)
        # instância própria para o CV: mesmo provedor, tempo limite maior
        cv_llm = overrides.llm or configurable_llm(settings.cv_llm_timeout_seconds)
        # o dublê dos testes também passa pelas regras do painel (plataformas e limite)
        injected = overrides.job_repository
        job_repository = ConfigurableJobRepository(
            system_settings.scrapers,
            (lambda _: injected) if injected else build_jobspy_repository,
        )
        try:
            yield Container(
                settings=settings,
                job_service=JobService(job_repository, job_store),
                match_service=MatchService(MatchEngine(llm, prompts=prompts), match_store),
                outreach_service=OutreachService(llm, SqlAlchemyOutreachStore(session_factory)),
                cv_tailor_service=CVTailorService(
                    career_histories,
                    LLMCVOptimizer(cv_llm, prompts=prompts),
                    TypstPdfAdapter(
                        settings.cv_template_path,
                        pdf_standard=None if settings.cv_pdf_standard == "none" else settings.cv_pdf_standard,
                    ),
                    LocalFileStorage(settings.cv_output_dir),
                    SqlAlchemyCVVersionStore(session_factory),
                ),
                profile_service=profile_service,
                system_settings=system_settings,
                prompt_service=PromptService(prompts),
                career_histories=career_histories,
                job_store=job_store,
                match_store=match_store,
                profiles=overrides.profiles or StoredCandidateProfiles(profile_service),
                llm=llm,
            )
        finally:
            await llm.aclose()
            if cv_llm is not llm:
                await cv_llm.aclose()
    finally:
        await engine.dispose()
