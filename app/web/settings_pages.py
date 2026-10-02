"""Painel de configurações (/settings): perfil, provedores de IA e conectores.

Formulários HTML comuns com POST/redirect/GET. Em erro de validação a página é
renderizada de novo (422) com a mensagem e os valores enviados, para não perder
o que foi digitado.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.domain.models import (
    LLMProviderKind,
    OutreachLanguage,
    ProfileBlockCategory,
    PromptName,
    WorkMode,
)
from app.web.container import Container
from app.web.dependencies import ContainerDep, require_same_origin
from app.web.settings_forms import (
    BlockForm,
    DetailsForm,
    ExperienceForm,
    LLMForm,
    PromptForm,
    ScrapersForm,
    describe_errors,
    form_dict,
    mask_secret,
)

# mensagens exibidas após um redirect bem-sucedido (?saved=<chave>)
_SAVED_MESSAGES = {
    "details": "Dados do perfil salvos.",
    "experience": "Experiência salva.",
    "skill": "Competência salva.",
    "metric": "Conquista salva.",
    "deleted": "Item removido.",
    "llm": "Provedor de IA salvo. Vale a partir da próxima análise.",
    "prompt": "Prompt salvo.",
    "prompt-reset": "Prompt restaurado para o padrão.",
    "scrapers": "Conectores salvos. Valem a partir da próxima busca.",
}
# categoria de bloco simples -> (chave da mensagem, âncora da seção)
_BLOCK_SECTIONS = {
    ProfileBlockCategory.SKILL: ("skill", "skills"),
    ProfileBlockCategory.METRIC: ("metric", "metrics"),
}


def build_settings_router(templates: Jinja2Templates) -> APIRouter:
    router = APIRouter(prefix="/settings", include_in_schema=False)
    protected = [Depends(require_same_origin)]

    def render(
        request: Request, name: str, tab: str, context: dict[str, Any], status: int = 200
    ) -> HTMLResponse:
        saved = _SAVED_MESSAGES.get(request.query_params.get("saved", ""))
        return templates.TemplateResponse(
            request, name, {"tab": tab, "saved": saved} | context, status_code=status
        )

    def redirect(path: str, saved: str, anchor: str = "") -> RedirectResponse:
        return RedirectResponse(f"{path}?saved={saved}{'#' + anchor if anchor else ''}", status_code=303)

    @router.get("")
    async def settings_home() -> Response:
        return RedirectResponse("/settings/profile", status_code=307)

    # --- Perfil profissional ----------------------------------------------------------

    async def render_profile(
        request: Request, container: Container, *, status: int = 200, **overrides: Any
    ) -> HTMLResponse:
        service = container.profile_service
        experiences = await service.experiences()
        context: dict[str, Any] = {
            "details": DetailsForm.values_from(await service.details()),
            "experiences": [
                {"block": block, "fields": ExperienceForm.values_from(experience)}
                for block, experience in experiences
            ],
            "skills": await service.blocks(ProfileBlockCategory.SKILL),
            "metrics": await service.blocks(ProfileBlockCategory.METRIC),
            "work_modes": [m for m in WorkMode if m is not WorkMode.UNKNOWN],
            "languages": list(OutreachLanguage),
            "new_experience": {},
            "error": None,
            "error_target": None,
        }
        return render(request, "settings/profile.html", "profile", context | overrides, status)

    @router.get("/profile")
    async def profile_page(request: Request, container: ContainerDep) -> HTMLResponse:
        return await render_profile(request, container)

    @router.post("/profile/details", dependencies=protected)
    async def save_details(request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form(), "preferred_work_modes")
        try:
            details = DetailsForm.model_validate(data).to_domain()
        except (ValidationError, ValueError) as exc:
            return await render_profile(
                request, container, status=422, details=data,
                error=describe_errors(exc), error_target="details",
            )
        await container.profile_service.save_details(details)
        return redirect("/settings/profile", "details", "details")

    @router.post("/profile/experiences", dependencies=protected)
    async def create_experience(request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form())
        service = container.profile_service
        try:
            form = ExperienceForm.model_validate(data)
            experience_id = form.id.strip() or await service.suggest_experience_id(form.company)
            await service.save_experience(form.to_domain(experience_id), is_active=form.is_active)
        except (ValidationError, ValueError) as exc:
            return await render_profile(
                request, container, status=422, new_experience=data,
                error=describe_errors(exc), error_target="new-experience",
            )
        return redirect("/settings/profile", "experience", "experiences")

    @router.post("/profile/experiences/{block_id}", dependencies=protected)
    async def update_experience(block_id: int, request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form())
        service = container.profile_service
        current = await service.experience(block_id)  # 404 se não existir
        try:
            form = ExperienceForm.model_validate(data)
            await service.save_experience(form.to_domain(current.id), block_id=block_id, is_active=form.is_active)
        except (ValidationError, ValueError) as exc:
            return await render_profile(
                request, container, status=422,
                error=describe_errors(exc), error_target=f"experience-{block_id}",
            )
        return redirect("/settings/profile", "experience", f"experience-{block_id}")

    @router.post("/profile/blocks", dependencies=protected)
    async def create_block(request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form())
        category = _simple_category(data.get("category", ""))
        saved, anchor = _BLOCK_SECTIONS[category]
        try:
            form = BlockForm.model_validate(data | {"is_active": True})
            await container.profile_service.save_block(category, form.title, form.content)
        except (ValidationError, ValueError) as exc:
            return await render_profile(
                request, container, status=422, error=describe_errors(exc), error_target=anchor
            )
        return redirect("/settings/profile", saved, anchor)

    @router.post("/profile/blocks/{block_id}", dependencies=protected)
    async def update_block(block_id: int, request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form())
        category = _simple_category(data.get("category", ""))
        saved, anchor = _BLOCK_SECTIONS[category]
        try:
            form = BlockForm.model_validate(data)
            await container.profile_service.save_block(
                category, form.title, form.content, block_id=block_id, is_active=form.is_active
            )
        except (ValidationError, ValueError) as exc:
            return await render_profile(
                request, container, status=422, error=describe_errors(exc), error_target=anchor
            )
        return redirect("/settings/profile", saved, anchor)

    @router.post("/profile/blocks/{block_id}/toggle", dependencies=protected)
    async def toggle_block(block_id: int, container: ContainerDep) -> Response:
        service = container.profile_service
        block = await service.set_active(block_id, not (await service.block(block_id)).is_active)
        return redirect("/settings/profile", _saved_key(block.category), _anchor(block.category, block_id))

    @router.post("/profile/blocks/{block_id}/delete", dependencies=protected)
    async def delete_block(block_id: int, container: ContainerDep) -> Response:
        block = await container.profile_service.block(block_id)
        await container.profile_service.delete_block(block_id)
        return redirect("/settings/profile", "deleted", _anchor(block.category))

    # --- Provedores de IA & prompts ---------------------------------------------------

    async def render_llm(
        request: Request, container: Container, *, status: int = 200, **overrides: Any
    ) -> HTMLResponse:
        settings = await container.system_settings.llm()
        context: dict[str, Any] = {
            "llm": {
                "provider": settings.provider.value,
                "gemini_model": settings.gemini_model,
                "ollama_base_url": settings.ollama_base_url,
                "ollama_model": settings.ollama_model,
            },
            "masked_key": mask_secret(settings.gemini_api_key),
            "providers": list(LLMProviderKind),
            "prompts": await container.prompt_service.list_all(),
            "prompt_drafts": {},
            "error": None,
            "error_target": None,
        }
        return render(request, "settings/llm.html", "llm", context | overrides, status)

    @router.get("/llm")
    async def llm_page(request: Request, container: ContainerDep) -> HTMLResponse:
        return await render_llm(request, container)

    @router.post("/llm", dependencies=protected)
    async def save_llm(request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form())
        service = container.system_settings
        try:
            settings = LLMForm.model_validate(data).to_domain(await service.llm())
        except (ValidationError, ValueError) as exc:
            # a chave digitada nunca volta para o navegador
            safe = {k: v for k, v in data.items() if k != "gemini_api_key"}
            return await render_llm(
                request, container, status=422, llm=safe,
                error=describe_errors(exc), error_target="provider",
            )
        await service.save_llm(settings)
        return redirect("/settings/llm", "llm", "provider")

    @router.post("/llm/prompts/{name}", dependencies=protected)
    async def save_prompt(name: PromptName, request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form())
        try:
            form = PromptForm.model_validate(data)
        except ValidationError as exc:
            return await render_llm(
                request, container, status=422, prompt_drafts={name: data.get("template_text", "")},
                error=describe_errors(exc), error_target=name.value,
            )
        await container.prompt_service.save(name, form.template_text)
        return redirect("/settings/llm", "prompt", name.value)

    @router.post("/llm/prompts/{name}/reset", dependencies=protected)
    async def reset_prompt(name: PromptName, container: ContainerDep) -> Response:
        await container.prompt_service.reset(name)
        return redirect("/settings/llm", "prompt-reset", name.value)

    # --- Conectores & rate limits -----------------------------------------------------

    async def render_scrapers(
        request: Request, container: Container, *, status: int = 200, **overrides: Any
    ) -> HTMLResponse:
        settings = await container.system_settings.scrapers()
        context: dict[str, Any] = {
            "scrapers": ScrapersForm.values_from(settings),
            "error": None,
            "error_target": None,
        }
        return render(request, "settings/scrapers.html", "scrapers", context | overrides, status)

    @router.get("/scrapers")
    async def scrapers_page(request: Request, container: ContainerDep) -> HTMLResponse:
        return await render_scrapers(request, container)

    @router.post("/scrapers", dependencies=protected)
    async def save_scrapers(request: Request, container: ContainerDep) -> Response:
        data = form_dict(await request.form(), "active_sites")
        try:
            settings = ScrapersForm.model_validate(data).to_domain()
        except (ValidationError, ValueError) as exc:
            values = data | {"linkedin_fetch_description": "linkedin_fetch_description" in data}
            return await render_scrapers(
                request, container, status=422, scrapers=values,
                error=describe_errors(exc), error_target="scrapers",
            )
        await container.system_settings.save_scrapers(settings)
        return redirect("/settings/scrapers", "scrapers", "scrapers")

    return router


def _simple_category(value: str) -> ProfileBlockCategory:
    """Competência ou conquista; experiências têm rotas próprias."""
    try:
        category = ProfileBlockCategory(value)
    except ValueError:
        category = None
    if category not in _BLOCK_SECTIONS:
        raise HTTPException(status_code=422, detail="Categoria inválida")
    return category


def _saved_key(category: ProfileBlockCategory) -> str:
    return _BLOCK_SECTIONS[category][0] if category in _BLOCK_SECTIONS else "experience"


def _anchor(category: ProfileBlockCategory, block_id: int | None = None) -> str:
    if category is ProfileBlockCategory.EXPERIENCE:
        return f"experience-{block_id}" if block_id else "experiences"
    return _BLOCK_SECTIONS[category][1]
