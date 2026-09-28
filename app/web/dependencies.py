"""Dependências do FastAPI compartilhadas entre a API JSON e as páginas HTML."""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request

from app.domain.exceptions import JobNotFoundError, ProfileError
from app.domain.models import CandidateProfile, JobPosting, MatchResult
from app.web.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_job_or_404(key: str, container: ContainerDep) -> JobPosting:
    job = await container.job_store.get(key)
    if job is None:
        raise JobNotFoundError(f"vaga {key} não encontrada")
    return job


JobDep = Annotated[JobPosting, Depends(get_job_or_404)]


async def profile_or_none(container: Container) -> CandidateProfile | None:
    """Para telas que funcionam sem perfil (listagens): só não comparam os matches."""
    try:
        return await container.profiles.get()
    except ProfileError:
        return None


async def matches_for(container: Container, jobs: list[JobPosting]) -> dict[str, MatchResult]:
    return await container.match_store.get_many([job.dedup_key for job in jobs])


def require_same_origin(request: Request) -> None:
    """Bloqueia formulários enviados por outros sites (CSRF).

    Sem isso, qualquer página aberta no navegador poderia postar para
    localhost e disparar buscas ou chamadas pagas ao LLM. Navegadores sempre
    enviam `Origin` (ou ao menos `Referer`) em POSTs de formulário.
    """
    sender = request.headers.get("origin") or request.headers.get("referer")
    if sender is None or urlsplit(sender).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail="Requisição de outra origem bloqueada")


def reject_cross_origin(request: Request) -> None:
    """CSRF na API: recusa requisições que um navegador enviou a partir de outro site.

    Diferente de `require_same_origin`, não exige o cabeçalho: clientes como
    curl e scripts não enviam `Origin`, e navegadores sempre o enviam em POSTs
    de outro site. Necessário porque há endpoints sem corpo JSON (ex.: o match),
    que um formulário comum de outro site conseguiria chamar.
    """
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != request.url.netloc:
        raise HTTPException(status_code=403, detail="Requisição de outra origem bloqueada")
