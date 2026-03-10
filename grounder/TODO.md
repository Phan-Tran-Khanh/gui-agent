# Grounder Module - Implementation Instructions

## Overview
The Grounder module interfaces with external UI grounding APIs.
It converts high-level MLLM action decisions into precise coordinates on the screen.

The Grounder is an adapter to an external API service that takes:
- Input: Sub-goal description, available UI elements, MLLM action suggestion
- Output: Precise coordinates for click/type/scroll actions

## Architecture

```
ExecutorAgent Decision (action_type, reasoning)
    ↓
GrounderAPI (external service)
    ↓
Precise Coordinates (x, y, text for type, etc.)
    ↓
Executor (performs action with coordinates)
```

## Components

### 1. ui_grounder.py
Interface to external UI grounding API.

**Key Responsibilities:**
- Accept action decision from ExecutorAgent
- Call external grounding API
- Convert decision to precise coordinates
- Handle API responses
- Cache grounding results

**TODO - Implementation:**
- [ ] Define UIGrounder class
- [ ] Implement __init__ with API endpoint and config
- [ ] Implement ground_action(action_decision, visual_state, available_elements) -> grounded_action
- [ ] Implement call_grounding_api() method
- [ ] Add error handling for API failures
- [ ] Add caching of groundings
- [ ] Add logging
- [ ] Handle cases where API can't ground action

## Data Structures

### ActionDecision (from ExecutorAgent)
```python
{
    "action_type": str,  # CLICK, TYPE, SCROLL, etc.
    "reasoning": str,
    "parameters": Optional[dict]
}
```

### GroundedAction (to Executor)
```python
{
    "action_type": str,
    "parameters": {
        "x": Optional[int],
        "y": Optional[int],
        "text": Optional[str],
        "direction": Optional[str],
        ...
    },
    "confidence": float,
    "grounding_source": str  # which element was grounded
}
```

## Integration Points

- **ExecutorAgent**: Receives action decisions
- **ExecutorModule**: Passes grounded actions with precise coordinates
- **Vision Module**: Uses detected elements for grounding
- **External API**: Calls endpoint for precise coordinate computation
