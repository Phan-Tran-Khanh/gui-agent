import { AgentEvent, AgentStage, AgentEventType } from "../types";

interface EmitConfig {
  taskId: string;
  onEvent: (event: AgentEvent) => void;
  onEnd: () => void;
}

const script: Array<{ type: AgentEventType; stage: AgentStage; title: string; description?: string; subgoalId?: string; reasoning?: string }> = [
  { type: "task_started", stage: "planning", title: "Task accepted", description: "Initializing planner." },
  { type: "plan_generated", stage: "planning", title: "Plan generated", description: "3 subgoals created." },
  { type: "subgoal_started", stage: "executing_subgoal", title: "Open settings screen", subgoalId: "sg-1" },
  {
    type: "action_decided",
    stage: "executing_subgoal",
    title: "Action: tap",
    subgoalId: "sg-1",
    reasoning: "Top-right avatar icon is likely account entry point.",
    description: "Decided next click target."
  },
  { type: "action_executed", stage: "executing_subgoal", title: "Action executed", subgoalId: "sg-1", description: "ADB tap successful." },
  { type: "reflection_updated", stage: "reflecting", title: "Progress verified", subgoalId: "sg-1", description: "Subgoal likely complete." },
  { type: "subgoal_started", stage: "executing_subgoal", title: "Enable notification toggle", subgoalId: "sg-2" },
  { type: "replan_triggered", stage: "replanning", title: "Replan triggered", subgoalId: "sg-2", description: "UI changed. Expanding subgoal." },
  { type: "subgoal_started", stage: "executing_subgoal", title: "Find notification setting", subgoalId: "sg-2b" },
  { type: "task_completed", stage: "completed", title: "Task completed", description: "All subgoals accomplished." }
];

export function runMockStream(config: EmitConfig): () => void {
  let isCancelled = false;
  let i = 0;

  const tick = () => {
    if (isCancelled) {
      return;
    }

    if (i >= script.length) {
      config.onEnd();
      return;
    }

    const model = script[i];
    const event: AgentEvent = {
      eventId: `${config.taskId}-${i}`,
      taskId: config.taskId,
      sequence: i,
      timestamp: new Date(Date.now() + i * 1200).toISOString(),
      stage: model.stage,
      type: model.type,
      title: model.title,
      description: model.description,
      subgoalId: model.subgoalId,
      confidence: 0.75 + ((i % 3) * 0.08),
      reasoning: model.reasoning,
      screenshotUrl: "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1200&q=60",
      metadata: {
        replay: false,
        source: "mock"
      }
    };

    config.onEvent(event);
    i += 1;

    window.setTimeout(tick, 900 + (i % 3) * 350);
  };

  window.setTimeout(tick, 600);

  return () => {
    isCancelled = true;
  };
}
