# MLLM Module - Implementation Instructions

## Overview
The MLLM module provides interfaces to the Google Gemini API and specialized agents.

Components:
1. **Gemini Client**: Low-level API interface
2. **Planner Agent**: Makes planning decisions (goal decomposition)
3. **Executor Agent**: Makes execution decisions (which action to take next)

## Architecture

```
GeminiClient (REST API interface)
    ↓
PlannerAgent (planning decisions)
ExecutorAgent (execution decisions)
```

## Components

### 1. gemini_client.py
Low-level interface to Google Gemini API.

**Key Responsibilities:**
- Handle REST API calls to Gemini
- Manage authentication via API key
- Send text and image to API
- Parse responses
- Handle errors and retries
- Rate limiting

**TODO - Implementation:**
- [ ] Define GeminiClient class
- [ ] Implement __init__ with API key from env
- [ ] Implement query_text(prompt) method
- [ ] Implement query_with_image(prompt, image_bytes) method
- [ ] Add error handling and retries
- [ ] Add rate limiting
- [ ] Add logging
- [ ] Add response caching (optional)

### 2. planner_agent.py
Specialized agent for planning decisions.

**Key Responsibilities:**
- Decompose user goal into sub-goals
- Use context and constraints
- Return structured sub-goal list
- Integrate with GeminiClient

**TODO - Implementation:**
- [ ] Define PlannerAgent class (wraps GeminiClient)
- [ ] Implement plan_goal(goal, context, constraints) method
- [ ] Create planning prompt template
- [ ] Parse sub-goals from response
- [ ] Add validation
- [ ] Add logging

### 3. executor_agent.py
Specialized agent for execution decisions (through Grounder).

**Key Responsibilities:**
- Decide next action given GUI state and sub-goal
- Integrate with GeminiClient
- Return action (which Grounder converts to coordinates)
- Provide reasoning

**TODO - Implementation:**
- [ ] Define ExecutorAgent class (wraps GeminiClient)
- [ ] Implement decide_action(visual_state, subgoal, available_actions) method
- [ ] Create execution prompt template
- [ ] Parse action from response
- [ ] Add logging

## Prompting Strategy

### Planning Prompt Template
```
Goal: [user goal]
Context from history: [past interactions]
Constraints: [app/instruction constraints]

Please decompose this goal into 3-5 sub-goals/milestones.
For each sub-goal, provide:
- Description
- Priority (order of execution)
- Estimated steps needed
- Success criteria

Format as JSON.
```

### Execution Prompt Template
```
Active Sub-goal: [current sub-goal]
Current GUI State: [captured elements, text, layout]
Available Actions: [CLICK, TYPE, SCROLL, BACK, WAIT]
Detected UI Elements: [list of elements]

What is the next action to accomplish this sub-goal?
Provide reasoning and the action with parameters.

Format: { "action": "...", "parameters": {...}, "reasoning": "..." }
```

## Integration Points

- **GeminiClient**: Core API wrapper
- **PlannerAgent**: Used by Planner for decomposition
- **ExecutorAgent**: Used by Grounder for action decisions
- **Configuration**: API key from environment or config
