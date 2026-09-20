"""Regression tests for provider-specific LiteLLM options."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mllm.assistant_agent import AssistantAgent


class AssistantAgentTests(unittest.TestCase):
    def test_openrouter_uses_litellm_api_base_keyword(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        agent = AssistantAgent(
            model="openrouter/nvidia/nemotron-3.5-lightning:free",
            api_key="test-key",
        )

        with patch("mllm.assistant_agent.litellm.completion", return_value=response) as completion:
            result = agent.query("describe this", image_bytes=b"image")

        self.assertEqual("ok", result)
        kwargs = completion.call_args.kwargs
        self.assertEqual("https://openrouter.ai/api/v1", kwargs["api_base"])
        self.assertNotIn("baseUrl", kwargs)


if __name__ == "__main__":
    unittest.main()
