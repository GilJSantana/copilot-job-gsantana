"""Caso de uso do CV Tailor: CV otimizado para a vaga, em PDF, com histórico de versões."""

import logging
import re
import uuid
from collections.abc import Callable

from app.domain.exceptions import CVVersionNotFoundError
from app.domain.interfaces import (
    ICareerHistoryRepository,
    ICVGenerator,
    ICVOptimizer,
    ICVVersionStore,
    IFileStorage,
)
from app.domain.models import CVVersion, JobPosting, OutreachLanguage, normalize_text

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex


class CVTailorService:
    def __init__(
        self,
        histories: ICareerHistoryRepository,
        optimizer: ICVOptimizer,
        generator: ICVGenerator,
        storage: IFileStorage,
        store: ICVVersionStore,
        *,
        id_factory: Callable[[], str] = _new_id,
    ) -> None:
        self._histories = histories
        self._optimizer = optimizer
        self._generator = generator
        self._storage = storage
        self._store = store
        self._new_id = id_factory

    async def tailor(
        self, job: JobPosting, *, language: OutreachLanguage = OutreachLanguage.PT
    ) -> CVVersion:
        """Otimiza o histórico para a vaga, gera o PDF e registra a nova versão.

        Cada chamada cria uma versão; as anteriores continuam disponíveis.
        Lança `ProfileError` (histórico ausente/inválido), `LLMProviderError`,
        `CVIntegrityError`, `CVRenderError` e `JobNotFoundError`.
        """
        history = await self._histories.get()
        cv = await self._optimizer.optimize_cv(job, history, language=language)
        pdf = await self._generator.generate_pdf(history, cv)

        version_id = self._new_id()
        reference = await self._storage.save(file_name(history.full_name, job, version_id), pdf)
        version = CVVersion(
            id=version_id,
            job_key=job.dedup_key,
            content=cv,
            history_fingerprint=history.fingerprint,
            template=self._generator.template,
            pdf_path=reference,
            provider=self._optimizer.name,
        )
        try:
            saved = await self._store.save(version)
        except BaseException:
            # sem o registro, o PDF ficaria órfão no disco
            await self._storage.delete(reference)
            raise
        logger.info("CV %s gerado para %s (%s)", saved.id, job.dedup_key, reference)
        return saved

    async def versions(self, job: JobPosting) -> list[CVVersion]:
        return await self._store.list_for_job(job.dedup_key)

    async def get(self, version_id: str) -> CVVersion:
        version = await self._store.get(version_id)
        if version is None:
            raise CVVersionNotFoundError(f"versão de CV {version_id} não encontrada")
        return version

    async def read_pdf(self, version_id: str) -> tuple[CVVersion, bytes]:
        version = await self.get(version_id)
        try:
            return version, await self._storage.read(version.pdf_path)
        except FileNotFoundError:
            raise CVVersionNotFoundError(
                f"O PDF da versão {version_id} não está mais em disco ({version.pdf_path})"
            ) from None


def file_name(full_name: str, job: JobPosting, version_id: str) -> str:
    """Nome do arquivo em disco: 'Ana-Souza_CV_Acme_<id da versão>.pdf'.

    O id completo garante que uma versão nunca sobrescreva o PDF de outra
    (um prefixo do id só tornaria a colisão improvável, não impossível).
    Só ASCII, sem espaços nem barras: seguro em qualquer sistema.
    """
    return f"{_slug(full_name, 40)}_CV_{_slug(job.company, 30)}_{version_id}.pdf"


def _slug(text: str, limit: int) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", normalize_text(text)).split()
    slug = "-".join(word.capitalize() for word in words)[:limit].strip("-")
    return slug or "sem-nome"
