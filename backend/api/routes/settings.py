from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from backend.config import settings

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".env"

KEY_FIELDS = {
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "PERPLEXITY_API_KEY": "perplexity_api_key",
    "DEEPGRAM_API_KEY": "deepgram_api_key",
    "RAGFLOW_API_KEY": "ragflow_api_key",
}

BUDGET_FIELDS = {
    "light": "budget_light",
    "standard": "budget_standard",
    "deep": "budget_deep",
    "exhaustive": "budget_exhaustive",
}


class SaveKeyRequest(BaseModel):
    key_name: str
    value: str


class SaveBudgetRequest(BaseModel):
    light: float
    standard: float
    deep: float
    exhaustive: float


def _read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _write_env_var(name: str, value: str) -> None:
    lines = _read_env_lines()
    updated = False
    new_line = f"{name}={value}"

    for index, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[index] = new_line
            updated = True
            break

    if not updated:
        lines.append(new_line)

    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


@router.get("/settings/keys")
async def get_key_statuses() -> dict[str, str]:
    return {
        key_name: "set" if getattr(settings, field_name, "") else "not_set"
        for key_name, field_name in KEY_FIELDS.items()
    }


@router.post("/settings/keys")
async def save_key(request: SaveKeyRequest) -> dict:
    field_name = KEY_FIELDS.get(request.key_name)
    if not field_name:
        return {"status": "error", "message": "Unsupported key_name"}

    _write_env_var(request.key_name, request.value)
    setattr(settings, field_name, request.value)
    return {"status": "ok", "key_name": request.key_name}


@router.get("/settings/budget")
async def get_budget_settings() -> dict[str, float]:
    return {
        "light": settings.budget_light,
        "standard": settings.budget_standard,
        "deep": settings.budget_deep,
        "exhaustive": settings.budget_exhaustive,
    }


@router.post("/settings/budget")
async def save_budget(request: SaveBudgetRequest) -> dict:
    payload = request.model_dump()

    for name, value in payload.items():
        env_name = f"BUDGET_{name.upper()}"
        field_name = BUDGET_FIELDS[name]
        _write_env_var(env_name, str(value))
        setattr(settings, field_name, float(value))

    return {"status": "ok", **payload}
