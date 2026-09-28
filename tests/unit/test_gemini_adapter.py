from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from app.adapters.gemini_adapter import GeminiAdapter
from app.domain.exceptions import LLMProviderError, LLMResponseFormatError
from app.domain.interfaces import ILLMProvider

pytestmark = pytest.mark.unit


class FakeGenAIClient:
    """Imita `client.aio.models.generate_content` do google-genai."""

    def __init__(self, *, text: str | None = None, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.calls: list[dict[str, Any]] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate_content))

    async def _generate_content(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._text)


def make_adapter(client: FakeGenAIClient, model: str = "gemini-test") -> GeminiAdapter:
    return GeminiAdapter(client=client, model=model)  # type: ignore[arg-type]


def test_is_an_llm_provider_named_after_the_model():
    adapter = make_adapter(FakeGenAIClient(), model="gemini-2.5-pro")

    assert isinstance(adapter, ILLMProvider)
    assert adapter.name == "gemini:gemini-2.5-pro"


def test_requires_api_key_when_no_client_is_injected():
    with pytest.raises(ValueError):
        GeminiAdapter(api_key="")


async def test_generate_forwards_prompt_system_prompt_and_temperature():
    client = FakeGenAIClient(text="olá")

    result = await make_adapter(client).generate("oi", system_prompt="seja breve", temperature=0.7)

    assert result == "olá"
    call = client.calls[0]
    assert call["model"] == "gemini-test"
    assert call["contents"] == "oi"
    assert call["config"].system_instruction == "seja breve"
    assert call["config"].temperature == 0.7
    assert call["config"].response_mime_type is None


async def test_generate_json_enables_json_mode_and_parses_object():
    client = FakeGenAIClient(text='{"score": 88, "rationale": "ok"}')

    result = await make_adapter(client).generate_json("avalie")

    assert result == {"score": 88, "rationale": "ok"}
    assert client.calls[0]["config"].response_mime_type == "application/json"
    assert client.calls[0]["config"].temperature == 0.0


@pytest.mark.parametrize("text", ["não é json", "[1, 2, 3]", '"string"'])
async def test_generate_json_rejects_non_object_payloads(text):
    with pytest.raises(LLMResponseFormatError):
        await make_adapter(FakeGenAIClient(text=text)).generate_json("avalie")


@pytest.mark.parametrize("text", [None, ""])
async def test_empty_response_is_a_format_error(text):
    with pytest.raises(LLMResponseFormatError):
        await make_adapter(FakeGenAIClient(text=text)).generate("oi")


@pytest.mark.parametrize(
    "error",
    [
        errors.ClientError(
            429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
        ),
        errors.ServerError(503, {"error": {"code": 503, "message": "down", "status": "UNAVAILABLE"}}),
        httpx.ReadTimeout("timeout"),
    ],
)
async def test_translates_sdk_and_network_errors_to_domain_errors(error):
    adapter = make_adapter(FakeGenAIClient(error=error))

    with pytest.raises(LLMProviderError) as exc_info:
        await adapter.generate_json("avalie")

    assert not isinstance(exc_info.value, LLMResponseFormatError)
    assert exc_info.value.__cause__ is error
