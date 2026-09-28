"""Caso de uso de match com cache: só paga o LLM quando o resultado salvo não vale mais."""

import logging

from app.domain.interfaces import IMatchResultStore
from app.domain.models import CandidateProfile, JobPosting, MatchResult
from app.services.match_engine import MatchEngine

logger = logging.getLogger(__name__)


class MatchService:
    def __init__(self, engine: MatchEngine, store: IMatchResultStore) -> None:
        self._engine = engine
        self._store = store

    async def match(
        self,
        profile: CandidateProfile,
        job: JobPosting,
        *,
        force: bool = False,
    ) -> MatchResult:
        """Devolve o match salvo se ainda for válido; senão recalcula e salva.

        Um match salvo é reaproveitado apenas se foi feito para o perfil atual
        (mesmo fingerprint) e com a avaliação do LLM. Matches de fallback (LLM
        indisponível na hora) são recalculados na próxima chance.

        Lança `JobNotFoundError` se a vaga não estiver armazenada.
        """
        if not force:
            cached = await self._store.get(job.dedup_key)
            if cached is not None and cached.is_current_for(profile) and cached.used_llm:
                return cached
            if cached is not None:
                logger.info("Match de %s desatualizado; recalculando", job.dedup_key)

        result = await self._engine.evaluate(profile, job)
        await self._store.save(result)
        return result
