from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional, List

from .event_emitter import EventEmitter
from .models import AgentEvent, AgentStage, AgentEventType, now_iso
from .task_manager import TaskManager


@dataclass
class SimpleSubgoal:
    id: str
    description: str
    confidence: float


@dataclass
class SimpleAction:
    action_type: str
    target: str
    confidence: float
    reasoning: str


class AgentRunner:
    """Temporary event-driven runner.

    Replace scripted emissions with real planner/executor/reflection calls as
    those modules are implemented.
    """

    def __init__(self, task_manager: TaskManager, emitter: EventEmitter) -> None:
        self.task_manager = task_manager
        self.emitter = emitter

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

            subgoals = self._build_subgoals(goal)

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

                parsed_screen = {
                    "parser_status": "skipped",
                    "parser_request_id": None,
                    "parser_latency_ms": 0.0,
                    "elements": [],
                    "elements_count": 0,
                    "note": "Runner does not own screen capture/parse. Use /api/v1/screen/parse in backend.",
                }

                await emit(
                    stage="executing_subgoal",
                    event_type="gui_state_updated",
                    title="GUI state update",
                    description="Runner skipped parser call in this flow.",
                    subgoal_id=subgoal.id,
                    subgoal_index=index,
                    metadata=parsed_screen,
                )

                action = self._decide_action(subgoal, parsed_screen["elements"])

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

                reflection = self._reflect_subgoal(parsed_screen["elements"])

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

    def _build_subgoals(self, goal: str) -> List[SimpleSubgoal]:
        return [
            SimpleSubgoal(id="sg-1", description=f"Open target app for goal: {goal}", confidence=0.82),
            SimpleSubgoal(id="sg-2", description="Navigate to target screen", confidence=0.80),
            SimpleSubgoal(id="sg-3", description="Perform final confirmation action", confidence=0.78),
        ]

    def _decide_action(self, subgoal: SimpleSubgoal, parsed_elements: list) -> SimpleAction:
        if parsed_elements:
            first = parsed_elements[0]
            target = str(first.get("content") or first.get("type") or "detected element")
            return SimpleAction(
                action_type="CLICK",
                target=target,
                confidence=0.84,
                reasoning="Detected UI elements from parsed_screen; selecting top-ranked candidate.",
            )

        return SimpleAction(
            action_type="WAIT",
            target="screen",
            confidence=0.55,
            reasoning="No parsed elements available; wait-and-retry fallback.",
        )

    def _reflect_subgoal(self, parsed_elements: list):
        class _Reflection:
            def __init__(self, is_accomplished: bool) -> None:
                self.is_accomplished = is_accomplished
                self.recovery_action = "continue" if is_accomplished else "expand"
                self.replan_request = None if is_accomplished else {"reason": "No parsed elements"}

            def to_dict(self) -> dict:
                return {
                    "is_accomplished": self.is_accomplished,
                    "recovery_action": self.recovery_action,
                    "replan_request": self.replan_request,
                }

        return _Reflection(is_accomplished=bool(parsed_elements))
