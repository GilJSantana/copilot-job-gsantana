"""Cálculo de aderência entre o perfil do candidato e uma vaga.

O score final é híbrido:
  * keyword_score — determinístico: % das skills do perfil citadas na vaga;
  * llm_score     — semântico: nota 0-100 atribuída pelo LLM.

score = weights.keyword * keyword_score + weights.semantic * llm_score

Se o LLM falhar ou responder fora do contrato, o engine degrada para o
keyword_score em vez de interromper a análise.
"""

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

from app.domain.exceptions import LLMProviderError, LLMResponseFormatError
from app.domain.interfaces import ILLMProvider, IPromptTemplateStore
from app.domain.models import (
    CandidateProfile,
    JobPosting,
    LLMAssessment,
    MatchResult,
    PromptName,
    SkillGap,
    normalize_text,
)
from app.services.prompts import resolve_prompt

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_CHARS = 6000

SYSTEM_PROMPT = (
    "Você é um recrutador técnico sênior. Avalie a aderência entre o candidato "
    "e a vaga. Responda APENAS com um objeto JSON no formato: "
    '{"score": <número 0-100>, "rationale": "<texto curto>", '
    '"strengths": ["..."], "gaps": ["..."], "job_skills": ["..."]}. '
    "O campo job_skills é obrigatório: liste as hard skills exigidas na descrição "
    "da vaga, cada uma com seu nome curto e usual, sem repetições "
    '(ex.: ["Python", "SQL", "ETL", "Linux", "POO", "Docker"]).'
)


@dataclass(frozen=True, slots=True)
class MatchWeights:
    keyword: float = 0.4
    semantic: float = 0.6

    def __post_init__(self) -> None:
        if self.keyword < 0 or self.semantic < 0:
            raise ValueError("pesos não podem ser negativos")
        if not math.isclose(self.keyword + self.semantic, 1.0):
            raise ValueError("a soma dos pesos deve ser 1.0")


class MatchEngine:
    def __init__(
        self,
        llm: ILLMProvider,
        weights: MatchWeights | None = None,
        *,
        prompts: IPromptTemplateStore | None = None,
    ) -> None:
        self._llm = llm
        self._weights = weights or MatchWeights()
        # SYSTEM_PROMPT é o padrão; o painel pode substituí-lo (MATCH_ENGINE_PROMPT)
        self._prompts = prompts

    async def evaluate(self, profile: CandidateProfile, job: JobPosting) -> MatchResult:
        matched = self.matched_skills(profile, job)
        keyword_score = 100 * len(matched) / len(profile.skills) if profile.skills else 0.0

        assessment = await self._assess(profile, job)
        if assessment is None:
            score = keyword_score
        else:
            score = (
                self._weights.keyword * keyword_score
                + self._weights.semantic * assessment.score
            )

        return MatchResult(
            job_key=job.dedup_key,
            score=round(score, 1),
            keyword_score=round(keyword_score, 1),
            llm_score=assessment.score if assessment else None,
            matched_skills=matched,
            strengths=assessment.strengths if assessment else (),
            gaps=assessment.gaps if assessment else (),
            rationale=assessment.rationale if assessment else "",
            provider=self._llm.name,
            profile_fingerprint=profile.fingerprint,
            job_skills=assessment.job_skills if assessment else (),
        )

    @staticmethod
    def matched_skills(profile: CandidateProfile, job: JobPosting) -> tuple[str, ...]:
        """Skills do perfil presentes na vaga (case/acento-insensitive, palavra inteira)."""
        text = normalize_text(job.searchable_text)
        return tuple(skill for skill in profile.skills if _mentions(text, skill))

    @classmethod
    def skill_gap(
        cls,
        profile: CandidateProfile,
        job: JobPosting,
        match: MatchResult | None = None,
    ) -> SkillGap:
        """Skills atendidas, faltantes e só do perfil.

        As skills da vaga vêm do LLM (salvas no match); sem elas, das que a
        fonte da vaga estruturou. "Python" no perfil cobre "Python 3" na vaga.
        """
        job_skills = (match.job_skills if match else ()) or job.skills
        matched = cls.matched_skills(profile, job)
        missing = tuple(
            required
            for required in job_skills
            if not any(
                _mentions(normalize_text(required), own)
                or _mentions(normalize_text(own), required)
                for own in profile.skills
            )
        )
        return SkillGap(
            job_skills=job_skills,
            matched_skills=matched,
            missing_skills=missing,
            extra_skills=tuple(s for s in profile.skills if s not in matched),
        )

    async def _assess(self, profile: CandidateProfile, job: JobPosting) -> LLMAssessment | None:
        try:
            system_prompt = await resolve_prompt(self._prompts, PromptName.MATCH_ENGINE, SYSTEM_PROMPT)
            payload = await self._llm.generate_json(
                self._build_prompt(profile, job), system_prompt=system_prompt
            )
            return self._parse_assessment(payload)
        except LLMProviderError as exc:
            logger.warning("LLM '%s' indisponível para %s: %s", self._llm.name, job.dedup_key, exc)
            return None

    @staticmethod
    def _build_prompt(profile: CandidateProfile, job: JobPosting) -> str:
        return (
            "## Candidato\n"
            f"Nome: {profile.full_name}\n"
            f"Headline: {profile.headline}\n"
            f"Experiência: {profile.years_of_experience} anos\n"
            f"Skills: {', '.join(profile.skills)}\n"
            f"Cargos-alvo: {', '.join(profile.target_roles)}\n"
            f"Resumo: {profile.summary}\n"
            + "".join(f"Experiência: {line}\n" for line in profile.experiences)
            + "".join(f"Conquista: {line}\n" for line in profile.achievements)
            + "\n"
            "## Vaga\n"
            f"Título: {job.title}\n"
            f"Empresa: {job.company}\n"
            f"Local: {job.location} ({job.work_mode})\n"
            f"Descrição:\n{job.description[:MAX_DESCRIPTION_CHARS]}\n"
        )

    @staticmethod
    def _parse_assessment(payload: dict[str, Any]) -> LLMAssessment:
        raw_score = payload.get("score")
        # bool é subclasse de int: rejeitar explicitamente
        if isinstance(raw_score, bool) or not isinstance(raw_score, int | float):
            raise LLMResponseFormatError(f"'score' inválido: {raw_score!r}")
        if not math.isfinite(raw_score):
            raise LLMResponseFormatError(f"'score' não finito: {raw_score!r}")

        def str_list(key: str) -> tuple[str, ...]:
            value = payload.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise LLMResponseFormatError(f"'{key}' deve ser lista de strings")
            return tuple(value)

        rationale = payload.get("rationale", "")
        if not isinstance(rationale, str):
            raise LLMResponseFormatError("'rationale' deve ser string")

        # tolerante à ausência: um prompt customizado no painel pode não pedir job_skills
        job_skills = tuple(
            dict.fromkeys(skill.strip() for skill in str_list("job_skills") if skill.strip())
        )
        return LLMAssessment(
            score=min(max(float(raw_score), 0.0), 100.0),
            rationale=rationale,
            strengths=str_list("strengths"),
            gaps=str_list("gaps"),
            job_skills=job_skills,
        )


def _mentions(normalized_text: str, skill: str) -> bool:
    """`skill` aparece como palavra inteira no texto já normalizado."""
    return bool(re.search(rf"(?<!\w){re.escape(normalize_text(skill))}(?!\w)", normalized_text))
