"""
Logger Utility for GUI Agent

Provides centralized logging configuration for the entire application.

TODO - Implementation Instructions:
    1. Define setup_logger(name, level) -> Logger:
        - Create logger with name
        - Set level (DEBUG, INFO, WARNING, ERROR)
        - Add console handler (formatted)
        - Add file handler (to output_dir/{name}.log)
        - Return configured logger
    2. Implement log formatting:
        - Include timestamp, level, logger name, message
        - Different format for console vs file
    3. Implement log levels:
        - DEBUG: detailed execution trace
        - INFO: major steps, decisions
        - WARNING: potential issues
        - ERROR: failures, exceptions
    4. Create convenience functions:
        - get_logger(name) -> returns configured logger
        - configure_root_logger(output_dir, debug_mode)
"""

import logging


def setup_logger(name: str, log_level: str = "INFO", output_dir: str = "./logs") -> logging.Logger:
    """
    TODO - Implementation Instructions:
        1. Create logger with given name
        2. Set log level from log_level string
        3. Create console handler with formatter
        4. Create file handler (output_dir/{name}.log) with formatter
        5. Add both handlers to logger
        6. Return logger
    """
    pass


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger with the given name."""
    return logging.getLogger(name)


def configure_root_logger(output_dir: str = "./logs", debug_mode: bool = False) -> None:
    """
    TODO - Implementation Instructions:
        1. Configure root logger
        2. Set level based on debug_mode (DEBUG if True, INFO if False)
        3. Add handlers
        4. Create output_dir if not exists
    """
    pass
