from typing import Literal
from pathlib import Path
import re
from pydantic import SecretStr, model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", hide_input_in_errors=True)
    environment: str = "local"
    version: str = "0.4.0"
    analytics_enabled: bool = False
    analytics_transport: Literal["postgres", "sqs"] = "postgres"
    sqs_queue_url: str | None = None
    sqs_dead_queue_url: str | None = None
    aws_region: str | None = None
    internal_ca_path: Path | None = None
    database_pool_size: int = Field(default=5, ge=1, le=10)
    database_max_overflow: int = Field(default=5, ge=0, le=10)
    database_url: SecretStr | None = None
    auth_mode: Literal["disabled", "local", "cognito"] = "disabled"
    auth_secret: SecretStr | None = None
    cognito_region: str = "us-east-1"
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None
    cognito_admin_group: str = "administrators"
    cognito_audience: str | None = None
    ticket_private_key_b64: SecretStr | None = None
    ticket_public_key_b64: str | None = None
    ticket_private_key_path: Path | None = None
    ticket_public_key_path: Path | None = None
    ticket_owner_secret: SecretStr | None = None
    attractions_url: str = "http://127.0.0.1:8001"
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
        for name in (
            "auth_secret",
            "ticket_secret",
            "ticket_owner_secret",
            "local_webhook_secret",
        ):
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
        if self.auth_mode == "cognito":
            pool = self.cognito_user_pool_id or ""
            if not re.fullmatch(
                r"(?:[a-z]{2}|us-gov)-[a-z]+-\d", self.cognito_region
            ) or not re.fullmatch(
                re.escape(self.cognito_region) + r"_[A-Za-z0-9]{1,100}", pool
            ):
                raise ValueError(
                    "Cognito region and matching user pool ID are required"
                )
            if not self.cognito_client_id or not re.fullmatch(
                r"[a-zA-Z0-9]{1,128}", self.cognito_client_id
            ):
                raise ValueError("Cognito app client ID is required")
        if self.database_url and self.environment == "aws":
            from sqlalchemy.engine import make_url

            query = make_url(self.database_url.get_secret_value()).query
            if query.get("sslmode") != "verify-full" or not query.get("sslrootcert"):
                raise ValueError(
                    "AWS database connections must verify the TLS server certificate"
                )
        if self.analytics_transport == "sqs":
            if not self.sqs_queue_url or not self.aws_region:
                raise ValueError("SQS requires a region and queue URL")
            if not re.fullmatch(
                r"https://sqs\."
                + re.escape(self.aws_region)
                + r"\.amazonaws\.com/[0-9]{12}/[A-Za-z0-9_-]+",
                self.sqs_queue_url,
            ):
                raise ValueError("Use the configured region's commercial AWS SQS URL")
        return self

    @property
    def cognito_issuer(self):
        suffix = (
            "amazonaws.com.cn"
            if self.cognito_region.startswith("cn-")
            else "amazonaws.com"
        )
        return f"https://cognito-idp.{self.cognito_region}.{suffix}/{self.cognito_user_pool_id}"
