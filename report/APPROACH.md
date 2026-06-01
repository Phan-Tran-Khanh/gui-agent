# Proposed Approach

**Problem:** How to make the MLLM to focus and to make a correct decision on navigation

**Assumption:**

- MLLM is a blackbox - Focus on engineering complexity
- MLLM nowadays are really good at making decision
- GUI perception only works on screenshots for best compatibility
- Environment: **Mobile** - Suitable for ordinary users

**Step-by-step:**

1. Given User Goal
    1. Retrieve **History Context / Past Interactions / Longterm Memory** *(Optional)*
    2. Retrieve **Constraints in Planning Sub-goals**
    Ref: How?
        1. Based on category of the application
        2. Based on category of user instruction
2. Decompose task and plan sub-goals
Ref: https://arxiv.org/abs/2312.13108 
*⇒ Task should be divided into milestones*
3. For each **Sub-goal** of **Sub-goals**
    1. Retrieve **Skills / Action Space**
    Ref $I$: https://arxiv.org/abs/2509.17328
    Ref $II$: https://arxiv.org/abs/2411.17465
    *⇒ MLLM should have a unified action space*
        1. Could be **Atomic GUI Skills (click, type, scroll)**
        2. Could be **Composite Skills (login, search, filter or order-free actions)** *(Optional)*
    2. Compile GUI state
        1. Vision
            1. Visual highlighting
            Ref: https://github.com/microsoft/OmniParser (Abort-Cannot boot model)
            *⇒ Detect GUI element by YOLOv8 and Set-of-Mask prompting*
            Ref: **https://arxiv.org/abs/2412.10342
            *⇒ Detect information-sensitive region programmatically*
            2. Masking (Irrelevant as NN isn’t trained to acknowledge the mask)
            Ref: https://arxiv.org/abs/2507.03730
            *⇒ Mask irrelevant components based on Gaussian and Norm Distribution*
            3. Cropping / Zoom *(Optional)*
            Ref: https://arxiv.org/abs/2505.00684
            *⇒ MLLM proposes the candidate GUI regions*
        2. Language
            1. Past **Sub-goals**
            2. Active **Sub-goal**
            Ref: https://arxiv.org/abs/2406.08451
            *⇒ Semantic context is good enough for reasoning*
                1. Detail **Reasoning behind Decisions**
                2. Achieved **Historical Actions**
                3. Available **Action Space**
                4. Suggest **Predicted Next Action** (likely) *(Optional)*
    3. Execute **Next Action**
    4. Reflect **Sub-goal**
        1. Detect **Stalled Interaction**
        Ref: https://arxiv.org/abs/2503.17709
        *⇒ Visual changes can be detected by algorithm in terms of computational efficiency*
        2. Verify **Sub-goal** satisfaction by GUI understanding ⇒ **Screen Question Answering**
        Ref: How?
        3. If **Sub-goal** unaccomplished
            1. Could be **Sub-goal Expansion**
            2. Could be **Full Plan Regeneration**

# Visualization

[D2 Diagram Playground](https://play.d2lang.com/)
```d2-diagram
direction: right
title: MLLM Mobile Navigation
User: {  shape: person  label: "User\nGoal"}
MLLM: {  label: "MLLM (Blackbox)\nDecision Engine"}
Environment: {  label: "Mobile Environment\n(Screenshot-based GUI)"}
# --------------------------------------------------# 1. Planning Phase# --------------------------------------------------
Planning: {  label: "1️⃣ Planning Phase"
  ContextRetrieval: {    label: "Retrieve Context\n- History\n- Past Interactions\n- Long-term Memory (Optional)"  }
  ConstraintRetrieval: {    label: "Retrieve Constraints\n- App Category\n- User Instruction Category"  }
  TaskDecomposition: {    label: "2️⃣ Decompose Task\ninto Milestones / Sub-goals"  }}
User -> Planning.ContextRetrievalPlanning.ContextRetrieval -> Planning.ConstraintRetrievalPlanning.ConstraintRetrieval -> Planning.TaskDecomposition# Planning.TaskDecomposition -> MLLM
# --------------------------------------------------# 2. Sub-goal Execution Loop# --------------------------------------------------
SubGoalLoop: {  label: "3️⃣ Sub-goal Execution Loop"
  SkillRetrieval: {    label: "Retrieve Skills / Action Space\n- Atomic (click, type, scroll)\n- Composite (login, search, filter)"  }
  GUIState: {    label: "Compile GUI State"
    Vision: {      label: "Vision Processing"
      Highlighting: {        label: "Visual Highlighting\n(YOLOv8 + Set-of-Mask)"      }
      Masking: {        label: "Mask Irrelevant Components\n(Gaussian / Norm Distribution)"      }
      Cropping: {        label: "Cropping / Zoom (Optional)\nCandidate Regions Proposed by MLLM"      }    }
    Language: {      label: "Language Context"
      PastSubGoals: {        label: "Past Sub-goals"      }
      ActiveSubGoal: {        label: "Active Sub-goal"      }
      Reasoning: {        label: "Semantic Reasoning\n- Decision Explanation\n- Historical Actions\n- Available Action Space\n- Predicted Next Action (Optional)"      }    }  }
  Execute: {    label: "Execute Next Action"  }
  Reflection: {    label: "4️⃣ Reflection"
    StallDetection: {      label: "Detect Stalled Interaction\n(Visual Change Detection)"    }
    Verification: {      label: "Verify Sub-goal\n(Screen QA / GUI Understanding)"    }
    Replan: {      label: "If Not Accomplished:\n- Sub-goal Expansion\n- Full Plan Regeneration"    }  }}
Planning.TaskDecomposition -> SubGoalLoop.SkillRetrieval
SubGoalLoop.SkillRetrieval -> SubGoalLoop.GUIStateSubGoalLoop.GUIState.Vision.Highlighting -> SubGoalLoop.GUIState.Vision.MaskingSubGoalLoop.GUIState.Vision.Masking -> SubGoalLoop.GUIState.Vision.Cropping
SubGoalLoop.GUIState.Language.PastSubGoals -> SubGoalLoop.GUIState.Language.ReasoningSubGoalLoop.GUIState.Language.ActiveSubGoal -> SubGoalLoop.GUIState.Language.Reasoning
# SubGoalLoop.GUIState -> SubGoalLoop.ExecuteSubGoalLoop.GUIState -> MLLMMLLM -> SubGoalLoop.ExecuteSubGoalLoop.Execute -> EnvironmentEnvironment -> SubGoalLoop.Reflection
SubGoalLoop.Reflection.StallDetection -> SubGoalLoop.Reflection.VerificationSubGoalLoop.Reflection.Verification -> SubGoalLoop.Reflection.Replan
SubGoalLoop.Reflection.Replan -> Planning.TaskDecomposition: "Regenerate Plan"SubGoalLoop.Reflection.Verification -> SubGoalLoop.SkillRetrieval: "Next Sub-goal"
```