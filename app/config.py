from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgrespassword@localhost/ai_platform"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/1"

    admin_bootstrap_key: str = "change-me-admin-key"

    # tier -> (bucket_capacity, refill_tokens_per_window, window_seconds)
    rate_limit_tiers: dict = {
        "free": {"capacity": 10, "refill": 10, "window_seconds": 60},
        "pro": {"capacity": 100, "refill": 100, "window_seconds": 60},
    }

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
