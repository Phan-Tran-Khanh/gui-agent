interface ObservabilityPanelProps {
  screenshot?: string;
  reasoning?: string;
  connected: boolean;
  taskId?: string;
}

export default function ObservabilityPanel({ screenshot, reasoning, connected, taskId }: ObservabilityPanelProps) {
  return (
    <section className="panel observability-panel">
      <header className="panel-header">
        <h2>Observability</h2>
        <span className={`signal ${connected ? "signal-up" : "signal-down"}`}>{connected ? "stream up" : "stream down"}</span>
      </header>

      <div className="snapshot-frame">
        {screenshot ? (
          <img src={screenshot} alt="Latest GUI snapshot" />
        ) : (
          <div className="snapshot-placeholder">
            <p>No screenshot yet</p>
            <small>Latest frame from vision compiler will appear here</small>
          </div>
        )}
      </div>

      <div className="reasoning-box">
        <h3>Latest Reasoning</h3>
        <p>{reasoning ?? "Reasoning stream will appear during execution."}</p>
      </div>

      <div className="meta-box">
        <h3>Run Metadata</h3>
        <p>Task ID: {taskId ?? "not started"}</p>
      </div>
    </section>
  );
}
