"""Erros de domínio do CV Tailor viram os status HTTP certos (JSON na API, HTML nas páginas)."""

import pytest

from app.domain.exceptions import CVIntegrityError, CVRenderError, CVVersionNotFoundError

pytestmark = pytest.mark.e2e

ERRORS = {
    "not-found": (CVVersionNotFoundError("versão x não encontrada"), 404),
    "integrity": (CVIntegrityError(["skills ausentes do histórico: Rust"]), 502),
    "render": (CVRenderError("template quebrado"), 500),
}


@pytest.fixture
def client_with_failing_routes(client):
    for name, (error, _) in ERRORS.items():

        async def fail(error=error):
            raise error

        client.app.add_api_route(f"/api/_test/{name}", fail)
        client.app.add_api_route(f"/_test/{name}", fail)
    return client


@pytest.mark.parametrize("name", ERRORS)
def test_api_returns_json_with_the_mapped_status(client_with_failing_routes, name):
    error, status = ERRORS[name]

    response = client_with_failing_routes.get(f"/api/_test/{name}")

    assert response.status_code == status
    assert response.json() == {"detail": str(error)}


@pytest.mark.parametrize("name", ERRORS)
def test_pages_render_the_error_page(client_with_failing_routes, name):
    _, status = ERRORS[name]

    response = client_with_failing_routes.get(f"/_test/{name}")

    assert response.status_code == status
    assert "Voltar às vagas" in response.text
