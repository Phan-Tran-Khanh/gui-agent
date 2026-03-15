#!/usr/bin/env python3
"""
GUI Agent - Main CLI Entry Point

Basic initialization of configuration and logging.
Foundation for future implementation of planning, execution, vision, and reflection modules.
"""

import argparse
import logging
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from config.config import Config, ConfigError
from mllm.assistant_agent import AssistantAgent


def setup_logger(debug_mode: bool = False) -> logging.Logger:
    """Configure and return the root logger."""
    level = logging.DEBUG if debug_mode else logging.INFO
    
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    return logging.getLogger("GUIAgent")


def setup_cli_parser() -> argparse.ArgumentParser:
    """Set up argument parser for CLI."""
    parser = argparse.ArgumentParser(
        description="GUI Agent - Mobile Navigation with MLLM",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--goal", "-g",
        type=str,
        required=True,
        help="The task/goal for the agent to accomplish"
    )
    
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        default=False,
        help="Enable debug logging"
    )
    
    return parser

def test_assistant_agent(config: Config, logger: logging.Logger) -> None:
    """Test AssistantAgent with a sample screenshot."""
    logger.info("=" * 60)
    logger.info("Testing AssistantAgent")
    logger.info("=" * 60)
    
    try:
        # Initialize AssistantAgent
        logger.info(f"Initializing AssistantAgent with model: {config.model}")
        assistant_agent = AssistantAgent(model=config.model, api_key=config.api_key)
        
        # Test with sample screenshot if available
        screenshot_path = Path("img/screen.jpg")
        
        if screenshot_path.exists():
            logger.info(f"Loading screenshot: {screenshot_path}")
            with open(screenshot_path, "rb") as f:
                image_bytes = f.read()
            
            # Determine MIME type
            suffix = screenshot_path.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp"
            }
            mime_type = mime_types.get(suffix, "image/png")
            
            logger.info(f"Sending screenshot to AssistantAgent with goal: {config.user_goal}")
            response = assistant_agent.query(
                prompt=config.user_goal,
                image_bytes=image_bytes,
                mime_type=mime_type
            )
            
            logger.info("AssistantAgent Response:")
            print(f"\n{response}\n")
        else:
            # Text-only test
            logger.info("No screenshot found, testing text-only query")
            prompt = f"How would I accomplish this on a mobile device: {config.user_goal}"
            response = assistant_agent.query(prompt=prompt)
            
            logger.info("AssistantAgent Response:")
            print(f"\n{response}\n")
        
        logger.info("AssistantAgent test completed successfully!")
        
    except Exception as e:
        logger.error(f"AssistantAgent test failed: {e}")


def main():
    """Main entry point for GUI Agent."""
    parser = setup_cli_parser()
    args = parser.parse_args()
    
    logger = setup_logger(debug_mode=args.debug)
    logger.info("=" * 60)
    logger.info("GUI Agent Starting")
    logger.info("=" * 60)
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = Config.from_args(args)
        logger.info(f"User Goal: {config.user_goal}")
        logger.debug(f"Config: {config.to_dict()}")

        # Initialize AssistantAgent
        logger.info(f"Initializing AssistantAgent with model: {config.model}")
        assistant_agent = AssistantAgent(model=config.model, api_key=config.api_key)

        # sameple test with screenshot
        screenshot_path = Path("img/screen.jpg")
        if screenshot_path.exists():
            logger.info(f"Loading screenshot: {screenshot_path}")
            with open(screenshot_path, "rb") as f:
                image_bytes = f.read()
            
            # Determine MIME type
            suffix = screenshot_path.suffix.lower()
            mime_types = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp"
            }
            mime_type = mime_types.get(suffix, "image/png")
    
            response = assistant_agent.query(
                prompt=config.user_goal,
                image_bytes=image_bytes,
                mime_type=mime_type
            )

            logger.info("=" * 60)
            logger.info("ASSISTANT AGENT RESPONSE:")
            logger.info(f"Response: {response}")
        else:
            logger.info("No screenshot found, testing text-only query")
            prompt = f"How would I accomplish this on a mobile device: {config.user_goal}"
            response = assistant_agent.query(prompt=prompt)

            logger.info("=" * 60)
            logger.info("ASSISTANT AGENT RESPONSE:")
            logger.info(f"Response: {response}")

        return 0
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
