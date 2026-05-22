from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import attach_chain
from app.database import dispose_engine
from app.services.notifications import register_default_observers

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    register_default_observers()
    log.info("application_startup", env=settings.ENVIRONMENT)
    yield
    await dispose_engine()
    log.info("application_shutdown")


app = FastAPI(
    title="BitePlate API",
    version="0.1.0",
    description="Smart Restaurant Management System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chain of Responsibility middleware: request-id → timing → logging → rate-limit
# wrapped in an error-translator. See app/core/middleware.py for the pattern.
attach_chain(app)

register_exception_handlers(app)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
