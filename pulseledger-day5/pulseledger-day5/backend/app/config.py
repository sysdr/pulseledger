"""
PulseLedger — typed configuration

Every connection string the service needs lives here, read from
environment variables (or a .env file), never hard-coded in the modules
that use them.

Day 3 added a second database URL. DATABASE_URL is the owner connection
(bootstrap and the tenant registry, the control plane). APP_DATABASE_URL
is a restricted role used for every tenant-scoped query (the data plane).

The Stripe key guard runs at settings-load time: a live key makes the
process refuse to boot. Stripe encodes the mode in the key prefix
(sk_test_ / rk_test_ vs sk_live_ / rk_live_), so the check needs no
network call.
"""
from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LESSON_DAY = 5

_TEST_PREFIXES = ("sk_test_", "rk_test_")
_LIVE_PREFIXES = ("sk_live_", "rk_live_")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://pulseledger:pulseledger@127.0.0.1:5432/pulseledger"
    )
    # Data plane: every tenant-scoped query runs as this role. It is not a
    # superuser and cannot bypass row-level security. The bootstrap creates it.
    app_database_url: str = (
        "postgresql+asyncpg://pulseledger_app:pulseledger_app@127.0.0.1:5432/pulseledger"
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    stripe_secret_key: SecretStr | None = None
    frontend_origins: list[str] = [
        "http://localhost:4005",
        "http://127.0.0.1:4005",
    ]
    dependency_timeout_s: float = 2.0

    @field_validator("stripe_secret_key", mode="before")
    @classmethod
    def _empty_key_is_none(cls, value):
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return None
        return value

    @field_validator("stripe_secret_key")
    @classmethod
    def _test_mode_only(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value()
        if raw.startswith(_LIVE_PREFIXES):
            raise ValueError(
                "live Stripe key refused: PulseLedger runs in Stripe test mode only"
            )
        if not raw.startswith(_TEST_PREFIXES):
            raise ValueError(
                "unrecognized Stripe key: expected an sk_test_ or rk_test_ prefix"
            )
        return value

    @property
    def stripe_mode(self) -> str:
        return "test" if self.stripe_secret_key else "unset"


@lru_cache
def get_settings() -> Settings:
    return Settings()
