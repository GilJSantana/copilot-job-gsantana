import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.web.app import create_app
from tests.e2e.conftest import SAME_ORIGIN

pytestmark = pytest.mark.e2e

FORM = {"search_term": "python", "location": "São Paulo", "sites": ["linkedin", "indeed"]}


def test_search_page_renders_components_and_handlers(client):
    html = client.post("/search", data=FORM, headers=SAME_ORIGIN).text

    assert "Buscar Oportunidades" in html
    assert "2 vagas encontradas" in html
    assert html.count("data-job-card") == 2
    assert 'data-action="optimize-cv"' in html
    assert 'data-action="copy-pitch"' in html
    assert "data-loading-template" in html
    assert "/static/js/job_search.js" in html


def test_advanced_filters_open_when_values_differ_from_defaults(client):
    default = client.get("/").text
    changed = client.post("/search", data=FORM | {"results_wanted": "5"}, headers=SAME_ORIGIN).text

    assert "<details" in default and " open>" not in default
    assert " open>" in changed


def test_search_script_is_served(client):
    response = client.get("/static/js/job_search.js")

    assert response.status_code == 200
    assert "onOptimizeCV" in response.text


def test_preview_is_disabled_by_default(client):
    assert client.get("/preview/search").status_code == 404


def test_preview_renders_mock_jobs_with_every_verdict(tmp_path):
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        profile_path=tmp_path / "profile.json",
        ui_preview=True,
    )
    with TestClient(create_app(settings)) as client:
        html = client.get("/preview/search").text

    assert "5 vagas encontradas" in html
    for score in ("88% Match", "71% Match", "54% Match", "23% Match"):
        assert score in html
    assert "Match não analisado" in html
    assert "dados simulados" in html
