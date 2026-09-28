import pytest

from app.domain.exceptions import LLMProviderError
from tests.e2e.conftest import SAME_ORIGIN

pytestmark = pytest.mark.e2e

EMAIL = {"subject": "Python Developer — APIs com FastAPI", "body": "Olá, Ana!\n\nVi a vaga..."}


@pytest.fixture
def key(client):
    client.post("/api/searches", json={"search_term": "python"})
    return client.get("/api/jobs").json()[0]["key"]


def draft(client, key, **body):
    return client.post(f"/api/jobs/{key}/outreach", json={"channel": "email"} | body)


def test_api_drafts_and_lists_messages(client, llm, key):
    llm._response = EMAIL

    response = draft(client, key, language="en", recipient_name="Ana")

    assert response.status_code == 200
    body = response.json()
    assert (body["channel"], body["language"], body["subject"]) == ("email", "en", EMAIL["subject"])
    assert (body["length"], body["max_length"], body["is_current"]) == (len(EMAIL["body"]), 1500, True)
    assert "Destinatário: Ana" in llm.calls[-1]["prompt"]

    history = client.get(f"/api/jobs/{key}/outreach").json()
    assert [m["subject"] for m in history] == [EMAIL["subject"]]


def test_api_uses_existing_match_strengths(client, llm, key):
    client.post(f"/api/jobs/{key}/match")  # LLM devolve strengths=["Python sólido"]
    llm._response = EMAIL

    draft(client, key)

    assert "Pontos fortes: Python sólido" in llm.calls[-1]["prompt"]


@pytest.mark.parametrize("body", [{"channel": "fax"}, {"language": "fr"}, {"recipient_name": "x" * 101}])
def test_api_rejects_invalid_requests(client, key, body):
    assert draft(client, key, **body).status_code == 422


def test_api_reports_llm_outage_as_503(client, llm, key):
    llm._error = LLMProviderError("connection refused")

    response = draft(client, key)

    assert response.status_code == 503
    assert "connection refused" in response.json()["detail"]


def test_api_reports_broken_llm_output_as_502(client, llm, key):
    llm._response = {"body": "e-mail sem assunto"}

    assert draft(client, key).status_code == 502
    assert client.get(f"/api/jobs/{key}/outreach").json() == []


def test_api_unknown_job_is_404(client):
    assert draft(client, "0000000000000000").status_code == 404


def test_page_flow_generates_and_shows_draft(client, llm, key):
    llm._response = EMAIL

    response = client.post(
        f"/jobs/{key}/outreach",
        data={"channel": "email", "language": "pt", "recipient_name": "Ana"},
        headers=SAME_ORIGIN,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{key}#outreach"
    page = client.get(f"/jobs/{key}").text
    assert "Assunto: Python Developer — APIs com FastAPI" in page
    assert "Copiar" in page
    assert f"{len(EMAIL['body'])}/1500 caracteres" in page


def test_page_form_is_protected_against_other_origins(client, llm, key):
    calls_before = len(llm.calls)

    response = client.post(
        f"/jobs/{key}/outreach", data={"channel": "email"}, headers={"origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert len(llm.calls) == calls_before


def test_page_shows_llm_outage_as_error_page(client, llm, key):
    llm._error = LLMProviderError("connection refused")

    response = client.post(f"/jobs/{key}/outreach", data={"channel": "email"}, headers=SAME_ORIGIN)

    assert response.status_code == 503
    assert "connection refused" in response.text


def test_llm_output_cannot_inject_html(client, llm, key):
    llm._response = {"subject": "<b>oi</b>", "body": "<script>alert(1)</script>"}
    draft(client, key)

    page = client.get(f"/jobs/{key}").text

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
