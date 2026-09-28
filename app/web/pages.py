"""Páginas HTML (Jinja2 + Tailwind)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.domain.exceptions import JobSourceError, ProfileError
from app.domain.models import JobSite, OutreachChannel, OutreachLanguage
from app.web.dependencies import (
    ContainerDep,
    JobDep,
    matches_for,
    profile_or_none,
    require_same_origin,
)
from app.web.schemas import JobDetailOut, JobSummaryOut, OutreachOut, SearchIn

PAGE_SIZE = 25

_DEFAULT_FORM: dict[str, Any] = {
    "search_term": "",
    "location": "",
    "sites": [JobSite.LINKEDIN.value, JobSite.INDEED.value],
    "results_wanted": 20,
    "hours_old": 72,
    "remote_only": False,
}


def build_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(include_in_schema=False)

    def render(request: Request, name: str, context: dict[str, Any], status: int = 200) -> HTMLResponse:
        return templates.TemplateResponse(request, name, context, status_code=status)

    @router.get("/")
    async def index(request: Request, container: ContainerDep, page: int = 1) -> HTMLResponse:
        page = max(page, 1)
        jobs = await container.job_store.list_recent(
            limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
        )
        has_next = len(jobs) > PAGE_SIZE
        jobs = jobs[:PAGE_SIZE]
        matches = await matches_for(container, jobs)
        profile = await profile_or_none(container)
        return render(
            request,
            "index.html",
            {
                "form": _DEFAULT_FORM,
                "jobs": [
                    JobSummaryOut.from_domain(j, match=matches.get(j.dedup_key), profile=profile)
                    for j in jobs
                ],
                "page": page,
                "has_next": has_next,
            },
        )

    @router.post("/search", dependencies=[Depends(require_same_origin)])
    async def search(
        request: Request,
        container: ContainerDep,
        search_term: Annotated[str, Form()] = "",
        location: Annotated[str, Form()] = "",
        sites: Annotated[list[str], Form()] = [],  # noqa: B006 — FastAPI copia o default
        results_wanted: Annotated[str, Form()] = "20",
        hours_old: Annotated[str, Form()] = "",
        remote_only: Annotated[bool, Form()] = False,
    ) -> HTMLResponse:
        form = {
            "search_term": search_term,
            "location": location,
            "sites": sites,
            "results_wanted": results_wanted,
            "hours_old": hours_old,
            "remote_only": remote_only,
        }

        def fail(message: str, status: int) -> HTMLResponse:
            return render(request, "index.html", {"form": form, "jobs": [], "error": message}, status)

        try:
            body = SearchIn(
                search_term=search_term,
                location=location,
                sites=sites,
                results_wanted=results_wanted,
                hours_old=hours_old or None,
                remote_only=remote_only,
            )
        except ValidationError as exc:
            return fail(_describe_validation_error(exc), 422)

        try:
            result = await container.job_service.search(body.to_criteria())
        except JobSourceError as exc:
            return fail(f"Nenhuma fonte respondeu: {exc}", 502)

        jobs = list(result.jobs)
        matches = await matches_for(container, jobs)
        profile = await profile_or_none(container)
        return render(
            request,
            "index.html",
            {
                "form": form,
                "result": result,
                "jobs": [
                    JobSummaryOut.from_domain(
                        j,
                        match=matches.get(j.dedup_key),
                        profile=profile,
                        is_new=j.dedup_key in result.new_keys,
                    )
                    for j in jobs
                ],
            },
        )

    @router.get("/jobs/{key}")
    async def job_detail(request: Request, job: JobDep, container: ContainerDep) -> HTMLResponse:
        match = await container.match_store.get(job.dedup_key)
        try:
            profile = await container.profiles.get()
            profile_error = None
        except ProfileError as exc:
            profile, profile_error = None, str(exc)
        drafts = await container.outreach_service.history(job)
        return render(
            request,
            "job_detail.html",
            {
                "job": JobDetailOut.from_domain(job, match=match, profile=profile),
                "profile_error": profile_error,
                "drafts": [OutreachOut.from_domain(d, profile) for d in drafts],
                "channels": list(OutreachChannel),
                "languages": list(OutreachLanguage),
            },
        )

    @router.post("/jobs/{key}/match", dependencies=[Depends(require_same_origin)])
    async def match_job(
        job: JobDep,
        container: ContainerDep,
        force: Annotated[bool, Form()] = False,
    ) -> Response:
        profile = await container.profiles.get()
        await container.match_service.match(profile, job, force=force)
        # POST/redirect/GET: recarregar a página não refaz a análise
        return RedirectResponse(f"/jobs/{job.dedup_key}", status_code=303)

    @router.post("/jobs/{key}/outreach", dependencies=[Depends(require_same_origin)])
    async def draft_outreach(
        job: JobDep,
        container: ContainerDep,
        channel: Annotated[OutreachChannel, Form()],
        language: Annotated[OutreachLanguage, Form()] = OutreachLanguage.PT,
        recipient_name: Annotated[str, Form(max_length=100)] = "",
    ) -> Response:
        profile = await container.profiles.get()
        await container.outreach_service.draft(
            profile,
            job,
            channel=channel,
            language=language,
            match=await container.match_store.get(job.dedup_key),
            recipient_name=recipient_name or None,
        )
        return RedirectResponse(f"/jobs/{job.dedup_key}#outreach", status_code=303)

    return router


_FIELD_LABELS = {
    "search_term": "Cargo ou palavra-chave",
    "location": "Local",
    "sites": "Sites",
    "results_wanted": "Vagas por site",
    "hours_old": "Publicadas nas últimas (horas)",
}


def _describe_validation_error(exc: ValidationError) -> str:
    problems = []
    for error in exc.errors():
        field = str(error["loc"][0]) if error["loc"] else ""
        problems.append(f"{_FIELD_LABELS.get(field, field)}: {error['msg']}")
    return "Verifique o formulário — " + "; ".join(problems)

