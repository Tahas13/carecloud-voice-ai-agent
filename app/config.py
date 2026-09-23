"""Application settings.

Everything secret or environment-specific comes from environment variables
(or a local .env file for development). Nothing is hardcoded in source.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database. SQLite for local dev/tests; PostgreSQL (Railway) in production.
    database_url: str = "sqlite:///./carecloud.db"

    # Vapi voice platform.
    vapi_api_key: str = ""
    vapi_webhook_secret: str = ""

    # Public (browser-safe) key + assistant id: enable the dashboard's
    # in-browser "talk to the agent" call button when both are set.
    vapi_public_key: str = ""
    vapi_assistant_id: str = ""

    # Display-only: the agent's phone number shown on the dashboard.
    agent_phone_number: str = "+1 (708) 523-1081"

    # Optional: attach your own OpenAI key to the Vapi org (setup script only).
    openai_api_key: str = ""

    # Public base URL of this service (used to build the webhook URL for Vapi).
    public_base_url: str = "http://localhost:8000"

    log_level: str = "INFO"

    # Seed demo patients on startup if the table is empty.
    seed_demo_data: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
