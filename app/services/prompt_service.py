"""Edição dos prompts de sistema pelo painel de configurações."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.interfaces import IPromptTemplateStore
from app.domain.models import PromptName, PromptTemplate
from app.services import cv_optimizer, match_engine

# Prompts originais do código: valem enquanto não houver customização ativa
DEFAULT_PROMPTS: dict[PromptName, str] = {
    PromptName.MATCH_ENGINE: match_engine.SYSTEM_PROMPT,
    PromptName.CV_TAILOR: cv_optimizer.SYSTEM_PROMPT,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class PromptView:
    """Prompt como o painel o mostra: o texto em uso e se ele é o padrão."""

    name: PromptName
    text: str
    default_text: str
    is_custom: bool
    updated_at: datetime | None = None


class PromptService:
    def __init__(self, store: IPromptTemplateStore) -> None:
        self._store = store

    async def list_all(self) -> list[PromptView]:
        return [await self.get(name) for name in PromptName]

    async def get(self, name: PromptName) -> PromptView:
        template = await self._store.get(name)
        default = DEFAULT_PROMPTS[name]
        if template is None or not template.is_active:
            return PromptView(name=name, text=default, default_text=default, is_custom=False)
        return PromptView(
            name=name,
            text=template.template_text,
            default_text=default,
            is_custom=True,
            updated_at=template.updated_at,
        )

    async def save(self, name: PromptName, text: str) -> PromptView:
        """Grava a customização. Texto igual ao padrão remove a customização:
        assim o prompt volta a acompanhar as melhorias do padrão no código."""
        text = text.replace("\r\n", "\n").strip()
        if text == DEFAULT_PROMPTS[name].strip():
            await self._store.delete(name)
        else:
            await self._store.save(PromptTemplate(name=name, template_text=text))
        return await self.get(name)

    async def reset(self, name: PromptName) -> PromptView:
        await self._store.delete(name)
        return await self.get(name)
