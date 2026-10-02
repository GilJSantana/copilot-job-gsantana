"""Histórico profissional lido de profile_data/profile_base.json (fonte da importação inicial para o banco)."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.domain.interfaces import ICareerHistoryRepository
from app.domain.models import (
    CareerHistory,
    Certification,
    ContactInfo,
    Education,
    Experience,
    OutreachLanguage,
)
from app.repositories.json_file import CachedJsonFile

_STRICT = ConfigDict(extra="forbid")


class _Contact(BaseModel):
    model_config = _STRICT
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    website: str = ""


class _Experience(BaseModel):
    model_config = _STRICT
    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    start: str
    end: str | None = None
    location: str = ""
    highlights: list[str] = []
    technologies: list[str] = []


class _Education(BaseModel):
    model_config = _STRICT
    degree: str = Field(min_length=1)
    institution: str = Field(min_length=1)
    start: str
    end: str | None = None


class _Certification(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1)
    issuer: str = ""
    year: int | None = None


class _HistoryFile(BaseModel):
    model_config = _STRICT
    full_name: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    contact: _Contact = _Contact()
    summary: str = ""
    skills: list[str] = []
    experiences: list[_Experience] = Field(min_length=1)
    education: list[_Education] = []
    certifications: list[_Certification] = []
    languages: list[str] = []
    # idioma em que o histórico está escrito
    language: OutreachLanguage = OutreachLanguage.PT
    achievements: list[str] = []


def _to_domain(data: _HistoryFile) -> CareerHistory:
    return CareerHistory(
        full_name=data.full_name,
        headline=data.headline,
        contact=ContactInfo(**data.contact.model_dump()),
        summary=data.summary,
        skills=tuple(data.skills),
        experiences=tuple(Experience(**e.model_dump()) for e in data.experiences),
        education=tuple(Education(**e.model_dump()) for e in data.education),
        certifications=tuple(Certification(**c.model_dump()) for c in data.certifications),
        languages=tuple(data.languages),
        language=data.language,
        achievements=tuple(data.achievements),
    )


class JsonCareerHistoryRepository(ICareerHistoryRepository):
    def __init__(self, path: Path) -> None:
        self._file = CachedJsonFile(
            path,
            _HistoryFile,
            _to_domain,
            label="Histórico profissional",
            example_hint="profile_data/profile_base.example.json",
        )

    async def get(self) -> CareerHistory:
        return await self._file.load()
