from datetime import date

import pytest

from app.web.templating import description_blocks, job_type_label, posted_ago, seniority_label

pytestmark = pytest.mark.unit

TODAY = date(2026, 10, 1)


@pytest.mark.parametrize(
    ("posted", "expected"),
    [
        (date(2026, 10, 1), "hoje"),
        (date(2026, 10, 2), "hoje"),  # fuso da fonte adiantado
        (date(2026, 9, 30), "ontem"),
        (date(2026, 9, 26), "há 5 dias"),
        (date(2026, 8, 1), "em 01/08/2026"),
        (None, ""),
    ],
)
def test_posted_ago(posted, expected):
    assert posted_ago(posted, today=TODAY) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Python Engineer", "Sênior"),
        ("Desenvolvedor Sênior", "Sênior"),
        ("Sr. Backend Developer", "Sênior"),
        ("Tech Lead Sênior", "Liderança"),
        ("Backend Developer Pleno", "Pleno"),
        ("Desenvolvedor Júnior", "Júnior"),
        ("Estagiário de Dados", "Júnior"),
        ("PL/SQL Developer", None),
        ("Internal Tools Engineer", None),
        ("Python Developer", None),
    ],
)
def test_seniority_label(title, expected):
    assert seniority_label(title) == expected


def test_job_type_label_translates_known_and_keeps_unknown():
    assert job_type_label("fulltime") == "Tempo integral"
    assert job_type_label("fulltime, contract") == "Tempo integral, Contrato"
    assert job_type_label("freelance") == "freelance"


def test_description_blocks_clean_jobspy_markdown():
    text = (
        "**Job Description:**\n"
        " Work in a fast\\-paced, mid\\-level team \\& grow.\n"
        "   \n\n"
        "Second   paragraph\n"
        "continues here with **bold** text.\n"
        "* First item\n"
        "* Second \\(CI\\-CD\\)\n"
        "\n"
        "**Skills:** Python"
    )

    assert description_blocks(text) == [
        ("h", "Job Description"),
        ("p", "Work in a fast-paced, mid-level team & grow."),
        ("p", "Second paragraph continues here with bold text."),
        ("ul", ["First item", "Second (CI-CD)"]),
        ("p", "Skills: Python"),
    ]


def test_description_blocks_of_empty_text():
    assert description_blocks("") == []
