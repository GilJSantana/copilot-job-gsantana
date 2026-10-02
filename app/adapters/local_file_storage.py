"""Armazenamento de arquivos em um diretório local (porta `IFileStorage`)."""

import asyncio
import re
from pathlib import Path

from app.domain.interfaces import IFileStorage

# nomes simples, sem diretórios: referências vindas do banco nunca escapam da raiz
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class LocalFileStorage(IFileStorage):
    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, name: str, data: bytes) -> str:
        path = self._resolve(name)
        await asyncio.to_thread(self._write, path, data)
        return name

    async def read(self, reference: str) -> bytes:
        return await asyncio.to_thread(self._resolve(reference).read_bytes)

    async def delete(self, reference: str) -> None:
        await asyncio.to_thread(self._resolve(reference).unlink, missing_ok=True)

    async def list_names(self) -> list[str]:
        def _list() -> list[str]:
            if not self._root.is_dir():
                return []
            return sorted(p.name for p in self._root.iterdir() if p.is_file() and _SAFE_NAME.match(p.name))

        return await asyncio.to_thread(_list)

    def _resolve(self, name: str) -> Path:
        if not _SAFE_NAME.match(name) or ".." in name:
            raise ValueError(f"nome de arquivo inválido: {name!r}")
        return self._root / name

    def _write(self, path: Path, data: bytes) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        # cada arquivo pertence a um registro: sobrescrever corromperia outra versão
        if path.exists():
            raise FileExistsError(f"{path.name} já existe")
        # grava em arquivo temporário e renomeia: nunca deixa um PDF pela metade
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
