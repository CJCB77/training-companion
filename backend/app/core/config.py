from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Training Companion API"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = ""

    supabase_url: str = ""

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url}/auth/v1"

    sentry_dsn: str = ""

    # Allowed CORS origins for the Expo frontend. Accepts a comma-separated
    # string in the env file (e.g. "http://localhost:8081,https://app.example.com").
    cors_origins: list[str] = ["*"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


settings = Settings()
