import { AgentStage } from "../types";

interface StageHeaderProps {
  stage: AgentStage;
  connected: boolean;
  onReset: () => void;
}

const stages: AgentStage[] = ["queued", "planning", "executing_subgoal", "reflecting", "replanning", "completed", "failed"];

export default function StageHeader({ stage, connected, onReset }: StageHeaderProps) {
  return (
    <header className="stage-header">
      <div>
        <h1>GUI Agent Control Room</h1>
        <p>Real-time planning, action, and reflection visibility</p>
      </div>

      <div className="stage-track" aria-label="pipeline stage">
        {stages.map((item) => (
          <span key={item} className={`track-chip ${stage === item ? "track-active" : ""}`}>
            {item.replace(/_/g, " ")}
          </span>
        ))}
      </div>

      <div className="header-actions">
        <span className={`signal ${connected ? "signal-up" : "signal-down"}`}>{connected ? "connected" : "disconnected"}</span>
        <button type="button" onClick={onReset}>Reset View</button>
      </div>
    </header>
  );
}
