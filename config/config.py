import json
import logging
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Exception raised for configuration errors."""

    pass


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # === MLLM Settings ===
    api_key: str = Field(default="", description="LLM API key")
    model: str = Field(default="gemini-3.5-flash", description="LLM model identifier")
    request_timeout: int = Field(
        default=60, description="LLM API request timeout in seconds"
    )

    # === OmniParser Settings ===
    parse_api_base_url: str = Field(
        default="", description="Base URL of the OmniParser service"
    )
    parse_api_timeout_sec: float = Field(
        default=10.0, description="OmniParser request timeout in seconds"
    )
    parse_api_retry_count: int = Field(
        default=1, description="Number of retries on OmniParser failure"
    )
    parse_api_retry_backoff_ms: int = Field(
        default=250, description="Retry back-off in milliseconds"
    )

    # === Feature Flags ===
    mock_mode: bool = Field(
        default=False,
        description="Return synthetic data for all external connections (OmniParser, ADB, LLM)",
    )

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("MODEL is required and cannot be empty")
        return v

    @model_validator(mode="after")
    def validate_api_key_when_live(self) -> "Config":
        if not self.mock_mode and not str(self.api_key).strip():
            raise ValueError("API_KEY is required when MOCK_MODE is false")
        return self

    @classmethod
    def from_args(cls, args) -> "Config":
        """Load Config from environment variables (.env file).

        The ``args`` parameter is accepted for call-site compatibility but
        is ignored — goals are per-request values and must be passed directly
        to the functions that use them.
        """
        try:
            return cls()
        except ValueError as e:
            raise ConfigError(f"Configuration validation failed: {e}")

    @classmethod
    def from_file(cls, filepath: str) -> "Config":
        """
        Load configuration from a JSON file.

        Args:
            filepath: Path to the configuration file

        Returns:
            Config instance

        Raises:
            ConfigError: If file cannot be loaded or parsed
        """
        logger = logging.getLogger("Config")
        filepath = Path(filepath)

        if not filepath.exists():
            raise ConfigError(f"Configuration file not found: {filepath}")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info(f"Loaded configuration from {filepath}")
            return cls(**data)

        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in configuration file: {e}")
        except ValueError as e:
            raise ConfigError(f"Invalid configuration: {e}")

    def to_dict(self) -> dict:
        """
        Convert configuration to dictionary.

        Returns:
            Dictionary representation of config
        """
        return self.model_dump()

    @property
    def mllm_config(self) -> dict:
        """Get MLLM configuration."""
        return {
            "model": self.model,
            "api_key": self.api_key,
            "request_timeout": self.request_timeout,
        }
