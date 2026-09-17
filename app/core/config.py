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

    # Plain SQLAlchemy URL, used when cloud_sql_connection_name
    # is not set (local dev, or any Postgres reachable directly
    # by network). Empty when connecting through the Cloud SQL
    # connector instead.
    database_url: str = ""

    # Set to route the DB connection through the Cloud SQL
    # Python Connector instead of database_url. Format:
    # "PROJECT:REGION:INSTANCE".
    cloud_sql_connection_name: str = ""
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""

    # ---------------------------------------------------------
    # Auth
    # ---------------------------------------------------------

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # ---------------------------------------------------------
    # Object storage (Google Cloud Storage)
    # ---------------------------------------------------------

    gcp_project_id: str
    gcp_storage_bucket: str

    # Service account to impersonate for signing URLs when the
    # ambient credentials have no private key (e.g. Cloud Run's
    # attached runtime service account). Not needed for local
    # dev against a downloaded service-account key file, since
    # that credential can already sign directly.
    gcp_service_account_email: str = ""

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
    # Video analysis (optional, parallel to the audio pipeline)
    # ---------------------------------------------------------

    # Off by default. With this false the API ignores every
    # video field, the signal upload route is 404, and results
    # carry no video sections: behaviour is identical to before
    # the feature existed.
    video_analysis_enabled: bool = False

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
