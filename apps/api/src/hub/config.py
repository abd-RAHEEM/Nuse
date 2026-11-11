from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str | None = None
    session_secret: str | None = None
    pin_pepper: str | None = None
    allow_signup: bool = False
    integration_encryption_key: str | None = None
    notion_token: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    google_gmail_redirect_uri: str | None = None
    web_origin: str = "http://127.0.0.1:3000"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value.removeprefix("postgresql://")
        if value.startswith("postgresql+asyncpg://"):
            parsed = urlsplit(value)
            query = [
                ("ssl" if key == "sslmode" else key, item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                if key != "channel_binding"
            ]
            return urlunsplit(parsed._replace(query=urlencode(query)))
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
