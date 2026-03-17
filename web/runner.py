from __future__ import annotations

import asyncio
from typing import Optional

from execution.subgoal_executor import SubGoalExecutor
from planning.planner import Planner
from reflection.reflector import Reflector
from .event_emitter import EventEmitter
from .models import AgentEvent, AgentStage, AgentEventType, now_iso
from .task_manager import TaskManager


class AgentRunner:
    """Temporary event-driven runner.

    Replace scripted emissions with real planner/executor/reflection calls as
    those modules are implemented.
    """

    def __init__(self, task_manager: TaskManager, emitter: EventEmitter) -> None:
        self.task_manager = task_manager
        self.emitter = emitter
        self.planner = Planner()
        self.subgoal_executor = SubGoalExecutor()
        self.reflector = Reflector()

    async def run(self, task_id: str, goal: str) -> None:
        sequence = 0

        async def emit(
            *,
            stage: AgentStage,
            event_type: AgentEventType,
            title: str,
            description: Optional[str] = None,
            subgoal_id: Optional[str] = None,
            subgoal_index: Optional[int] = None,
            confidence: Optional[float] = None,
            reasoning: Optional[str] = None,
            metadata: Optional[dict] = None,
        ) -> None:
            nonlocal sequence
            event = AgentEvent(
                eventId=f"{task_id}-{sequence}",
                taskId=task_id,
                sequence=sequence,
                timestamp=now_iso(),
                stage=stage,
                type=event_type,
                title=title,
                description=description,
                subgoalId=subgoal_id,
                subgoalIndex=subgoal_index,
                confidence=confidence,
                reasoning=reasoning,
                metadata=metadata or {},
            )
            sequence += 1
            await self.task_manager.append_event(task_id, event)
            await self.emitter.publish(task_id, event)

        try:
            await emit(
                stage="planning",
                event_type="task_started",
                title="Task accepted",
                description=f"Goal received: {goal}",
            )

            subgoals = self.planner.plan(goal)

            await emit(
                stage="planning",
                event_type="plan_generated",
                title="Plan generated",
                description=f"{len(subgoals)} subgoals prepared.",
                metadata={
                    "subgoal_count": len(subgoals),
                    "subgoals": [subgoal.description for subgoal in subgoals],
                },
            )

            for index, subgoal in enumerate(subgoals, start=1):
                await emit(
                    stage="executing_subgoal",
                    event_type="subgoal_started",
                    title=subgoal.description,
                    description="Sub-goal execution started.",
                    subgoal_id=subgoal.id,
                    subgoal_index=index,
                    confidence=subgoal.confidence,
                )

                execution = self.subgoal_executor.execute_subgoal(subgoal, initial_visual_state={})

                for action in execution.actions_taken:
                    await emit(
                        stage="executing_subgoal",
                        event_type="action_decided",
                        title=f"Action decided: {action.action_type}",
                        description=f"Target: {action.target}",
                        subgoal_id=subgoal.id,
                        subgoal_index=index,
                        confidence=action.confidence,
                        reasoning=action.reasoning,
                    )
                    await asyncio.sleep(0.2)

                    await emit(
                        stage="executing_subgoal",
                        event_type="action_executed",
                        title=f"Action executed: {action.action_type}",
                        description="Action completed in executor simulation.",
                        subgoal_id=subgoal.id,
                        subgoal_index=index,
                        confidence=action.confidence,
                    )
                    await asyncio.sleep(0.15)

                reflection = self.reflector.reflect(execution, subgoal, gui_state={})

                await emit(
                    stage="reflecting",
                    event_type="reflection_updated",
                    title="Reflection complete",
                    description=f"Recovery action: {reflection.recovery_action}",
                    subgoal_id=subgoal.id,
                    subgoal_index=index,
                    confidence=0.8 if reflection.is_accomplished else 0.55,
                    reasoning=(
                        "Sub-goal accomplished; continue pipeline."
                        if reflection.is_accomplished
                        else "Sub-goal incomplete; recovery selected."
                    ),
                    metadata=reflection.to_dict(),
                )

                if reflection.recovery_action in {"replan", "expand"}:
                    await emit(
                        stage="replanning",
                        event_type="replan_triggered",
                        title="Replan triggered",
                        description="Sub-goal requires expansion/replanning.",
                        subgoal_id=subgoal.id,
                        subgoal_index=index,
                        metadata=reflection.replan_request,
                    )

                if reflection.recovery_action == "fail":
                    await self.task_manager.mark_failed(task_id, "Reflection requested task failure")
                    await emit(
                        stage="failed",
                        event_type="task_failed",
                        title="Task failed",
                        description="Reflection requested hard failure.",
                    )
                    return

                await asyncio.sleep(0.2)

            await emit(
                stage="completed",
                event_type="task_completed",
                title="Task completed",
                description="All sub-goals marked accomplished by executor/reflection loop.",
                confidence=0.9,
            )
        except asyncio.CancelledError:
            await self.task_manager.mark_failed(task_id, "Cancelled by user")
            await emit(
                stage="failed",
                event_type="task_failed",
                title="Task cancelled",
                description="Run was cancelled by user.",
            )
            raise
        except Exception as exc:  # pragma: no cover
            await self.task_manager.mark_failed(task_id, str(exc))
            await emit(
                stage="failed",
                event_type="task_failed",
                title="Task failed",
                description=str(exc),
            )
