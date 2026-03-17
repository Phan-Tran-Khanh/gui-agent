#!/usr/bin/env python3
"""
GUI Agent - Main CLI Entry Point

ASSIST-GUI Pipeline - Step 1: Planner
Decomposes user goal into milestones and subtasks for mobile GUI automation.
"""

import argparse
import logging
import sys
from pathlib import Path
import base64

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from config.config import Config, ConfigError
from mllm.assistant_agent import AssistantAgent
from mllm.planner_agent import PlannerAgent
from planning.planner import Planner
from planning.context_retriever import ContextRetriever
from planning.constraint_retriever import ConstraintRetriever

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
        description="GUI Agent - ASSIST-GUI Pipeline Step 1: Planner",
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


def main():
    """Main entry point for GUI Agent - Step 1: Planner."""
    parser = setup_cli_parser()
    args = parser.parse_args()
    
    logger = setup_logger(debug_mode=args.debug)
    logger.info("=" * 70)
    logger.info("ASSIST-GUI Pipeline - Step 1: Planner")
    logger.info("=" * 70)
    
    try:
        # Load configuration
        logger.info("Loading configuration...")
        config = Config.from_args(args)
        logger.info(f"User Goal: {config.user_goal}")
        logger.debug(f"Config: {config.to_dict()}")

        # Get annotated image from GUI State Compiler
        logger.info("")
        logger.info("Compiling GUI state with UI element highlighting...")                        # TODO: Imp GUI state, returning a base64-encoded      #         gui_compiler = GUIStateComper()
#         image_base64 = gui_compiler.compile_gui_state()

        # read annotated image from file for testing
        image_path = Path("img/screen.jpg")
        image_base64 = None
        if image_path.exists():
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        if image_base64:
            logger.info("Successfully obtained annotated GUI image")
        else:
            logger.warning("No annotated GUI image available, proceeding with text-only planning")

        # Initialize dependencies
        logger.info("")
        logger.info("Initializing dependencies...")
        
        assistant_agent = AssistantAgent(model=config.model, api_key=config.api_key)
        planner_agent = PlannerAgent(assistant_agent)
        context_retriever = ContextRetriever(config)
        constraint_retriever = ConstraintRetriever(config)

        # Initialize Planner with dependencies
        logger.info("Initializing Planner...")
        planner = Planner(
            planner_agent=planner_agent,
            context_retriever=context_retriever,
            constraint_retriever=constraint_retriever,
            logger=logger
        )

        # Generate plan
        logger.info("")
        logger.info("Generating plan for user goal...")
        logger.info("")
        
        plan = planner.plan(
            user_goal=config.user_goal,
            image_base64=image_base64
        )

     
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
