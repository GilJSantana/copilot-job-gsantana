"""Adapter do Ollama (API REST local) para a porta `ILLMProvider`."""

import json
from typing import Any

import httpx

from app.domain.exceptions import LLMProviderError, LLMResponseFormatError
from app.domain.interfaces import ILLMProvider

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"


class OllamaAdapter(ILLMProvider):
    """Traduz chamadas do domínio para `POST /api/chat` do Ollama.

    Erros HTTP e de rede são convertidos em `LLMProviderError`, de modo que
    os services nunca dependam de exceções do `httpx`.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(timeout_seconds)
        )
        self._model = model

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    async def aclose(self) -> None:
        """Fecha o cliente HTTP, se tiver sido criado por este adapter."""
        if self._owns_client:
            await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        return await self._chat(prompt, system_prompt, temperature)

    async def generate_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        text = await self._chat(prompt, system_prompt, temperature, response_format="json")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(f"Ollama retornou JSON inválido: {exc}") from exc
        if not isinstance(payload, dict):
            raise LLMResponseFormatError(
                f"Ollama retornou {type(payload).__name__}, esperado objeto JSON"
            )
        return payload

    async def _chat(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        response_format: str | None = None,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if response_format:
            body["format"] = response_format

        try:
            response = await self._client.post("/api/chat", json=body)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"Ollama HTTP {exc.response.status_code}: {_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Falha de rede ao chamar o Ollama: {exc!r}") from exc

        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise LLMResponseFormatError("Resposta do Ollama fora do formato esperado") from exc
        if not isinstance(content, str) or not content:
            raise LLMResponseFormatError("Ollama retornou resposta vazia")
        return content


def _error_detail(response: httpx.Response) -> str:
    """O Ollama devolve erros como {"error": "..."}; cai para o texto bruto se não for JSON."""
    try:
        return str(response.json()["error"])
    except (ValueError, KeyError, TypeError):
        return response.text
