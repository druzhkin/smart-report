from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Gateway
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Direct APIs
    perplexity_api_key: str = ""
    deepgram_api_key: str = ""
    gamma_api_key: str = ""
    firecrawl_api_key: str = ""

    # Observability
    langsmith_api_key: str = ""
    langchain_tracing_v2: bool = True
    langchain_project: str = "smart-report"

    # RAGFlow
    ragflow_api_key: str = ""
    ragflow_base_url: str = "http://localhost:9380"
    ragflow_reports_dataset_id: str = ""
    ragflow_facts_dataset_id: str = ""
    ragflow_reports_dataset_name: str = "smart-report-reports"
    ragflow_facts_dataset_name: str = "smart-report-facts"

    # Database
    postgres_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/smart_report",
        validation_alias=AliasChoices("POSTGRES_URL", "DATABASE_URL"),
    )
    redis_url: str = "redis://localhost:6379"

    # Storage
    outputs_dir: str = "./outputs"

    # Development mode (cheap models, limited iterations)
    dev_mode: bool = False
    enable_apo_scheduler: bool = True

    # Budget limits (USD)
    budget_light: float = 0.50
    budget_standard: float = 2.00
    budget_deep: float = 5.00
    budget_exhaustive: float = 15.00
    max_budget_usd: float = 5.00

    # Public site pricing (USD)
    public_price_light: float = 0.50
    public_price_standard: float = 2.00
    public_price_deep: float = 5.00
    public_price_exhaustive: float = 15.00

    # Presentation
    presenton_url: str = "http://localhost:5000"

    # Push Notifications
    next_public_vapid_key: str = ""
    vapid_private_key: str = ""


settings = Settings()


def normalize_database_url(
    raw_url: str, *, async_driver: bool | None = True
) -> str:
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    if raw_url.startswith("postgresql://"):
        if async_driver is None:
            return raw_url
        driver = "postgresql+asyncpg://" if async_driver else "postgresql+psycopg://"
        return raw_url.replace("postgresql://", driver, 1)

    if raw_url.startswith("postgresql+asyncpg://") or raw_url.startswith("postgresql+psycopg://"):
        return raw_url

    if raw_url.startswith("sqlite:///") and async_driver:
        return raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    if raw_url.startswith("sqlite+aiosqlite:///") and not async_driver:
        return raw_url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)

    return raw_url
