from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "Training Companion API"
    environment: str = "development"
    debug: bool = False

    database_url: str = ""

    supabase_url: str = ""
    supabase_jwt_secret: str = ""

    sentry_dsn: str = ""


settings = Settings()
