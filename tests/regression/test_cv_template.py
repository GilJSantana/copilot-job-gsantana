"""O template de CV compila, fica em uma página e trata os dados como texto puro."""

import json
from pathlib import Path

import pytest
import typst

pytestmark = pytest.mark.regression

TEMPLATE = Path("templates/cv/ats_base.typ")
EXAMPLE = json.loads(Path("templates/cv/ats_base.example.json").read_text(encoding="utf-8"))


def compile_cv(data: dict | None = None, **options) -> bytes:
    sys_inputs = {"cv": json.dumps(data)} if data is not None else {}
    return typst.compile(str(TEMPLATE), sys_inputs=sys_inputs, **options)


def test_example_compiles_standalone():
    assert compile_cv().startswith(b"%PDF")


@pytest.mark.parametrize("lang", ["pt", "en"])
def test_compiles_in_both_languages(lang):
    assert compile_cv(EXAMPLE | {"lang": lang}).startswith(b"%PDF")


def test_compiles_as_pdf_ua1():
    """PDF/UA-1 exige, entre outros, título e idioma do documento: o template os define."""
    assert compile_cv(EXAMPLE, pdf_standards=["ua-1"]).startswith(b"%PDF")


def test_optional_sections_can_be_absent():
    minimal = {
        "lang": "pt",
        "name": "Ana",
        "headline": "Dev",
        "experiences": [
            {"title": "Dev", "company": "ACME", "start": "2020-01", "end": None, "highlights": ["Fiz APIs."]}
        ],
    }

    assert compile_cv(minimal).startswith(b"%PDF")


def test_data_is_never_interpreted_as_typst_markup():
    """Histórico e texto do LLM entram como texto: marcação Typst não pode executar
    (um #panic interpretado derrubaria a compilação; um $ solto quebraria o parser)."""
    hostile = '#panic("injetado") $ * _ @ref <label> #import "x.typ"'
    data = EXAMPLE | {
        "name": hostile,
        "summary": hostile,
        "skills": [hostile],
        "experiences": [EXAMPLE["experiences"][0] | {"title": hostile, "highlights": [hostile]}],
    }

    assert compile_cv(data).startswith(b"%PDF")
