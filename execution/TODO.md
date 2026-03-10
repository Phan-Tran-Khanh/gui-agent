# Execution Module - Implementation Instructions

## Overview
The Execution module handles the sub-goal execution loop:
1. **Skill Retrieval**: Get available skills/actions for current state
2. **Executor**: Execute the next action decided by MLLM
3. **Sub-goal Loop Manager**: Orchestrate execution of current sub-goal

## Architecture

```
Sub-goal
    ↓
SkillManager (retrieve available skills/actions)
    ↓
Executor (get visual state, integrate with grounder)
    ↓
Execute Action via ADB
    ↓
Screenshot Capture
    ↓
Reflection Module (verify sub-goal, detect stalls, replan)
```

## Components

### 1. skill_manager.py
Manages available skills and action space.

**Key Responsibilities:**
- Define action space (atomic and composite)
- Atomic skills: click (coords), type (text), scroll (direction)
- Composite skills: login, search, filter (optional)
- Filter available skills based on current GUI state
- Provide skill descriptions for MLLM decision-making

**TODO - Implementation:**
- [ ] Define Action/Skill data structure
- [ ] Define atomic actions (CLICK, TYPE, SCROLL, WAIT, BACK)
- [ ] Define composite actions (optional)
- [ ] Implement SkillManager class
- [ ] Implement get_available_actions() method
- [ ] Implement filter_actions_by_state() method
- [ ] Create action descriptions for MLLM prompts

### 2. executor.py
Responsible for executing actions on the mobile device.

**Key Responsibilities:**
- Accept action from MLLM via Grounder
- Execute action using ADB interface
- Capture screenshots after execution
- Track execution metadata
- Handle execution failures and retries

**TODO - Implementation:**
- [ ] Define Executor class
- [ ] Implement execute_action(action) method
- [ ] Integrate with ADB interface
- [ ] Implement screenshot capture after action
- [ ] Add retry logic for failed actions
- [ ] Add timing/delay between actions
- [ ] Implement logging of all executions

### 3. subgoal_executor.py
Orchestrates the execution of a single sub-goal.

**Key Responsibilities:**
- Manage the sub-goal execution loop
- Interact with SkillManager for action retrieval
- Call Executor to perform actions
- Integrate with Grounder for action decision-making
- Handle loop termination (success, failure, max steps)
- Pass execution results to Reflection module

**TODO - Implementation:**
- [ ] Define SubGoalExecutor class
- [ ] Implement execute_subgoal(subgoal) method
- [ ] Implement sub-goal execution loop
- [ ] Integrate with SkillManager
- [ ] Integrate with Executor
- [ ] Integrate with Grounder (external API)
- [ ] Implement loop termination logic
- [ ] Add step counter and max-steps check
- [ ] Log all sub-goal execution trace

## Data Structures

### Action
```python
{
    "action_type": str,  # CLICK, TYPE, SCROLL, WAIT, BACK
    "parameters": {
        "x": Optional[int],
        "y": Optional[int],
        "text": Optional[str],
        "direction": Optional[str]
    },
    "description": str
}
```

### ExecutionResult
```python
{
    "action": Action,
    "success": bool,
    "screenshot_before": bytes,
    "screenshot_after": bytes,
    "timestamp": str,
    "error": Optional[str]
}
```

## Integration Points

- **SkillManager**: Provides available actions
- **Executor**: Performs actual action execution
- **ADB Interface**: Android device interaction
- **Grounder**: External API for action grounding (subgoal -> action coordinates)
- **Vision Module**: GUI state understanding
- **Reflection Module**: Sub-goal verification and stall detection
