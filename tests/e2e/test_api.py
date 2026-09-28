import json

import pytest

from app.domain.exceptions import JobSourceError
from tests.e2e.conftest import PROFILE

pytestmark = pytest.mark.e2e

SEARCH = {"search_term": "python", "location": "São Paulo"}


def search(client, **overrides):
    return client.post("/api/searches", json=SEARCH | overrides)


def test_health_reports_llm_provider(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "llm_provider": "mock"}


def test_openapi_documents_the_api(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert {"/api/searches", "/api/jobs", "/api/jobs/{key}", "/api/jobs/{key}/match"} <= set(paths)
    assert "/search" not in paths  # rotas HTML ficam fora da documentação


# --- Perfil ------------------------------------------------------------------------


def test_returns_profile_with_fingerprint(client):
    body = client.get("/api/profile").json()

    assert body["full_name"] == PROFILE["full_name"]
    assert body["skills"] == PROFILE["skills"]
    assert len(body["fingerprint"]) == 16


def test_missing_profile_is_a_503_with_instructions(client, profile_path):
    profile_path.unlink()

    response = client.get("/api/profile")

    assert response.status_code == 503
    assert "profile.example.json" in response.json()["detail"]


def test_invalid_profile_names_the_bad_field(client, profile_path):
    profile_path.write_text(json.dumps(PROFILE | {"skils": ["typo"], "years_of_experience": -1}))

    detail = client.get("/api/profile").json()["detail"]

    assert "years_of_experience" in detail
    assert "skils" in detail


# --- Busca -------------------------------------------------------------------------


def test_search_deduplicates_persists_and_flags_new_jobs(client, repository):
    response = search(client, sites=["linkedin", "indeed"], results_wanted=5, remote_only=True)

    assert response.status_code == 200
    body = response.json()
    assert (body["total_fetched"], body["duplicates_removed"], body["new_count"]) == (3, 1, 2)
    python = body["jobs"][0]
    assert python["title"] == "Python Developer"
    assert python["is_new"] is True
    assert python["other_listings"] == [{"source": "indeed", "url": "https://br.indeed.com/viewjob?jk=1"}]

    criteria = repository.calls[0]
    assert (criteria.search_term, criteria.results_wanted, criteria.remote_only) == ("python", 5, True)


def test_repeating_a_search_finds_nothing_new(client):
    search(client)

    body = search(client).json()

    assert body["new_count"] == 0
    assert not any(job["is_new"] for job in body["jobs"])


@pytest.mark.parametrize(
    "payload",
    [
        {"search_term": ""},
        {"sites": []},
        {"sites": ["orkut"]},
        {"results_wanted": 0},
        {"results_wanted": 101},
        {"hours_old": 0},
    ],
)
def test_search_rejects_invalid_input(client, payload):
    assert search(client, **payload).status_code == 422


def test_search_reports_source_failure_as_bad_gateway(client, repository):
    repository._error = JobSourceError("linkedin: 429")

    response = search(client)

    assert response.status_code == 502
    assert "429" in response.json()["detail"]


# --- Vagas ---------------------------------------------------------------------------


def test_lists_and_paginates_stored_jobs(client):
    search(client)

    all_jobs = client.get("/api/jobs").json()
    second_page = client.get("/api/jobs", params={"limit": 1, "offset": 1}).json()

    assert [job["title"] for job in all_jobs] == ["Python Developer", "Data Engineer"]
    assert [job["title"] for job in second_page] == ["Data Engineer"]


def test_job_detail_includes_description(client):
    key = search(client).json()["jobs"][0]["key"]

    body = client.get(f"/api/jobs/{key}").json()

    assert body["description"] == "Buscamos Python, FastAPI e Docker."
    assert body["match"] is None


def test_unknown_job_is_404(client):
    response = client.get("/api/jobs/0000000000000000")

    assert response.status_code == 404
    assert "0000000000000000" in response.json()["detail"]


# --- Match ---------------------------------------------------------------------------


def test_match_scores_and_is_cached(client, llm):
    key = search(client).json()["jobs"][0]["key"]

    first = client.post(f"/api/jobs/{key}/match")
    second = client.post(f"/api/jobs/{key}/match")

    assert first.status_code == 200
    body = first.json()
    # 3/3 skills citadas -> 100; 0.4*100 + 0.6*90 = 94
    assert (body["score"], body["verdict"], body["is_current"]) == (94.0, "strong", True)
    assert body["gaps"] == ["Kubernetes"]
    assert second.json() == body
    assert len(llm.calls) == 1


def test_force_recomputes_the_match(client, llm):
    key = search(client).json()["jobs"][0]["key"]
    client.post(f"/api/jobs/{key}/match")

    client.post(f"/api/jobs/{key}/match", params={"force": True})

    assert len(llm.calls) == 2


def test_editing_the_profile_marks_matches_as_outdated_and_recomputes(client, llm, profile_path):
    key = search(client).json()["jobs"][0]["key"]
    client.post(f"/api/jobs/{key}/match")

    profile_path.write_text(json.dumps(PROFILE | {"skills": ["Python", "Go"]}))

    listed = client.get("/api/jobs").json()[0]
    assert listed["match"]["is_current"] is False

    rematched = client.post(f"/api/jobs/{key}/match").json()
    assert rematched["is_current"] is True
    assert rematched["matched_skills"] == ["Python"]
    assert len(llm.calls) == 2


def test_match_requires_a_profile(client, profile_path):
    key = search(client).json()["jobs"][0]["key"]
    profile_path.unlink()

    assert client.post(f"/api/jobs/{key}/match").status_code == 503


def test_match_for_unknown_job_is_404(client):
    assert client.post("/api/jobs/0000000000000000/match").status_code == 404



# --- CSRF na API ---------------------------------------------------------------------


def test_api_blocks_browser_requests_from_other_sites(client, llm):
    """O match não tem corpo JSON: sem esta proteção, um formulário comum de
    outro site conseguiria dispará-lo (e gastar o LLM)."""
    key = search(client).json()["jobs"][0]["key"]

    response = client.post(f"/api/jobs/{key}/match", headers={"origin": "https://evil.example"})

    assert response.status_code == 403
    assert llm.calls == []


def test_api_accepts_clients_without_origin_and_same_origin(client):
    key = search(client).json()["jobs"][0]["key"]

    assert client.post(f"/api/jobs/{key}/match").status_code == 200
    assert client.post(
        f"/api/jobs/{key}/match", headers={"origin": "http://testserver"}
    ).status_code == 200


def test_json_endpoints_refuse_non_json_bodies(client):
    """Formulários de outros sites só conseguem enviar text/plain ou form-urlencoded."""
    for content_type in ("text/plain", "application/x-www-form-urlencoded"):
        response = client.post(
            "/api/searches", content='{"search_term": "python"}', headers={"content-type": content_type}
        )
        assert response.status_code == 422
