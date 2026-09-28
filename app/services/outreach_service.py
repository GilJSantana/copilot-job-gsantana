"""Rascunhos de mensagens para recrutadores e gestores, gerados pelo LLM."""

import logging
from typing import Any

from app.domain.exceptions import LLMResponseFormatError, OutreachGenerationError
from app.domain.interfaces import ILLMProvider, IOutreachStore
from app.domain.models import (
    CandidateProfile,
    JobPosting,
    MatchResult,
    OutreachChannel,
    OutreachLanguage,
    OutreachMessage,
)

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_CHARS = 4000

_CHANNEL_GUIDE = {
    OutreachChannel.LINKEDIN_CONNECTION: (
        "nota de convite de conexão do LinkedIn: 2 a 3 frases, direto ao ponto, "
        "sem assunto"
    ),
    OutreachChannel.LINKEDIN_MESSAGE: (
        "mensagem direta no LinkedIn: saudação, 1 parágrafo conectando o perfil à vaga, "
        "chamada para conversa; sem assunto"
    ),
    OutreachChannel.EMAIL: (
        "e-mail curto: assunto específico (cargo + diferencial), saudação, "
        "2 parágrafos curtos, chamada para conversa, assinatura com o nome"
    ),
}

_LANGUAGE_NAMES = {OutreachLanguage.PT: "português do Brasil", OutreachLanguage.EN: "inglês"}

SYSTEM_PROMPT = (
    "Você escreve mensagens de candidatos para recrutadores. Regras invioláveis:\n"
    "1. Use SOMENTE fatos do perfil fornecido. Nunca invente experiências, empresas, "
    "números, certificações ou skills.\n"
    "2. Não mencione lacunas nem pontos fracos do candidato.\n"
    "3. Sem placeholders como [Nome] ou [Empresa]: se o nome do destinatário não for "
    "informado, use uma saudação neutra.\n"
    "4. Tom profissional e natural, sem bajulação nem clichês.\n"
    'Responda APENAS com JSON: {"subject": <string ou null>, "body": "<mensagem>"}'
)


class OutreachService:
    def __init__(self, llm: ILLMProvider, store: IOutreachStore) -> None:
        self._llm = llm
        self._store = store

    async def draft(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        *,
        channel: OutreachChannel,
        language: OutreachLanguage = OutreachLanguage.PT,
        match: MatchResult | None = None,
        recipient_name: str | None = None,
    ) -> OutreachMessage:
        """Gera e grava um rascunho para a vaga.

        O match só é usado se foi feito para o perfil atual: pontos fortes de
        um perfil antigo poderiam citar algo que o candidato já removeu.

        Lança `LLMProviderError` se o LLM estiver indisponível,
        `OutreachGenerationError` se ele não respeitar as regras do canal e
        `JobNotFoundError` se a vaga não estiver armazenada.
        """
        if match is not None and not match.is_current_for(profile):
            match = None
        prompt = self._build_prompt(profile, job, channel, language, match, recipient_name)

        payload = await self._llm.generate_json(prompt, system_prompt=SYSTEM_PROMPT, temperature=0.5)
        subject, body = self._parse(payload, channel)
        if len(body) > channel.max_length:
            # uma única chance de corrigir: cortar a mensagem a deixaria sem sentido
            logger.info("Rascunho com %d caracteres (limite %d); pedindo reescrita", len(body), channel.max_length)
            retry = (
                f"{prompt}\n\nSua resposta anterior tinha {len(body)} caracteres no corpo. "
                f"Reescreva com NO MÁXIMO {channel.max_length} caracteres, mantendo o essencial."
            )
            payload = await self._llm.generate_json(retry, system_prompt=SYSTEM_PROMPT, temperature=0.3)
            subject, body = self._parse(payload, channel)
            if len(body) > channel.max_length:
                raise OutreachGenerationError(
                    f"O LLM gerou {len(body)} caracteres mesmo após pedido de reescrita "
                    f"(limite de {channel.max_length}). Tente novamente."
                )

        message = OutreachMessage(
            job_key=job.dedup_key,
            channel=channel,
            language=language,
            subject=subject,
            body=body,
            provider=self._llm.name,
            profile_fingerprint=profile.fingerprint,
        )
        return await self._store.save(message)

    async def history(self, job: JobPosting) -> list[OutreachMessage]:
        return await self._store.list_for_job(job.dedup_key)

    @staticmethod
    def _parse(payload: dict[str, Any], channel: OutreachChannel) -> tuple[str | None, str]:
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip():
            raise LLMResponseFormatError("rascunho sem 'body'")
        subject = payload.get("subject")
        if channel.requires_subject:
            if not isinstance(subject, str) or not subject.strip():
                raise LLMResponseFormatError("e-mail sem 'subject'")
            return subject.strip(), body.strip()
        # canais sem assunto: ignora um assunto que o LLM tenha mandado por engano
        return None, body.strip()

    @staticmethod
    def _build_prompt(
        profile: CandidateProfile,
        job: JobPosting,
        channel: OutreachChannel,
        language: OutreachLanguage,
        match: MatchResult | None,
        recipient_name: str | None,
    ) -> str:
        lines = [
            f"Canal: {_CHANNEL_GUIDE[channel]}.",
            f"Idioma: {_LANGUAGE_NAMES[language]}.",
            f"Limite: no máximo {channel.max_length} caracteres no corpo.",
            f"Destinatário: {recipient_name.strip() if recipient_name and recipient_name.strip() else 'nome desconhecido'}.",
            "",
            "## Candidato (única fonte de fatos)",
            f"Nome: {profile.full_name}",
            f"Headline: {profile.headline}",
            f"Experiência: {profile.years_of_experience:g} anos",
            f"Skills: {', '.join(profile.skills)}",
            f"Resumo: {profile.summary}",
        ]
        if match is not None and (match.strengths or match.matched_skills):
            lines += [
                "",
                "## Pontos de conexão com a vaga (já validados)",
                f"Skills em comum: {', '.join(match.matched_skills) or '—'}",
                f"Pontos fortes: {'; '.join(match.strengths) or '—'}",
            ]
        lines += [
            "",
            "## Vaga",
            f"Cargo: {job.title}",
            f"Empresa: {job.company}",
            f"Descrição:\n{job.description[:MAX_DESCRIPTION_CHARS]}",
        ]
        return "\n".join(lines)
