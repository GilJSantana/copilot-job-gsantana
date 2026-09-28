"""Fábrica da aplicação FastAPI."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.web import api, pages
from app.web.container import Overrides, build_container
from app.web.errors import register_error_handlers
from app.web.templating import create_templates


def create_app(settings: Settings | None = None, overrides: Overrides | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # migrações, conexões e adapters são criados na subida e liberados na descida
        async with build_container(settings, overrides) as container:
            app.state.container = container
            yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    templates = create_templates()
    app.include_router(api.router)
    app.include_router(pages.build_router(templates))
    register_error_handlers(app, templates)
    return app
