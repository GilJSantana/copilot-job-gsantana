"""Manutenção dos PDFs de CV: encontra e remove arquivos sem versão registrada."""

import logging
import re
from dataclasses import dataclass

from app.domain.interfaces import ICVVersionStore, IFileStorage

logger = logging.getLogger(__name__)

# só arquivos gerados pelo CV Tailor ('<nome>_CV_<empresa>_<id de 32 hex>.pdf'):
# qualquer outro arquivo na pasta é do usuário e nunca é tocado
CV_FILE_PATTERN = re.compile(r"^.+_CV_.+_[0-9a-f]{32}\.pdf$")


@dataclass(frozen=True, slots=True)
class OrphanReport:
    orphans: tuple[str, ...]
    deleted: tuple[str, ...]
    # True quando o banco não tem nenhuma versão: provável banco errado (DATABASE_URL)
    suspicious: bool


class CVFileJanitor:
    """Órfãos surgem quando o registro some e o arquivo fica (ex.: vaga apagada
    do banco, que remove as versões em cascata). A limpeza é explícita e
    conservadora: apagar PDFs por engano é pior do que deixá-los no disco."""

    def __init__(self, storage: IFileStorage, store: ICVVersionStore) -> None:
        self._storage = storage
        self._store = store

    async def prune(self, *, apply: bool = False, force: bool = False) -> OrphanReport:
        """Lista os órfãos; com `apply=True`, remove-os.

        Se o banco não tiver nenhuma versão registrada e houver PDFs na pasta,
        provavelmente o banco é outro (novo, vazio ou apontado por engano): nesse
        caso só remove com `force=True`.
        """
        referenced = await self._store.referenced_files()
        candidates = [name for name in await self._storage.list_names() if CV_FILE_PATTERN.match(name)]
        orphans = tuple(name for name in candidates if name not in referenced)
        suspicious = not referenced and bool(orphans)

        if not apply or (suspicious and not force):
            return OrphanReport(orphans=orphans, deleted=(), suspicious=suspicious)

        for name in orphans:
            await self._storage.delete(name)
            logger.info("PDF órfão removido: %s", name)
        return OrphanReport(orphans=orphans, deleted=orphans, suspicious=suspicious)
