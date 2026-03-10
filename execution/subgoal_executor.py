"""
Sub-goal Executor for Execution Module

Orchestrates the execution of a single sub-goal by managing the action loop.
Coordinates between SkillManager, Executor, and Grounder.

TODO - Implementation Instructions:
    1. Define SubGoalExecution dataclass:
        - subgoal: SubGoal
        - actions_taken: List[ExecutionResult]
        - status: str (in_progress, completed, failed)
        - total_steps: int
        - is_accomplished: bool
    2. Implement SubGoalExecutor class:
        - Constructor takes config, skill_manager, executor, grounder, gui_state_compiler
    3. Implement execute_subgoal(subgoal, visual_state) -> SubGoalExecution:
        - Initialize execution tracking
        - Enter execution loop (max_steps check)
        - Each iteration:
            a. Update GUI state with vision processing
            b. Call grounder to decide next action
            c. Execute action via executor
            d. Call reflection module to verify progress
            e. Check if subgoal accomplished
        - Return final SubGoalExecution result
    4. Implement _update_gui_state() method:
        - Call GUI state compiler with current screenshot
        - Get detected elements, masks, cropped regions
    5. Implement _get_mllm_decision(current_visual_state, subgoal) method:
        - Call grounder external API
        - Pass visual state and active sub-goal
        - Get next action decision
    6. Implement loop termination checks:
        - Check max_steps reached
        - Check sub-goal accomplishment via reflection
        - Check execution failures
    7. Add comprehensive logging of entire loop
"""

from typing import Optional, List


class SubGoalExecution:
    """
    TODO - Implementation Instructions:
        1. Define __init__ with:
            - subgoal: SubGoal
            - actions_taken: List[ExecutionResult]
            - status: str
            - total_steps: int
            - is_accomplished: bool
        2. Add to_dict() for serialization
        3. Add summary() method for logging
    """
    pass


class SubGoalExecutor:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config, skill_manager, executor, grounder, gui_state_compiler, reflector):
            - Store all components
            - Initialize logger
            - Set max_steps from config
        2. Implement execute_subgoal(subgoal, initial_visual_state) -> SubGoalExecution:
            - Create SubGoalExecution tracking object
            - Loop for up to max_steps:
                a. Compile current GUI state via gui_state_compiler
                b. Call grounder.decide_action(visual_state, subgoal)
                c. Execute action via executor
                d. Append ExecutionResult to actions_taken
                e. Check reflector for stall/verification
                f. If subgoal accomplished or failed, break
            - Return final SubGoalExecution
        3. Implement _prepare_visual_context() -> dict:
            - Get current screenshot
            - Process via vision module
            - Include detected elements, masks, etc.
            - Return context for grounder
        4. Implement _check_subgoal_progress(results_so_far) -> dict:
            - Call reflector to verify progress
            - Check if stalled
            - Return verification result
    """
    pass


def execute_subgoal_with_fallback(executor, subgoal, max_attempts: int = 2) -> SubGoalExecution:
    """
    TODO - Implementation Instructions:
        1. Attempt execute_subgoal up to max_attempts times
        2. On failure, allow full plan regeneration
        3. Return final SubGoalExecution result
    """
    pass
