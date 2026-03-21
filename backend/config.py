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

    # Database
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/smart_report"
    redis_url: str = "redis://localhost:6379"

    # Storage
    outputs_dir: str = "./outputs"

    # Development mode (cheap models, limited iterations)
    dev_mode: bool = False

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
