"""
Step 1: Planner Implementation Guide

This document describes the implementation of Step 1 (Planner) from the ASSIST-GUI Pipeline.
"""

# ASSIST-GUI Pipeline - Step 1: Planner

## Overview

The **Planner** is the first step in the ASSIST-GUI pipeline. It takes a user's natural language goal and decomposes it into a structured set of sub-goals (milestones) that can be executed sequentially or in parallel.

### Key Responsibilities

1. **Goal Decomposition**: Convert user's natural language goal into actionable sub-goals
2. **Context Retrieval**: Gather relevant context from history and long-term memory
3. **Constraint Retrieval**: Fetch domain-specific constraints based on app/instruction categories
4. **Dependency Management**: Establish relationships between sub-goals
5. **Prioritization**: Determine execution order based on dependencies
6. **Validation**: Ensure sub-goals are valid, consistent, and achievable

## Architecture

### Class Hierarchy

```
Planner
├── _planner_agent: PlannerAgent (from MLLM module)
├── _assistant_agent: AssistantAgent (from MLLM module)
└── ContextRetriever & ConstraintRetriever (dependencies)

SubGoal (dataclass)
├── id: str
├── description: str
├── priority: int
├── estimated_steps: int
├── dependencies: List[str]
└── success_criteria: str
```

### Data Flow

```
User Goal (natural language)
    ↓
Planner.plan()
    ↓
[Retrieve Context] ← ContextRetriever
    ↓
[Retrieve Constraints] ← ConstraintRetriever
    ↓
[Call PlannerAgent] ← LLM (Gemini/OpenAI)
    ↓
[Parse Response] → List of SubGoal objects
    ↓
[Validate Sub-goals]
    - Check circular dependencies
    - Validate each sub-goal structure
    - Verify dependency references
    ↓
[Prioritize Sub-goals]
    - Topological sort by dependencies
    - Assign execution priority
    ↓
List[SubGoal] (ordered by execution)
```

## Usage Examples

### Basic Planning

```python
from planning import Planner
from config.config import Config

# Initialize
config = Config(model="gemini-3.1-flash-lite-preview", api_key="YOUR_API_KEY")
planner = Planner(config)

# Plan a goal
subgoals = planner.plan(
    user_goal="Turn off ad personalization on my phone",
    app_category="settings",
    instruction_category="toggle"
)

# Access results
for sg in subgoals:
    print(f"[{sg.priority}] {sg.description}")
    print(f"  Steps: {sg.estimated_steps}, Success: {sg.success_criteria}")
```

### Planning with Refinement

```python
subgoals = planner.plan_with_refinement(
    user_goal="Find and disable notifications",
    app_category="settings",
    instruction_category="navigation",
    refinement_query="Focus on privacy and notification settings"
)
```

## Key Features

### 1. Context Retrieval

The planner retrieves context to help the MLLM make better decisions:

- **History**: Past interactions from current session
- **Long-term Memory**: Learned patterns and successful past tasks
- **Session Metadata**: User ID, session ID

**TODO**: Integrate with persistent storage (database/cache) for actual history and memory.

Currently returns empty context structure - ready for database integration.

### 2. Constraint Retrieval

Constraints guide the LLM in planning by providing domain-specific knowledge:

#### App Categories
- `settings`: Hierarchical menu structure, drilling down into submenus
- `social`: Search, feed scrolling, profile access
- `shopping`: Product browsing, cart, checkout
- `navigation`: Location search, directions, maps

#### Instruction Categories
- `navigation`: Moving between screens, scrolling, hierarchy
- `data_entry`: Text input, form submission, validation
- `search`: Text input, results browsing, filtering
- `toggle`: Toggle switches, state changes, confirmation

**Easily Extensible**: Add more categories to `CONSTRAINT_DATABASE` in `constraint_retriever.py`

### 3. Dependency Management

Sub-goals can have dependencies on other sub-goals:

```python
SubGoal(
    id="sg_1",
    description="Open Settings app",
    dependencies=[],  # No dependencies (first step)
    priority=1
)

SubGoal(
    id="sg_2",
    description="Navigate to Privacy section",
    dependencies=["sg_1"],  # Must execute after sg_1
    priority=2
)
```

### 4. Validation

The planner validates sub-goals to ensure consistency:

- **Circular Dependency Detection**: Uses DFS-based cycle detection
- **Structure Validation**: Checks all required fields are present and valid
- **Reference Validation**: Ensures all dependencies reference existing sub-goals

Raises `ValueError` if validation fails.

### 5. Prioritization

Uses **topological sort** to order sub-goals:

- Executes dependencies first
- Independent sub-goals can run in parallel
- Assigns execution priority (1 = first)

## Integration with Other Components

### Next Steps in Pipeline

After planning, the decomposed sub-goals are fed to:

1. **Step 2 - GUI Parser** (vision module):
   - Parse current screenshot into structured GUI elements
   - Identify clickable elements and their positions

2. **Step 3 - Actor** (execution module):
   - Generate executable actions (click, type, scroll) for each sub-goal
   - Execute actions on mobile device

3. **Step 4 - Reflection** (reflection module):
   - Verify if sub-goal was accomplished
   - Detect stalled interactions
   - Trigger replanning if needed

### Dependencies

- **MLLM Module**:
  - `AssistantAgent`: Generic LLM interface
  - `PlannerAgent`: Specialized planning agent

- **Config Module**:
  - Provides API keys and model configuration

## TODO / Future Enhancements

### Short-term

1. **Context Storage**: Implement persistent storage for:
   - User interaction history
   - Long-term memory of past tasks
   - User preferences and patterns

2. **Constraint Expansion**: Add more app and instruction categories:
   - Music streaming, payments, messaging
   - Complex workflows, multi-step processes

3. **Caching**: Cache identical planning queries to avoid redundant LLM calls

### Medium-term

1. **Confidence Scoring**: Add confidence scores to sub-goals based on:
   - Historical success rates
   - Complexity estimation
   - Constraint satisfaction

2. **Parallel Planning**: Generate multiple plan alternatives and select the best

3. **Plan Optimization**: Merge similar sub-goals, reduce redundancy

### Long-term

1. **Learning from Feedback**: Update constraints based on success/failure
2. **User Preferences**: Tailor planning to individual user preferences
3. **Dynamic Replanning**: Adjust plan mid-execution based on feedback from reflection module

## Error Handling

The planner handles errors gracefully:

```python
try:
    subgoals = planner.plan(user_goal, app_category, instruction_category)
except ValueError as e:
    logger.error(f"Planning validation failed: {e}")
    # Handle invalid plan
except Exception as e:
    logger.error(f"Unexpected planning error: {e}")
    # Handle other errors
```

## Logging

The planner provides detailed logging at multiple levels:

- **INFO**: High-level planning progress
- **DEBUG**: Detailed steps (context, constraints, validation)

```bash
# Run with debug logging
python planning_demo.py --goal "..." --debug
```

Example output:
```
2026-03-15 14:23:45 | INFO     | Planner | Planner initialized
2026-03-15 14:23:45 | INFO     | Planner | Planning goal: Turn off ad personalization
2026-03-15 14:23:46 | INFO     | Planner | PlannerAgent generated 3 sub-goals
2026-03-15 14:23:46 | INFO     | Planner | ======== PLAN SUMMARY ========
2026-03-15 14:23:46 | INFO     | Planner | [1] sg_1: Open Privacy settings
...
```

## Files Modified/Created

1. **planning/planner.py**: Main Planner class and SubGoal dataclass
2. **planning/context_retriever.py**: Context retrieval for planning
3. **planning/constraint_retriever.py**: Constraint database and retrieval
4. **planning/__init__.py**: Module exports
5. **planning_demo.py**: Demo script showing how to use the Planner

## Testing

To test the planner implementation:

```bash
# Basic test
python planning_demo.py --goal "Turn off ad personalization" --app-category settings --instruction-category toggle

# With refinement
python planning_demo.py --goal "Find settings" --refinement "Focus on privacy" --debug

# Debug mode with detailed logging
python planning_demo.py --goal "..." --debug
```

## References

- ASSIST-GUI Paper: https://arxiv.org/abs/2312.13108
- Decomposition approach inspired by hierarchical task planning
- LLM integration via litellm library (supports multiple providers)
