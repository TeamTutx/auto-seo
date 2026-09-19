from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./signal.db"

    secret_key: str = "change-me-to-a-random-secret"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Where the frontend runs - used to build the redirect after the Google
    # OAuth callback (app/routers/google_integration.py).
    frontend_url: str = "http://localhost:3000"

    # Comma-separated list of origins allowed to call this API (CORS) - see
    # app/main.py. Must include the real frontend origin(s) in production;
    # the default only covers local dev.
    cors_origins: str = "http://localhost:3000"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Comma-separated emails allowed into /admin/* (app/deps.py require_admin).
    # Checked on every request, so revoking access = editing this value.
    admin_emails: str = ""

    # Dodo Payments (Merchant of Record) - see app/services/dodo.py. Billing is
    # "enabled" only once both keys are set; until then checkout endpoints
    # answer 503 and the pricing page shows plans without a buy button.
    dodo_api_key: str = ""
    dodo_webhook_key: str = ""
    dodo_environment: str = "test_mode"  # "test_mode" | "live_mode"
    # Override the API host (a staging proxy, or a local mock in tests). Empty =
    # Dodo's own host for dodo_environment.
    dodo_base_url: str = ""

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

    # Google Search Console + Analytics (Signal roadmap "GSC/GA integration",
    # see plan.md). Unlike the vendor keys above, this is an OAuth client, not
    # a static key - see backend/README.md for how to create one. Empty by
    # default: the connect flow returns a clean error instead of crashing.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/integrations/google/callback"

    @property
    def admin_email_set(self) -> set:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def billing_enabled(self) -> bool:
        return bool(self.dodo_api_key and self.dodo_webhook_key)


settings = Settings()
