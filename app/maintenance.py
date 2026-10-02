"""Tarefas de manutenção pela linha de comando.

    uv run python -m app.maintenance prune-cvs            # lista PDFs órfãos
    uv run python -m app.maintenance prune-cvs --apply    # remove-os
"""

import argparse
import asyncio
import sys

from app.adapters.local_file_storage import LocalFileStorage
from app.core.config import Settings
from app.repositories.cv_version_store import SqlAlchemyCVVersionStore
from app.repositories.database import create_engine, create_session_factory
from app.repositories.migrate import upgrade_to_head
from app.services.cv_file_janitor import CVFileJanitor


async def prune_cvs(settings: Settings, *, apply: bool, force: bool) -> int:
    engine = create_engine(settings.database_url)
    try:
        await upgrade_to_head(engine)
        janitor = CVFileJanitor(
            LocalFileStorage(settings.cv_output_dir),
            SqlAlchemyCVVersionStore(create_session_factory(engine)),
        )
        report = await janitor.prune(apply=apply, force=force)
    finally:
        await engine.dispose()

    if not report.orphans:
        print(f"Nenhum PDF órfão em {settings.cv_output_dir}.")
        return 0
    print(f"{len(report.orphans)} PDF(s) sem versão registrada em {settings.cv_output_dir}:")
    for name in report.orphans:
        print(f"  {name}")
    if report.suspicious and not report.deleted:
        print(
            "\nO banco não tem nenhuma versão de CV registrada. Confira se DATABASE_URL "
            f"({settings.database_url}) é o banco certo. Para remover mesmo assim: --apply --force"
        )
        return 1
    if report.deleted:
        print(f"\n{len(report.deleted)} arquivo(s) removido(s).")
    else:
        print("\nNada foi removido. Para remover: --apply")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.maintenance")
    commands = parser.add_subparsers(dest="command", required=True)
    prune = commands.add_parser("prune-cvs", help="lista (ou remove) PDFs de CV sem versão registrada")
    prune.add_argument("--apply", action="store_true", help="remove os arquivos listados")
    prune.add_argument("--force", action="store_true", help="remove mesmo se o banco não tiver versões")
    args = parser.parse_args(argv)

    if args.command == "prune-cvs":
        return asyncio.run(prune_cvs(Settings(), apply=args.apply, force=args.force))
    return 2


if __name__ == "__main__":
    sys.exit(main())
