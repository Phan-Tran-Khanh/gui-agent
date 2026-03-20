/**
 * Sequential Executor Service
 *
 * Calls the /api/v1/sequential/execute endpoint to start sequential execution
 * on the backend and returns the task_id for WebSocket connection.
 */

export interface SequentialExecuteRequest {
  goal: string;
  device_id?: string;
  base64_image?: string;
  max_steps?: number;
  step_delay_sec?: number;
  output_dir?: string;
}

export interface SequentialExecuteResponse {
  success: boolean;
  goal_achieved: boolean;
  total_steps: number;
  completion_message: string;
  timestamp: string;
  errors: string[];
  steps_summary: Array<{
    step_number: number;
    timestamp: string;
    action_executed: string | null;
    elements_detected: number;
    goal_achieved: boolean;
    goal_check_reasoning: string;
    error: string | null;
    metadata: Record<string, unknown>;
  }>;
}

/**
 * Call the sequential/execute API endpoint
 * Note: This is a long-running operation, so use WebSocket for real-time updates
 *
 * @param apiBase - Base URL for API (e.g., http://localhost:8000/api/v1)
 * @param request - Sequential execution request parameters
 * @param taskId - Optional task ID to associate with this execution
 * @returns Promise that resolves when execution completes
 */
export async function callSequentialExecute(
  apiBase: string,
  request: SequentialExecuteRequest,
  taskId?: string
): Promise<SequentialExecuteResponse> {
  const payload = {
    goal: request.goal,
    device_id: request.device_id || "144321556E009492",
    base64_image: request.base64_image,
    max_steps: request.max_steps || 15,
    step_delay_sec: request.step_delay_sec || 3.0,
    output_dir: request.output_dir || "output",
    task_id: taskId, // Include task_id if provided so backend can emit events
  };

  const response = await fetch(`${apiBase}/sequential/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Sequential execute failed: ${response.statusText}`);
  }

  const result = (await response.json()) as SequentialExecuteResponse;
  return result;
}

/**
 * Start sequential execution and return task_id for WebSocket connection.
 * This is a fire-and-forget approach - the API call runs in the background
 * and events are published via WebSocket.
 *
 * @param apiBase - Base URL for API
 * @param request - Sequential execution request
 * @param taskId - Task ID for tracking
 * @returns task_id that can be used to connect WebSocket
 */
export function startSequentialExecution(
  apiBase: string,
  request: SequentialExecuteRequest,
  taskId: string
): string {
  // Start the API call in the background without awaiting
  // Events will be published via WebSocket in real-time
  callSequentialExecute(apiBase, request, taskId).catch((error) => {
    console.error("Sequential execution error:", error);
  });

  // Return task_id immediately so frontend can connect WebSocket
  return taskId;
}
