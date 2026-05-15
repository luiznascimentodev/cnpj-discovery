from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cnpj"
    postgres_user: str = "cnpj_user"
    postgres_password: str = "changeme"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # CORS origins aceitos — separados por vírgula no env
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    redis_url: str = "redis://localhost:6379/0"

    enrichment_service_url: str = "http://localhost:8010"
    enrichment_api_key: str = "development-enrichment-key"
    paid_contact_feature_key: str = "crawler_contacts"

    stripe_webhook_secret: str = ""
    stripe_signature_tolerance_seconds: int = 300

    app_base_url: str = "http://localhost:5173"
    email_from: str = "CNPJ Discovery <noreply@localhost>"
    resend_api_key: str = ""
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""

    environment: str = "development"

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
