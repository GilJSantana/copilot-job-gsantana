import hashlib
import json
from dataclasses import asdict, replace

import pytest

from app.domain.models import (
    CandidateProfile,
    JobSite,
    LLMProviderKind,
    LLMSettings,
    ProfileBlock,
    ProfileBlockCategory,
    ProfileDetails,
    PromptName,
    PromptTemplate,
    ScraperSettings,
)
from tests.cv_builders import HISTORY

pytestmark = pytest.mark.unit


def llm(**overrides) -> LLMSettings:
    values = {
        "provider": LLMProviderKind.OLLAMA,
        "gemini_model": "gemini-2.5-flash",
        "ollama_base_url": "http://localhost:11434",
        "ollama_model": "llama3.1",
    }
    return LLMSettings(**values | overrides)


def test_gemini_requires_an_api_key():
    with pytest.raises(ValueError, match="API key"):
        llm(provider=LLMProviderKind.GEMINI)

    assert llm(provider=LLMProviderKind.GEMINI, gemini_api_key="segredo").model == "gemini-2.5-flash"


def test_ollama_works_without_a_gemini_key():
    assert llm().model == "llama3.1"


@pytest.mark.parametrize("overrides", [{"ollama_base_url": "localhost:11434"}, {"ollama_model": " "}, {"gemini_model": ""}])
def test_llm_settings_reject_invalid_values(overrides):
    with pytest.raises(ValueError):
        llm(**overrides)


def test_api_key_never_appears_in_repr():
    assert "segredo" not in repr(llm(gemini_api_key="segredo"))


def scrapers(**overrides) -> ScraperSettings:
    values = {"active_sites": [JobSite.LINKEDIN], "min_delay_seconds": 2.0, "max_delay_seconds": 6.0}
    return ScraperSettings(**values | overrides)


def test_scraper_settings_normalize_sites_to_a_tuple():
    assert scrapers().active_sites == (JobSite.LINKEDIN,)


@pytest.mark.parametrize(
    "overrides",
    [
        {"active_sites": []},
        {"min_delay_seconds": -1},
        {"min_delay_seconds": 7.0},
        {"max_requests_per_hour": -1},
    ],
)
def test_scraper_settings_reject_invalid_values(overrides):
    with pytest.raises(ValueError):
        scrapers(**overrides)


def test_blocks_require_a_title_within_the_column_size():
    with pytest.raises(ValueError):
        ProfileBlock(category=ProfileBlockCategory.SKILL, title=" ")
    with pytest.raises(ValueError):
        ProfileBlock(category=ProfileBlockCategory.METRIC, title="x" * 101)


def test_prompts_cannot_be_empty():
    with pytest.raises(ValueError):
        PromptTemplate(name=PromptName.MATCH_ENGINE, template_text="  \n")


def test_profile_details_require_name_and_headline():
    with pytest.raises(ValueError):
        ProfileDetails(full_name="", headline="Dev")
    with pytest.raises(ValueError):
        ProfileDetails(full_name="Ana", headline="Dev", years_of_experience=-1)


def _fingerprint_before_the_panel(obj, *new_fields: str) -> str:
    data = {k: v for k, v in asdict(obj).items() if k not in new_fields}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def test_fingerprints_ignore_the_new_fields_while_empty():
    """Matches e CVs calculados antes dos campos do painel continuam válidos."""
    profile = CandidateProfile(full_name="Ana", headline="Dev", skills=("Python",))

    assert profile.fingerprint == _fingerprint_before_the_panel(profile, "experiences", "achievements")
    assert HISTORY.fingerprint == _fingerprint_before_the_panel(HISTORY, "achievements")
    assert replace(profile, achievements=("20TB no S3",)).fingerprint != profile.fingerprint
    assert replace(HISTORY, achievements=("20TB no S3",)).fingerprint != HISTORY.fingerprint


def test_achievements_back_numbers_cited_in_the_cv_summary():
    history = replace(HISTORY, achievements=("Migração de 20TB no S3",))

    assert "20TB" in history.full_text
