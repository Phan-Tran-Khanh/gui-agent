<!-- filepath: d:\DATA\master\gui-agent\IMPLEMENTATION_PROGRESS.md -->
# GUI Agent Implementation Progress

**Last Updated:** March 25, 2026  
**Current Status:** In Development - Sequential Executor Phase

---

## 📋 Overview

This document tracks the implementation progress of the GUI Agent system based on the **APPROACH.md** and **ASSIST-GUI pipeline**.

The system is currently focusing on the **Sequential Executor** (`/api/v1/sequential/execute`) endpoint for real device automation.

---

## 🎯 Reference Architecture

Based on **APPROACH.md**, the complete pipeline should have:

```
1. Planning Phase
   ├─ Context Retrieval
   ├─ Constraint Retrieval
   └─ Task Decomposition → Milestones + Sub-goals

2. Sub-goal Execution Loop
   ├─ Skill Retrieval (Action Space)
   ├─ GUI State Compilation
   │  ├─ Vision Processing (OmniParser)
   │  │  ├─ Visual Highlighting (YOLOv8 + Set-of-Mask)
   │  │  ├─ Masking (Irrelevant Components)
   │  │  └─ Cropping/Zoom (Optional)
   │  └─ Language Context
   │     ├─ Past Sub-goals
   │     ├─ Active Sub-goal
   │     └─ Semantic Reasoning
   ├─ Execute Next Action
   └─ Reflection Phase
      ├─ Stall Detection
      ├─ Sub-goal Verification
      └─ Re-planning (if needed)
```

---

## ✅ Completed Components

### Backend Services

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| **Assistant Agent** | `mllm/assistant_agent.py` | ✅ Done | LiteLLM wrapper for Gemini, OpenAI, Claude |
| **Planner Agent** | `mllm/planner_agent.py` | ✅ Done | Decomposes goal → milestones + subtasks |
| **Planner** | `planning/planner.py` | ✅ Done | Orchestrates planning with context + constraints |
| **Context Retriever** | `planning/context_retriever.py` | ✅ Done | Retrieves history context |
| **Constraint Retriever** | `planning/constraint_retriever.py` | ✅ Done | Retrieves constraints by app/instruction category |
| **Goal Completion Checker** | `web/goal_completion_checker.py` | ✅ Done | Verifies goal achievement using AssistantAgent |
| **OmniParser Client** | `web/omniparser_client.py` | ✅ Done | HTTP client for OmniParser GUI parsing |
| **Sequential Executor** | `web/sequential_executor.py` | ✅ Done | Main loop: OmniParser → Planner → Executor |
| **Sequential Runner** | `web/sequential_runner.py` | ✅ Done | Event emitter for publishing to frontend |
| **Device Config** | `config/device_config.py` | ✅ Done | Centralized device specs (width, height) |
| **ADB Integration** | `adb/adb.py` | ✅ Done | Android device automation |
| **Event Emitter** | `web/event_emitter.py` | ✅ Done | Real-time event publishing |
| **Task Manager** | `web/task_manager.py` | ✅ Done | Track task state and events |
| **Backend API** | `web/backend.py` | ✅ Done | FastAPI endpoints for task/sequential execution |

### Frontend Services

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| **Sequential Executor Service** | `frontend/src/services/sequentialExecutor.ts` | ✅ Done | Calls `/api/v1/sequential/execute` API |
| **Screenshot Service** | `frontend/src/services/screenshotService.ts` | ✅ Done | Maps step numbers to screenshot URLs |
| **WebSocket Client** | `frontend/src/services/wsClient.ts` | ✅ Done | Connects to `/ws/task/{task_id}` |
| **Event Reducer** | `frontend/src/eventReducer.ts` | ✅ Done | Processes events + extracts screenshot URLs |
| **App.tsx Integration** | `frontend/src/App.tsx` | ✅ Done | `startSequentialTask()` function |
| **Observability Panel** | `frontend/src/components/ObservabilityPanel.tsx` | ✅ Done | Displays latest screenshot + metadata |

### Utilities

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| **Box Annotator** | `utils/box_annotator.py` | ✅ Done | Draws bounding boxes on screenshots |
| **Logger** | `utils/logger.py` | ✅ Done | Structured logging |

---

## 🔄 Current Implementation Details

### Sequential Executor Flow (`/api/v1/sequential/execute`)

```
1. Frontend calls API with:
   - goal: "Open GitHub app"
   - device_id: "144321556E009492"
   - task_id: "task-1774028105483"  ← Optional for event emission

2. Backend:
   ├─ PHASE 1: Capture screenshot from device (ADB)
   ├─ PHASE 2: Parse with OmniParser → element_index + bbox
   ├─ PHASE 3: Annotate screenshot with bounding boxes
   ├─ PHASE 4: Check goal achieved (AssistantAgent + screenshot + elements)
   │           ├─ If YES → emit task_completed, stop
   │           └─ If NO → continue
   ├─ PHASE 5: Send to Planner with parsed_elements
   │           ├─ Planner receives element_index reference list
   │           ├─ LLM selects element_index to interact with
   │           └─ Coordinates extracted from parsed_elements bbox
   ├─ PHASE 6: Execute action via ADB
   │           └─ Convert subtask → ADB command → execute
   └─ PHASE 7: Wait 3-5 seconds → capture next screenshot → Loop

3. Event Emission (if task_id provided):
   - task_started
   - gui_state_updated (elements detected)
   - plan_generated (milestones created)
   - action_decided (LLM chose element)
   - action_executed (ADB action completed)
   - task_completed (goal achieved)
   - task_failed (error occurred)

4. Frontend:
   ├─ Creates task via /api/v1/task/start
   ├─ Calls /api/v1/sequential/execute with task_id
   ├─ Connects WebSocket to /ws/task/{task_id}
   └─ Receives real-time events + renders screenshots
```

### Element Coordinate Grounding

**Before (❌ Not implemented):**
```
Planner → LLM generates coordinates → 
  Problem: LLM might hallucinate coordinates
```

**After (✅ Current Implementation):**
```
OmniParser detects elements → returns [element_index, bbox]
                ↓
Planner receives reference list:
  [0] icon GitHub | bbox=[0.30, 0.09, 0.48, 0.21] | interactive:✓
  [1] icon Reddit | bbox=[0.03, 0.47, 0.26, 0.57] | interactive:✓
  ...
                ↓
LLM selects: element_index=0 (GitHub)
                ↓
PlannerAgent maps: element_index → extracts bbox from parsed_elements
                ↓
Convert bbox (normalized 0-1) → pixel coordinates:
  center_x = (x_min + x_max) / 2 * screen_width
  center_y = (y_min + y_max) / 2 * screen_height
  → [pixel_x, pixel_y] for ADB click
```

### Screenshot Rendering on Frontend

```
Backend emits event:
{
  "type": "action_executed",
  "stage": "executing_subgoal",
  "subgoalIndex": 1,
  "metadata": {"step": 1, ...}
}
                ↓
Frontend eventReducer:
  - Extracts step number from metadata
  - Constructs URL: /output/step_1_raw.png
  - Stores as latestScreenshot
                ↓
ObservabilityPanel renders:
  <img src="http://localhost:8000/output/step_1_raw.png" />
```

---

## ⚠️ Known Issues & Todos

### Issues

| Issue | Impact | Status |
|-------|--------|--------|
| WebSocket 403 error on cold start | Frontend cannot receive events initially | 🔴 **NEEDS FIX** |
| Task creation before sequential/execute | Need to create task first, then call sequential execute | 🟡 **WORKAROUND APPLIED** |
| Screenshot serving from output folder | Need to set up static file serving in FastAPI | 🟡 **PARTIAL** |

### Missing / Not Implemented

#### Phase 1: Planning (Mostly Done ✅)

- [x] Context Retrieval
- [x] Constraint Retrieval
- [x] Task Decomposition → Milestones
- [x] Grounded Subtask Generation (with element_index)
- [ ] **Sub-goal Expansion** *(if initial plan fails)*

#### Phase 2: Vision Processing (Partial ⚠️)

- [x] OmniParser Integration (Screenshot parsing)
- [x] Element Detection (YOLOv8 via OmniParser)
- [x] Bounding Box Annotation
- [ ] **Masking Irrelevant Components** *(Optional - Gaussian/Norm Distribution)*
- [ ] **Cropping/Zoom** *(Optional - MLLM-proposed regions)*

#### Phase 3: Execution (Done ✅)

- [x] Action Space Definition (click, type, scroll, etc.)
- [x] ADB Integration
- [x] Action Execution
- [ ] **Composite Skills** *(login, search, filter)* - Optional

#### Phase 4: Reflection (Minimal ⚠️)

- [x] Goal Completion Check (using AssistantAgent)
- [ ] **Stall Detection** *(Visual change detection algorithm)*
- [ ] **Screen QA / Sub-goal Verification** *(SoM prompting)*
- [ ] **Smart Re-planning** *(Expansion vs Full Regeneration)*

#### Frontend Integration (In Progress 🔄)

- [x] API Integration
- [x] WebSocket Connection
- [x] Event Handling
- [x] Screenshot Rendering
- [ ] **Static file serving** *(output folder)*
- [ ] **Error handling & retry logic**
- [ ] **Progress visualization** *(step counter, timeline)*

---

## 📊 Step-by-Step Breakdown for Sequential Executor

### What Happens When Frontend Calls `/sequential/execute`

**Step 1: Task Creation (Optional but Recommended)**
```bash
POST /api/v1/task/start
{
  "goal": "Open GitHub app"
}
→ Returns: task_id = "task-1234567890"
```

**Step 2: Start Sequential Execution**
```bash
POST /api/v1/sequential/execute
{
  "goal": "Open GitHub app",
  "device_id": "144321556E009492",
  "task_id": "task-1234567890",
  "max_steps": 15
}
→ Returns: final result after execution completes
  (This is async - events published via WebSocket)
```

**Step 3: Connect WebSocket for Real-time Events**
```javascript
ws = new WebSocket("ws://localhost:8000/ws/task/task-1234567890")

ws.onmessage = (event) => {
  // Receive events like:
  // { type: "gui_state_updated", subgoalIndex: 1, ... }
  // { type: "action_executed", subgoalIndex: 1, ... }
  // { type: "task_completed", ... }
}
```

**Step 4: Backend Processing (Per Iteration)**

```
Iteration 1:
├─ Capture screenshot from device
├─ OmniParser: detect 41 elements → element_index 0-40
├─ Annotate: draw bounding boxes on screenshot
├─ Goal Check: "Is GitHub open?" → NO
├─ Planner: decompose goal → select element_index 8 (GitHub icon)
├─ Executor: click on pixel coordinates derived from element_index 8
├─ Wait 3 seconds
└─ Emit events to frontend via WebSocket

Iteration 2:
├─ Capture new screenshot
├─ OmniParser: detect elements in new state
├─ Annotate screenshot
├─ Goal Check: "Is GitHub open?" → YES ✅
├─ Emit: task_completed
└─ Stop execution
```

**Step 5: Frontend Screenshot Rendering**

```
Receive event: { type: "action_executed", metadata: { step: 1 } }
         ↓
Extract step number: 1
         ↓
Construct URL: "http://localhost:8000/output/step_1_raw.png"
         ↓
Render: <img src={url} />
```

---

## 🚀 Next Steps / Roadmap

### Immediate (This Week)

- [ ] Fix WebSocket 403 error
  - [ ] Ensure task is created before WebSocket connection
  - [ ] Check if task_id is properly registered in task_manager
  
- [ ] Set up static file serving for `/output` folder
  - [ ] Configure FastAPI to serve files from `output/` directory
  - [ ] Test screenshot URLs work in browser
  
- [ ] Test end-to-end sequential execution
  - [ ] Manual test: call API → check events → see screenshots
  - [ ] Verify coordinates are correctly extracted and used

### Short Term (Next 2 Weeks)

- [ ] Add **Stall Detection** to reflection phase
  - [ ] Visual change detection algorithm
  - [ ] Timeout handling for stuck interactions

- [ ] Implement **Screen QA** for sub-goal verification
  - [ ] Ask LLM: "Is the goal achieved?" instead of simple text matching
  - [ ] Use Set-of-Mask (SoM) prompting for better grounding

- [ ] Add **Smart Re-planning**
  - [ ] Detect failure patterns
  - [ ] Decide: expand sub-goal vs regenerate full plan

### Medium Term (Next Month)

- [ ] **Composite Skills** implementation
  - [ ] Pre-trained skills: login, search, filter
  - [ ] Order-free action composition

- [ ] **Masking & Cropping** vision improvements
  - [ ] Mask irrelevant UI components
  - [ ] Crop candidate regions proposed by MLLM

- [ ] **Long-term Memory**
  - [ ] Store successful action sequences
  - [ ] Retrieve similar tasks for faster planning

---

## 📝 Configuration

### Device Configuration (Centralized)

```python
# config/device_config.py
DeviceConfig.set_device_spec(width=1080, height=2400, dpi=420)

# Access from anywhere:
width = DeviceConfig.get_width()   # → 1080
height = DeviceConfig.get_height() # → 2400
```

### Environment Variables

```bash
# .env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_BASE_URL=ws://localhost:8000/ws
PARSE_API_BASE_URL=http://localhost:8001  # OmniParser endpoint
MODEL=gemini-2.0-flash
API_KEY=your-api-key-here
```

---

## 🧪 Testing Commands

### Test OmniParser Connection

```bash
python -m web.backend
# Then: curl http://localhost:8000/api/v1/screen/parse
```

### Test Sequential Execution

```bash
# Create task first
curl -X POST http://localhost:8000/api/v1/task/start \
  -H "Content-Type: application/json" \
  -d '{"goal":"Open GitHub app"}'
# → Returns: {"task_id": "task-xxx"}

# Then start sequential execution
curl -X POST http://localhost:8000/api/v1/sequential/execute \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Open GitHub app",
    "device_id": "144321556E009492",
    "task_id": "task-xxx",
    "max_steps": 15
  }'
```

### Test Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
# Submit task → Watch events stream in → See screenshots render
```

---

## 📚 Key Files to Review

| File | Purpose |
|------|---------|
| `APPROACH.md` | Full system architecture overview |
| `assist_gui_example_pipeline.md` | Example walkthrough of the pipeline |
| `web/sequential_executor.py` | Main execution loop implementation |
| `mllm/planner_agent.py` | Planning logic + element grounding |
| `config/device_config.py` | Centralized device specs |
| `frontend/src/App.tsx` | Frontend integration entry point |

---

## 🎓 Learning Resources

- **ASSIST-GUI Paper**: https://arxiv.org/abs/2312.13108
- **OmniParser**: https://github.com/microsoft/OmniParser
- **Set-of-Mask (SoM)**: https://arxiv.org/abs/2412.10342

---

**Status Summary:**
- ✅ **Core Backend:** ~95% Complete
- ✅ **Frontend Integration:** ~80% Complete
- ⚠️ **Vision Processing:** ~50% Complete (OmniParser done, masking/cropping optional)
- ⚠️ **Reflection Phase:** ~30% Complete (basic goal check done, stall detection pending)
- 🔴 **Known Issues:** WebSocket 403, static file serving

**Blockers:**
1. WebSocket connection failing with 403
2. Output folder files not being served by FastAPI
