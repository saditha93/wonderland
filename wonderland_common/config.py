from typing import Literal
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", hide_input_in_errors=True)
    environment: str = "local"
    version: str = "0.2.0"
    database_url: SecretStr | None = None
    auth_mode: Literal["disabled", "local"] = "disabled"
    auth_secret: SecretStr | None = None
    ticket_secret: SecretStr | None = None
    payment_provider: Literal["local", "stripe"] = "local"
    local_webhook_secret: SecretStr | None = None
    stripe_secret_key: SecretStr | None = None
    stripe_webhook_secret: SecretStr | None = None
    frontend_url: str = "http://localhost:5173"

    @model_validator(mode="after")
    def safe_configuration(self):
        if self.auth_mode == "local" and self.environment not in {"local", "test"}:
            raise ValueError(
                "Local identities are prohibited outside local/test environments"
            )
        if self.database_url and not self.database_url.get_secret_value().startswith(
            "postgresql+psycopg://"
        ):
            raise ValueError("A PostgreSQL psycopg URL is required")
        for name in ("auth_secret", "ticket_secret", "local_webhook_secret"):
            value = getattr(self, name)
            if value and len(value.get_secret_value()) < 32:
                raise ValueError(f"{name} must contain at least 32 characters")
        if self.auth_mode == "local" and not self.auth_secret:
            raise ValueError("Local auth requires a signing secret")
        if (
            self.stripe_secret_key
            and not self.stripe_secret_key.get_secret_value().startswith("sk_test_")
        ):
            raise ValueError("Only Stripe test secret keys are permitted")
        return self
