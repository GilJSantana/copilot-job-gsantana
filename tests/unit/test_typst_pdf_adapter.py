import io
from dataclasses import replace

import pytest
from pypdf import PdfReader

from app.adapters.typst_pdf_adapter import TypstPdfAdapter, build_render_data
from app.domain.exceptions import CVRenderError
from app.domain.models import OutreachLanguage, TailoredExperience
from tests.cv_builders import HISTORY, tailored_cv

pytestmark = pytest.mark.unit


def text_of(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


# --- Dados enviados ao template ------------------------------------------------------


def test_render_data_combines_history_facts_with_tailored_content():
    data = build_render_data(HISTORY, tailored_cv())

    assert data["name"] == "Ana Souza"
    assert data["headline"] == "Engenheira Backend | Python e Kafka"  # do CV
    assert data["contact"]["email"] == "ana@email.com"  # do histórico
    assert data["skills"] == ["Python", "Kafka", "AWS"]
    assert data["keywords"] == ["Python", "Kafka"]
    assert data["lang"] == "pt"
    first = data["experiences"][0]
    assert (first["title"], first["company"], first["start"], first["end"]) == (
        "Engenheira de Software Sênior",
        "Pagamentos SA",
        "2022-03",
        None,
    )
    assert first["highlights"] == ["Processei 2 milhões de transações por dia com Kafka."]
    assert data["education"][0]["institution"] == "USP"
    assert data["certifications"] == [{"name": "AWS Developer Associate", "issuer": "AWS", "year": 2023}]


def test_render_data_follows_the_order_of_the_tailored_cv():
    cv = tailored_cv(experiences=tuple(reversed(tailored_cv().experiences)))

    assert [e["company"] for e in build_render_data(HISTORY, cv)["experiences"]] == [
        "Logística Ltda",
        "Pagamentos SA",
    ]


def test_render_data_refuses_unknown_experience():
    cv = tailored_cv(experiences=(TailoredExperience(experience_id="google", highlights=()),))

    with pytest.raises(CVRenderError):
        build_render_data(HISTORY, cv)


# --- PDF ---------------------------------------------------------------------------------


async def test_generates_pdf_readable_by_ats_in_logical_order():
    pdf = await TypstPdfAdapter().generate_pdf(HISTORY, tailored_cv())

    text = text_of(pdf)
    sections = ["RESUMO PROFISSIONAL", "COMPETÊNCIAS", "EXPERIÊNCIA PROFISSIONAL", "FORMAÇÃO ACADÊMICA"]
    positions = [text.index(section) for section in sections]
    assert positions == sorted(positions)
    assert text.index("Pagamentos SA") < text.index("Logística Ltda")
    assert "Processei 2 milhões de transações por dia com Kafka." in text
    # só os highlights escolhidos para a vaga entram, não o histórico inteiro
    assert "Participei de plantões de suporte." not in text
    assert "03/2022 – Atual" in text


async def test_pdf_metadata_supports_ats_indexing():
    pdf = await TypstPdfAdapter().generate_pdf(HISTORY, tailored_cv())

    metadata = PdfReader(io.BytesIO(pdf)).metadata
    assert metadata.author == "Ana Souza"
    assert metadata.title == "Ana Souza — Engenheira Backend | Python e Kafka"
    assert metadata["/Keywords"] == "Python, Kafka"


async def test_english_cv_uses_english_headings():
    pdf = await TypstPdfAdapter().generate_pdf(HISTORY, tailored_cv(language=OutreachLanguage.EN))

    text = text_of(pdf)
    assert "PROFESSIONAL EXPERIENCE" in text
    assert "03/2022 – Present" in text


@pytest.mark.parametrize(("standard", "declares_ua"), [("ua-1", True), (None, False)])
async def test_pdf_is_tagged_and_ua1_declares_conformance(standard, declares_ua):
    """O Typst marca a estrutura (títulos, listas, ordem de leitura) sempre; o PDF/UA-1
    além disso valida os requisitos de acessibilidade na compilação e os declara."""
    pdf = await TypstPdfAdapter(pdf_standard=standard).generate_pdf(HISTORY, tailored_cv())

    root = PdfReader(io.BytesIO(pdf)).trailer["/Root"]
    xmp = root["/Metadata"].get_object().get_data().decode()
    assert "/StructTreeRoot" in root
    assert root["/MarkInfo"]["/Marked"] == True  # noqa: E712 — BooleanObject do pypdf
    assert ("pdfuaid:part" in xmp) is declares_ua


async def test_fits_one_page_for_a_typical_history():
    pdf = await TypstPdfAdapter().generate_pdf(HISTORY, tailored_cv())

    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_template_name_comes_from_the_file():
    assert TypstPdfAdapter().template == "ats_base"


def test_missing_template_fails_at_startup(tmp_path):
    with pytest.raises(ValueError, match="não encontrado"):
        TypstPdfAdapter(tmp_path / "nao_existe.typ")


async def test_broken_template_is_a_render_error(tmp_path):
    broken = tmp_path / "quebrado.typ"
    broken.write_text("#let x = (\n", encoding="utf-8")

    with pytest.raises(CVRenderError, match="quebrado.typ"):
        await TypstPdfAdapter(broken).generate_pdf(HISTORY, tailored_cv())


async def test_history_facts_with_special_characters_render_as_text():
    history = replace(HISTORY, full_name="Ana #Souza $ _Dev_")

    pdf = await TypstPdfAdapter().generate_pdf(history, tailored_cv())

    assert "Ana #Souza $ _Dev_" in text_of(pdf)
