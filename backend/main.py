import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.api.routes import health, library, reports, settings as settings_routes
from backend.config import settings
from backend.prompt_library.optimizer import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.outputs_dir, exist_ok=True)
    if settings.enable_apo_scheduler:
        start_scheduler()
    logger.info("Smart Report API started")
    yield
    if settings.enable_apo_scheduler:
        stop_scheduler()
    logger.info("Smart Report API shutting down")


app = FastAPI(
    title="Smart Report API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(library.router, prefix="/api", tags=["library"])
app.include_router(settings_routes.router, prefix="/api", tags=["settings"])


@app.get("/config/budget")
async def budget_info() -> dict:
    return {
        "light": settings.budget_light,
        "standard": settings.budget_standard,
        "deep": settings.budget_deep,
        "exhaustive": settings.budget_exhaustive,
    }
