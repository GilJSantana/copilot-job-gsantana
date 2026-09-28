"""Adapter do Google Gemini (SDK `google-genai`) para a porta `ILLMProvider`."""

import json
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.domain.exceptions import LLMProviderError, LLMResponseFormatError
from app.domain.interfaces import ILLMProvider

DEFAULT_MODEL = "gemini-2.5-flash"


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
        self._model = model

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
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=prompt, config=config
            )
        except errors.APIError as exc:
            raise LLMProviderError(f"Gemini API {exc.code} {exc.status}: {exc.message}") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Falha de rede ao chamar o Gemini: {exc!r}") from exc

        # `text` é None quando não há candidatos (ex.: bloqueio de segurança)
        if not response.text:
            raise LLMResponseFormatError("Gemini retornou resposta vazia")
        return response.text
