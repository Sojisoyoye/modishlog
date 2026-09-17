"""Application configuration using pydantic-settings."""

import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq-style query params that asyncpg does not accept as URL query params.
# SSL is handled via connect_args={"ssl": True} on the engine instead.
_LIBPQ_DROP = frozenset(
    {
        "sslmode",
        "sslrootcert",
        "sslcert",
        "sslkey",
        "sslpassword",
        "channel_binding",
        "gssencmode",
        "krbsrvname",
        "gsslib",
        "target_session_attrs",
        "connect_timeout",
        "keepalives",
        "keepalives_idle",
        "keepalives_interval",
        "keepalives_count",
        "application_name",
        "fallback_application_name",
        "load_balance_hosts",
        "options",
    }
)

_SSL_REQUIRED_MODES = frozenset({"require", "verify-ca", "verify-full"})


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database — normalised to postgresql+asyncpg:// with libpq params stripped
    # No default: must be supplied via DATABASE_URL env var or .env file
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5433/modishlog"
    # True when the original DATABASE_URL contained sslmode=require|verify-*
    DATABASE_SSL: bool = False

    @model_validator(mode="before")
    @classmethod
    def detect_ssl(cls, data: Any) -> Any:
        """Detect SSL requirement from the raw DATABASE_URL before field validation."""
        if isinstance(data, dict):
            url = data.get("DATABASE_URL", "")
            if isinstance(url, str) and "sslmode=" in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query, keep_blank_values=True)
                sslmode = (params.get("sslmode") or [None])[0]
                if sslmode in _SSL_REQUIRED_MODES:
                    data["DATABASE_SSL"] = True
        return data

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, value: Any) -> str:
        """Normalise Neon/Heroku-style URLs for asyncpg.

        - Rewrites postgres:// and postgresql:// to postgresql+asyncpg://
        - Strips all libpq query params (sslmode, channel_binding, etc.)
          SSL is configured via DATABASE_SSL + connect_args on the engine.
        """
        if not isinstance(value, str):
            return value
        for old in ("postgres://", "postgresql://"):
            if value.startswith(old):
                value = "postgresql+asyncpg://" + value[len(old) :]
                break
        parsed = urlparse(value)
        if parsed.query:
            params = parse_qs(parsed.query, keep_blank_values=True)
            for key in _LIBPQ_DROP:
                params.pop(key, None)
            value = urlunparse(
                parsed._replace(query=urlencode({k: v[0] for k, v in params.items()}))
            )
        return value

    # Security — SECRET_KEY has no default; must be set explicitly in every environment
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS — accepts a JSON array string or comma-separated string from env vars
    CORS_ORIGINS: list[str] = ["http://localhost:4200"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("["):
                return json.loads(value)
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def reject_wildcard_origins(cls, v: list[str]) -> list[str]:
        if "*" in v:
            raise ValueError(
                "CORS_ORIGINS must not contain '*'. "
                "Using a wildcard origin with allow_credentials=True violates the "
                "CORS spec and exposes credentials to any origin. "
                "Specify explicit allowed origins instead."
            )
        return v

    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(
                f"ALGORITHM must be one of {sorted(allowed)} to prevent algorithm "
                f"confusion attacks. Got: {v!r}"
            )
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == "dev-secret-change-in-production" or len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters and must not be the "
                "development default. Set a strong random value in your environment."
            )
        return v

    # File uploads — /app/uploads is writable by appuser in Docker
    UPLOAD_DIR: str = "/app/uploads"
    # Maximum number of rows accepted in a single CSV bulk-upload request.
    # Prevents OOM on maliciously large uploads.
    MAX_CSV_ROWS: int = 50000

    # Database connection pool — exposed as env vars so they can be tuned per environment.
    #
    # Headroom math (task #228, reproduced as a real failure by task #243's
    # load test): production runs self-hosted Postgres
    # (docker-compose.prod.yml's `db` service, plain postgres:15-alpine,
    # default max_connections=100) behind gunicorn --workers 2. Total app
    # connection demand is workers * (DB_POOL_SIZE + DB_MAX_OVERFLOW) — at
    # the old 10+20, that was 2*30=60, which a 200-concurrent-user load test
    # saturated completely (sqlalchemy.exc.TimeoutError: QueuePool limit
    # ... reached), producing real 500s on /products and /sales. Raised to
    # 15+25=40/worker (2*40=80 total) to use more of the previously-unused
    # headroom under max_connections=100, while still leaving 20 connections
    # free for migrations, admin psql sessions, and health checks. If
    # --workers is ever raised, lower these accordingly (env vars) or raise
    # Postgres's own max_connections first (confirm available RAM on the
    # Hetzner box before doing that — each extra connection slot reserves
    # shared memory) — don't let workers * (pool_size + max_overflow)
    # silently exceed max_connections. See
    # .taskmaster/docs/loadtest-findings-243.md for the full reproduction.
    #
    # Staging uses Neon (serverless Postgres), not this self-hosted setup —
    # pool_recycle and pool_pre_ping below exist for Neon's idle-connection
    # drops as well as any transient network blip against the self-hosted
    # instance.
    DB_POOL_SIZE: int = 15
    DB_MAX_OVERFLOW: int = 25
    # Recycle connections after 1800 s (30 min) to protect against Neon
    # serverless idle-connection drops (~5 min timeout) on staging, and
    # against any long-idle connection going stale in general.
    # pool_pre_ping=True provides additional protection by validating
    # connections before checkout.
    DB_POOL_RECYCLE: int = 1800  # seconds (30 minutes)

    # Bounds how many bulk-upload background jobs run concurrently per
    # worker process (task #255). run_bulk_upload_job_in_background()
    # pulls from the same per-worker DB connection pool as foreground
    # request handling -- task #243's load test found that an unbounded
    # burst of concurrent imports (many businesses uploading at once)
    # degrades every other business's dashboard/product/sales page loads
    # on that worker. Capping concurrent background jobs, rather than
    # adding a second DB pool, keeps this fix simple and avoids re-opening
    # the connection budget math above (task #228) that's already tuned
    # against Postgres's max_connections=100.
    BULK_UPLOAD_MAX_CONCURRENT_JOBS: int = 2

    # Environment
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    APP_VERSION: str = "1.0.0"

    # Set only by docker-compose.e2e.yml — a real Playwright run legitimately
    # logs in far more than the login endpoint's normal 10/minute limit
    # across its full suite (many specs, each with their own beforeEach
    # login). Deliberately NOT tied to ENVIRONMENT=test: backend-tests.yml's
    # plain pytest CI job also sets ENVIRONMENT=test (for unrelated reasons),
    # and several real security regression tests there specifically verify
    # the strict limit IS enforced — conflating the two flags broke them.
    E2E_RELAXED_LOGIN_RATE_LIMIT: bool = False

    # Set only by docker-compose.e2e.yml — self-service /auth/onboard normally
    # requires clicking an emailed verification link before the first login,
    # but the E2E suite has no real inbox to read that link from and its
    # single shared E2E_EMAIL test user must be able to log in immediately
    # across the whole run. Deliberately a dedicated flag, not ENVIRONMENT=test,
    # for the same reason as E2E_RELAXED_LOGIN_RATE_LIMIT above: the plain
    # pytest CI job also sets ENVIRONMENT=test and has its own regression
    # tests that verify the real blocking behaviour.
    E2E_AUTO_VERIFY_EMAIL: bool = False

    # Set only by docker-compose.e2e.yml — /auth/onboard's normal 5/minute
    # limit is easy to exceed within a single e2e run: register.spec.ts alone
    # makes several onboard calls (happy path, duplicate-email pre-seeding),
    # and other files sharing the same CI test business add more across a
    # shard's full run. Same dedicated-flag rationale as
    # E2E_RELAXED_LOGIN_RATE_LIMIT and E2E_AUTO_VERIFY_EMAIL above.
    E2E_RELAXED_ONBOARD_RATE_LIMIT: bool = False

    # Set only by docker-compose.loadtest.yml — the global default_limits
    # ("200/minute", core/rate_limit.py) is keyed on client IP, which is
    # meaningless for a load-test tool: every virtual user originates from
    # the same load-generator host, so the per-IP limit caps throughput at
    # a fraction of what real traffic (spread across many customer IPs)
    # would ever hit. Deliberately a dedicated flag, not reused from the
    # E2E_* flags above, since those only cover login/onboard specifically.
    LOADTEST_RELAXED_RATE_LIMIT: bool = False

    # Task #252: self-service business account deletion is a grace-period
    # soft delete, not immediate -- gives the OWNER a window to cancel
    # before a background purge job (see task #260) anonymizes PII.
    BUSINESS_DELETION_GRACE_PERIOD_DAYS: int = 30

    # External APIs
    FX_API_KEY: str = ""
    FX_API_URL: str = "https://api.example.com/fx"
    FX_LIVE_API_URL: str = "https://open.er-api.com/v6/latest/USD"
    FX_CACHE_TTL_HOURS: int = 4
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"

    # Redis — used for shared rate-limit state across gunicorn workers.
    # Empty string = fall back to in-memory (single-worker / dev mode).
    REDIS_URL: str = ""

    # Fernet key rotation — comma-separated list, newest key first.
    # If empty, falls back to deriving a key from SECRET_KEY (legacy behaviour).
    # Example: "key_new,key_old" — decryption tries each in order; encryption uses first.
    FERNET_KEYS: str = ""

    # Error tracking
    SENTRY_DSN: str = ""

    # Transactional email (Resend) — empty key means "not configured":
    # send_email() logs instead of sending, keeping local/dev/CI working
    # with zero setup.
    RESEND_API_KEY: str = ""
    # contact@ (not noreply@) -- both email types today (verification, forgot
    # password) are ones a user may legitimately need to reply to for
    # support. Reserve noreply@ for a future email type that genuinely
    # doesn't need a reply path.
    EMAILS_FROM_EMAIL: str = "contact@modishlog.com"
    EMAILS_FROM_NAME: str = "ModishLog"
    # Base URL used to build verification/reset links in outgoing emails.
    FRONTEND_URL: str = "http://localhost:4200"

    @property
    def emails_enabled(self) -> bool:
        return bool(self.RESEND_API_KEY)

    # Billing (Paystack, task #237/#238) — empty means "not configured":
    # initiate_checkout() raises BillingNotConfiguredError rather than a
    # confusing raw API failure, keeping local/dev/CI working with zero
    # setup. Plan codes are created once in the Paystack dashboard (where
    # the actual NGN price per tier is set) and referenced here by code --
    # this app never computes or sends a charge amount itself.
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_BASIC_PLAN_CODE: str = ""
    PAYSTACK_PRO_PLAN_CODE: str = ""

    # CAPTCHA (Cloudflare Turnstile, task #250) -- empty means "not
    # configured": verify_turnstile_token() skips verification entirely,
    # keeping local/dev/CI/E2E onboarding working with zero setup. Once
    # configured, this becomes the primary defense against scripted
    # fake-account creation (the existing per-IP rate limit is already
    # beatable with rotating IPs/proxies), so verification fails closed
    # on a Cloudflare API error rather than open.
    TURNSTILE_SECRET_KEY: str = ""


settings = Settings()
