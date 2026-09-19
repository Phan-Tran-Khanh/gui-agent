"""Behavioral tests for deterministic typed-action grounding."""

from __future__ import annotations

import unittest

from pydantic import TypeAdapter

from execution.action_resolver import ActionResolutionError, resolve_action
from execution.models import ActionIntent, Observation, ScreenElement


ACTION_INTENT_ADAPTER = TypeAdapter(ActionIntent)


class ActionResolverTests(unittest.TestCase):
    """The production changes these tests catch are unsafe coordinate mappings."""

    def _observation(self, *elements: ScreenElement) -> Observation:
        return Observation(
            observation_id="screen-1",
            width=1000,
            height=2000,
            elements=list(elements),
        )

    def test_scroll_down_moves_finger_up(self) -> None:
        """A reversed gesture would scroll content in the wrong semantic direction."""
        action = resolve_action(
            ACTION_INTENT_ADAPTER.validate_python(
                {
                    "kind": "SCROLL",
                    "direction": "DOWN",
                    "extent": 0.60,
                    "expected_effect": "show lower settings",
                }
            ),
            self._observation(),
        )

        self.assertGreater(action.start[1], action.end[1])

    def test_top_edge_swipe_starts_inside_top_inset(self) -> None:
        """A top gesture must start inside the display instead of at coordinate zero."""
        action = resolve_action(
            ACTION_INTENT_ADAPTER.validate_python(
                {
                    "kind": "EDGE_SWIPE",
                    "edge": "TOP",
                    "extent": 0.50,
                    "expected_effect": "open notifications",
                }
            ),
            self._observation(),
        )

        self.assertEqual((500, 20), action.start)
        self.assertGreater(action.end[1], action.start[1])

    def test_slider_value_maps_inside_slider_bounds(self) -> None:
        """A slider endpoint must honor the required five-percent safe inset."""
        observation = self._observation(
            ScreenElement(
                element_id="media-volume",
                bounds=(0.20, 0.40, 0.80, 0.50),
                role="slider",
                interactive=True,
            )
        )

        action = resolve_action(
            ACTION_INTENT_ADAPTER.validate_python(
                {
                    "kind": "SET_SLIDER",
                    "element_id": "media-volume",
                    "value": 0.0,
                    "expected_effect": "mute media volume",
                }
            ),
            observation,
        )

        self.assertEqual((230, 900), action.point)

    def test_out_of_bounds_target_is_rejected(self) -> None:
        """A detector box outside the screenshot must not generate a tap coordinate."""
        observation = self._observation(
            ScreenElement(
                element_id="unsafe-target",
                bounds=(-0.10, 0.20, 0.20, 0.30),
                text="Unsafe",
            )
        )

        intent = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": "unsafe-target",
                "expected_effect": "open unsafe target",
            }
        )

        with self.assertRaises(ActionResolutionError):
            resolve_action(intent, observation)

    def test_noninteractive_context_cannot_be_tapped_without_inspection(self) -> None:
        """Context-only labels must not become accidental device targets."""
        observation = self._observation(
            ScreenElement(
                element_id="network-heading",
                bounds=(0.10, 0.10, 0.90, 0.20),
                text="Network & internet",
                interactive=False,
            )
        )
        intent = ACTION_INTENT_ADAPTER.validate_python(
            {
                "kind": "TAP",
                "element_id": "network-heading",
                "expected_effect": "open network settings",
            }
        )

        with self.assertRaises(ActionResolutionError):
            resolve_action(intent, observation)


if __name__ == "__main__":
    unittest.main()
