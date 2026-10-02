"""Perfil do candidato lido de profile_data/profile.json (fonte da importação inicial para o banco)."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.domain.interfaces import IProfileRepository
from app.domain.models import CandidateProfile, WorkMode
from app.repositories.json_file import CachedJsonFile


class _ProfileFile(BaseModel):
    """Formato do arquivo. Campos desconhecidos são recusados para pegar erros de digitação."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    skills: list[str] = Field(min_length=1)
    summary: str = ""
    years_of_experience: float = Field(default=0.0, ge=0)
    target_roles: list[str] = []
    preferred_locations: list[str] = []
    preferred_work_modes: list[WorkMode] = []
    languages: list[str] = []


class JsonProfileRepository(IProfileRepository):
    """Relê o arquivo sempre que ele muda: editar o perfil tem efeito imediato
    (e, via fingerprint, faz os matches antigos serem recalculados)."""

    def __init__(self, path: Path) -> None:
        self._file = CachedJsonFile(
            path,
            _ProfileFile,
            lambda data: CandidateProfile(**data.model_dump()),
            label="Perfil",
            example_hint="profile_data/profile.example.json",
        )

    async def get(self) -> CandidateProfile:
        return await self._file.load()
