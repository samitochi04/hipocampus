"""
app/config.py

Defines the single source of truth for all environment-driven configuration.
Every other module that needs a secret, URL, or tunable value imports
get_settings() from here instead of reading os.environ directly.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed container for every environment variable the backend needs.
    Pydantic validates types and required-ness at startup, so a missing
    or malformed env var fails fast instead of breaking mid-request.
    Values are loaded from the process environment first, falling back
    to a local .env file (see .env.example) when present.
    """

    # --- Database ---------------------------------------------------------
    DB_URL: str  # Async Postgres connection string, e.g. postgresql+asyncpg://user:pass@host:5432/hipocampus_db

    # --- Redis ---------------------------------------------------------
    REDIS_URL: str  # e.g. redis://localhost:6379/0, shared by the API and the Celery broker/backend

    # --- Auth / JWT ---------------------------------------------------------
    JWT_SECRET_KEY: str  # Signing secret for access tokens — must stay private, rotate if ever leaked
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # Access token lifetime, default 7 days

    # --- Cookies ---------------------------------------------------------
    COOKIE_NAME: str = "hipocampus_session"
    COOKIE_DOMAIN: str | None = None  # None = current host only; set in prod if client/api are on different subdomains
    COOKIE_SECURE: bool = True  # Set False only for local http:// development

    # --- Qwen / Model Studio ---------------------------------------------------------
    QWEN_API_KEY: str
    QWEN_ENDPOINT: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    # --- CORS ---------------------------------------------------------
    # Stored as a plain comma-separated string so pydantic-settings never
    # tries to json.loads() it. Parsed into a list once in main.py when
    # CORSMiddleware is configured.
    # Examples in .env:
    #   CORS_ORIGINS=http://localhost:5173
    #   CORS_ORIGINS=http://localhost:5173,http://localhost:3000
    CORS_ORIGINS: str = "http://localhost:5173"

    # --- Dev convenience -------------------------------------------------------
    # When true, create_all_tables() runs on startup so you don't need Alembic
    # for local development. Always false in production — use Alembic migrations.
    # Must be a Settings field (not os.getenv) so pydantic-settings reads it
    # from .env / .env.local files correctly.
    AUTO_CREATE_TABLES: bool = False

    model_config = SettingsConfigDict(
        # Pydantic-settings accepts a list of env files and merges them in
        # order — later files take priority over earlier ones. Missing files
        # are silently ignored, so this is safe in both environments:
        #
        #   Docker  — only .env exists → Docker hostnames (postgres, redis)
        #             and CORS_ORIGINS=http://localhost:3000 are loaded.
        #
        #   Local   — both files exist → .env.local overrides DB_URL,
        #             REDIS_URL, and CORS_ORIGINS with localhost values
        #             for running the API directly with `uvicorn --reload`.
        env_file=[".env", ".env.local"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns the process-wide Settings instance, building it once and caching
    it for the lifetime of the process (lru_cache with no args = singleton).
    Takes no parameters.
    Used by: nearly every module that needs a config value — main.py,
    core/db.py, core/redis_client.py, core/security.py, services/*, tasks/*.
    """
    return Settings()