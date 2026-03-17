import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import ChatPanel from "./components/ChatPanel";
import ObservabilityPanel from "./components/ObservabilityPanel";
import StageHeader from "./components/StageHeader";
import TimelinePanel from "./components/TimelinePanel";
import { appReducer, initialState } from "./eventReducer";
import { runMockStream } from "./services/mockStream";
import { AgentWsClient } from "./services/wsClient";
import { AgentEvent } from "./types";

function createTaskId(): string {
  return `task-${Date.now()}`;
}

export default function App() {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const [isRunning, setIsRunning] = useState(false);
  const wsRef = useRef<AgentWsClient | null>(null);
  const cancelMockRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    return () => {
      wsRef.current?.disconnect();
      cancelMockRef.current?.();
    };
  }, []);

  const apiBase = useMemo(() => import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1", []);
  const wsBase = useMemo(() => import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000/ws", []);

  const appendEvent = (event: AgentEvent) => {
    dispatch({ type: "append_event", event });

    if (event.type === "task_completed" || event.type === "task_failed") {
      setIsRunning(false);
    }
  };

  const startMock = (taskId: string) => {
    cancelMockRef.current?.();
    cancelMockRef.current = runMockStream({
      taskId,
      onEvent: appendEvent,
      onEnd: () => setIsRunning(false)
    });
  };

  const startLiveTask = async (prompt: string): Promise<void> => {
    const taskId = createTaskId();
    dispatch({ type: "new_task", taskId, prompt });
    setIsRunning(true);

    try {
      const response = await fetch(`${apiBase}/task/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ goal: prompt })
      });

      if (!response.ok) {
        throw new Error("backend unavailable");
      }

      const payload = (await response.json()) as { task_id: string };
      const actualTaskId = payload.task_id || taskId;

      const client = new AgentWsClient();
      wsRef.current?.disconnect();
      wsRef.current = client;
      client.connect(`${wsBase}/task/${actualTaskId}`, {
        onConnection: (connected) => dispatch({ type: "connection", connected }),
        onEvent: appendEvent
      });
    } catch {
      dispatch({ type: "append_message", message: {
        id: `fallback-${Date.now()}`,
        role: "system",
        text: "Backend stream unavailable. Running local simulation stream.",
        timestamp: new Date().toISOString()
      } });
      dispatch({ type: "connection", connected: false });
      startMock(taskId);
    }
  };

  return (
    <div className="app-shell">
      <div className="background-grid" />
      <StageHeader
        stage={state.stage}
        connected={state.connected}
        onReset={() => {
          setIsRunning(false);
          wsRef.current?.disconnect();
          cancelMockRef.current?.();
          dispatch({ type: "reset" });
        }}
      />

      <main className="workspace-grid">
        <ChatPanel messages={state.messages} onSubmit={startLiveTask} isRunning={isRunning} />
        <TimelinePanel events={state.events} subgoals={state.subgoals} stage={state.stage} />
        <ObservabilityPanel
          connected={state.connected}
          taskId={state.taskId}
          reasoning={state.latestReasoning}
          screenshot={state.latestScreenshot}
        />
      </main>
    </div>
  );
}
