"""Resolução dos prompts de sistema: customização do painel ou o padrão do código."""

from app.domain.interfaces import IPromptTemplateStore
from app.domain.models import PromptName


async def resolve_prompt(store: IPromptTemplateStore | None, name: PromptName, default: str) -> str:
    """Prompt customizado e ativo, se houver; senão `default`."""
    if store is None:
        return default
    template = await store.get(name)
    return template.template_text if template and template.is_active else default
