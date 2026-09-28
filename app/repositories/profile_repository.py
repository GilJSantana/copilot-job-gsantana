"""Perfil do candidato lido de um arquivo JSON (profile_data/profile.json)."""

import asyncio
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.exceptions import ProfileError
from app.domain.interfaces import IProfileRepository
from app.domain.models import CandidateProfile, WorkMode


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
        self._path = path
        self._cached: tuple[int, CandidateProfile] | None = None

    async def get(self) -> CandidateProfile:
        return await asyncio.to_thread(self._load)

    def _load(self) -> CandidateProfile:
        try:
            mtime = self._path.stat().st_mtime_ns
        except FileNotFoundError:
            raise ProfileError(
                f"Perfil não encontrado em {self._path}. "
                "Copie profile_data/profile.example.json para esse caminho e preencha."
            ) from None

        if self._cached and self._cached[0] == mtime:
            return self._cached[1]

        try:
            data = _ProfileFile.model_validate_json(self._path.read_bytes())
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, error['loc'])) or 'arquivo'}: {error['msg']}"
                for error in exc.errors()
            )
            raise ProfileError(f"Perfil inválido em {self._path} — {problems}") from exc

        profile = CandidateProfile(**data.model_dump())
        self._cached = (mtime, profile)
        return profile
