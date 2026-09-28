"""Configuração de logs da aplicação."""

import logging

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format=_FORMAT)
