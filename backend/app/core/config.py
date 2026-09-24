from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str

    # Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Object storage (S3-compatible: works for AWS S3, Cloudflare R2, etc.)
    storage_endpoint_url: str
    storage_access_key_id: str
    storage_secret_access_key: str
    storage_bucket_name: str

    # Transcription providers
    # IMPORTANT: exactly one Groq API key, from one Groq organization/account.
    # Do not add multiple Groq keys/accounts here to round-robin around rate
    # limits — that violates Groq's Acceptable Use Policy regardless of
    # whether the accounts are paid. If you need more Groq throughput,
    # request a higher limit from Groq directly (Developer/Enterprise tiers).
    groq_api_key: str
    groq_model: str = "whisper-large-v3-turbo"

    # Fallback: a different vendor entirely, used only when Groq is
    # unavailable or clearly near its limit. This is a legitimate
    # multi-provider fallback chain, not account multiplication.
    openai_api_key: str | None = None

    allowed_origins: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
