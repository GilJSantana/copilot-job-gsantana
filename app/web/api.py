"""API JSON (/api)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.web.dependencies import (
    ContainerDep,
    JobDep,
    matches_for,
    profile_or_none,
    reject_cross_origin,
)
from app.web.schemas import (
    HealthOut,
    JobDetailOut,
    JobSummaryOut,
    MatchOut,
    OutreachIn,
    OutreachOut,
    ProfileOut,
    SearchIn,
    SearchOut,
)

router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(reject_cross_origin)])


@router.get("/health")
async def health(container: ContainerDep) -> HealthOut:
    return HealthOut(status="ok", llm_provider=container.llm.name)


@router.get("/profile")
async def get_profile(container: ContainerDep) -> ProfileOut:
    return ProfileOut.from_domain(await container.profiles.get())


@router.post("/searches")
async def search_jobs(body: SearchIn, container: ContainerDep) -> SearchOut:
    """Busca vagas nas fontes, remove duplicatas e grava. Pode levar minutos
    (delay entre sites + descrição completa do LinkedIn)."""
    result = await container.job_service.search(body.to_criteria())
    jobs = list(result.jobs)
    matches = await matches_for(container, jobs)
    profile = await profile_or_none(container)
    return SearchOut(
        total_fetched=result.total_fetched,
        duplicates_removed=result.duplicates_removed,
        new_count=len(result.new_keys),
        jobs=[
            JobSummaryOut.from_domain(
                job,
                match=matches.get(job.dedup_key),
                profile=profile,
                is_new=job.dedup_key in result.new_keys,
            )
            for job in jobs
        ],
    )


@router.get("/jobs")
async def list_jobs(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobSummaryOut]:
    jobs = await container.job_store.list_recent(limit=limit, offset=offset)
    matches = await matches_for(container, jobs)
    profile = await profile_or_none(container)
    return [
        JobSummaryOut.from_domain(job, match=matches.get(job.dedup_key), profile=profile)
        for job in jobs
    ]


@router.get("/jobs/{key}")
async def get_job(job: JobDep, container: ContainerDep) -> JobDetailOut:
    match = await container.match_store.get(job.dedup_key)
    return JobDetailOut.from_domain(job, match=match, profile=await profile_or_none(container))


@router.post("/jobs/{key}/match")
async def match_job(job: JobDep, container: ContainerDep, force: bool = False) -> MatchOut:
    """Match perfil x vaga. Reaproveita o resultado salvo se ainda for válido."""
    profile = await container.profiles.get()
    result = await container.match_service.match(profile, job, force=force)
    return MatchOut.from_domain(result, profile)


@router.post("/jobs/{key}/outreach")
async def draft_outreach(job: JobDep, body: OutreachIn, container: ContainerDep) -> OutreachOut:
    """Gera um rascunho de mensagem para recrutador. Cada chamada cria um novo
    rascunho (os anteriores ficam no histórico)."""
    profile = await container.profiles.get()
    message = await container.outreach_service.draft(
        profile,
        job,
        channel=body.channel,
        language=body.language,
        match=await container.match_store.get(job.dedup_key),
        recipient_name=body.recipient_name,
    )
    return OutreachOut.from_domain(message, profile)


@router.get("/jobs/{key}/outreach")
async def list_outreach(job: JobDep, container: ContainerDep) -> list[OutreachOut]:
    profile = await profile_or_none(container)
    return [OutreachOut.from_domain(m, profile) for m in await container.outreach_service.history(job)]
