"""
Centralized configuration for FanFlow AI.

All secrets and environment-specific values are read from environment
variables (never hard-coded), following 12-factor app practice and
keeping credentials out of source control.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load variables from a local .env file (if present) into the process
# environment. In real deployments (Render, Railway, etc.) env vars are set
# directly on the platform and this is a harmless no-op.
load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # Anthropic API
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # Flask
    secret_key: str = os.getenv("FLASK_SECRET_KEY", "")
    debug: bool = _get_bool("FLASK_DEBUG", False)

    # Security
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
    allowed_origins: tuple[str, ...] = tuple(
        o.strip()
        for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5000").split(",")
        if o.strip()
    )
    max_message_length: int = int(os.getenv("MAX_MESSAGE_LENGTH", "500"))

    def validate(self) -> list[str]:
        """Return a list of human-readable problems with the current config."""
        problems = []
        if not self.anthropic_api_key:
            problems.append(
                "ANTHROPIC_API_KEY is not set. The AI assistant will run in "
                "degraded/offline mode until this is configured."
            )
        if not self.secret_key and not self.debug:
            problems.append(
                "FLASK_SECRET_KEY is not set. Required for secure sessions in "
                "production."
            )
        return problems


config = Config()
