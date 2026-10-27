"""Adapter do Google Gemini (SDK `google-genai`) para a porta `ILLMProvider`."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.domain.exceptions import LLMProviderError, LLMResponseFormatError
from app.domain.interfaces import ILLMProvider

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_ATTEMPTS = 3
# 429 (limite por minuto) e 5xx (ex.: 503 de alta demanda) costumam passar sozinhos
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}

# não usamos `tools`; sem isso o SDK liga o AFC e emite avisos a cada chamada
_NO_AFC = types.AutomaticFunctionCallingConfig(disable=True)

logger = logging.getLogger(__name__)


class GeminiAdapter(ILLMProvider):
    """Traduz chamadas do domínio para a API do Gemini.

    Erros do SDK e de rede são convertidos em `LLMProviderError`, de modo que
    os services nunca dependam de exceções do `google-genai`.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 60.0,
        client: genai.Client | None = None,
        retry_base_delay: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._owns_client = client is None
        if client is None:
            if not api_key:
                raise ValueError("api_key é obrigatória para o GeminiAdapter")
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
            )
        self._client = client
        # o SDK já monta `models/{model}`; o prefixo vindo do .env/painel geraria 404
        self._model = model.strip().removeprefix("models/")
        self._retry_base_delay = retry_base_delay
        self._sleep = sleep

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    async def aclose(self) -> None:
        """Fecha o cliente HTTP, se tiver sido criado por este adapter."""
        if self._owns_client:
            await self._client.aio.aclose()

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            automatic_function_calling=_NO_AFC,
        )
        return await self._generate_text(prompt, config)

    async def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json",
            automatic_function_calling=_NO_AFC,
        )
        text = await self._generate_text(prompt, config)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(f"Gemini retornou JSON inválido: {exc}") from exc
        if not isinstance(payload, dict):
            raise LLMResponseFormatError(
                f"Gemini retornou {type(payload).__name__}, esperado objeto JSON"
            )
        return payload

    async def _generate_text(self, prompt: str, config: types.GenerateContentConfig) -> str:
        # DEBUG apenas: o prompt carrega dados do perfil/CV do usuário
        logger.debug(
            "Gemini payload: model=%s config=%s contents=%r",
            self._model,
            config.model_dump(exclude_none=True),
            prompt,
        )
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model, contents=prompt, config=config
                )
                break
            except errors.APIError as exc:
                error = LLMProviderError(f"Gemini API {exc.code} {exc.status}: {exc.message}")
                if exc.code not in _TRANSIENT_STATUS or attempt == MAX_ATTEMPTS:
                    raise error from exc
            except httpx.TransportError as exc:
                error = LLMProviderError(f"Falha de rede ao chamar o Gemini: {exc!r}")
                if attempt == MAX_ATTEMPTS:
                    raise error from exc
            except httpx.HTTPError as exc:
                raise LLMProviderError(f"Falha de rede ao chamar o Gemini: {exc!r}") from exc
            delay = self._retry_base_delay * 2 ** (attempt - 1)
            logger.warning(
                "%s (tentativa %d/%d); nova tentativa em %.1fs", error, attempt, MAX_ATTEMPTS, delay
            )
            await self._sleep(delay)

        # `text` é None quando não há candidatos (ex.: bloqueio de segurança)
        if not response.text:
            raise LLMResponseFormatError("Gemini retornou resposta vazia")
        return response.text
