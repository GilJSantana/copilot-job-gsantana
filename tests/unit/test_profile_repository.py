import json
import os
from pathlib import Path

import pytest

from app.domain.exceptions import ProfileError
from app.domain.models import WorkMode
from app.repositories.profile_repository import JsonProfileRepository

pytestmark = pytest.mark.unit

VALID = {
    "full_name": "Gil",
    "headline": "Backend Python",
    "skills": ["Python", "Docker"],
    "preferred_work_modes": ["remote", "hybrid"],
}


@pytest.fixture
def path(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    return path


def rewrite(path, data) -> None:
    """Grava e força um mtime diferente (sistemas de arquivos com baixa resolução)."""
    stat = path.stat()
    path.write_text(json.dumps(data), encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))


async def test_loads_profile_from_json(path):
    profile = await JsonProfileRepository(path).get()

    assert profile.full_name == "Gil"
    assert profile.skills == ("Python", "Docker")
    assert profile.preferred_work_modes == (WorkMode.REMOTE, WorkMode.HYBRID)


async def test_reuses_parsed_profile_while_file_is_unchanged(path):
    repository = JsonProfileRepository(path)

    assert await repository.get() is await repository.get()


async def test_picks_up_edits_without_restart(path):
    repository = JsonProfileRepository(path)
    before = await repository.get()

    rewrite(path, VALID | {"skills": ["Python", "Go"]})
    after = await repository.get()

    assert after.skills == ("Python", "Go")
    assert after.fingerprint != before.fingerprint


async def test_missing_file_explains_how_to_create_it(tmp_path):
    with pytest.raises(ProfileError, match="profile.example.json"):
        await JsonProfileRepository(tmp_path / "nao-existe.json").get()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("{ não é json", "arquivo"),
        (json.dumps(VALID | {"skills": []}), "skills"),
        (json.dumps(VALID | {"full_name": ""}), "full_name"),
        (json.dumps(VALID | {"years_of_experience": -1}), "years_of_experience"),
        (json.dumps(VALID | {"preferred_work_modes": ["lunar"]}), "preferred_work_modes"),
        (json.dumps(VALID | {"skils": ["typo"]}), "skils"),
    ],
)
async def test_invalid_file_names_the_problem(path, content, expected):
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ProfileError, match=expected):
        await JsonProfileRepository(path).get()


async def test_example_profile_shipped_with_the_project_is_valid():
    profile = await JsonProfileRepository(Path("profile_data/profile.example.json")).get()

    assert profile.skills
