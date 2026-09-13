from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./signal.db"

    secret_key: str = "change-me-to-a-random-secret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    # Which app.services.rank_providers implementation is active - see that
    # package's __init__.py for the registered options. Switching vendors is
    # just changing this value; no other code needs to change.
    rank_provider: str = "serpapi"
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    serpapi_key: str = ""

    # Which app.services.ai_providers implementation is active - same pattern
    # as rank_provider above.
    ai_provider: str = "openai"
    openai_api_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
