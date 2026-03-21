"""
Constraint Retriever for Planning Phase

Responsible for retrieving constraints that guide task decomposition:
- App category constraints (social, shopping, navigation, etc.)
- Instruction category constraints (navigation, data_entry, search, etc.)
- Combined constraint set
"""

import logging
from typing import List, Dict, Any, Optional


# Constraint Database Template
CONSTRAINT_DATABASE = {
    "app_categories": {
        "settings": [
            "Settings app typically has hierarchical menu structure",
            "Navigation involves drilling down into submenu sections",
            "Some settings may require confirmation before changes take effect",
            "Back button or up arrow available for navigation"
        ],
        "social": [
            "Search for users/posts typically involves text input",
            "Handle feed scrolling for browsing content",
            "Avatar/profile access through user profiles",
            "May require authentication for certain actions"
        ],
        "shopping": [
            "Browse products with search and filter options",
            "Add to cart functionality available",
            "Checkout process with multiple steps",
            "Payment required for completion"
        ],
        "navigation": [
            "Search location requires text input or address selection",
            "Get directions available after location selection",
            "Handle maps interface for route visualization",
            "Route selection and alternative options"
        ],
    },
    "instruction_categories": {
        "navigation": [
            "Involves moving between screens/sections",
            "May require scrolling to find target elements",
            "Back navigation may be needed",
            "Multiple levels of menu hierarchy possible"
        ],
        "data_entry": [
            "Involves typing text into input fields",
            "Form submission required after data entry",
            "Validation may occur after submission",
            "Error handling for invalid input"
        ],
        "search": [
            "Involves text input in search field",
            "Results browsing and pagination",
            "Item selection from results",
            "May include filters and sorting options"
        ],
        "toggle": [
            "Involves finding a toggle/switch element",
            "Single click/tap to toggle state",
            "Visual feedback for state change",
            "Confirmation may be required"
        ],
    }
}


class ConstraintRetriever:
    """
    Retrieves constraints that guide task planning and decomposition.
    Provides app-specific and instruction-specific constraints.
    """

    def __init__(self, config: Any = None):
        """
        Initialize the ConstraintRetriever.

        Args:
            config: Configuration object (optional)
        """
        self._config = config
        self._logger = logging.getLogger(self.__class__.__name__)
        self._constraint_db = CONSTRAINT_DATABASE
        self._logger.info("ConstraintRetriever initialized")

    def get_app_constraints(self, app_category: Optional[str]) -> List[str]:
        """
        Get constraints for a specific app category.

        Args:
            app_category: Category of the target app (e.g., 'settings', 'social')

        Returns:
            List of constraint strings for the app category
        """
        if not app_category:
            self._logger.debug("No app category specified, returning empty constraints")
            return []

        app_category = app_category.lower()
        constraints = self._constraint_db["app_categories"].get(app_category, [])

        self._logger.debug(f"Retrieved {len(constraints)} constraints for app: {app_category}")
        return constraints

    def get_instruction_constraints(self, instruction_category: Optional[str]) -> List[str]:
        """
        Get constraints for a specific instruction category.

        Args:
            instruction_category: Category of the instruction (e.g., 'navigation', 'data_entry')

        Returns:
            List of constraint strings for the instruction category
        """
        if not instruction_category:
            self._logger.debug("No instruction category specified, returning empty constraints")
            return []

        instruction_category = instruction_category.lower()
        constraints = self._constraint_db["instruction_categories"].get(instruction_category, [])

        self._logger.debug(f"Retrieved {len(constraints)} constraints for instruction: {instruction_category}")
        return constraints

    def merge_constraints(
        self,
        app_constraints: List[str],
        instruction_constraints: List[str]
    ) -> List[str]:
        """
        Merge app and instruction constraints, removing duplicates.

        Args:
            app_constraints: Constraints from app category
            instruction_constraints: Constraints from instruction category

        Returns:
            Merged list of constraints with duplicates removed
        """
        self._logger.debug(
            f"Merging {len(app_constraints)} app constraints "
            f"with {len(instruction_constraints)} instruction constraints"
        )

        # Combine and deduplicate
        merged = list(dict.fromkeys(app_constraints + instruction_constraints))

        self._logger.debug(f"Merged into {len(merged)} unique constraints")
        return merged

    def retrieve_constraints(
        self,
        app_category: Optional[str] = None,
        instruction_category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve complete constraint set for planning.

        Args:
            app_category: Category of the target app
            instruction_category: Category of the instruction

        Returns:
            Dictionary with app constraints, instruction constraints, and merged constraints
        """
        self._logger.debug(
            f"Retrieving constraints for app={app_category}, instruction={instruction_category}"
        )

        app_constraints = self.get_app_constraints(app_category)
        instruction_constraints = self.get_instruction_constraints(instruction_category)
        merged_constraints = self.merge_constraints(app_constraints, instruction_constraints)

        result = {
            "app_category": app_category,
            "instruction_category": instruction_category,
            "app_constraints": app_constraints,
            "instruction_constraints": instruction_constraints,
            "merged_constraints": merged_constraints
        }

        return result
