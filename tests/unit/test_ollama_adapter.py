import json
from typing import Any

import httpx
import pytest

from app.adapters.ollama_adapter import OllamaAdapter
from app.domain.exceptions import LLMProviderError, LLMResponseFormatError
from app.domain.interfaces import ILLMProvider

pytestmark = pytest.mark.unit

BASE_URL = "http://ollama.test"


class OllamaStub:
    """Servidor Ollama falso via `httpx.MockTransport`; registra os corpos recebidos."""

    def __init__(self, handler) -> None:
        self.requests: list[dict[str, Any]] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append({"path": request.url.path, "body": json.loads(request.content)})
        return self._handler(request)

    def adapter(self, model: str = "llama-test") -> OllamaAdapter:
        client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(self))
        return OllamaAdapter(model=model, client=client)


def reply(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def test_is_an_llm_provider_named_after_the_model():
    adapter = OllamaStub(lambda r: reply("")).adapter(model="qwen2.5:7b")

    assert isinstance(adapter, ILLMProvider)
    assert adapter.name == "ollama:qwen2.5:7b"


async def test_generate_posts_chat_request_with_system_and_user_messages():
    stub = OllamaStub(lambda r: reply("olá"))

    result = await stub.adapter().generate("oi", system_prompt="seja breve", temperature=0.7)

    assert result == "olá"
    request = stub.requests[0]
    assert request["path"] == "/api/chat"
    assert request["body"] == {
        "model": "llama-test",
        "messages": [
            {"role": "system", "content": "seja breve"},
            {"role": "user", "content": "oi"},
        ],
        "stream": False,
        "options": {"temperature": 0.7},
    }


async def test_generate_omits_system_message_when_not_given():
    stub = OllamaStub(lambda r: reply("olá"))

    await stub.adapter().generate("oi")

    assert stub.requests[0]["body"]["messages"] == [{"role": "user", "content": "oi"}]


async def test_generate_json_enables_json_format_and_parses_object():
    stub = OllamaStub(lambda r: reply('{"score": 72, "rationale": "ok"}'))

    result = await stub.adapter().generate_json("avalie")

    assert result == {"score": 72, "rationale": "ok"}
    assert stub.requests[0]["body"]["format"] == "json"
    assert stub.requests[0]["body"]["options"]["temperature"] == 0.0


@pytest.mark.parametrize("content", ["não é json", "[1, 2]", "42"])
async def test_generate_json_rejects_non_object_payloads(content):
    adapter = OllamaStub(lambda r: reply(content)).adapter()

    with pytest.raises(LLMResponseFormatError):
        await adapter.generate_json("avalie")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"message": {"content": ""}}),
        httpx.Response(200, json={"done": True}),
        httpx.Response(200, text="<html>proxy</html>"),
    ],
)
async def test_unexpected_response_shapes_are_format_errors(response):
    adapter = OllamaStub(lambda r: response).adapter()

    with pytest.raises(LLMResponseFormatError):
        await adapter.generate("oi")


async def test_http_error_is_translated_with_ollama_error_detail():
    adapter = OllamaStub(
        lambda r: httpx.Response(404, json={"error": "model 'llama-test' not found"})
    ).adapter()

    with pytest.raises(LLMProviderError, match="404.*model 'llama-test' not found") as exc_info:
        await adapter.generate("oi")

    assert not isinstance(exc_info.value, LLMResponseFormatError)


async def test_network_error_is_translated_to_provider_error():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(LLMProviderError, match="rede"):
        await OllamaStub(refuse).adapter().generate("oi")


async def test_aclose_only_closes_clients_it_created():
    injected = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: reply("")))
    await OllamaAdapter(client=injected).aclose()
    assert not injected.is_closed

    owned = OllamaAdapter()
    await owned.aclose()
    assert owned._client.is_closed
