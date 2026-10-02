"""Otimização do conteúdo do CV para uma vaga, com o LLM e verificação de integridade."""

import logging
import re
from typing import Any

from app.domain.exceptions import CVIntegrityError, LLMResponseFormatError, ProfileError
from app.domain.interfaces import ICVOptimizer, ILLMProvider, IPromptTemplateStore
from app.domain.models import (
    CareerHistory,
    Experience,
    JobPosting,
    OutreachLanguage,
    PromptName,
    TailoredCV,
    TailoredExperience,
    normalize_text,
)
from app.services.prompts import resolve_prompt

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_CHARS = 6000
MAX_HIGHLIGHTS = 5
MAX_SKILLS = 20
# highlights usados quando uma experiência precisa voltar ao texto original
FALLBACK_HIGHLIGHTS = 3

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_LANGUAGE_NAMES = {OutreachLanguage.PT: "português do Brasil", OutreachLanguage.EN: "inglês"}

SYSTEM_PROMPT = (
    "Você é especialista em currículos aprovados por ATS (Applicant Tracking Systems).\n"
    "Regras invioláveis:\n"
    "1. Use SOMENTE fatos do histórico fornecido. Nunca invente experiências, cargos, "
    "empresas, certificações, skills ou resultados.\n"
    "2. Todo número (anos, %, valores, prazos, tamanhos de equipe) deve ser copiado "
    "exatamente como aparece no histórico daquela experiência.\n"
    "3. Cada highlight é uma reescrita de um highlight do histórico da MESMA experiência: "
    "evidencie o que se relaciona com a vaga e use os termos dela SOMENTE quando forem "
    "verdadeiros. Nunca transforme responsabilidades da vaga em experiência do candidato.\n"
    "4. Skills: apenas da lista permitida, da mais para a menos relevante para a vaga.\n"
    "5. Frases objetivas começando por verbo de ação; sem clichês nem adjetivos vazios.\n"
    "Responda APENAS com JSON no formato:\n"
    '{"headline": "...", "summary": "...", "skills": ["..."], '
    '"experiences": [{"id": "<id do histórico>", "highlights": ["..."]}], '
    '"matched_keywords": ["termos da vaga cobertos pelo CV"]}'
)


class LLMCVOptimizer(ICVOptimizer):
    def __init__(self, llm: ILLMProvider, *, prompts: IPromptTemplateStore | None = None) -> None:
        self._llm = llm
        # SYSTEM_PROMPT é o padrão; o painel pode substituí-lo (CV_TAILOR_PROMPT)
        self._prompts = prompts

    @property
    def name(self) -> str:
        return self._llm.name

    async def optimize_cv(
        self,
        job: JobPosting,
        history: CareerHistory,
        *,
        language: OutreachLanguage,
    ) -> TailoredCV:
        if not history.experiences:
            raise ProfileError("O histórico profissional não tem experiências para montar o CV.")

        prompt = self._build_prompt(job, history, language)
        try:
            cv = await self._ask(prompt, history, language)
        except LLMResponseFormatError as exc:
            # modelos pequenos às vezes quebram o formato; uma nova chance, com o motivo
            logger.info("Resposta fora do formato (%s); pedindo de novo", exc)
            cv = await self._ask(
                f"{prompt}\n\nSua resposta anterior foi recusada: {exc}. "
                "Siga exatamente o formato JSON pedido.",
                history,
                language,
            )
        violations = cv.violations_against(history)
        if not violations:
            return cv

        logger.info("CV com %d divergências do histórico; pedindo correção", len(violations))
        retry = (
            f"{prompt}\n\n## Correções obrigatórias\nSua resposta anterior violou as regras:\n"
            + "\n".join(f"- {violation}" for violation in violations)
            + "\nReescreva corrigindo TODOS os itens, sem acrescentar nada fora do histórico."
        )
        cv = await self._ask(retry, history, language)
        violations = cv.violations_against(history)
        if not violations:
            return cv

        # Última linha de defesa: remove o que não tem lastro. Só retira conteúdo,
        # nunca acrescenta, então o resultado é sempre fiel ao histórico.
        logger.warning("CV ainda divergente após correção; removendo: %s", "; ".join(violations))
        cv = self._repair(cv, history)
        remaining = cv.violations_against(history)
        if remaining:
            raise CVIntegrityError(remaining)
        return cv

    async def _ask(self, prompt: str, history: CareerHistory, language: OutreachLanguage) -> TailoredCV:
        system_prompt = await resolve_prompt(self._prompts, PromptName.CV_TAILOR, SYSTEM_PROMPT)
        payload = await self._llm.generate_json(prompt, system_prompt=system_prompt, temperature=0.3)
        return self._normalize(self._parse(payload, language), history)

    # --- Interpretação da resposta ---------------------------------------------------

    @staticmethod
    def _parse(payload: dict[str, Any], language: OutreachLanguage) -> TailoredCV:
        def text(key: str) -> str:
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                raise LLMResponseFormatError(f"CV sem '{key}'")
            return value.strip()

        def strings(value: Any, what: str) -> tuple[str, ...]:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise LLMResponseFormatError(f"'{what}' deve ser lista de strings")
            return tuple(item.strip() for item in value if item.strip())

        raw_experiences = payload.get("experiences")
        if not isinstance(raw_experiences, list):
            raise LLMResponseFormatError("'experiences' deve ser uma lista")
        experiences = []
        for item in raw_experiences:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise LLMResponseFormatError("experiência sem 'id'")
            experiences.append(
                TailoredExperience(
                    experience_id=item["id"],
                    highlights=strings(item.get("highlights", []), "highlights"),
                )
            )
        if not experiences:
            raise LLMResponseFormatError("CV sem experiências")

        return TailoredCV(
            language=language,
            headline=text("headline"),
            summary=text("summary"),
            skills=strings(payload.get("skills", []), "skills"),
            experiences=tuple(experiences),
            matched_keywords=strings(payload.get("matched_keywords", []), "matched_keywords"),
        )

    @classmethod
    def _normalize(cls, cv: TailoredCV, history: CareerHistory) -> TailoredCV:
        """Regras determinísticas, aplicadas no código e não confiadas ao LLM."""
        given = {tailored.experience_id: tailored for tailored in cv.experiences}
        # todas as experiências entram (lacunas na trajetória prejudicam a candidatura);
        # as omitidas pelo LLM voltam com os highlights originais
        completed = [
            given.get(experience.id) or _original(experience) for experience in history.experiences
        ]
        # ids desconhecidos seguem adiante para a verificação de integridade apontá-los
        unknown = [t for t in cv.experiences if history.experience(t.experience_id) is None]
        ordered = sorted(completed, key=lambda t: history.experience(t.experience_id).start, reverse=True)
        experiences = tuple(
            TailoredExperience(experience_id=t.experience_id, highlights=t.highlights[:MAX_HIGHLIGHTS])
            for t in (*ordered, *unknown)
        )
        return TailoredCV(
            language=cv.language,
            headline=cv.headline,
            summary=cv.summary,
            skills=tuple(dict.fromkeys(cv.skills))[:MAX_SKILLS],
            experiences=experiences,
            matched_keywords=cls._present_keywords(cv, experiences),
        )

    @staticmethod
    def _present_keywords(cv: TailoredCV, experiences: tuple[TailoredExperience, ...]) -> tuple[str, ...]:
        """Só mantém as palavras-chave que o CV de fato contém."""
        body = normalize_text(
            " ".join((cv.headline, cv.summary, *cv.skills, *(h for t in experiences for h in t.highlights)))
        )
        return tuple(
            keyword
            for keyword in dict.fromkeys(cv.matched_keywords)
            if re.search(rf"(?<!\w){re.escape(normalize_text(keyword))}(?!\w)", body)
        )

    # --- Correção por remoção ---------------------------------------------------------------

    @classmethod
    def _repair(cls, cv: TailoredCV, history: CareerHistory) -> TailoredCV:
        experiences = []
        seen: set[str] = set()
        for tailored in cv.experiences:
            original = history.experience(tailored.experience_id)
            if original is None or tailored.experience_id in seen:
                continue
            seen.add(tailored.experience_id)
            kept = tuple(
                h for h in tailored.highlights if cv.highlight_problem(h, original, history) is None
            )
            experiences.append(
                TailoredExperience(experience_id=original.id, highlights=kept)
                if kept
                else _original(original)
            )

        known = history.known_skills
        history_numbers = set(_NUMBER.findall(history.full_text))

        def faithful(text: str) -> bool:
            return set(_NUMBER.findall(text)) <= history_numbers

        summary = cv.summary if faithful(cv.summary) else history.summary
        if not summary.strip():
            raise CVIntegrityError(["resumo com números inventados e histórico sem resumo base"])
        return TailoredCV(
            language=cv.language,
            headline=cv.headline if faithful(cv.headline) else history.headline,
            summary=summary,
            skills=tuple(s for s in cv.skills if normalize_text(s) in known),
            experiences=tuple(experiences),
            matched_keywords=cv.matched_keywords,
        )

    # --- Prompt ---------------------------------------------------------------------------

    @staticmethod
    def _build_prompt(job: JobPosting, history: CareerHistory, language: OutreachLanguage) -> str:
        allowed_skills = dict.fromkeys(
            (*history.skills, *(t for e in history.experiences for t in e.technologies))
        )
        lines = [
            f"Idioma do CV: {_LANGUAGE_NAMES[language]}.",
            f"Até {MAX_HIGHLIGHTS} highlights por experiência e {MAX_SKILLS} skills.",
            "",
            "## Vaga",
            f"Cargo: {job.title}",
            f"Empresa: {job.company}",
            f"Descrição:\n{job.description[:MAX_DESCRIPTION_CHARS]}",
            "",
            "## Histórico do candidato (única fonte de fatos)",
            f"Headline atual: {history.headline}",
            f"Resumo base: {history.summary}",
            f"Skills permitidas: {', '.join(allowed_skills)}",
        ]
        if history.achievements:
            lines += ["Conquistas (podem ser citadas no resumo):"]
            lines += [f"- {achievement}" for achievement in history.achievements]
        for experience in history.experiences:
            period = f"{experience.start} a {experience.end or 'atual'}"
            lines += [
                "",
                f"### id: {experience.id}",
                f"{experience.title} — {experience.company} ({period})",
                f"Tecnologias: {', '.join(experience.technologies) or '—'}",
                *(f"- {highlight}" for highlight in experience.highlights),
            ]
        return "\n".join(lines)


def _original(experience: Experience) -> TailoredExperience:
    return TailoredExperience(
        experience_id=experience.id, highlights=experience.highlights[:FALLBACK_HIGHLIGHTS]
    )
