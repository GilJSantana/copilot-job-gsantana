"""Painel de configurações (/settings): navegação, formulários e efeito no resto da aplicação."""

import re

import pytest

from tests.e2e.conftest import SAME_ORIGIN

pytestmark = pytest.mark.e2e

EVIL = {"origin": "https://evil.example"}

LLM_FORM = {
    "provider": "ollama",
    "gemini_model": "gemini-2.5-flash",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "llama3.1",
}
SCRAPERS_FORM = {
    "active_sites": ["linkedin", "indeed"],
    "min_delay_seconds": "1",
    "max_delay_seconds": "3",
    "max_requests_per_hour": "60",
    "linkedin_fetch_description": "true",
}
EXPERIENCE_FORM = {
    "title": "Tech Lead",
    "company": "Move Tech 40+",
    "start": "2021-01",
    "highlights": "Liderei a migração de 20TB no S3.\nReduzi 76% do tempo de ETL.",
    "technologies": "Python, AWS",
    "is_active": "true",
}


def post(client, path, data, **kwargs):
    return client.post(path, data=data, headers=SAME_ORIGIN, follow_redirects=False, **kwargs)


# --- Navegação --------------------------------------------------------------------------


def test_header_has_a_gear_link_to_the_settings(client):
    page = client.get("/").text

    assert re.search(r'<a href="/settings" aria-label="Configurações"', page)


def test_settings_opens_on_the_profile_tab(client):
    response = client.get("/settings", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/settings/profile"


@pytest.mark.parametrize(
    ("path", "tab"),
    [
        ("/settings/profile", "Perfil Profissional"),
        ("/settings/llm", "Provedores de IA &amp; Prompts"),
        ("/settings/scrapers", "Conectores &amp; Rate Limits"),
    ],
)
def test_each_tab_renders_and_is_marked_active(client, path, tab):
    response = client.get(path)

    assert response.status_code == 200
    active = re.search(rf'<a href="{path}" aria-current="page"[^>]*>.*?</a>', response.text, re.S)
    assert active and tab in active.group(0)
    assert 'data-settings-link\n           aria-current="page"' in response.text


@pytest.mark.parametrize(
    ("path", "data"),
    [
        ("/settings/profile/details", {"full_name": "X", "headline": "Y"}),
        ("/settings/profile/blocks", {"category": "SKILL", "title": "Go"}),
        ("/settings/llm", LLM_FORM),
        ("/settings/llm/prompts/MATCH_ENGINE_PROMPT", {"template_text": "x"}),
        ("/settings/scrapers", SCRAPERS_FORM),
    ],
)
def test_forms_from_other_origins_are_blocked(client, path, data):
    assert client.post(path, data=data, headers=EVIL).status_code == 403


# --- Perfil profissional ---------------------------------------------------------------


def test_profile_tab_shows_the_imported_profile(client):
    page = client.get("/settings/profile").text

    assert 'value="Ana Souza"' in page
    assert "Pagamentos SA" in page and "Logística Ltda" in page
    assert "PostgreSQL" in page


def test_saving_details_updates_the_profile(client):
    data = {
        "full_name": "Gil Jesus",
        "headline": "Engenheiro de Dados",
        "summary": "+20 anos em TI.",
        "years_of_experience": "20",
        "target_roles": "Data Engineer, Tech Lead",
        "preferred_work_modes": ["remote", "hybrid"],
        "language": "pt",
        "education": "Sistemas de Informação | USP | 2004-02 | 2008-12",
        "certifications": "AWS Solutions Architect | Amazon | 2024",
    }

    response = post(client, "/settings/profile/details", data)

    assert response.status_code == 303
    assert response.headers["location"] == "/settings/profile?saved=details#details"
    profile = client.get("/api/profile").json()
    assert (profile["full_name"], profile["years_of_experience"]) == ("Gil Jesus", 20)
    assert profile["target_roles"] == ["Data Engineer", "Tech Lead"]
    assert profile["preferred_work_modes"] == ["remote", "hybrid"]
    page = client.get(response.headers["location"]).text
    assert "Dados do perfil salvos." in page
    assert "Sistemas de Informação | USP | 2004-02 | 2008-12" in page


def test_invalid_details_keep_what_was_typed(client):
    data = {"full_name": "Gil Jesus", "headline": "Dev", "education": "Só o nome do curso"}

    response = post(client, "/settings/profile/details", data)

    assert response.status_code == 422
    assert "Formação" in response.text
    assert 'value="Gil Jesus"' in response.text


def test_adding_an_experience_feeds_the_cv_history(client):
    response = post(client, "/settings/profile/experiences", EXPERIENCE_FORM)

    assert response.status_code == 303
    page = client.get("/settings/profile").text
    assert "Move Tech 40+" in page
    assert "id move-tech-40" in page


def test_invalid_experience_reopens_the_form_with_the_error(client):
    response = post(client, "/settings/profile/experiences", EXPERIENCE_FORM | {"end": "2020-01"})

    assert response.status_code == 422
    assert "anterior ao início" in response.text
    assert re.search(r'<details id="new-experience"[^>]*\bopen\b', response.text)
    assert "Liderei a migração de 20TB no S3." in response.text


def test_editing_an_experience_keeps_its_id(client):
    post(client, "/settings/profile/experiences", EXPERIENCE_FORM | {"id": "movetech"})
    created = re.findall(r'<details id="experience-(\d+)"', client.get("/settings/profile").text)[-1]

    response = post(client, f"/settings/profile/experiences/{created}", EXPERIENCE_FORM | {"title": "CTO", "id": "outro"})

    assert response.status_code == 303
    page = client.get("/settings/profile").text
    assert "CTO" in page and "id movetech" in page and "id outro" not in page


def test_skills_can_be_added_deactivated_and_removed(client):
    post(client, "/settings/profile/blocks", {"category": "SKILL", "title": "Kubernetes"})
    assert "Kubernetes" in client.get("/api/profile").json()["skills"]

    skill_id = re.search(r'blocks/(\d+)/toggle"[^<]*>\s*<button[^>]*Kubernetes', client.get("/settings/profile").text)
    assert skill_id
    post(client, f"/settings/profile/blocks/{skill_id.group(1)}/toggle", {})
    assert "Kubernetes" not in client.get("/api/profile").json()["skills"]

    response = post(client, f"/settings/profile/blocks/{skill_id.group(1)}/delete", {})
    assert response.headers["location"] == "/settings/profile?saved=deleted#skills"
    assert 'aria-label="Remover Kubernetes"' not in client.get("/settings/profile").text


def test_metrics_are_listed_and_editable(client):
    post(client, "/settings/profile/blocks", {"category": "METRIC", "title": "Redução de 76% no ETL", "content": "Spark"})
    metric_id = re.findall(r'<details id="metric-(\d+)"', client.get("/settings/profile").text)[0]

    response = post(
        client,
        f"/settings/profile/blocks/{metric_id}",
        {"category": "METRIC", "title": "Redução de 76% no tempo de ETL", "content": "Spark e Airflow"},
    )

    assert response.status_code == 303
    page = client.get("/settings/profile").text
    assert "Redução de 76% no tempo de ETL" in page
    assert "Inativo" in page  # o switch "Ativa" não foi enviado


def test_unknown_blocks_and_categories(client):
    assert post(client, "/settings/profile/blocks/999/delete", {}).status_code == 404
    assert post(client, "/settings/profile/blocks", {"category": "EXPERIENCE", "title": "x"}).status_code == 422


# --- Provedores de IA & prompts --------------------------------------------------------


def test_gemini_without_api_key_is_rejected(client):
    response = post(client, "/settings/llm", LLM_FORM | {"provider": "gemini"})

    assert response.status_code == 422
    assert "API key do Gemini" in response.text


def test_api_key_is_saved_masked_and_kept_when_left_blank(client):
    post(client, "/settings/llm", LLM_FORM | {"provider": "gemini", "gemini_api_key": "AIzaSecreta1234"})

    page = client.get("/settings/llm").text
    assert "••••1234" in page
    assert "AIzaSecreta1234" not in page
    assert client.get("/api/health").json()["llm_provider"] == "mock"  # dublê injetado

    # campo em branco mantém a chave; trocar o modelo continua valendo
    assert post(client, "/settings/llm", LLM_FORM | {"provider": "gemini", "gemini_model": "gemini-2.5-pro"}).status_code == 303
    page = client.get("/settings/llm").text
    assert "••••1234" in page and 'value="gemini-2.5-pro"' in page


def test_api_key_can_be_removed(client):
    post(client, "/settings/llm", LLM_FORM | {"gemini_api_key": "AIzaSecreta1234"})

    post(client, "/settings/llm", LLM_FORM | {"clear_gemini_api_key": "true"})

    assert "••••1234" not in client.get("/settings/llm").text


def test_a_typed_api_key_is_not_echoed_back_on_errors(client):
    response = post(client, "/settings/llm", LLM_FORM | {"gemini_api_key": "AIzaSecreta1234", "ollama_base_url": "ftp://x"})

    assert response.status_code == 422
    assert "AIzaSecreta1234" not in response.text


def test_custom_match_prompt_is_used_and_can_be_reset(client, llm):
    response = post(client, "/settings/llm/prompts/MATCH_ENGINE_PROMPT", {"template_text": "Avalie com rigor. JSON."})
    assert response.headers["location"] == "/settings/llm?saved=prompt#MATCH_ENGINE_PROMPT"
    assert "Personalizado" in client.get("/settings/llm").text

    key = client.post("/api/searches", json={"search_term": "python"}).json()["jobs"][0]["key"]
    client.post(f"/api/jobs/{key}/match")
    assert llm.calls[-1]["system_prompt"] == "Avalie com rigor. JSON."

    post(client, "/settings/llm/prompts/MATCH_ENGINE_PROMPT/reset", {})
    client.post(f"/api/jobs/{key}/match", params={"force": True})
    assert llm.calls[-1]["system_prompt"].startswith("Você é um recrutador técnico sênior")


def test_unknown_prompt_is_rejected(client):
    assert post(client, "/settings/llm/prompts/OUTRO", {"template_text": "x"}).status_code == 422


# --- Conectores & rate limits ----------------------------------------------------------


def test_scrapers_tab_shows_the_env_defaults(client):
    page = client.get("/settings/scrapers").text

    assert 'name="max_requests_per_hour" type="number" inputmode="numeric"\n               value="60"' in page
    assert page.count('name="active_sites"') == 5


def test_only_active_platforms_appear_in_the_search(client, repository):
    post(client, "/settings/scrapers", SCRAPERS_FORM | {"active_sites": ["indeed"]})

    home = client.get("/").text
    assert 'name="sites" value="indeed"' in home
    assert 'name="sites" value="linkedin"' not in home

    client.post("/api/searches", json={"search_term": "python", "sites": ["linkedin", "indeed"]})
    assert repository.calls[-1].sites == ("indeed",)
    response = client.post("/api/searches", json={"search_term": "python", "sites": ["linkedin"]})
    assert response.status_code == 422


def test_hourly_limit_is_enforced(client, repository):
    post(client, "/settings/scrapers", SCRAPERS_FORM | {"max_requests_per_hour": "2"})

    assert client.post("/api/searches", json={"search_term": "python", "sites": ["linkedin", "indeed"]}).status_code == 200
    response = client.post("/api/searches", json={"search_term": "python", "sites": ["linkedin"]})

    assert response.status_code == 429
    assert "Limite de 2 requisições por hora" in response.json()["detail"]
    page = client.post("/search", data={"search_term": "python", "sites": ["linkedin"]}, headers=SAME_ORIGIN)
    assert page.status_code == 429 and "Limite de 2 requisições" in page.text
    assert len(repository.calls) == 1


def test_invalid_scraper_settings_are_rejected(client):
    response = post(client, "/settings/scrapers", SCRAPERS_FORM | {"min_delay_seconds": "9", "max_delay_seconds": "3"})

    assert response.status_code == 422
    assert "mínimo &lt;= máximo" in response.text
    assert post(client, "/settings/scrapers", SCRAPERS_FORM | {"active_sites": []}).status_code == 422


# --- Instalação nova ---------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/settings/profile", "/settings/llm", "/settings/scrapers"])
def test_panel_works_on_a_fresh_install(blank_client, path):
    response = blank_client.get(path)

    assert response.status_code == 200


def test_a_profile_built_in_the_panel_enables_match_and_cv(blank_client, llm):
    post(blank_client, "/settings/profile/details", {"full_name": "Ana Souza", "headline": "Backend", "language": "pt"})
    post(blank_client, "/settings/profile/blocks", {"category": "SKILL", "title": "Python"})
    post(
        blank_client,
        "/settings/profile/experiences",
        {"id": "pagamentos", "title": "Engenheira", "company": "Pagamentos SA", "start": "2022-03",
         "highlights": "Migrei o monólito para FastAPI.", "technologies": "FastAPI", "is_active": "true"},
    )

    key = blank_client.post("/api/searches", json={"search_term": "python"}).json()["jobs"][0]["key"]
    assert blank_client.post(f"/api/jobs/{key}/match").json()["matched_skills"] == ["Python"]

    llm._response = {
        "headline": "Engenheira Backend",
        "summary": "Engenheira backend com foco em Python.",
        "skills": ["Python", "FastAPI"],
        "experiences": [{"id": "pagamentos", "highlights": ["Migrei o monólito para FastAPI."]}],
        "matched_keywords": ["Python"],
    }
    cv = blank_client.post(f"/api/jobs/{key}/cvs", json={"language": "pt"})
    assert cv.status_code == 200
    assert cv.json()["experiences"][0]["company"] == "Pagamentos SA"
