import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from app.domain.exceptions import ProfileBlockNotFoundError, ProfileError
from app.domain.models import (
    Experience,
    OutreachLanguage,
    ProfileBlockCategory,
    ProfileDetails,
    WorkMode,
)
from app.repositories.career_history_repository import JsonCareerHistoryRepository
from app.repositories.profile_repository import JsonProfileRepository
from app.services.profile_service import ProfileService, StoredCandidateProfiles, StoredCareerHistories
from tests.cv_builders import HISTORY
from tests.doubles import InMemoryProfileBlockStore, InMemorySystemConfigStore

pytestmark = pytest.mark.unit

DETAILS = ProfileDetails(
    full_name="Gil Jesus",
    headline="Engenheiro de Dados | Python e AWS",
    summary="+20 anos em TI.",
    years_of_experience=20,
    target_roles=("Data Engineer",),
    preferred_work_modes=(WorkMode.REMOTE,),
)

BRADESCO = Experience(
    id="bradesco",
    title="Engenheiro de Dados",
    company="Bradesco",
    start="2015-01",
    end="2020-12",
    highlights=("Reduzi em 76% o tempo de ETL.",),
    technologies=("Python", "SQL"),
)
MOVE_TECH = Experience(id="move-tech", title="Tech Lead", company="Move Tech 40+", start="2021-01")


@pytest.fixture
def service() -> ProfileService:
    return ProfileService(InMemorySystemConfigStore(), InMemoryProfileBlockStore())


async def configured(service: ProfileService) -> ProfileService:
    await service.save_details(DETAILS)
    await service.save_experience(BRADESCO)
    await service.save_experience(MOVE_TECH)
    await service.save_block(ProfileBlockCategory.SKILL, "Python")
    await service.save_block(ProfileBlockCategory.SKILL, "AWS")
    await service.save_block(ProfileBlockCategory.METRIC, "Migração de 20TB no S3", "Data lake na AWS")
    return service


# --- Dados gerais ---------------------------------------------------------------------


async def test_details_round_trip(service):
    assert await service.details() is None

    await service.save_details(DETAILS)

    assert await service.details() == DETAILS


async def test_corrupted_details_are_a_profile_error():
    configs = InMemorySystemConfigStore()
    configs.values["profile.details"] = '{"full_name": ""}'

    with pytest.raises(ProfileError, match="inválidos"):
        await ProfileService(configs, InMemoryProfileBlockStore()).details()


# --- Visões para o match e o CV --------------------------------------------------------


async def test_candidate_profile_is_built_from_details_and_active_blocks(service):
    await configured(service)

    profile = await service.candidate_profile()

    assert (profile.full_name, profile.years_of_experience) == ("Gil Jesus", 20)
    assert profile.skills == ("Python", "AWS")
    assert profile.target_roles == ("Data Engineer",)
    # experiência atual primeiro
    assert profile.experiences == (
        "Tech Lead — Move Tech 40+ (2021-01 a atual)",
        "Engenheiro de Dados — Bradesco (2015-01 a 2020-12)",
    )
    assert profile.achievements == ("Migração de 20TB no S3: Data lake na AWS",)


async def test_career_history_orders_experiences_and_carries_achievements(service):
    await configured(service)

    history = await service.career_history()

    assert [e.id for e in history.experiences] == ["move-tech", "bradesco"]
    assert history.skills == ("Python", "AWS")
    assert history.achievements == ("Migração de 20TB no S3: Data lake na AWS",)
    assert history.contact == DETAILS.contact


async def test_inactive_blocks_stay_out_of_match_and_cv(service):
    await configured(service)
    aws = (await service.blocks(ProfileBlockCategory.SKILL))[1]
    bradesco = (await service.experiences())[0][0]

    await service.set_active(aws.id, False)
    await service.set_active(bradesco.id, False)

    assert (await service.candidate_profile()).skills == ("Python",)
    assert [e.id for e in (await service.career_history()).experiences] == ["move-tech"]


async def test_editing_a_block_changes_the_fingerprints(service):
    await configured(service)
    profile, history = await service.candidate_profile(), await service.career_history()

    await service.save_block(ProfileBlockCategory.SKILL, "Kubernetes")

    assert (await service.candidate_profile()).fingerprint != profile.fingerprint
    assert (await service.career_history()).fingerprint != history.fingerprint


@pytest.mark.parametrize(
    ("missing", "message"),
    [("details", "/settings/profile"), ("skills", "competência"), ("experiences", "experiência")],
)
async def test_missing_data_explains_where_to_fix(service, missing, message):
    if missing != "details":
        await service.save_details(DETAILS)
    if missing != "experiences":
        await service.save_experience(BRADESCO)
    if missing != "skills":
        await service.save_block(ProfileBlockCategory.SKILL, "Python")

    view = service.career_history if missing == "experiences" else service.candidate_profile
    with pytest.raises(ProfileError, match=message):
        await view()


async def test_ports_delegate_to_the_service(service):
    await configured(service)

    assert await StoredCandidateProfiles(service).get() == await service.candidate_profile()
    assert await StoredCareerHistories(service).get() == await service.career_history()


# --- Experiências --------------------------------------------------------------------


async def test_suggested_ids_are_slugs_that_do_not_collide(service):
    assert await service.suggest_experience_id("Move Tech 40+") == "move-tech-40"

    await service.save_experience(replace(MOVE_TECH, id="vava-doces"))

    assert await service.suggest_experience_id("Vavá Doces") == "vava-doces-2"


async def test_experience_ids_must_be_unique_and_well_formed(service):
    await service.save_experience(BRADESCO)

    with pytest.raises(ValueError, match="já existe"):
        await service.save_experience(replace(MOVE_TECH, id="bradesco"))
    with pytest.raises(ValueError, match="minúsculas"):
        await service.save_experience(replace(MOVE_TECH, id="Move Tech"))


async def test_the_experience_id_is_fixed_after_creation(service):
    """As versões de CV referenciam a experiência pelo id."""
    block = await service.save_experience(BRADESCO)

    await service.save_experience(replace(BRADESCO, id="outro", title="Coordenador"), block_id=block.id)

    assert await service.experience(block.id) == replace(BRADESCO, title="Coordenador")


async def test_unknown_or_mismatched_blocks_are_not_found(service):
    skill = await service.save_block(ProfileBlockCategory.SKILL, "Python")

    with pytest.raises(ProfileBlockNotFoundError):
        await service.experience(skill.id)
    with pytest.raises(ProfileBlockNotFoundError):
        await service.save_block(ProfileBlockCategory.METRIC, "x", block_id=skill.id)
    with pytest.raises(ProfileBlockNotFoundError):
        await service.block(999)


async def test_experiences_cannot_be_saved_as_plain_blocks(service):
    with pytest.raises(ValueError):
        await service.save_block(ProfileBlockCategory.EXPERIENCE, "Bradesco")


# --- Importação dos arquivos JSON -----------------------------------------------------

PROFILE_FILE = {
    "full_name": "Ana S.",
    "headline": "Backend Developer",
    "skills": ["python", "Kubernetes"],
    "years_of_experience": 6,
    "target_roles": ["Backend Engineer"],
    "preferred_work_modes": ["remote"],
}


def write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def repositories(tmp_path: Path, profile: dict | None, history: dict | None):
    return (
        JsonProfileRepository(write(tmp_path / "profile.json", profile) if profile else tmp_path / "x.json"),
        JsonCareerHistoryRepository(
            write(tmp_path / "profile_base.json", history) if history else tmp_path / "y.json"
        ),
    )


async def test_import_merges_both_files(service, tmp_path):
    imported = await service.import_legacy(*repositories(tmp_path, PROFILE_FILE, asdict(HISTORY)))

    assert imported is True
    details = await service.details()
    # identificação do histórico (escrito para o CV); preferências do profile.json
    assert (details.full_name, details.headline) == (HISTORY.full_name, HISTORY.headline)
    assert (details.years_of_experience, details.target_roles) == (6, ("Backend Engineer",))
    assert details.education == HISTORY.education
    # skills sem repetir (comparação sem caixa), na ordem do histórico
    assert (await service.candidate_profile()).skills == (*HISTORY.skills, "Kubernetes")
    assert {e.id for e in (await service.career_history()).experiences} == {"logistica", "pagamentos"}


async def test_import_works_with_only_the_profile_file(service, tmp_path):
    assert await service.import_legacy(*repositories(tmp_path, PROFILE_FILE, None)) is True

    profile = await service.candidate_profile()
    assert (profile.full_name, profile.skills) == ("Ana S.", ("python", "Kubernetes"))
    assert (await service.details()).language is OutreachLanguage.PT
    with pytest.raises(ProfileError, match="experiência"):
        await service.career_history()


async def test_import_never_overwrites_the_database(service, tmp_path):
    await service.save_block(ProfileBlockCategory.SKILL, "Go")

    assert await service.import_legacy(*repositories(tmp_path, PROFILE_FILE, asdict(HISTORY))) is False
    assert await service.details() is None


async def test_import_without_files_or_with_invalid_files_does_nothing(service, tmp_path):
    assert await service.import_legacy(*repositories(tmp_path, None, None)) is False
    assert await service.import_legacy(*repositories(tmp_path, {"full_name": ""}, None)) is False
    assert await service.details() is None
