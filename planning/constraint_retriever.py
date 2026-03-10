"""
Constraint Retriever for Planning Phase

Responsible for retrieving constraints that guide task decomposition:
- App category constraints (social, shopping, navigation, etc.)
- Instruction category constraints (navigation, data_entry, search, etc.)
- Combined constraint set

TODO - Implementation Instructions:
    1. Define ConstraintRetriever class with constructor taking config
    2. Create constraint database/mapping:
        - App category to constraints mapping
        - Instruction category to constraints mapping
    3. Implement get_app_constraints(app_category: str) method:
        - Return list of constraints for app type
        - Include common UI patterns
        - Include typical navigation flows
    4. Implement get_instruction_constraints(instruction_category: str) method:
        - Return list of constraints for instruction type
        - Include expected sub-tasks
        - Include typical success criteria
    5. Implement merge_constraints() method:
        - Combine app and instruction constraints
        - Prioritize overlapping constraints
        - Handle conflicts
    6. Add caching for constraint retrieval
    7. Add logging and error handling
"""


class ConstraintRetriever:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config):
            - Store config
            - Load constraint database
            - Set up cache
        2. Implement get_app_constraints(app_category: str) -> List[str]:
            - Check cache first
            - Load from database by category
            - Return constraint list
        3. Implement get_instruction_constraints(instruction_category: str) -> List[str]:
            - Check cache first
            - Load from database by category
            - Return constraint list
        4. Implement merge_constraints(app_constraints, instruction_constraints) -> List[str]:
            - Deduplicate constraints
            - Apply priority/ordering
            - Return merged list
    """
    pass


def retrieve_constraints_for_planning(app_category: str, instruction_category: str) -> dict:
    """
    TODO - Implementation Instructions:
        1. Create ConstraintRetriever instance
        2. Get app and instruction constraints
        3. Merge constraints
        4. Return structured constraints dict with metadata
    """
    pass


# TODO - Constraint Database Template
CONSTRAINT_DATABASE = {
    "app_categories": {
        "social": ["Search for users/posts", "Handle feed scrolling", "Avatar/profile access"],
        "shopping": ["Browse products", "Add to cart", "Checkout process", "Payment required"],
        "navigation": ["Search location", "Get directions", "Handle maps", "Route selection"],
        # Add more as needed
    },
    "instruction_categories": {
        "navigation": ["Involves moving between screens", "May require scrolling"],
        "data_entry": ["Involves typing", "Form submission required"],
        "search": ["Involves text input", "Results browsing", "Item selection"],
        # Add more as needed
    }
}
