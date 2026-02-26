from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.routes.agents import router as agents_router
from app.api.routes.eval import router as eval_router
from app.api.routes.health import router as health_router
from app.api.routes.incidents import router as incidents_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("cdrmind.startup", model=settings.llm_model)
    yield
    logger.info("cdrmind.shutdown")


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="cdrmind SOC Copilot",
    version="0.1.0",
    description="SOC Copilot — orchestrates RAG, task runner, and policy enforcement",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(health_router)
app.include_router(incidents_router)
app.include_router(agents_router)
app.include_router(eval_router)
