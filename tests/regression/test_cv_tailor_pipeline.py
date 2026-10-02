"""CV Tailor de ponta a ponta com as implementações reais (Typst, disco, SQLite);
só o LLM é substituído."""

import io
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from app.adapters.local_file_storage import LocalFileStorage
from app.adapters.typst_pdf_adapter import TypstPdfAdapter
from app.domain.models import OutreachLanguage
from app.repositories.career_history_repository import JsonCareerHistoryRepository
from app.repositories.cv_version_store import SqlAlchemyCVVersionStore
from app.repositories.job_store import SqlAlchemyJobStore
from app.services.cv_optimizer import LLMCVOptimizer
from app.services.cv_tailor_service import CVTailorService
from tests.cv_builders import JOB
from tests.doubles import MockLLMAdapter

pytestmark = pytest.mark.regression

EXAMPLE = json.loads(Path("profile_data/profile_base.example.json").read_text(encoding="utf-8"))

LLM_RESPONSE = {
    "headline": "Engenheiro de Software Backend | Python e FastAPI",
    "summary": "Resumo completo da sua carreira.",
    "skills": ["Python", "FastAPI", "AWS"],
    "experiences": [
        {"id": "empresa-atual", "highlights": ["Reduzi a latência p95 da API de 800 ms para 120 ms com FastAPI."]},
        {"id": "empresa-anterior", "highlights": ["Desenvolvi APIs REST em Django e PostgreSQL."]},
    ],
    "matched_keywords": ["Python", "FastAPI"],
}


async def test_tailors_renders_stores_and_reads_back(tmp_path, session_factory):
    history_path = tmp_path / "profile_base.json"
    history_path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
    await SqlAlchemyJobStore(session_factory).save_many([JOB])
    service = CVTailorService(
        JsonCareerHistoryRepository(history_path),
        LLMCVOptimizer(MockLLMAdapter(LLM_RESPONSE)),
        TypstPdfAdapter(),
        LocalFileStorage(tmp_path / "output_cvs"),
        SqlAlchemyCVVersionStore(session_factory),
    )

    version = await service.tailor(JOB, language=OutreachLanguage.PT)
    found, pdf = await service.read_pdf(version.id)

    assert found == version
    assert (tmp_path / "output_cvs" / version.pdf_path).read_bytes() == pdf
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Engenheiro de Software Backend | Python e FastAPI" in text
    assert "Reduzi a latência p95 da API de 800 ms para 120 ms com FastAPI." in text
    assert text.index("Empresa Atual") < text.index("Empresa Anterior")
