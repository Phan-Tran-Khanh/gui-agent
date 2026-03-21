#!/usr/bin/env python3
"""
GUI Agent - Main CLI Entry Point

ASSIST-GUI Pipeline - Step 1: Planner + Step 3: Executor
Decomposes user goal into milestones and subtasks, then executes them.
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
from execution.executor import Executor


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
        description="GUI Agent - ASSIST-GUI Pipeline Planner + Executor Test",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--goal", "-g",
        type=str,
        required=True,
        help="The task/goal for the agent to accomplish"
    )
    
    parser.add_argument(
        "--device-id", "-d",
        type=str,
        default="emulator-5554",
        help="Android device ID or emulator name (default: emulator-5554)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--skip-execution", "-s",
        action="store_true",
        default=False,
        help="Skip execution phase, only test planner"
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


def test_planner_and_executor(goal: str, device_id: str, logger: logging.Logger) -> bool:
    """
    Test the full pipeline: Planner → Executor
    
    Args:
        goal: User goal to accomplish
        device_id: Android device ID
        logger: Logger instance
    
    Returns:
        True if pipeline completed successfully, False otherwise
    """
    try:
        logger.info("=" * 80)
        logger.info("TESTING PLANNER AND EXECUTOR PIPELINE")
        logger.info("=" * 80)
        
        # ============================================================================
        # PHASE 1: LOAD CONFIGURATION
        # ============================================================================
        logger.info("")
        logger.info("PHASE 1: Loading Configuration")
        logger.info("-" * 80)
        
        config = Config.from_args(argparse.Namespace(goal=goal, debug=False))
        logger.info(f" Configuration loaded")
        logger.info(f"  Model: {config.model}")
        logger.info(f"  User Goal: {config.user_goal}")
        
        # ============================================================================
        # PHASE 2: INITIALIZE PLANNER DEPENDENCIES
        # ============================================================================
        logger.info("")
        logger.info("PHASE 2: Initializing Planner")
        logger.info("-" * 80)
        
        # Get annotated image (optional)
        image_base64 = None
        image_path = Path("img/screen.jpg")
        if image_path.exists():
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
            logger.info(f" Loaded annotated image from {image_path}")
        else:
            logger.warning(f"⚠ No annotated image found at {image_path}, proceeding with text-only planning")
        
        # Initialize agents
        assistant_agent = AssistantAgent(model=config.model, api_key=config.api_key)
        planner_agent = PlannerAgent(assistant_agent)
        context_retriever = ContextRetriever(config)
        constraint_retriever = ConstraintRetriever(config)
        
        # Initialize Planner
        planner = Planner(
            planner_agent=planner_agent,
            context_retriever=context_retriever,
            constraint_retriever=constraint_retriever,
            logger=logger
        )
        logger.info(" Planner initialized")
        
        # ============================================================================
        # PHASE 3: GENERATE PLAN
        # ============================================================================
        logger.info("")
        logger.info("PHASE 3: Generating Plan")
        logger.info("-" * 80)
        
        plan = planner.plan(
            user_goal=config.user_goal,
            image_base64=image_base64
        )
        
        logger.info(f" Plan generated with {len(plan.milestones)} milestones")
        logger.info("")
        logger.info("Generated Plan:")
        for milestone in plan.milestones:
            logger.info(f"  [{milestone.priority}] {milestone.id}: {milestone.description}")
            logger.info(f"      Success criteria: {milestone.success_criteria}")
            for subtask in milestone.subtasks:
                logger.info(f"      └─ {subtask.id}: {subtask.description}")
                logger.info(f"         Action: {subtask.action_hint.value}")
                logger.info(f"         Element: {subtask.expected_ui_element}")
                # Display grounded data
                if subtask.coordinates:
                    logger.info(f"         Coordinates: {subtask.coordinates}")
                if subtask.element_type:
                    logger.info(f"         Element Type: {subtask.element_type}")
                if subtask.confidence:
                    logger.info(f"         Confidence: {subtask.confidence}")
                if subtask.scroll_direction:
                    logger.info(f"         Scroll: {subtask.scroll_direction} ({subtask.scroll_distance})")
                if subtask.input_text:
                    logger.info(f"         Input Text: {subtask.input_text}")
                if subtask.alternative_ui_elements:
                    logger.info(f"         Alternatives: {', '.join(subtask.alternative_ui_elements)}")
        
        # ============================================================================
        # PHASE 4: INITIALIZE EXECUTOR
        # ============================================================================
        logger.info("")
        logger.info("PHASE 4: Initializing Executor")
        logger.info("-" * 80)
        
        executor = Executor(
            device_id=device_id,
            logger=logger
        )
        logger.info(f" Executor initialized for device: {device_id}")
        
        # ============================================================================
        # PHASE 5: EXECUTE PLAN
        # ============================================================================
        logger.info("")
        logger.info("PHASE 5: Executing Plan")
        logger.info("-" * 80)
        
        success, results = executor.execute_plan(plan)
        
        # ============================================================================
        # PHASE 6: REPORT RESULTS
        # ============================================================================
        logger.info("")
        logger.info("PHASE 6: Execution Results")
        logger.info("-" * 80)
        
        # Print detailed results for each milestone
        for milestone_result in results:
            status_symbol = "" if milestone_result.success else "✗"
            logger.info(f"{status_symbol} Milestone {milestone_result.milestone_id}: {milestone_result.completed_subtasks} subtasks")
            
            if not milestone_result.success:
                logger.error(f"  Failed at: {milestone_result.failed_subtask_id}")
                logger.error(f"  Error: {milestone_result.error_message}")
            
            for subtask_result in milestone_result.execution_history:
                subtask_status = "" if subtask_result.success else "✗"
                logger.info(f"  {subtask_status} {subtask_result.subtask_id}: {subtask_result.action_type.value}")
                if not subtask_result.success:
                    logger.info(f"     Error: {subtask_result.error_message}")
        
        # Get execution summary
        summary = executor.get_execution_summary(results)
        
        logger.info("")
        logger.info("EXECUTION SUMMARY")
        logger.info("-" * 80)
        logger.info(f"Status: {summary['status'].upper()}")
        logger.info(f"Milestones: {summary['completed_milestones']}/{summary['total_milestones']} completed")
        logger.info(f"Subtasks: {summary['total_subtasks']} executed")
        if summary['failed_milestone']:
            logger.info(f"Failed at milestone: {summary['failed_milestone']}")
        
        logger.info("")
        logger.info("=" * 80)
        if success:
            logger.info(" PIPELINE TEST PASSED - All milestones executed successfully!")
        else:
            logger.info("✗ PIPELINE TEST FAILED - Execution stopped at first failure")
        logger.info("=" * 80)
        
        return success
        
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error during pipeline test: {e}")
        return False


def main():
    """Main entry point for testing Planner and Executor."""
    parser = setup_cli_parser()
    args = parser.parse_args()
    
    logger = setup_logger(debug_mode=args.debug)
    
    try:
        if args.skip_execution:
            logger.info("Skipping execution phase per --skip-execution flag")
            # Run only the planner phase
            config = Config.from_args(args)
            
            assistant_agent = AssistantAgent(model=config.model, api_key=config.api_key)
            planner_agent = PlannerAgent(assistant_agent)
            context_retriever = ContextRetriever(config)
            constraint_retriever = ConstraintRetriever(config)
            
            planner = Planner(
                planner_agent=planner_agent,
                context_retriever=context_retriever,
                constraint_retriever=constraint_retriever,
                logger=logger
            )
            
            image_base64 = None
            image_path = Path("img/screen.jpg")
            if image_path.exists():
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            plan = planner.plan(user_goal=config.user_goal, image_base64=image_base64)
            return 0
        else:
            # Run the full pipeline test
            success = test_planner_and_executor(
                goal=args.goal,
                device_id=args.device_id,
                logger=logger
            )
            return 0 if success else 1
            
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
