import { AgentEvent, AgentStage, AgentEventType } from "../types";
import mockFlow from "./mock_flow.json";

interface EmitConfig {
  taskId: string;
  onEvent: (event: AgentEvent) => void;
  onEnd: () => void;
}

// Build the scripted events from the JSON mock flow so the frontend sees realistic events.
const rawExecution: any[] = (mockFlow as any).execution_rall ?? [];
const rawChat: any[] = (mockFlow as any).missionChat ?? [];

const script: Array<Partial<AgentEvent>> = [];

// First, convert mission chat messages into lightweight AgentEvent entries with chat metadata.
rawChat.forEach((m: any, idx: number) => {
  script.push({
    type: "plan_generated",
    stage: "planning",
    title: "Mission chat",
    description: m.content,
    timestamp: m.timestamp,
    metadata: {
      chatMessage: {
        id: m.messageId ?? `msg-${idx}`,
        role: m.role === "assistant" ? "system" : m.role,
        text: m.content,
        timestamp: m.timestamp
      }
    }
  });
});

// Then append the execution events from the flow
rawExecution.forEach((e: any) => {
  script.push(e);
});

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

    const model = script[i] as any;
    const event: AgentEvent = {
      eventId: model.eventId ?? `${config.taskId}-${i}`,
      taskId: config.taskId,
      sequence: i,
      timestamp: model.timestamp ?? new Date(Date.now() + i * 1200).toISOString(),
      stage: (model.stage as AgentStage) ?? "planning",
      type: (model.type as AgentEventType) ?? "gui_state_updated",
      title: model.title ?? "",
      description: model.description,
      subgoalId: model.subgoalId,
      confidence: typeof model.confidence === "number" ? model.confidence : 0.75 + ((i % 3) * 0.08),
      reasoning: model.reasoning,
      screenshotUrl: model.screenshotUrl ?? model.screenshotUrl,
      metadata: {
        replay: false,
        source: "mock",
        ...(model.metadata ?? {})
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
