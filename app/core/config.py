from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Web-layer settings only.

    Deliberately does NOT contain any LLM or Whisper API keys.
    Those are owned by the api/ package, which discovers them
    from the environment itself (see api/config.py) using the
    round-robin, model-scoped naming convention:

        GROQ_GPT_OSS_120B_KEY_1
        GROQ_GPT_OSS_120B_KEY_2
        GROQ_WHISPER_LARGE_V3_KEY_1
        ...

    Keeping the two config systems separate means adding a key
    is still a .env change with no code change, and this file
    never has to enumerate providers or models.

    extra="ignore" is required: the same .env file holds the
    api/ package's key variables, which are not fields here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------
    # Database
    # ---------------------------------------------------------

    database_url: str

    # ---------------------------------------------------------
    # Auth
    # ---------------------------------------------------------

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # ---------------------------------------------------------
    # Object storage (S3-compatible: AWS S3, Cloudflare R2, ...)
    # ---------------------------------------------------------

    storage_endpoint_url: str
    storage_access_key_id: str
    storage_secret_access_key: str
    storage_bucket_name: str
    storage_region: str = "auto"

    # How long a browser upload or report download link stays
    # valid, in seconds.
    storage_url_expiry_seconds: int = 900

    # ---------------------------------------------------------
    # Pipeline
    # ---------------------------------------------------------

    # Concurrent sessions processed in this process. Each one
    # holds a Silero VAD pass and several queued API requests,
    # so this is a memory/CPU bound, not an API-limit bound.
    # The API limits are enforced separately by api/scheduler.py.
    pipeline_workers: int = 4

    # Largest upload accepted, in megabytes.
    max_upload_mb: int = 100

    # ---------------------------------------------------------
    # HTTP
    # ---------------------------------------------------------

    allowed_origins: str = "http://localhost:3000"

    # Requests per minute per client, enforced by
    # app/core/rate_limit.py.
    request_rate_limit_per_minute: int = 60

    # Set to true when running behind a proxy or load balancer
    # that sets X-Forwarded-For. Leave false otherwise, or a
    # client can spoof its own rate-limit bucket.
    trust_forwarded_for: bool = False

    @property
    def allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
