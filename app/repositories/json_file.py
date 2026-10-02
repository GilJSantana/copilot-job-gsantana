"""Leitura de arquivos JSON de configuração do usuário, validados e recarregados ao mudar."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.domain.exceptions import ProfileError


class CachedJsonFile[Schema: BaseModel, Entity]:
    """Valida o arquivo com `schema`, converte com `convert` e relê só quando o
    arquivo muda (mtime): editar o arquivo tem efeito sem reiniciar a aplicação."""

    def __init__(
        self,
        path: Path,
        schema: type[Schema],
        convert: Callable[[Schema], Entity],
        *,
        label: str,
        example_hint: str,
    ) -> None:
        self._label = label
        self._path = path
        self._schema = schema
        self._convert = convert
        self._example_hint = example_hint
        self._cached: tuple[int, Entity] | None = None

    async def load(self) -> Entity:
        return await asyncio.to_thread(self._load)

    def _load(self) -> Entity:
        try:
            mtime = self._path.stat().st_mtime_ns
        except FileNotFoundError:
            raise ProfileError(
                f"{self._label} não encontrado em {self._path}. "
                f"Copie {self._example_hint} para esse caminho e preencha."
            ) from None

        if self._cached and self._cached[0] == mtime:
            return self._cached[1]

        try:
            data = self._schema.model_validate_json(self._path.read_bytes())
            entity = self._convert(data)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, error['loc'])) or 'arquivo'}: {error['msg']}"
                for error in exc.errors()
            )
            raise ProfileError(f"{self._label} inválido em {self._path} — {problems}") from exc
        except ValueError as exc:  # regras do domínio (datas, ids repetidos...)
            raise ProfileError(f"{self._label} inválido em {self._path} — {exc}") from exc

        self._cached = (mtime, entity)
        return entity
