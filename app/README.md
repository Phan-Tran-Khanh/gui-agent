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
