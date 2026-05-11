from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_INTERNAL_API_KEY = "development-enrichment-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cnpj"
    postgres_user: str = "cnpj_user"
    postgres_password: str = "changeme"

    redis_url: str = "redis://localhost:6379/0"

    enrichment_host: str = "0.0.0.0"
    enrichment_port: int = 8010
    enrichment_api_key: str = DEFAULT_INTERNAL_API_KEY

    environment: str = "development"

    domain_first_crawler_enabled: bool = False

    brasilapi_enabled: bool = True
    brasilapi_base_url: str = "https://brasilapi.com.br/api"
    brave_search_api_key: str = ""
    brave_search_base_url: str = "https://api.search.brave.com"
    google_cse_api_key: str = ""
    google_cse_cx: str = ""
    google_cse_base_url: str = "https://www.googleapis.com/customsearch/v1"
    searxng_url: str = ""

    @property
    def google_cse_enabled(self) -> bool:
        return bool(self.google_cse_api_key and self.google_cse_cx)

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def validate_runtime_security(self) -> None:
        if self.is_production and self.enrichment_api_key == DEFAULT_INTERNAL_API_KEY:
            raise RuntimeError("ENRICHMENT_API_KEY must be changed in production")


settings = Settings()

