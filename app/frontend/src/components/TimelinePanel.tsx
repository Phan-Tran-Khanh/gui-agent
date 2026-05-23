import { AgentEvent, SubgoalModel } from "../types";

interface TimelinePanelProps {
  events: AgentEvent[];
  subgoals: SubgoalModel[];
  stage: string;
}

function stageLabel(stage: string): string {
  return stage.replace(/_/g, " ");
}

export default function TimelinePanel({ events, subgoals, stage }: TimelinePanelProps) {
  return (
    <section className="panel timeline-panel">
      <header className="panel-header">
        <h2>Execution Rail</h2>
        <span className="stage-label">{stageLabel(stage)}</span>
      </header>

      <div className="subgoal-strip">
        {subgoals.length === 0 ? <p>No subgoals yet</p> : null}
        {subgoals.map((subgoal) => (
          <span key={subgoal.id} className={`subgoal-chip subgoal-${subgoal.status}`}>
            {subgoal.description}
          </span>
        ))}
      </div>

      <div className="timeline-list" role="log" aria-live="polite">
        {events.map((event) => (
          <article key={event.eventId} className={`event-card event-${event.stage}`}>
            <header>
              <strong>{event.title}</strong>
              <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
            </header>
            {event.description ? <p>{event.description}</p> : null}
            <footer>
              <span>{event.type}</span>
              {typeof event.confidence === "number" ? <span>{Math.round(event.confidence * 100)}% confidence</span> : null}
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}
