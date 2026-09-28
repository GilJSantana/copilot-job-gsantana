import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.models import JobPosting, JobSite
from app.web.app import create_app
from app.web.container import Overrides
from tests.doubles import FakeJobRepository, MockLLMAdapter

PROFILE = {
    "full_name": "Gil Jesus",
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


@pytest.fixture
def client(profile_path, repository, llm) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///:memory:",
        profile_path=profile_path,
        llm_provider="ollama",
    )
    app = create_app(settings, Overrides(job_repository=repository, llm=llm))
    with TestClient(app) as client:  # o "with" executa o lifespan (migrações, conexões)
        yield client


SAME_ORIGIN = {"origin": "http://testserver"}
