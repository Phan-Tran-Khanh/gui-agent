export type AgentStage =
  | "queued"
  | "planning"
  | "executing_subgoal"
  | "reflecting"
  | "replanning"
  | "completed"
  | "failed";

export type AgentEventType =
  | "task_started"
  | "plan_generated"
  | "subgoal_started"
  | "gui_state_updated"
  | "action_decided"
  | "action_executed"
  | "reflection_updated"
  | "replan_triggered"
  | "task_completed"
  | "task_failed";

export interface AgentEvent {
  eventId: string;
  taskId: string;
  sequence: number;
  timestamp: string;
  stage: AgentStage;
  type: AgentEventType;
  title: string;
  description?: string;
  subgoalId?: string;
  subgoalIndex?: number;
  confidence?: number;
  reasoning?: string;
  screenshotUrl?: string;
  screenshotBase64?: string;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface SubgoalModel {
  id: string;
  description: string;
  status: "pending" | "active" | "done" | "failed";
}

export interface ChatMessage {
  id: string;
  role: "user" | "system";
  text: string;
  timestamp: string;
}

export interface AppState {
  taskId?: string;
  stage: AgentStage;
  connected: boolean;
  events: AgentEvent[];
  subgoals: SubgoalModel[];
  activeSubgoalId?: string;
  latestReasoning?: string;
  latestScreenshot?: string;
  messages: ChatMessage[];
}
