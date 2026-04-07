from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.api.routes import health, library, reports, settings as settings_routes
from backend.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    for path in settings.runtime_dirs:
        Path(path).mkdir(parents=True, exist_ok=True)
    logger.info("Smart Report API started (v2 runtime enabled)")
    yield
    logger.info("Smart Report API shutting down")


app = FastAPI(
    title="Smart Report API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
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
