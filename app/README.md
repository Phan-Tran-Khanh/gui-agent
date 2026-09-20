# GUI Agent — Web Application

This directory contains the web application for the GUI Agent project:

- `backend/` — FastAPI server that exposes the agent task API and WebSocket event stream
- `frontend/` — React + TypeScript (Vite) UI that connects to the backend

---

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm

---

## Backend

### 1. Install dependencies

From the **project root** (`gui-agent/`):

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | _(required)_ | LLM API key |
| `MODEL` | `gemini/gemini-3.1-flash-lite-preview` | Model identifier |
| `REQUEST_TIMEOUT` | `60` | LLM API request timeout in seconds |
| `PARSE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the OmniParser service |
| `PARSE_API_TIMEOUT_SEC` | `10` | Request timeout in seconds |
| `PARSE_API_RETRY_COUNT` | `1` | Number of retries on failure |
| `PARSE_API_RETRY_BACKOFF_MS` | `250` | Retry back-off in milliseconds |
| `MOCK_MODE` | `false` | Set to `true` to return synthetic data for all external connections (OmniParser, ADB device, LLM). No real device or API keys required. |

### Running in mock mode

```bash
MOCK_MODE=true uvicorn app.backend.backend:app --host 0.0.0.0 --port 8000 --reload
```

In mock mode:
- `POST /api/v1/sequential/execute` works without `PARSE_API_BASE_URL` being set
- Each task runs through **two simulated steps** (plan → action → goal achieved) emitting real WebSocket events
- No Android device or LLM credentials are required

### Closed-loop acceptance gates

The deterministic replay corpus is hardware-free and safe to run in CI or during local development:

```bash
python scripts/run_acceptance.py --replay-only
```

It prints a JSON report and fails if any replay produces unsafe coordinates or an unsupported dispatch, a configured volume repetition is incomplete, the fixed general corpus drops below 90% verified completion, or the HTTP/WebSocket compatibility checks fail. The corpus references only sanitized `output1/` artifacts; it contains no copied screenshots, device identifiers, credentials, or request IDs. Its semantic labels are manually curated fixture oracles, so a replay-only pass is a deterministic regression signal—not evidence that a physical device completed the action.

Live Android acceptance is strictly opt-in. It may open Settings, temporarily adjust and restore media volume, send bounded navigation gestures, and type an acceptance marker only into a currently discovered native text field. Each action must also produce a foreground-app, UI-hierarchy, screenshot, or audio-oracle effect; an ADB success alone does not pass. Supply the exact device serial only when that device is safe to exercise:

```bash
python scripts/run_acceptance.py --device emulator-5554
```

The live tests are otherwise skipped by normal `unittest` discovery. A `--device` run treats any skipped live case as a failed acceptance run; configure the selected device with native scroll, text, and long-press targets, and set `ANDROID_E2E_ALLOW_SLIDER_MUTATION=true` when a slider mutation is safe. They use `dumpsys audio` solely as the media-volume oracle.

### 3. Run the backend server

From the **project root** (`gui-agent/`):

```bash
uvicorn app.backend.backend:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

---

## Frontend

### 1. Install dependencies

```bash
cd app/frontend
npm install
```

### 2. Run the development server

```bash
npm run dev
```

The UI will be available at `http://localhost:5173`.

### 3. Build for production

```bash
npm run build
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/task/start` | Start a new agent task `{ "goal": "..." }` |
| `GET` | `/api/v1/task/{task_id}` | Get task snapshot and replay events |
| `POST` | `/api/v1/task/{task_id}/cancel` | Cancel a running task |
| `WS` | `/ws/task/{task_id}` | Live WebSocket event stream |
| `POST` | `/api/v1/sequential/execute` | Run OmniParser → Planner → Executor loop |
| `POST` | `/api/v1/screen/parse` | Parse a screenshot with OmniParser |

---

## Quick Start (both services together)

Open two terminals from the project root:

**Terminal 1 — backend:**
```bash
uvicorn app.backend.backend:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — frontend:**
```bash
cd app/frontend && npm install && npm run dev
```

Then open `http://localhost:5173` in your browser.
