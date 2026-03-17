# GUI Agent Frontend

Control-room chat interface for the GUI Agent pipeline.

## Features

- Prompt-driven chat input for user goals
- Live execution rail with stage-aware event cards
- Subgoal chips with active/done/failed status
- Observability panel for latest screenshot and reasoning
- WebSocket-first integration with automatic mock fallback
- Responsive layout for desktop and mobile

## Stack

- React 18 + TypeScript
- Vite 5

## Run

```bash
cd frontend
npm install
npm run dev
```

If your backend is available, set environment variables in `.env`:

```bash
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_BASE_URL=ws://localhost:8000/ws
```

If backend is not reachable, the UI automatically runs a local simulation stream.

## Expected Backend Contract

### Start task

- `POST /api/v1/task/start`
- Body:

```json
{ "goal": "Open settings and enable notifications" }
```

- Response:

```json
{ "task_id": "task-123" }
```

### Stream task updates

- `WS /ws/task/{task_id}`
- Message payload:

```json
{
  "eventId": "task-123-1",
  "taskId": "task-123",
  "sequence": 1,
  "timestamp": "2026-03-16T09:00:00.000Z",
  "stage": "executing_subgoal",
  "type": "action_decided",
  "title": "Action: tap",
  "description": "Decided next click target.",
  "subgoalId": "sg-1",
  "confidence": 0.87,
  "reasoning": "Top-right avatar icon is likely account entry point.",
  "screenshotUrl": "http://.../artifacts/frame.png"
}
```

## Notes

- `screenshotBase64` can be used instead of `screenshotUrl` for inline image transport.
- Timeline ordering is controlled by `sequence`.
