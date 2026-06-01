
# Example Pipeline from ASSIST-GUI Paper (Mobile Screenshot Scenario)

This document demonstrates how the proposed method in the ASSIST-GUI paper works using a **mobile screenshot automation example**.

---

# 1. Scenario

## Screenshot (Input)
Android **Settings screen**:

```
Settings
 ├ Network & Internet
 ├ Connected devices
 ├ Apps
 ├ Privacy
 ├ Location
 ├ Security
 └ Ads
```

## User Prompt
```
Please turn off ad personalization on my phone.
```

The agent receives:

```
Input:
- User query
- Screenshot of mobile UI
```

Goal:

```
Settings → Privacy → Ads → Disable ad personalization
```

---

# 2. Step 1 — Planner

The **Planner converts the query into milestones and subtasks.**

## Planner Input

```
User Query:
"Please turn off ad personalization on my phone."

Instruction reference:
1. Open Settings
2. Tap Privacy
3. Tap Ads
4. Turn off "Ad Personalization"
```

## Planner Output

```
Milestone 1: Open Privacy settings
  Subtask 1.1: Locate "Privacy" in settings menu
  Subtask 1.2: Tap "Privacy"

Milestone 2: Open Ads settings
  Subtask 2.1: Locate "Ads"
  Subtask 2.2: Tap "Ads"

Milestone 3: Disable Ad Personalization
  Subtask 3.1: Locate toggle "Ad Personalization"
  Subtask 3.2: Tap toggle to disable
```

---

# 3. Step 2 — GUI Parser

The **GUI Parser converts screenshot → structured GUI representation.**

## Input

```
Screenshot: Android Settings screen
```

## Output

```
Panel: Settings Menu

elements:
Network & Internet  [120,210]
Connected devices   [120,260]
Apps                [120,310]
Privacy             [120,360]
Location            [120,410]
Security            [120,460]
Ads                 [120,510]
```

The representation includes:

- text
- UI element
- coordinates

---

# 4. Step 3 — Actor (Generate Action)

The **Actor generates executable actions.**

## Actor Input

```
Milestone:
Open Privacy settings

Subtask:
Tap "Privacy"

GUI:
Privacy [120,360]
Location [120,410]
Security [120,460]

Previous action: none
```

## Actor Output

```
click(120,360)
```

---

# 5. Step 4 — Environment Execution

System executes:

```
click(120,360)
```

Result:

```
Privacy settings screen opens.
```

A **new screenshot** is captured.

---

# 6. Step 5 — Critic

The **Critic evaluates whether the action succeeded.**

## Critic Input

```
Subtask:
Tap Privacy

Action:
click(120,360)

Screenshot before:
Settings menu

Screenshot after:
Privacy menu opened
```

## Critic Output

```
{
 "Success": true,
 "Finished": true,
 "Reason": "Privacy settings screen opened successfully."
}
```

---

# 7. Next Iteration

The agent moves to the next subtask.

---

# 8. Example Next Step

## GUI Parser Output

```
Panel: Privacy Settings

elements:
Permissions Manager   [120,200]
Notifications         [120,250]
Ads                   [120,300]
```

## Actor Input

```
Subtask:
Tap "Ads"

GUI:
Ads [120,300]
```

## Actor Output

```
click(120,300)
```

---

# 9. Final Step

## GUI Parser Output

```
Panel: Ads Settings

elements:
Ad Personalization Toggle  [600,350]
Toggle state: ON
```

## Actor Output

```
click(600,350)
```

---

# 10. Critic Output

```
{
 "Success": true,
 "Finished": true,
 "Reason": "Ad personalization successfully turned off."
}
```

Task completed.

---

# 11. Full Pipeline Summary

| Step | Module | Output |
|-----|------|------|
| 1 | Planner | task → milestones + subtasks |
| 2 | GUI Parser | screenshot → UI elements |
| 3 | Actor | generate actions |
| 4 | Environment | execute action |
| 5 | Critic | verify success |
| Loop | Actor + Critic | continue until finished |

---

# Pipeline Overview

```
User Query
     ↓
Planner
     ↓
Milestones + Subtasks
     ↓
GUI Parser
     ↓
Structured UI Elements
     ↓
Actor
     ↓
Action (click / type)
     ↓
Environment executes
     ↓
Critic evaluates
     ↓
Loop until task completed
```
