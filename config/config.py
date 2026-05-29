import json
import logging
from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # === MLLM Settings (from .env) ===
    api_key: str = Field(
        ...,
        description="API key for the LLM provider"
    )
    model: str = Field(
        default="gemini-2.0-flash",
        description="LLM model name"
    )
    
    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: Optional[str]) -> str:
        if not v or not str(v).strip():
            raise ValueError("API_KEY is required and cannot be empty")
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("MODEL is required and cannot be empty")
        return v

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
        """Get MLLM configuration (model and api_key from .env)."""
        return {
            "model": self.model,
            "api_key": self.api_key,
        }
