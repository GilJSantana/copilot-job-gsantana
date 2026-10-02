"""Perfil do candidato mantido no banco e editado pelo painel de configurações.

Uma única fonte alimenta o match (`CandidateProfile`) e o CV Tailor
(`CareerHistory`): dados gerais em system_configs e blocos em profile_core.
"""

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace

from pydantic import TypeAdapter, ValidationError

from app.domain.exceptions import ProfileBlockNotFoundError, ProfileError
from app.domain.interfaces import (
    ICareerHistoryRepository,
    IProfileBlockStore,
    IProfileRepository,
    ISystemConfigStore,
)
from app.domain.models import (
    PROFILE_BLOCK_TITLE_MAX,
    CandidateProfile,
    CareerHistory,
    ContactInfo,
    Experience,
    OutreachLanguage,
    ProfileBlock,
    ProfileBlockCategory,
    ProfileDetails,
    normalize_text,
)

logger = logging.getLogger(__name__)

DETAILS_KEY = "profile.details"
_DETAILS = TypeAdapter(ProfileDetails)
_EXPERIENCE = TypeAdapter(Experience)
_EXPERIENCE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

_NOT_CONFIGURED = "Perfil não configurado. Preencha os dados em /settings/profile"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_text(text)).strip("-") or "experiencia"


def _period(experience: Experience) -> str:
    return f"{experience.start} a {experience.end or 'atual'}"


class ProfileService:
    def __init__(self, configs: ISystemConfigStore, blocks: IProfileBlockStore) -> None:
        self._configs = configs
        self._blocks = blocks

    # --- Dados gerais ---------------------------------------------------------------

    async def details(self) -> ProfileDetails | None:
        stored = (await self._configs.get_many(DETAILS_KEY)).get(DETAILS_KEY)
        if stored is None:
            return None
        try:
            return _DETAILS.validate_json(stored)
        except ValidationError as exc:
            raise ProfileError(f"Dados do perfil inválidos no banco: {exc}") from exc

    async def save_details(self, details: ProfileDetails) -> None:
        await self._configs.set_many(
            {DETAILS_KEY: _DETAILS.dump_json(details).decode()},
            {DETAILS_KEY: "Dados gerais do perfil (JSON)"},
        )

    # --- Blocos ---------------------------------------------------------------------

    async def blocks(self, category: ProfileBlockCategory) -> list[ProfileBlock]:
        return await self._blocks.list_all(category)

    async def experiences(self) -> list[tuple[ProfileBlock, Experience]]:
        """Blocos de experiência (ativos ou não) com os campos já interpretados."""
        return [(block, self._experience(block)) for block in await self.blocks(ProfileBlockCategory.EXPERIENCE)]

    async def save_experience(
        self, experience: Experience, *, block_id: int | None = None, is_active: bool = True
    ) -> ProfileBlock:
        """O id da experiência é fixo depois de criado: as versões de CV o referenciam.

        Lança `ValueError` se o id for inválido ou já estiver em uso.
        """
        others = [(b, e) for b, e in await self.experiences() if b.id != block_id]
        if block_id is not None:
            experience = replace(experience, id=(await self.experience(block_id)).id)
        if not _EXPERIENCE_ID.match(experience.id):
            raise ValueError("o id deve ter só letras minúsculas, números, - e _")
        if any(other.id == experience.id for _, other in others):
            raise ValueError(f"já existe uma experiência com o id '{experience.id}'")
        return await self._blocks.save(self._experience_block(experience, block_id, is_active))

    async def block(self, block_id: int) -> ProfileBlock:
        """Lança `ProfileBlockNotFoundError` se o bloco não existir."""
        return await self._existing(block_id)

    async def experience(self, block_id: int) -> Experience:
        """Lança `ProfileBlockNotFoundError` se o bloco não for uma experiência existente."""
        return self._experience(await self._existing(block_id, ProfileBlockCategory.EXPERIENCE))

    async def suggest_experience_id(self, company: str) -> str:
        """Id livre derivado da empresa ('Move Tech 40+' -> 'move-tech-40')."""
        taken = {experience.id for _, experience in await self.experiences()}
        base = _slug(company)
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    async def save_block(
        self,
        category: ProfileBlockCategory,
        title: str,
        content: str = "",
        *,
        block_id: int | None = None,
        is_active: bool = True,
    ) -> ProfileBlock:
        """Competências e conquistas (experiências usam `save_experience`)."""
        if category is ProfileBlockCategory.EXPERIENCE:
            raise ValueError("experiências são gravadas por save_experience")
        if block_id is not None:
            await self._existing(block_id, category)
        block = ProfileBlock(
            id=block_id, category=category, title=title.strip(), content=content.strip(), is_active=is_active
        )
        return await self._blocks.save(block)

    async def set_active(self, block_id: int, is_active: bool) -> ProfileBlock:
        block = await self._existing(block_id)
        return await self._blocks.save(replace(block, is_active=is_active))

    async def delete_block(self, block_id: int) -> None:
        await self._blocks.delete(block_id)

    # --- Visões consumidas pelo match e pelo CV Tailor -----------------------------

    async def candidate_profile(self) -> CandidateProfile:
        details = await self._required_details()
        skills = await self._active_titles(ProfileBlockCategory.SKILL)
        if not skills:
            raise ProfileError("Cadastre ao menos uma competência em /settings/profile")
        return CandidateProfile(
            full_name=details.full_name,
            headline=details.headline,
            skills=skills,
            summary=details.summary,
            years_of_experience=details.years_of_experience,
            target_roles=details.target_roles,
            preferred_locations=details.preferred_locations,
            preferred_work_modes=details.preferred_work_modes,
            languages=details.languages,
            experiences=tuple(
                f"{e.title} — {e.company} ({_period(e)})" for e in await self._active_experiences()
            ),
            achievements=await self._achievements(),
        )

    async def career_history(self) -> CareerHistory:
        details = await self._required_details()
        experiences = await self._active_experiences()
        if not experiences:
            raise ProfileError("Cadastre ao menos uma experiência em /settings/profile")
        return CareerHistory(
            full_name=details.full_name,
            headline=details.headline,
            contact=details.contact,
            summary=details.summary,
            skills=await self._active_titles(ProfileBlockCategory.SKILL),
            experiences=experiences,
            education=details.education,
            certifications=details.certifications,
            languages=details.languages,
            language=details.language,
            achievements=await self._achievements(),
        )

    # --- Migração dos arquivos JSON -------------------------------------------------

    async def import_legacy(
        self, profiles: IProfileRepository, histories: ICareerHistoryRepository
    ) -> bool:
        """Copia profile.json e profile_base.json para o banco, se ele ainda não tiver perfil.

        Nunca sobrescreve: depois da primeira importação, o banco é a fonte.
        """
        if await self.details() is not None or await self._blocks.list_all():
            return False
        profile = await _load_or_none(profiles.get)
        history = await _load_or_none(histories.get)
        if profile is None and history is None:
            return False

        base = history or profile
        assert base is not None
        await self.save_details(
            ProfileDetails(
                full_name=base.full_name,
                headline=base.headline,
                summary=base.summary,
                years_of_experience=profile.years_of_experience if profile else 0.0,
                contact=history.contact if history else ContactInfo(),
                target_roles=profile.target_roles if profile else (),
                preferred_locations=profile.preferred_locations if profile else (),
                preferred_work_modes=profile.preferred_work_modes if profile else (),
                languages=base.languages,
                education=history.education if history else (),
                certifications=history.certifications if history else (),
                language=history.language if history else OutreachLanguage.PT,
            )
        )
        skills: dict[str, str] = {}
        for skill in (*(history.skills if history else ()), *(profile.skills if profile else ())):
            skills.setdefault(normalize_text(skill), skill)
        await self._blocks.add_many(
            [self._experience_block(e, None, True) for e in (history.experiences if history else ())]
            + [
                ProfileBlock(category=ProfileBlockCategory.SKILL, title=skill[:PROFILE_BLOCK_TITLE_MAX])
                for skill in skills.values()
            ]
        )
        return True

    # --- Internos -------------------------------------------------------------------

    async def _required_details(self) -> ProfileDetails:
        details = await self.details()
        if details is None:
            raise ProfileError(_NOT_CONFIGURED)
        return details

    async def _existing(self, block_id: int, category: ProfileBlockCategory | None = None) -> ProfileBlock:
        block = await self._blocks.get(block_id)
        if block is None or (category is not None and block.category is not category):
            raise ProfileBlockNotFoundError(f"bloco {block_id} não encontrado")
        return block

    async def _active_titles(self, category: ProfileBlockCategory) -> tuple[str, ...]:
        return tuple(b.title for b in await self.blocks(category) if b.is_active)

    async def _achievements(self) -> tuple[str, ...]:
        return tuple(
            f"{b.title}: {b.content}" if b.content else b.title
            for b in await self.blocks(ProfileBlockCategory.METRIC)
            if b.is_active
        )

    async def _active_experiences(self) -> tuple[Experience, ...]:
        active = [e for b, e in await self.experiences() if b.is_active]
        # atuais primeiro, depois pela data de término e de início mais recentes
        return tuple(sorted(active, key=lambda e: (e.end or "9999-12", e.start), reverse=True))

    @staticmethod
    def _experience(block: ProfileBlock) -> Experience:
        try:
            return _EXPERIENCE.validate_json(block.content)
        except ValidationError as exc:
            raise ProfileError(f"Experiência '{block.title}' inválida no banco: {exc}") from exc

    @staticmethod
    def _experience_block(experience: Experience, block_id: int | None, is_active: bool) -> ProfileBlock:
        return ProfileBlock(
            id=block_id,
            category=ProfileBlockCategory.EXPERIENCE,
            title=experience.company[:PROFILE_BLOCK_TITLE_MAX],
            content=_EXPERIENCE.dump_json(experience).decode(),
            is_active=is_active,
        )


async def _load_or_none[T](load: Callable[[], Awaitable[T]]) -> T | None:
    try:
        return await load()
    except ProfileError as exc:  # arquivo ausente (instalação nova) ou inválido
        logger.info("Perfil não importado: %s", exc)
        return None


class StoredCandidateProfiles(IProfileRepository):
    """Porta do match sobre o perfil do banco."""

    def __init__(self, service: ProfileService) -> None:
        self._service = service

    async def get(self) -> CandidateProfile:
        return await self._service.candidate_profile()


class StoredCareerHistories(ICareerHistoryRepository):
    """Porta do CV Tailor sobre o histórico do banco."""

    def __init__(self, service: ProfileService) -> None:
        self._service = service

    async def get(self) -> CareerHistory:
        return await self._service.career_history()
