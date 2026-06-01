#!/usr/bin/env python3
"""
Example usage of Step 1: Planner from ASSIST-GUI Pipeline

This script demonstrates how to:
1. Initialize the Planner
2. Decompose a user goal into sub-goals/milestones
3. View the generated plan
"""

import argparse
import logging
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from config.config import Config, ConfigError
from planning.planner import Planner


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
        description="Step 1: Planner - Decompose user goal into sub-goals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic planning
  python planning_demo.py --goal "Turn off ad personalization" --app-category settings --instruction-category toggle

  # Planning with refinement
  python planning_demo.py --goal "Find and disable notifications" --refinement "Focus on privacy settings"

  # Debug mode
  python planning_demo.py --goal "Login to my account" --debug
        """
    )
    
    parser.add_argument(
        "--goal", "-g",
        type=str,
        required=True,
        help="The task/goal for the agent to accomplish"
    )
    
    parser.add_argument(
        "--app-category",
        type=str,
        default=None,
        help="App category (e.g., 'settings', 'social', 'shopping', 'navigation')"
    )
    
    parser.add_argument(
        "--instruction-category",
        type=str,
        default=None,
        help="Instruction category (e.g., 'navigation', 'data_entry', 'search', 'toggle')"
    )
    
    parser.add_argument(
        "--refinement",
        type=str,
        default=None,
        help="Optional refinement query to refine the initial plan"
    )
    
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        default=False,
        help="Enable debug logging"
    )
    
    return parser


def main():
    """Main entry point for planning demo."""
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

        # Initialize Planner
        logger.info("Initializing Planner...")
        planner = Planner(config)

        # Generate plan
        logger.info("")
        logger.info("Generating plan...")
        logger.info("")
        
        if args.refinement:
            subgoals = planner.plan_with_refinement(
                user_goal=config.user_goal,
                app_category=args.app_category,
                instruction_category=args.instruction_category,
                refinement_query=args.refinement
            )
        else:
            subgoals = planner.plan(
                user_goal=config.user_goal,
                app_category=args.app_category,
                instruction_category=args.instruction_category
            )

        # Output plan details
        logger.info("")
        logger.info("=" * 70)
        logger.info("PLAN DETAILS")
        logger.info("=" * 70)
        
        for i, sg in enumerate(subgoals, 1):
            logger.info(f"\nSub-goal {i}:")
            logger.info(f"  ID: {sg.id}")
            logger.info(f"  Description: {sg.description}")
            logger.info(f"  Priority: {sg.priority}")
            logger.info(f"  Estimated Steps: {sg.estimated_steps}")
            if sg.dependencies:
                logger.info(f"  Dependencies: {', '.join(sg.dependencies)}")
            logger.info(f"  Success Criteria: {sg.success_criteria}")

        logger.info("")
        logger.info("=" * 70)
        logger.info("Planning completed successfully!")
        logger.info("=" * 70)
        
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
