# GUI Agent - Mobile Navigation with MLLM

A mobile GUI agent system that uses Multi-Modal Large Language Models (MLLM) for autonomous navigation and task execution on Android devices.

## Overview

This project implements a complete GUI agent framework that follows this workflow:

1. **Planning Phase** - Decompose user goals into sub-goals
2. **Execution Loop** - For each sub-goal, execute actions and check progress
3. **Reflection** - Detect stalled interactions and verify goal completion

## Project Structure

```
gui-agent/
├── main.py                          # CLI entry point
├── config/
│   ├── __init__.py
│   └── config.py                    # Configuration management
├── planning/
│   ├── __init__.py
│   ├── TODO.md                      # Planning module instructions
│   ├── planner.py                   # Task decomposition
│   ├── context_retriever.py         # Retrieve history/context
│   └── constraint_retriever.py      # Retrieve app/instruction constraints
├── execution/
│   ├── __init__.py
│   ├── TODO.md                      # Execution module instructions
│   ├── executor.py                  # Action executor
│   ├── skill_manager.py             # Manage action space
│   └── subgoal_executor.py          # Sub-goal execution loop
├── vision/
│   ├── __init__.py
│   ├── TODO.md                      # Vision module instructions
│   ├── gui_state_compiler.py        # Compile GUI state
│   ├── visual_highlighting.py       # YOLOv8 element detection
│   ├── masking.py                   # Gaussian/Norm masking
│   └── cropping.py                  # Region cropping/zoom
├── reflection/
│   ├── __init__.py
│   ├── TODO.md                      # Reflection module instructions
│   ├── reflector.py                 # Main reflection orchestrator
│   ├── stall_detector.py            # Detect stalled interaction
│   ├── verification.py              # Verify sub-goal completion
│   └── replan_manager.py            # Handle plan recovery
├── mllm/
│   ├── __init__.py
│   ├── TODO.md                      # MLLM module instructions
│   ├── gemini_client.py             # Google Gemini API interface
│   ├── planner_agent.py             # Planning agent
│   └── executor_agent.py            # Execution decision agent
├── adb/
│   ├── __init__.py
│   ├── TODO.md                      # ADB module instructions
│   └── adb_interface.py             # Android Debug Bridge interface
├── grounder/
│   ├── __init__.py
│   ├── TODO.md                      # Grounder module instructions
│   └── ui_grounder.py               # UI element grounding API
├── utils/
│   ├── __init__.py
│   ├── logger.py                    # Logging utility
│   └── constants.py                 # Shared constants
└── README.md                        # This file
```

## Key Modules

### Planning Module
- **planner.py**: Decomposes user goals into sub-goals using Gemini
- **context_retriever.py**: Retrieves interaction history and long-term memory
- **constraint_retriever.py**: Retrieves app/instruction specific constraints

### Execution Module
- **subgoal_executor.py**: Orchestrates the execution loop for each sub-goal
- **executor.py**: Executes individual actions via ADB on the device
- **skill_manager.py**: Manages available actions (CLICK, TYPE, SCROLL, etc.)

### Vision Module
- **gui_state_compiler.py**: Compiles complete GUI state from screenshots
- **visual_highlighting.py**: Uses YOLOv8 to detect UI elements
- **masking.py**: Masks sensitive/irrelevant regions (Gaussian or Norm-based)
- **cropping.py**: Crops and zooms into specific UI regions

### Reflection Module
- **reflector.py**: Main reflection orchestrator
- **stall_detector.py**: Detects when interaction is stalled using visual change detection
- **verification.py**: Verifies sub-goal completion using screen QA
- **replan_manager.py**: Handles plan recovery (expansion or regeneration)

### MLLM Module
- **gemini_client.py**: Low-level interface to Google Gemini REST API
- **planner_agent.py**: Specialized agent for planning decisions
- **executor_agent.py**: Specialized agent for execution decisions

### ADB Module
- **adb_interface.py**: Interface to Android Debug Bridge for device control

### Grounder Module
- **ui_grounder.py**: Converts MLLM action decisions to precise screen coordinates via external API

## CLI Usage

```bash
python main.py --goal "Find and open settings" \
               --app_category shopping \
               --instruction_category navigation \
               --device-id emulator-5554 \
               --enable-highlighting \
               --enable-masking \
               --output_dir ./outputs \
               --debug
```

## Web Frontend + Streaming Backend

The repository now includes a web backend (`web/`) that exposes task APIs and
websocket event streaming compatible with the frontend in `frontend/`.

### 1) Install backend dependencies

```bash
pip install -r requirements.txt
```

### 2) Run backend server

```bash
uvicorn web.backend:app --host 0.0.0.0 --port 8000 --reload
```

### 3) Run frontend

```bash
cd frontend
npm install
npm run dev
```

### API Contract

- `POST /api/v1/task/start` with JSON body `{ "goal": "..." }`
- `GET /api/v1/task/{task_id}` for snapshot + replayable events
- `POST /api/v1/task/{task_id}/cancel` to stop run
- `WS /ws/task/{task_id}` for live event streaming

### Current backend behavior

The web backend now routes runs through lightweight module implementations:

- `planning/planner.py` for heuristic sub-goal decomposition
- `execution/subgoal_executor.py` for deterministic action simulation
- `reflection/reflector.py` for accomplishment/recovery decisions

This produces stage-aligned events across planning -> executing_subgoal ->
reflecting -> completed, while keeping interfaces compatible with future
device-integrated implementations.

### CLI Parameters

- `--goal` (required): User goal/instruction for the agent
- `--app_category`: Type of app (social, shopping, navigation, etc.)
- `--instruction_category`: Type of instruction (navigation, data_entry, search, etc.)
- `--vision_enhancement`: Enable vision preprocessing (default: True)
- `--enable-highlighting`: Enable YOLOv8 UI element detection
- `--enable-masking`: Enable Gaussian/Norm masking
- `--enable-cropping`: Enable region cropping
- `--device-id`: Android device ID for ADB connection
- `--output_dir`: Directory for logs and results (default: ./outputs)
- `--debug`: Enable debug logging
- `--max-steps`: Maximum execution steps (default: 50)

## Implementation Status

All modules are provided as **skeleton with TODO instructions**. Each file contains:

1. **Docstrings** explaining the component's purpose
2. **TODO comments** with detailed implementation instructions
3. **Class/method stubs** with signatures
4. **Data structure templates** for key classes

To implement:
- Read the TODO.md file for each module to understand the architecture
- Follow the TODO instructions in each Python file
- Implement one module at a time
- All modules share a common logging approach via `utils/logger.py`

## Configuration

Environment variables required:
- `GEMINI_API_KEY`: Google Gemini API key for MLLM
- `ADB_PATH`: Path to adb executable (optional, defaults to 'adb')

## Dependencies

(To be added in requirements.txt after implementation)
- google-generativeai (or requests for REST API)
- opencv-python (vision processing)
- ultralytics (YOLOv8 model)
- Pillow (image processing)
- dataclasses (Python 3.7+)

## Workflow

```
User Goal
    ↓
[Planning Phase]
├─ Retrieve context/history
├─ Retrieve constraints
└─ Decompose into sub-goals
    ↓
[Sub-goal Execution Loop]
├─ Retrieve available skills
├─ Compile GUI state (vision + language context)
├─ Decide next action (ExecutorAgent)
├─ Ground action coordinates (UIGrounder)
├─ Execute action (ADB)
├─ Detect stalls (StallDetector)
├─ Verify progress (Verifier)
└─ Replan if needed (ReplanManager)
    ↓
[Reflection & Recovery]
├─ Check if sub-goal accomplished
├─ If failed, request replan
└─ Continue to next sub-goal
    ↓
Goal Completed
```

## References

- Planning: https://arxiv.org/abs/2312.13108
- Skill Management: https://arxiv.org/abs/2509.17328, https://arxiv.org/abs/2411.17465
- Visual Highlighting: https://arxiv.org/abs/2412.10342
- Masking: https://arxiv.org/abs/2507.03730
- Cropping: https://arxiv.org/abs/2505.00684
- Semantic Reasoning: https://arxiv.org/abs/2406.08451
- Stall Detection: https://arxiv.org/abs/2503.17709

## Notes

- All MLLM calls go through Google Gemini API
- Screenshots are processed with configurable vision enhancements
- The Grounder is an external API adapter for precise coordinate grounding
- Reflection uses both visual change detection and screen QA for verification
- Full plan regeneration is possible if sub-goals consistently fail

---

**This is a skeleton implementation with detailed TODO instructions. Start implementing from the Planning module, then Execution, then Vision, Reflection, MLLM, ADB, Grounder, and finally integrate components in main.py.**
