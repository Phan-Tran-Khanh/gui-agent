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
 * Start sequential execution and return actual task_id from backend for WebSocket connection.
 * 
 * We make a special call to just start the background execution and get the real task_id
 * that was created on the backend. The actual execution result is handled asynchronously.
 *
 * @param apiBase - Base URL for API
 * @param request - Sequential execution request
 * @returns Promise<task_id> - actual task_id from backend for WebSocket connection
 */
export async function startSequentialExecution(
  apiBase: string,
  request: SequentialExecuteRequest
): Promise<string> {
  const payload = {
    goal: request.goal,
    device_id: request.device_id || "144321556E009492",
    base64_image: request.base64_image,
    max_steps: request.max_steps || 15,
    step_delay_sec: request.step_delay_sec || 3.0,
    output_dir: request.output_dir || "output",
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

  const result = (await response.json()) as { task_id: string };
  console.log("Sequential execution started with task_id:", result.task_id);
  return result.task_id; // Return actual task_id from backend
}
