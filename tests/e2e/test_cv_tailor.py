import io
import re

import pytest
from pypdf import PdfReader

from app.domain.exceptions import LLMProviderError
from tests.cv_builders import llm_cv
from tests.e2e.conftest import SAME_ORIGIN

pytestmark = pytest.mark.e2e


def first_key(client, llm):
    client.post("/api/searches", json={"search_term": "python"})
    llm._response = llm_cv()  # a partir daqui o LLM responde como otimizador de CV
    return client.get("/api/jobs").json()[0]["key"]


@pytest.fixture
def key(client, llm):
    return first_key(client, llm)


def tailor(client, key, **body):
    return client.post(f"/api/jobs/{key}/cvs", json=body)


def pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


# --- API -------------------------------------------------------------------------------------


def test_api_generates_a_version_with_its_pdf(client, key, cv_output_dir):
    response = tailor(client, key, language="en")

    assert response.status_code == 200
    cv = response.json()
    assert re.fullmatch(r"[0-9a-f]{32}", cv["id"])
    assert (cv["job_key"], cv["language"], cv["template"], cv["provider"]) == (key, "en", "ats_base", "mock")
    assert cv["is_current"] is True
    assert cv["matched_keywords"] == ["Python", "FastAPI", "Kafka", "AWS"]
    assert cv["experiences"][0] | {"highlights": None} == {
        "experience_id": "pagamentos",
        "title": "Engenheira de Software Sênior",
        "company": "Pagamentos SA",
        "highlights": None,
    }
    assert cv["download_name"] == "Ana-Souza_CV_Acme.pdf"
    assert cv["pdf_url"] == f"/api/cvs/{cv['id']}/pdf"
    assert [p.name for p in cv_output_dir.iterdir()] == [f"Ana-Souza_CV_Acme_{cv['id']}.pdf"]


def test_api_lists_versions_newest_first_and_gets_one(client, key):
    first = tailor(client, key).json()
    second = tailor(client, key).json()

    listed = client.get(f"/api/jobs/{key}/cvs").json()
    assert [cv["id"] for cv in listed] == [second["id"], first["id"]]
    assert client.get(f"/api/cvs/{first['id']}").json() == first


def test_api_serves_the_pdf_inline_or_as_download(client, key):
    cv = tailor(client, key).json()

    inline = client.get(cv["pdf_url"])
    download = client.get(cv["pdf_url"], params={"download": True})

    assert inline.status_code == 200
    assert inline.headers["content-type"] == "application/pdf"
    assert inline.headers["content-disposition"] == 'inline; filename="Ana-Souza_CV_Acme.pdf"'
    assert inline.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"] == 'attachment; filename="Ana-Souza_CV_Acme.pdf"'
    text = pdf_text(inline.content)
    assert "Engenheira de Software Backend | Python, FastAPI e Kafka" in text
    assert "Pagamentos SA" in text


def test_editing_the_history_marks_versions_as_outdated(client, key):
    cv = tailor(client, key).json()

    client.post(
        "/settings/profile/blocks",
        data={"category": "METRIC", "title": "Migração de 20TB no S3"},
        headers=SAME_ORIGIN,
    )

    assert client.get(f"/api/cvs/{cv['id']}").json()["is_current"] is False


@pytest.mark.parametrize("version_id", ["0" * 32, "f" * 32])
def test_unknown_version_is_404(client, version_id):
    assert client.get(f"/api/cvs/{version_id}").status_code == 404
    assert client.get(f"/api/cvs/{version_id}/pdf").status_code == 404


@pytest.mark.parametrize("version_id", ["..%2F..%2Fetc%2Fpasswd", "ABC", "0" * 31, "g" * 32])
def test_malformed_version_ids_are_rejected(client, version_id):
    assert client.get(f"/api/cvs/{version_id}/pdf").status_code in {404, 422}


def test_pdf_removed_from_disk_is_404(client, key, cv_output_dir):
    cv = tailor(client, key).json()
    for pdf in cv_output_dir.iterdir():
        pdf.unlink()

    response = client.get(cv["pdf_url"])

    assert response.status_code == 404
    assert "não está mais em disco" in response.json()["detail"]


def test_missing_history_is_503_with_instructions(blank_client, llm):
    response = tailor(blank_client, first_key(blank_client, llm))

    assert response.status_code == 503
    assert "/settings/profile" in response.json()["detail"]


def test_llm_outage_is_503_and_leaves_nothing_behind(client, key, llm, cv_output_dir):
    llm._error = LLMProviderError("connection refused")

    assert tailor(client, key).status_code == 503
    assert client.get(f"/api/jobs/{key}/cvs").json() == []
    assert not cv_output_dir.exists() or not any(cv_output_dir.iterdir())


@pytest.mark.parametrize("body", [{"language": "fr"}, {"language": ""}])
def test_invalid_language_is_422(client, key, body):
    assert tailor(client, key, **body).status_code == 422


def test_cv_for_unknown_job_is_404(client):
    assert tailor(client, "0000000000000000").status_code == 404


def test_api_blocks_cv_generation_from_other_sites(client, key, llm):
    calls_before = len(llm.calls)

    response = client.post(
        f"/api/jobs/{key}/cvs", json={}, headers={"origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert len(llm.calls) == calls_before


# --- Páginas --------------------------------------------------------------------------------


def test_page_flow_generates_and_lists_the_cv(client, key):
    before = client.get(f"/jobs/{key}").text
    assert "Gerar CV" in before

    response = client.post(
        f"/jobs/{key}/cvs", data={"language": "pt"}, headers=SAME_ORIGIN, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{key}#cv"
    page = client.get(f"/jobs/{key}").text
    cv = client.get(f"/api/jobs/{key}/cvs").json()[0]
    assert "Gerar nova versão" in page
    assert cv["pdf_url"] in page
    assert f'{cv["pdf_url"]}?download=true' in page
    assert "Engenheira de Software Backend | Python, FastAPI e Kafka" in page
    assert "Termos da vaga cobertos" in page


def test_page_without_history_explains_and_hides_the_form(blank_client, llm):
    page = blank_client.get(f"/jobs/{first_key(blank_client, llm)}").text

    assert "/settings/profile" in page
    assert "Gerar CV" not in page


def test_page_form_is_protected_against_other_origins(client, key, llm):
    calls_before = len(llm.calls)

    response = client.post(f"/jobs/{key}/cvs", data={"language": "pt"}, headers={"origin": "https://evil.example"})

    assert response.status_code == 403
    assert len(llm.calls) == calls_before


def test_llm_text_cannot_inject_html_in_the_page(client, key, llm):
    llm._response = llm_cv(headline="<script>alert(1)</script> Backend")
    tailor(client, key)

    page = client.get(f"/jobs/{key}").text

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
