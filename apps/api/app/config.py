"""Application settings, read from environment variables (and `.env` in local development)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "myTrakIn"
    environment: Literal["development", "test", "staging", "production"] = "development"

    # Database. Use Supabase's *transaction* pooler (port 6543) in serverless deployments.
    database_url: str = Field(..., description="postgresql://user:pass@host:port/db")
    db_pool: Literal["none", "queue"] = "none"   # "none" = one connection per request (serverless)
    db_pool_size: int = 5

    # Supabase
    supabase_url: str = ""
    supabase_jwt_secret: str = ""                # legacy HS256 projects; leave empty to use JWKS (ES256/RS256)
    supabase_service_role_key: str = ""          # server-only: storage uploads and admin invites
    jwt_audience: str = "authenticated"

    # Web
    web_origin: str = "http://localhost:3000"
    extra_cors_origins: Annotated[list[str], NoDecode] = []   # comma-separated in the environment

    # E-mail. Resend first; plain SMTP (e.g. Zoho) as fallback.
    # Without either, e-mails are logged instead of sent.
    resend_api_key: str = ""
    email_from: str = "myTrakIn <no-reply@example.com>"
    email_host: str = ""                           # e.g. smtp.zoho.in (Django-style name)
    email_port: int = 587
    email_host_user: str = ""
    email_host_password: str = ""
    email_use_tls: bool = True                     # STARTTLS on port 587

    # Optional AI answers on top of the rule-based suggestions (Anthropic or DeepSeek).
    ai_provider: Literal["anthropic", "deepseek"] = "anthropic"
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"             # Anthropic model
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"          # or deepseek-reasoner
    deepseek_base_url: str = "https://api.deepseek.com"

    # Scheduled jobs: Vercel Cron sends `Authorization: Bearer $CRON_SECRET`.
    cron_secret: str = ""

    # Security
    require_mfa_for_money_roles: bool = True     # admins and finance must have signed in with MFA (aal2)
    signing_link_days: int = 30
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5

    @field_validator("extra_cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [self.web_origin, *self.extra_cors_origins]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
