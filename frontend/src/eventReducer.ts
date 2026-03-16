import { AppState, AgentEvent, ChatMessage, SubgoalModel } from "./types";

export type AppAction =
  | { type: "connection"; connected: boolean }
  | { type: "new_task"; taskId: string; prompt: string }
  | { type: "append_event"; event: AgentEvent }
  | { type: "append_message"; message: ChatMessage }
  | { type: "reset" };

export const initialState: AppState = {
  stage: "queued",
  connected: false,
  events: [],
  subgoals: [],
  messages: [
    {
      id: "welcome",
      role: "system",
      text: "Control room online. Submit a task to start planning and execution streaming.",
      timestamp: new Date().toISOString()
    }
  ]
};

function upsertSubgoal(subgoals: SubgoalModel[], event: AgentEvent): SubgoalModel[] {
  if (!event.subgoalId) {
    return subgoals;
  }

  const exists = subgoals.find((s) => s.id === event.subgoalId);
  const nextStatus: SubgoalModel["status"] =
    event.type === "task_failed"
      ? "failed"
      : event.type === "task_completed"
        ? "done"
        : event.stage === "executing_subgoal"
          ? "active"
          : exists?.status ?? "pending";

  if (!exists) {
    return [
      ...subgoals,
      {
        id: event.subgoalId,
        description: event.title,
        status: nextStatus
      }
    ];
  }

  return subgoals.map((subgoal) =>
    subgoal.id === event.subgoalId
      ? {
          ...subgoal,
          status: nextStatus,
          description: event.title || subgoal.description
        }
      : subgoal
  );
}

export function appReducer(state: AppState, action: AppAction): AppState {
  if (action.type === "reset") {
    return initialState;
  }

  if (action.type === "connection") {
    return {
      ...state,
      connected: action.connected
    };
  }

  if (action.type === "new_task") {
    return {
      ...state,
      taskId: action.taskId,
      stage: "queued",
      events: [],
      subgoals: [],
      activeSubgoalId: undefined,
      latestReasoning: undefined,
      latestScreenshot: undefined,
      messages: [
        ...state.messages,
        {
          id: `u-${Date.now()}`,
          role: "user",
          text: action.prompt,
          timestamp: new Date().toISOString()
        },
        {
          id: `s-${Date.now()}`,
          role: "system",
          text: `Task queued (${action.taskId}). Awaiting planning stream...`,
          timestamp: new Date().toISOString()
        }
      ]
    };
  }

  if (action.type === "append_message") {
    return {
      ...state,
      messages: [...state.messages, action.message]
    };
  }

  const sortedEvents = [...state.events, action.event].sort((a, b) => a.sequence - b.sequence);
  const updatedSubgoals = upsertSubgoal(state.subgoals, action.event);

  let systemMessage: ChatMessage | undefined;
  if (action.event.type === "task_completed") {
    systemMessage = {
      id: `m-${action.event.eventId}`,
      role: "system",
      text: "Task completed successfully.",
      timestamp: action.event.timestamp
    };
  }

  if (action.event.type === "task_failed") {
    systemMessage = {
      id: `m-${action.event.eventId}`,
      role: "system",
      text: `Task failed: ${action.event.description ?? "No reason provided"}`,
      timestamp: action.event.timestamp
    };
  }

  return {
    ...state,
    stage: action.event.stage,
    events: sortedEvents,
    subgoals: updatedSubgoals,
    activeSubgoalId: action.event.subgoalId ?? state.activeSubgoalId,
    latestReasoning: action.event.reasoning ?? state.latestReasoning,
    latestScreenshot: action.event.screenshotBase64 ?? action.event.screenshotUrl ?? state.latestScreenshot,
    messages: systemMessage ? [...state.messages, systemMessage] : state.messages
  };
}
