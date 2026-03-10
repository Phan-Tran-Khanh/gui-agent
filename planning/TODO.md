# Planning Module - Implementation Instructions

## Overview
The Planning module handles the first phase of the GUI Agent workflow:
1. **Context Retrieval**: Retrieve history, past interactions, and optional long-term memory
2. **Constraint Retrieval**: Retrieve constraints based on app category and user instruction category
3. **Task Decomposition**: Decompose the user goal into sub-goals/milestones

## Architecture

```
User Goal
    ↓
ContextRetriever (get history, interactions, memory)
    ↓
ConstraintRetriever (get app/instruction constraints)
    ↓
Planner (decompose goal into sub-goals)
    ↓
Sub-goals List
```

## Components

### 1. context_retriever.py
Responsible for retrieving context information.

**Key Responsibilities:**
- Retrieve interaction history from previous sessions
- Retrieve long-term memory (optional learning from past tasks)
- Format context for use by planner

**TODO - Implementation:**
- [ ] Define ContextRetriever class
- [ ] Implement `retrieve_history(user_id)` method
- [ ] Implement `retrieve_long_term_memory(user_id)` method
- [ ] Implement context formatting with caching
- [ ] Add logging for retrieval operations

### 2. constraint_retriever.py
Responsible for retrieving constraints for planning.

**Key Responsibilities:**
- Retrieve constraints based on app category (e.g., social, shopping, navigation)
- Retrieve constraints based on user instruction category (e.g., navigation, data_entry, search)
- Provide constraints to planner for better decomposition

**TODO - Implementation:**
- [ ] Define ConstraintRetriever class
- [ ] Implement `get_app_constraints(app_category)` method
- [ ] Implement `get_instruction_constraints(instruction_category)` method
- [ ] Create constraint mapping/database
- [ ] Add cache for constraint retrieval
- [ ] Implement constraint merging/prioritization

### 3. planner.py
Main planner that decomposes user goal into sub-goals.

**Key Responsibilities:**
- Accept user goal
- Use context and constraints to generate decomposition
- Create sub-goals/milestones
- Prioritize sub-goals
- Integrate with MLLM (Gemini) for planning decisions

**TODO - Implementation:**
- [ ] Define Planner class with constructor taking config
- [ ] Implement `plan(user_goal, context, constraints)` method returning sub-goals
- [ ] Implement `decompose_goal_into_milestones()` method
- [ ] Add integration with PlannerAgent from MLLM module
- [ ] Implement sub-goal prioritization
- [ ] Add caching/memoization for identical goals
- [ ] Implement logging of planning process

## Data Structures

### Context
```python
{
    "interaction_history": List[Interaction],
    "long_term_memory": Optional[Memory],
    "session_id": str,
    "timestamp": str
}
```

### Constraints
```python
{
    "app_category": str,
    "instruction_category": str,
    "app_specific_constraints": List[str],
    "instruction_specific_constraints": List[str]
}
```

### SubGoal
```python
{
    "id": str,
    "description": str,
    "priority": int,
    "estimated_steps": int,
    "dependencies": List[str]
}
```

## Integration Points

- **MLLM**: Uses PlannerAgent for decomposition decisions
- **Configuration**: Reads app_category and instruction_category from config
- **Execution**: Passes sub-goals to execution module
