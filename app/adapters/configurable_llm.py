"""LLM que segue a configuração do painel: trocar o provedor vale na próxima chamada."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.domain.interfaces import ILLMProvider
from app.domain.models import LLMSettings

LLMSettingsSource = Callable[[], Awaitable[LLMSettings]]
AdapterBuilder = Callable[[LLMSettings, float], ILLMProvider]


class ConfigurableLLMProvider(ILLMProvider):
    """Proxy que recria o adapter concreto quando as configurações mudam.

    Adapters substituídos só são fechados no `aclose`: uma chamada ainda em
    andamento no adapter antigo não perde a conexão no meio da resposta.
    """

    def __init__(
        self,
        source: LLMSettingsSource,
        *,
        initial: LLMSettings,
        timeout_seconds: float,
        build: AdapterBuilder,
    ) -> None:
        self._source = source
        self._timeout = timeout_seconds
        self._build = build
        self._settings = initial
        self._adapter: ILLMProvider | None = None
        self._retired: list[ILLMProvider] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Provedor/modelo configurado na última chamada (ou o inicial)."""
        return f"{self._settings.provider}:{self._settings.model}"

    async def current_name(self) -> str:
        settings = await self._source()
        return f"{settings.provider}:{settings.model}"

    @property
    def timeout_seconds(self) -> float:
        return self._timeout

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        adapter = await self._current()
        return await adapter.generate(prompt, system_prompt=system_prompt, temperature=temperature)

    async def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        adapter = await self._current()
        return await adapter.generate_json(prompt, system_prompt=system_prompt, temperature=temperature)

    async def aclose(self) -> None:
        adapters = [*self._retired, *([self._adapter] if self._adapter else [])]
        self._adapter, self._retired = None, []
        for adapter in adapters:
            await adapter.aclose()

    async def _current(self) -> ILLMProvider:
        settings = await self._source()
        async with self._lock:
            if self._adapter is None or settings != self._settings:
                if self._adapter is not None:
                    self._retired.append(self._adapter)
                self._adapter = self._build(settings, self._timeout)
                self._settings = settings
            return self._adapter
