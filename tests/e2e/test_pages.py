import pytest

from app.domain.exceptions import JobSourceError
from app.domain.models import JobSite
from tests.e2e.conftest import SAME_ORIGIN, make_job

pytestmark = pytest.mark.e2e

FORM = {"search_term": "python", "location": "São Paulo", "sites": ["linkedin", "indeed"]}


def submit_search(client, **overrides):
    return client.post("/search", data=FORM | overrides, headers=SAME_ORIGIN)


def first_job_key(client):
    return client.get("/api/jobs").json()[0]["key"]


def test_home_shows_empty_state(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Nenhuma vaga ainda" in response.text


def test_search_form_shows_results_with_new_badge(client):
    response = submit_search(client)

    assert response.status_code == 200
    assert "Python Developer" in response.text
    assert "Data Engineer" in response.text
    assert "Nova" in response.text
    assert "1 duplicatas removidas" in response.text
    assert "Indeed ↗" in response.text  # anúncio da mesma vaga em outra fonte


def test_search_form_keeps_values_and_explains_errors(client):
    response = submit_search(client, search_term="", sites=[])

    assert response.status_code == 422
    assert "Cargo ou palavra-chave" in response.text
    assert "Sites" in response.text
    assert 'value="São Paulo"' in response.text


def test_search_form_reports_source_failure(client, repository):
    repository._error = JobSourceError("linkedin: 429")

    response = submit_search(client)

    assert response.status_code == 502
    assert "Nenhuma fonte respondeu" in response.text


@pytest.mark.parametrize(
    "headers",
    [{}, {"origin": "https://evil.example"}, {"referer": "https://evil.example/page"}],
)
def test_forms_from_other_origins_are_blocked(client, repository, headers):
    response = client.post("/search", data=FORM, headers=headers)

    assert response.status_code == 403
    assert repository.calls == []


def test_referer_is_accepted_when_origin_is_absent(client):
    response = client.post("/search", data=FORM, headers={"referer": "http://testserver/"})

    assert response.status_code == 200


def test_home_lists_stored_jobs_after_search(client):
    submit_search(client)

    response = client.get("/")

    assert "Python Developer" in response.text
    assert "Nova" not in response.text  # "nova" só faz sentido logo após a busca


def test_job_detail_and_match_flow(client, llm):
    submit_search(client)
    key = first_job_key(client)

    before = client.get(f"/jobs/{key}")
    assert "Ainda não analisada" in before.text
    assert "Analisar match" in before.text

    response = client.post(f"/jobs/{key}/match", headers=SAME_ORIGIN, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/jobs/{key}"

    after = client.get(f"/jobs/{key}")
    assert "78%" in after.text
    assert "Bom match" in after.text
    assert "Kubernetes" in after.text
    assert "Reanalisar" in after.text


def test_match_form_is_protected_against_other_origins(client, llm):
    submit_search(client)

    response = client.post(f"/jobs/{first_job_key(client)}/match", headers={"origin": "https://evil.example"})

    assert response.status_code == 403
    assert llm.calls == []


def test_job_detail_without_profile_explains_and_hides_button(blank_client):
    submit_search(blank_client)

    response = blank_client.get(f"/jobs/{first_job_key(blank_client)}")

    assert response.status_code == 200
    assert "/settings/profile" in response.text
    assert "Analisar match" not in response.text


def test_unknown_job_renders_html_404(client):
    response = client.get("/jobs/0000000000000000")

    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "Voltar às vagas" in response.text


def test_third_party_content_cannot_inject_scripts(client, repository):
    repository._jobs = [
        make_job(
            "Dev <script>alert(1)</script>",
            description="<img src=x onerror=alert(2)>",
            url="javascript:alert(3)",
            source=JobSite.LINKEDIN,
        )
    ]
    submit_search(client)
    key = first_job_key(client)

    pages = [client.get("/").text, client.get(f"/jobs/{key}").text]

    for html in pages:
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert 'href="javascript:' not in html
    assert "<img src=x" not in pages[1]
