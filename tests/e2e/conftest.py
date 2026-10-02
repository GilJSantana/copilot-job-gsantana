import json
from collections.abc import Iterator
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.models import JobPosting, JobSite
from app.web.app import create_app
from app.web.container import Overrides
from tests.cv_builders import HISTORY
from tests.doubles import FakeJobRepository, MockLLMAdapter

# mesma pessoa do HISTORY: na subida os dois arquivos são importados juntos para o banco
PROFILE = {
    "full_name": "Ana Souza",
    "headline": "Backend Python Developer",
    "skills": ["Python", "FastAPI", "Docker"],
    "years_of_experience": 6,
}

LLM_RESPONSE = {
    "score": 90,
    "rationale": "Boa aderência técnica.",
    "strengths": ["Python sólido"],
    "gaps": ["Kubernetes"],
}


def make_job(title: str = "Python Developer", **overrides: Any) -> JobPosting:
    values: dict[str, Any] = {
        "title": title,
        "company": "ACME",
        "location": "São Paulo, SP",
        "url": f"https://www.linkedin.com/jobs/view/{abs(hash(title))}",
        "source": JobSite.LINKEDIN,
        "description": "Buscamos Python, FastAPI e Docker.",
    }
    return JobPosting(**values | overrides)


@pytest.fixture
def profile_path(tmp_path: Path) -> Path:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(PROFILE), encoding="utf-8")
    return path


@pytest.fixture
def history_path(tmp_path: Path) -> Path:
    path = tmp_path / "profile_base.json"
    path.write_text(json.dumps(asdict(HISTORY), ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def cv_output_dir(tmp_path: Path) -> Path:
    return tmp_path / "output_cvs"


@pytest.fixture
def repository() -> FakeJobRepository:
    return FakeJobRepository(
        [
            make_job("Python Developer"),
            make_job("Data Engineer"),
            # mesma vaga do primeiro item, publicada no Indeed
            make_job(
                "Python Developer",
                source=JobSite.INDEED,
                url="https://br.indeed.com/viewjob?jk=1",
                location="São Paulo, São Paulo, Brazil",
            ),
        ]
    )


@pytest.fixture
def llm() -> MockLLMAdapter:
    return MockLLMAdapter(LLM_RESPONSE)


# skills do perfil importado: as do histórico e depois as do profile.json, sem repetir
SKILLS = ["Python", "FastAPI", "Django", "PostgreSQL", "Docker"]


def _client(profile_path: Path, history_path: Path, cv_output_dir: Path, repository, llm) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        profile_path=profile_path,
        career_history_path=history_path,
        cv_output_dir=cv_output_dir,
        llm_provider="ollama",
    )
    app = create_app(settings, Overrides(job_repository=repository, llm=llm))
    with TestClient(app) as client:  # o "with" executa o lifespan (migrações, importação, conexões)
        yield client


@pytest.fixture
def client(profile_path, history_path, cv_output_dir, repository, llm) -> Iterator[TestClient]:
    """Banco com o perfil e o histórico importados dos arquivos JSON."""
    yield from _client(profile_path, history_path, cv_output_dir, repository, llm)


@pytest.fixture
def blank_client(tmp_path, cv_output_dir, repository, llm) -> Iterator[TestClient]:
    """Instalação nova: nenhum arquivo para importar, banco sem perfil."""
    yield from _client(tmp_path / "nao-existe.json", tmp_path / "nao-existe-base.json", cv_output_dir, repository, llm)


SAME_ORIGIN = {"origin": "http://testserver"}
