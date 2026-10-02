import json
import os
from pathlib import Path

import pytest

from app.domain.exceptions import ProfileError
from app.domain.models import OutreachLanguage
from app.repositories.career_history_repository import JsonCareerHistoryRepository

pytestmark = pytest.mark.unit

EXAMPLE = json.loads(Path("profile_data/profile_base.example.json").read_text(encoding="utf-8"))


@pytest.fixture
def path(tmp_path):
    path = tmp_path / "profile_base.json"
    path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
    return path


def with_experience(**changes):
    return EXAMPLE | {"experiences": [EXAMPLE["experiences"][0] | changes]}


async def test_example_shipped_with_the_project_is_valid(path):
    history = await JsonCareerHistoryRepository(path).get()

    assert history.full_name == "Seu Nome"
    assert [e.id for e in history.experiences] == ["empresa-atual", "empresa-anterior"]
    assert history.experiences[0].is_current
    assert history.contact.linkedin == "linkedin.com/in/seu-perfil"
    assert history.certifications[0].year == 2023
    assert history.language is OutreachLanguage.PT


async def test_language_is_optional_and_validated(path):
    without = {key: value for key, value in EXAMPLE.items() if key != "language"}
    path.write_text(json.dumps(without), encoding="utf-8")
    assert (await JsonCareerHistoryRepository(path).get()).language is OutreachLanguage.PT

    path.write_text(json.dumps(EXAMPLE | {"language": "fr"}), encoding="utf-8")
    with pytest.raises(ProfileError, match="language"):
        await JsonCareerHistoryRepository(path).get()


async def test_picks_up_edits_without_restart(path):
    repository = JsonCareerHistoryRepository(path)
    before = await repository.get()

    stat = path.stat()
    path.write_text(json.dumps(EXAMPLE | {"headline": "Staff Engineer"}), encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    after = await repository.get()

    assert after.headline == "Staff Engineer"
    assert after.fingerprint != before.fingerprint


async def test_missing_file_explains_how_to_create_it(tmp_path):
    with pytest.raises(ProfileError, match="Histórico profissional não encontrado.*profile_base.example.json"):
        await JsonCareerHistoryRepository(tmp_path / "nao-existe.json").get()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (EXAMPLE | {"experiences": []}, "experiences"),
        (with_experience(start="03/2022"), "AAAA-MM"),
        (with_experience(start="2022-03", end="2021-01"), "anterior ao início"),
        (with_experience(id="Empresa Atual"), "experiences.0.id"),
        (EXAMPLE | {"experiences": [EXAMPLE["experiences"][0]] * 2}, "repetidos"),
        (EXAMPLE | {"contact": {"emial": "x"}}, "emial"),
        (EXAMPLE | {"full_name": ""}, "full_name"),
    ],
)
async def test_invalid_file_names_the_problem(path, data, expected):
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ProfileError, match=expected):
        await JsonCareerHistoryRepository(path).get()
