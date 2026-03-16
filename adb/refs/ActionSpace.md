# ADB Action Space Implementation

## Overview

This document defines the **ADB Action Space** used to control an Android device programmatically.

Each action represents a **single atomic interaction** that can be executed through **ADB shell commands**.

Design goals:

1. **Minimal information requirement** — each action receives only the parameters necessary for execution.
2. **Pure function interface** — actions are implemented as stateless functions.
3. **Direct ADB mapping** — each action maps directly to one or more `adb shell input` commands.
4. **Deterministic behavior** — actions do not maintain internal state.

---

# Action Execution Model

The system executes actions in the following order:

```
Model Output
      │
      ▼
Action JSON
      │
      ▼
Action Dispatcher
      │
      ▼
Pure Action Function
      │
      ▼
ADB Command Execution
```

---

# Coordinate System

All screen interactions use **pixel coordinates**.

```
(0,0) ──────────────► X
  │
  │
  │
  ▼
  Y
```

Where:

* `(0,0)` = top-left corner of the screen
* `x` increases → right
* `y` increases → downward

---

# Action Specification

Each action is represented as a **JSON object**.

Example:

```json
{
  "action_type": "click",
  "target": [540, 920]
}
```

---

# Action Dispatcher

The dispatcher routes action JSON to the correct function.

### Pseudocode

```
function execute_action(action):

    type = action["action_type"]

    if type == "click":
        click(action["target"])

    else if type == "long_press":
        long_press(action["target"])

    else if type == "swipe":
        swipe(action["start"], action["direction"], action["distance"])

    else if type == "input_text":
        input_text(action["text"])

    else if type == "drag":
        drag(action["start"], action["end"])

    else if type == "enter":
        press_enter()

    else if type == "navigate_back":
        navigate_back()

    else if type == "navigate_home":
        navigate_home()

    else if type == "navigate_recent":
        navigate_recent()

    else if type == "wait":
        wait_action()
```

---

# Action Implementations

---

# 1. Click

## Purpose

Simulates a **single tap** at a specific screen coordinate.

## Required Input

```
target = (x, y)
```

## Action Format

```json
{
  "action_type": "click",
  "target": [x, y]
}
```

---

## Execution Steps

1. Receive target coordinate `(x, y)`
2. Validate coordinate values
3. Execute ADB tap command

---

## Pseudocode

```
function click(target):

    x, y = target

    command = "adb shell input tap x y"

    execute(command)
```

---

# 2. Long Press

## Purpose

Simulates pressing and holding on a screen element.

ADB does not have a dedicated long press command, so it is simulated using **swipe with identical start/end points**.

---

## Required Input

```
target = (x, y)
```

---

## Action Format

```json
{
  "action_type": "long_press",
  "target": [x, y]
}
```

---

## Execution Steps

1. Receive `(x, y)`
2. Define press duration (e.g., 1000ms)
3. Execute swipe command with identical start/end

---

## Pseudocode

```
function long_press(target):

    x, y = target

    duration = 1000

    command = "adb shell input swipe x y x y duration"

    execute(command)
```

---

# 3. Swipe

## Purpose

Changes the current viewport by performing a swipe gesture.

---

## Required Input

```
start = (x, y)
direction = {up, down, left, right}
distance = {short, medium, long}
```

---

## Action Format

```json
{
  "action_type": "swipe",
  "start": [x, y],
  "direction": "up",
  "distance": "medium"
}
```

---

## Step 1 — Convert Distance

Distance is mapped to pixel movement.

Example mapping:

```
short  = 300
medium = 600
long   = 1000
```

---

## Step 2 — Compute End Coordinate

Example rules:

```
up    → (x, y - d)
down  → (x, y + d)
left  → (x - d, y)
right → (x + d, y)
```

---

## Pseudocode

```
function swipe(start, direction, distance):

    x, y = start

    d = map_distance(distance)

    if direction == "up":
        x2 = x
        y2 = y - d

    if direction == "down":
        x2 = x
        y2 = y + d

    if direction == "left":
        x2 = x - d
        y2 = y

    if direction == "right":
        x2 = x + d
        y2 = y

    command = "adb shell input swipe x y x2 y2"

    execute(command)
```

---

# 4. Input Text

## Purpose

Types text into the currently focused input field.

---

## Required Input

```
text
```

---

## Action Format

```json
{
  "action_type": "input_text",
  "text": "hello world"
}
```

---

## Execution Steps

1. Escape spaces
2. Send text through ADB

---

## Pseudocode

```
function input_text(text):

    text = escape_spaces(text)

    command = "adb shell input text text"

    execute(command)
```

---

# 5. Drag

## Purpose

Simulates dragging an object from one position to another.

---

## Required Input

```
start = (x1, y1)
end   = (x2, y2)
```

---

## Action Format

```json
{
  "action_type": "drag",
  "start": [x1, y1],
  "end": [x2, y2]
}
```

---

## Execution Steps

1. Receive start and end coordinates
2. Execute swipe command with duration

---

## Pseudocode

```
function drag(start, end):

    x1, y1 = start
    x2, y2 = end

    duration = 500

    command = "adb shell input swipe x1 y1 x2 y2 duration"

    execute(command)
```

---

# 6. Enter

## Purpose

Simulates pressing the **Enter key**.

---

## Action Format

```json
{
  "action_type": "enter"
}
```

---

## Pseudocode

```
function press_enter():

    command = "adb shell input keyevent 66"

    execute(command)
```

---

# 7. Navigate Back

## Purpose

Returns to the previous screen.

---

## Action Format

```json
{
  "action_type": "navigate_back"
}
```

---

## Pseudocode

```
function navigate_back():

    command = "adb shell input keyevent 4"

    execute(command)
```

---

# 8. Navigate Home

## Purpose

Returns to the Android home screen.

---

## Action Format

```json
{
  "action_type": "navigate_home"
}
```

---

## Pseudocode

```
function navigate_home():

    command = "adb shell input keyevent 3"

    execute(command)
```

---

# 9. Navigate Recent Apps

## Purpose

Opens the recent applications view.

---

## Action Format

```json
{
  "action_type": "navigate_recent"
}
```

---

## Pseudocode

```
function navigate_recent():

    command = "adb shell input keyevent 187"

    execute(command)
```

---

# 10. Wait

## Purpose

Pauses execution to allow the interface to update or content to load.

---

## Action Format

```json
{
  "action_type": "wait"
}
```

---

## Pseudocode

```
function wait_action():

    sleep(2 seconds)
```

---

# Action Validation

Before execution, the action must pass validation.

### Pseudocode

```
function validate_action(action):

    ensure "action_type" exists

    if action_type requires coordinates:
        ensure coordinates exist

    if action_type == "swipe":
        ensure direction and distance valid
```

---

# Design Principles

### 1. Minimal Parameter Design

Each action receives **only the parameters required for execution**.

Example:

```
click → (x, y)
drag → (x1, y1, x2, y2)
input_text → text
```

---

### 2. Stateless Execution

All functions are **pure functions**.

They:

* receive inputs
* execute commands
* return immediately

No persistent state is maintained.

---

### 3. Direct ADB Mapping

Every action directly corresponds to an ADB command.

Example mapping:

| Action     | ADB Command                      |
| ---------- | -------------------------------- |
| click      | `input tap`                      |
| long press | `input swipe x y x y duration`   |
| swipe      | `input swipe`                    |
| drag       | `input swipe start end duration` |
| enter      | `keyevent 66`                    |
| back       | `keyevent 4`                     |
| home       | `keyevent 3`                     |
| recent     | `keyevent 187`                   |