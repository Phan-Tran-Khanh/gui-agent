"""
Task Planner for Planning Phase

Responsible for decomposing user goal into milestones with subtasks:
- Accept user goal
- Retrieve context and constraints
- Decompose goal using MLLM (PlannerAgent)
- Generate prioritized plan with milestones

Reference: https://arxiv.org/abs/2312.13108
"""

import logging
from typing import List, Dict, Any, Optional
from mllm.planner_agent import PlannerAgent, Plan, Milestone, SubTask
from mllm.enums import ExecutionStatus
from planning.context_retriever import ContextRetriever
from planning.constraint_retriever import ConstraintRetriever


class Planner:
    """
    Task Planner that decomposes user goals into milestones and subtasks.
    Integrates with PlannerAgent, ContextRetriever, and ConstraintRetriever.
    """

    def __init__(
        self,
        planner_agent: PlannerAgent,
        context_retriever: ContextRetriever,
        constraint_retriever: ConstraintRetriever,
        logger: logging.Logger
    ):
        """
        Initialize the Planner with required dependencies.

        Args:
            planner_agent: PlannerAgent for LLM-based goal decomposition
            context_retriever: ContextRetriever for retrieving context
            constraint_retriever: ConstraintRetriever for retrieving constraints
            logger: Logger instance for logging
        """
        self._planner_agent = planner_agent
        self._context_retriever = context_retriever
        self._constraint_retriever = constraint_retriever
        self._logger = logger

        self._logger.info("Planner initialized")

    def plan(
        self,
        user_goal: str,
        image_base64: Optional[str] = None,
        parsed_elements: Optional[List[Dict[str, Any]]] = None,
        app_category: Optional[str] = None,
        instruction_category: Optional[str] = None
    ) -> Plan:
        """
        Decompose a user goal into a structured plan with milestones and subtasks.

        Args:
            user_goal: The user's natural language goal
            image_base64: Optional base64 encoded image with highlighted UI elements
            parsed_elements: Optional list of parsed elements from OmniParser with coordinates
            app_category: Category of the target app (e.g., 'settings', 'social', 'shopping')
            instruction_category: Category of the instruction (e.g., 'navigation', 'data_entry', 'search')

        Returns:
            Plan object with milestones and subtasks ready for execution
        """
        self._logger.info(f"Planning goal: {user_goal}")
        self._logger.debug(f"App category: {app_category}, Instruction category: {instruction_category}")
        
        if image_base64:
            self._logger.debug("Image data provided for planning")
        
        if parsed_elements:
            self._logger.debug(f"Parsed elements provided: {len(parsed_elements)} elements")

        # Retrieve context and constraints
        context = self._context_retriever.retrieve_context()
        constraints_result = self._constraint_retriever.retrieve_constraints(app_category, instruction_category)
        constraints = constraints_result["merged_constraints"]

        self._logger.debug(f"Retrieved context with {len(context)} items")
        self._logger.debug(f"Retrieved {len(constraints)} constraints")

        # Use PlannerAgent to decompose goal (with optional image and parsed elements)
        try:
            plan = self._planner_agent.plan_goal(
                user_goal,
                context,
                constraints,
                image_base64=image_base64,
                parsed_elements=parsed_elements
            )
            self._logger.info(f"PlannerAgent generated {len(plan.milestones)} milestones")
        except Exception as e:
            self._logger.error(f"Failed to plan goal with PlannerAgent: {e}")
            raise

        # Validate plan
        self._validate_plan(plan)
        self._logger.info(f"Validated plan with {len(plan.milestones)} milestones")

        # Log plan summary
        self._log_plan_summary(plan)

        return plan

    def _validate_plan(self, plan: Plan) -> None:
        """
        Validate the generated plan for consistency and correctness.

        Args:
            plan: Plan object to validate

        Raises:
            ValueError: If validation fails
        """
        self._logger.debug(f"Validating plan with {len(plan.milestones)} milestones")

        # Check for circular dependencies
        if self._has_circular_dependencies(plan.milestones):
            raise ValueError("Circular dependencies detected in milestones")

        # Validate each milestone and subtask structure
        milestone_ids = {m.id for m in plan.milestones}
        for milestone in plan.milestones:
            if not milestone.id or not isinstance(milestone.id, str):
                raise ValueError(f"Invalid milestone ID: {milestone.id}")
            if not milestone.description or not isinstance(milestone.description, str):
                raise ValueError(f"Invalid milestone description: {milestone.description}")
            
            # Verify dependencies reference existing milestones
            for dep in milestone.dependencies:
                if dep not in milestone_ids:
                    raise ValueError(f"Milestone {milestone.id} references non-existent dependency {dep}")
            
            # Validate subtasks
            if not milestone.subtasks:
                raise ValueError(f"Milestone {milestone.id} has no subtasks")
            
            for subtask in milestone.subtasks:
                if not subtask.id or not subtask.description or not subtask.action_hint:
                    raise ValueError(f"Invalid subtask in milestone {milestone.id}: {subtask.id}")

        self._logger.debug("Plan validation completed successfully")

    def _has_circular_dependencies(self, milestones: List[Milestone]) -> bool:
        """
        Check if there are circular dependencies in milestones.

        Args:
            milestones: List of Milestone objects to check

        Returns:
            True if circular dependencies exist, False otherwise
        """
        milestone_map = {m.id: m for m in milestones}

        def has_cycle(m_id: str, visited: set, rec_stack: set) -> bool:
            """Recursive helper to detect cycles."""
            visited.add(m_id)
            rec_stack.add(m_id)

            m = milestone_map.get(m_id)
            if not m:
                return False

            for dep_id in m.dependencies:
                if dep_id not in visited:
                    if has_cycle(dep_id, visited, rec_stack):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(m_id)
            return False

        visited = set()
        for m in milestones:
            if m.id not in visited:
                if has_cycle(m.id, visited, set()):
                    return True

        return False

    def _log_plan_summary(self, plan: Plan) -> None:
        """
        Log a summary of the generated plan.

        Args:
            plan: Plan object to summarize
        """
        self._logger.info("=" * 70)
        self._logger.info("PLAN SUMMARY")
        self._logger.info("=" * 70)

        total_subtasks = sum(len(m.subtasks) for m in plan.milestones)
        self._logger.info(f"Total Milestones: {len(plan.milestones)}")
        self._logger.info(f"Total Subtasks: {total_subtasks}")
        self._logger.info(f"Total Subtasks: {total_subtasks}")
        self._logger.info("")

        for m in plan.milestones:
            dep_str = f" (depends on: {', '.join(m.dependencies)})" if m.dependencies else ""
            self._logger.info(f"[{m.priority}] {m.id}: {m.description}{dep_str}")
            self._logger.info(f"    Estimated steps: {m.estimated_steps}")
            self._logger.info(f"    Success criteria: {m.success_criteria}")
            
            for st in m.subtasks:
                self._logger.info(f"      {st.id}: {st.description}")
                self._logger.info(f"        Action: {st.action_hint.value}, Element: {st.expected_ui_element}")
                if st.alternative_ui_elements:
                    self._logger.info(f"        Alternatives: {st.alternative_ui_elements}")
            
            self._logger.info("")

        self._logger.info("=" * 70)
