"""Tradução de erros de domínio em respostas HTTP (JSON na API, HTML nas páginas)."""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from app.domain.exceptions import (
    DomainError,
    JobNotFoundError,
    JobSourceError,
    LLMProviderError,
    LLMResponseFormatError,
    OutreachGenerationError,
    ProfileError,
)

logger = logging.getLogger(__name__)

_STATUS: dict[type[DomainError], int] = {
    JobNotFoundError: 404,
    # a fonte externa falhou: não é erro do cliente nem nosso
    JobSourceError: 502,
    # a aplicação não funciona até o perfil ser configurado
    ProfileError: 503,
    # o LLM respondeu fora do contrato: falha do serviço externo
    LLMResponseFormatError: 502,
    OutreachGenerationError: 502,
    # o LLM não respondeu (fora do ar, quota, timeout); a ordem importa:
    # LLMResponseFormatError é subclasse e precisa vir antes
    LLMProviderError: 503,
}


def register_error_handlers(app: FastAPI, templates: Jinja2Templates) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> Response:
        status = next((code for kind, code in _STATUS.items() if isinstance(exc, kind)), 500)
        if status >= 500:
            logger.warning("%s em %s: %s", type(exc).__name__, request.url.path, exc)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": str(exc)}, status_code=status)
        return templates.TemplateResponse(
            request, "error.html", {"status": status, "message": str(exc)}, status_code=status
        )
