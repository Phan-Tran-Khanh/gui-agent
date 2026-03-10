# Reflection Module - Implementation Instructions

## Overview
The Reflection module validates sub-goal progress and handles recovery:
1. **Stall Detection**: Detect when interaction is stalled (no visual change)
2. **Verification**: Verify if sub-goal is accomplished
3. **Replan Manager**: Request sub-goal expansion or full plan regeneration

Reference: https://arxiv.org/abs/2503.17709, https://arxiv.org/abs/2406.08451

## Architecture

```
Execution Results + Screenshots
    ↓
StallDetector (visual change detection)
    ↓
Verification (screen question answering)
    ↓
ReplanManager (decide recovery strategy)
    ↓
Continue/Replan/Fail Decision
```

## Components

### 1. stall_detector.py
Detects when agent interaction is stalled.

**Key Responsibilities:**
- Compare consecutive screenshots
- Detect visual changes
- Track action effectiveness
- Identify stalled patterns

Reference: https://arxiv.org/abs/2503.17709

**TODO - Implementation:**
- [ ] Define StallDetector class
- [ ] Implement detect_stall(prev_screenshot, curr_screenshot) -> bool
- [ ] Implement visual_diff(image1, image2) -> similarity_score
- [ ] Implement stall_pattern_detection()
- [ ] Add configurable stall threshold
- [ ] Add stall history tracking
- [ ] Add logging

### 2. verification.py
Verifies if sub-goal is accomplished.

**Key Responsibilities:**
- Accept sub-goal and current GUI state
- Use MLLM for screen question answering
- Determine if sub-goal success criteria met
- Return verification result

**TODO - Implementation:**
- [ ] Define VerificationResult dataclass
- [ ] Implement Verifier class
- [ ] Implement verify_subgoal(subgoal, gui_state) -> VerificationResult
- [ ] Integrate with Gemini for screen QA
- [ ] Implement success criteria checking
- [ ] Add confidence scoring
- [ ] Add logging

### 3. reflector.py
Main reflection orchestrator.

**Key Responsibilities:**
- Coordinate stall detection and verification
- Decide on recovery action
- Integrate with replan manager
- Provide reflection results

**TODO - Implementation:**
- [ ] Define ReflectionResult dataclass
- [ ] Implement Reflector class
- [ ] Implement reflect(execution_result, subgoal, gui_state) -> ReflectionResult
- [ ] Integrate StallDetector and Verifier
- [ ] Implement decision logic for recovery
- [ ] Add logging

### 4. replan_manager.py
Manages plan recovery strategies.

**Key Responsibilities:**
- Sub-goal expansion (add intermediate sub-goals)
- Full plan regeneration
- Decide which strategy to use
- Track replan history

**TODO - Implementation:**
- [ ] Define ReplanManager class
- [ ] Implement expand_subgoal() method
- [ ] Implement regenerate_plan() method
- [ ] Implement decide_replan_strategy() method
- [ ] Add replan attempt limiting
- [ ] Add logging

## Data Structures

### StallResult
```python
{
    "is_stalled": bool,
    "visual_similarity": float,
    "stall_consecutive_count": int,
    "reason": str
}
```

### VerificationResult
```python
{
    "is_accomplished": bool,
    "confidence": float,
    "reasoning": str,
    "unmet_criteria": List[str]
}
```

### ReflectionResult
```python
{
    "stall_detected": bool,
    "is_accomplished": bool,
    "recovery_action": str,  # continue/replan/expand/fail
    "replan_request": Optional[ReplanRequest]
}
```

## Integration Points

- **Execution**: Receives ExecutionResult from SubGoalExecutor
- **Vision**: Uses GUIState for verification
- **MLLM**: Uses Gemini for screen QA verification
- **Planning**: Requests replan when needed
