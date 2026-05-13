from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "cnpj"
    postgres_user: str = "cnpj_user"
    postgres_password: str = "changeme"

    redis_url: str = "redis://localhost:6379/0"

    etl_data_dir: str = "/tmp/cnpj_data"
    etl_batch_size: int = 500_000
    etl_workers: int = 4          # mantido para compatibilidade
    etl_download_workers: int = 2
    etl_process_workers: int = 6
    etl_index_workers: int = 4    # índices criados em paralelo
    etl_active_only: bool = True
    etl_auto_load_public_data: bool = False
    etl_min_free_gb: int = 70
    etl_keep_zips_after_load: bool = False

    discord_webhook_url: str = ""
    slack_webhook_url: str = ""

    rf_share_token: str = "gn672Ad4CF8N6TK"
    rf_webdav_base: str = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
    rf_http_index_url: str = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
    dados_gov_cnpj_url: str = "https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj"

    environment: str = "development"

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @field_validator("etl_batch_size")
    @classmethod
    def batch_size_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("etl_batch_size must be positive")
        return v

    @field_validator("etl_workers")
    @classmethod
    def workers_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("etl_workers must be positive")
        return v

    @field_validator("etl_min_free_gb")
    @classmethod
    def min_free_gb_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("etl_min_free_gb must be non-negative")
        return v


settings = Settings()
