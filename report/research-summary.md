# Research Summary: GUI Agent for Mobile Navigation

## Goal & Motivation
- Build a mobile GUI agent that can autonomously navigate apps using an MLLM.
- Treat the MLLM as a black box and ground decisions in screenshot-based perception to reduce hallucinated actions.

## System Overview
- Four-phase pipeline: Planning, Sub-goal Execution Loop, Reflection, Completion.
- Planning: retrieve context/history, retrieve constraints by app/instruction category, decompose into milestones and sub-goals.
- Execution loop: retrieve action space, compile GUI state (vision + language), decide next action, execute, and reflect.
- Reflection: detect stalls, verify sub-goal completion, and replan (expand sub-goal or regenerate plan).

## Action Space & Decision Grounding
- Unified action space with atomic skills (click, type, scroll) and optional composite skills (login, search, filter).
- Key grounding method: OmniParser returns element indices and bounding boxes; the planner selects an element index and converts bbox to pixel coordinates for ADB actions.
- This removes LLM coordinate hallucination and ties actions to real UI components.

## Vision & GUI State Compilation
- Vision pipeline: screenshot to OmniParser to UI element detection (YOLOv8 + Set-of-Mask).
- Optional enhancements: masking irrelevant components and cropping/zooming for focus.
- Language context: past sub-goals, active sub-goal, reasoning summary, available action space, optional next-action prediction.

## Execution & Backend Flow
- Sequential executor loop: capture screenshot, parse elements, annotate, goal check, plan action, execute via ADB, wait, repeat.
- Event-driven backend emits task_started, gui_state_updated, action_decided, action_executed, task_completed.

## Frontend & Observability
- WebSocket streaming of events for real-time UI updates.
- Observability panel renders latest screenshots by mapping step numbers to output images.

## Implementation Status (from docs)
- Backend core complete: planner, executor, OmniParser client, ADB integration, task manager, event emitter, API.
- Frontend integration mostly complete: service layer, event reducer, observability panel.
- Known issues: WebSocket 403 on cold start, static file serving for output screenshots, missing reflection features.

## Current Gaps / Future Work
- Reflection phase: stall detection, screen QA for sub-goal verification, smart replanning.
- Vision improvements: masking and cropping.
- Composite skills and long-term memory for reuse and adaptation.

## Evaluation Ideas
- Success rate on app navigation tasks.
- Compare grounded element selection vs. coordinate hallucination.
- Latency per step, steps to completion, and failure recovery rate.
- Qualitative analysis of stall detection and replanning benefits.
