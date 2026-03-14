"""
Configuration Manager for GUI Agent

This module manages all configuration settings for the GUI Agent system.
It handles CLI parameters and environment variables separately for clarity.

Environment Variables (from .env):
    - MODEL: LLM model (gemini/gemini-2.0-flash, openai/gpt-4, claude/claude-2)
    - API_KEY: API key for the LLM provider

CLI Arguments:
    - --goal: User's task/goal
    - --app-category: Mobile app category
    - --instruction-category: User instruction category
    - --device-id: Android device ID
    - --enable-highlighting, --enable-masking, --enable-cropping: Vision features
    - --output-dir: Output directory
    - --debug: Debug mode
    - --max-steps: Maximum execution steps
"""

import json
import logging
import os
from argparse import Namespace
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class ConfigError(Exception):
    """Exception raised for configuration errors."""
    pass


@dataclass
class Config:
    """
    Configuration container for GUI Agent.
    
    Fields from CLI Arguments:
        user_goal: The task/goal for the agent to accomplish (REQUIRED)
        app_category: Category of the mobile app
        instruction_category: Category of instruction
        device_id: Android device ID for ADB connection
        vision_enhancement: Master toggle for vision preprocessing
        enable_highlighting: Enable YOLOv8 UI element detection
        enable_masking: Enable masking irrelevant regions
        enable_cropping: Enable region cropping
        output_dir: Directory for logs and results
        debug_mode: Enable debug logging
        max_steps: Maximum execution steps per sub-goal
    
    Fields from Environment (.env):
        provider: LLM provider (gemini, openai, claude)
        api_key: API key for the LLM provider
    
    Fields with Defaults:
        max_replan_attempts: Maximum replan attempts
        stall_threshold: Visual similarity threshold for stall detection
        action_delay: Delay between actions
        adb_path: Path to adb executable
        grounding_api_endpoint: External grounding API URL
        grounding_api_timeout: Grounding API timeout
    """
    
    # === Required (from CLI) ===
    user_goal: str
    
    # === From CLI (optional) ===
    app_category: Optional[str] = None
    instruction_category: Optional[str] = None
    device_id: Optional[str] = None
    output_dir: Path = field(default_factory=lambda: Path("./outputs"))
    debug_mode: bool = False
    
    # === Vision settings (from CLI) ===
    vision_enhancement: bool = True
    enable_highlighting: bool = True
    enable_masking: bool = False
    enable_cropping: bool = False
    
    # === Execution settings (defaults) ===
    max_steps: int = 50
    max_replan_attempts: int = 3
    stall_threshold: float = 0.95
    action_delay: float = 0.5
    adb_path: str = "adb"
    
    # === MLLM settings (from .env) ===
    model: str = field(default_factory=lambda: os.getenv("MODEL"))
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("API_KEY"))
    
    # === Grounder settings (defaults) ===
    grounding_api_endpoint: Optional[str] = None
    grounding_api_timeout: int = 30
    
    # === Internal ===
    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("Config"),
        repr=False,
        compare=False
    )

    def __post_init__(self):
        """Validate and normalize configuration after initialization."""
        # Convert output_dir to Path if string
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        
        # Expand to absolute path
        self.output_dir = self.output_dir.resolve()
        
        # Validate
        self.validate()

    def validate(self) -> None:
        """
        Validate the configuration.
        
        Raises:
            ConfigError: If validation fails
        """
        errors = []
        
        # Required fields
        if not self.user_goal or not self.user_goal.strip():
            errors.append("user_goal (--goal) is required and cannot be empty")
        
        if not self.api_key:
            errors.append("API_KEY environment variable is required")
        
        if not self.model:
            errors.append("MODEL environment variable is required")
        
        # Numeric validations
        if self.max_steps < 1:
            errors.append("max_steps must be at least 1")
        
        if self.max_replan_attempts < 0:
            errors.append("max_replan_attempts cannot be negative")
        
        if not 0.0 <= self.stall_threshold <= 1.0:
            errors.append("stall_threshold must be between 0.0 and 1.0")

        if self.action_delay < 0:
            errors.append("action_delay cannot be negative")
        
        # Raise all errors at once
        if errors:
            error_msg = "Configuration validation failed:\n  - " + "\n  - ".join(errors)
            self._logger.error(error_msg)
            raise ConfigError(error_msg)
        
        self._logger.debug("Configuration validation passed")

    @classmethod
    def from_args(cls, args: Namespace) -> "Config":
        """
        Create Config from argparse Namespace and environment variables.
        
        Args:
            args: Parsed command-line arguments
            
        Returns:
            Config instance
        """
        # Extract CLI arguments
        config_kwargs = {
            "user_goal": getattr(args, "goal", ""),
            "app_category": getattr(args, "app_category", None),
            "instruction_category": getattr(args, "instruction_category", None),
            "device_id": getattr(args, "device_id", None),
            "vision_enhancement": getattr(args, "vision_enhancement", True),
            "enable_highlighting": getattr(args, "enable_highlighting", True),
            "enable_masking": getattr(args, "enable_masking", False),
            "enable_cropping": getattr(args, "enable_cropping", False),
            "output_dir": Path(getattr(args, "output_dir", "./outputs")),
            "debug_mode": getattr(args, "debug", False),
            "max_steps": getattr(args, "max_steps", 50),
            # MLLM settings are loaded from .env via field defaults
        }
        
        # Filter out None and False values for optional fields
        config_kwargs = {k: v for k, v in config_kwargs.items() if v}
        
        return cls(**config_kwargs)

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
        except TypeError as e:
            raise ConfigError(f"Invalid configuration structure: {e}")

    def save(self, filepath: str) -> None:
        """
        Save configuration to a JSON file.
        
        Args:
            filepath: Path to save the configuration
        """
        filepath = Path(filepath)
        
        # Create directory if needed
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict, handling non-serializable fields
        data = self.to_dict()
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        
        self._logger.info(f"Saved configuration to {filepath}")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary.
        
        Returns:
            Dictionary representation of config (excluding logger)
        """
        data = asdict(self)
        # Remove non-serializable fields
        data.pop("_logger", None)
        # Convert Path to string
        if "output_dir" in data:
            data["output_dir"] = str(data["output_dir"])
        return data

    # === Property groups for easier access ===

    @property
    def vision_config(self) -> Dict[str, bool]:
        """Get vision-related settings as a dictionary."""
        return {
            "vision_enhancement": self.vision_enhancement,
            "enable_highlighting": self.enable_highlighting,
            "enable_masking": self.enable_masking,
            "enable_cropping": self.enable_cropping,
        }

    @property
    def execution_config(self) -> Dict[str, Any]:
        """Get execution-related settings as a dictionary."""
        return {
            "max_steps": self.max_steps,
            "max_replan_attempts": self.max_replan_attempts,
            "stall_threshold": self.stall_threshold,
            "action_delay": self.action_delay,
        }

    @property
    def mllm_config(self) -> Dict[str, Any]:
        """Get MLLM-related settings (model and api_key from .env)."""
        return {
            "model": self.model,
            "api_key": self.api_key,
        }

    def ensure_output_dir(self) -> Path:
        """Create output directory if it doesn't exist and return the path."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir
