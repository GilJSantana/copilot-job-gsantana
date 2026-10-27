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

    def __init__(
        self, *, text: str | None = None, error: Exception | None = None, errors: tuple[Exception, ...] = ()
    ) -> None:
        self._text = text
        self._error = error
        self._errors = list(errors)  # consumidos um por chamada, antes de responder
        self.calls: list[dict[str, Any]] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate_content))

    async def _generate_content(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self._errors:
            raise self._errors.pop(0)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(text=self._text)


async def _no_sleep(_: float) -> None:
    pass


def make_adapter(
    client: FakeGenAIClient, model: str = "gemini-test", sleep=_no_sleep
) -> GeminiAdapter:
    return GeminiAdapter(client=client, model=model, sleep=sleep)  # type: ignore[arg-type]


def _api_error(code: int, status: str) -> errors.APIError:
    payload = {"error": {"code": code, "message": status.lower(), "status": status}}
    return (errors.ServerError if code >= 500 else errors.ClientError)(code, payload)


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


async def test_strips_models_prefix_from_model_name():
    client = FakeGenAIClient(text="ok")

    await make_adapter(client, model=" models/gemini-2.5-flash ").generate("oi")

    assert client.calls[0]["model"] == "gemini-2.5-flash"


async def test_retries_transient_errors_with_exponential_backoff():
    delays: list[float] = []

    async def record(delay: float) -> None:
        delays.append(delay)

    client = FakeGenAIClient(
        text="ok", errors=[_api_error(503, "UNAVAILABLE"), httpx.ConnectError("reset")]
    )

    assert await make_adapter(client, sleep=record).generate("oi") == "ok"
    assert len(client.calls) == 3
    assert delays == [1.0, 2.0]


async def test_gives_up_after_three_attempts():
    client = FakeGenAIClient(error=_api_error(503, "UNAVAILABLE"))

    with pytest.raises(LLMProviderError):
        await make_adapter(client).generate("oi")

    assert len(client.calls) == 3


@pytest.mark.parametrize("code,status", [(404, "NOT_FOUND"), (400, "INVALID_ARGUMENT")])
async def test_does_not_retry_permanent_errors(code, status):
    client = FakeGenAIClient(error=_api_error(code, status))

    with pytest.raises(LLMProviderError):
        await make_adapter(client).generate("oi")

    assert len(client.calls) == 1


async def test_disables_automatic_function_calling():
    client = FakeGenAIClient(text="{}")
    adapter = make_adapter(client)

    await adapter.generate("oi")
    await adapter.generate_json("oi")

    assert all(c["config"].automatic_function_calling.disable for c in client.calls)
