"""
Assistant Agent for MLLM Module

Generic interface for interacting with various LLM providers (e.g., Gemini, OpenAI, Claude).
Uses litellm for dynamic provider support.
"""

import logging
from typing import Dict, Any
import litellm

class AssistantAgent:
    """
    Generic interface for interacting with various LLM providers.
    """

    def __init__(self, model: str, api_key: str):
        """
        Initialize the AssistantAgent.

        Args:
            model: The LLM model (e.g., "gemini-3.1-flash-lite-preview")
            api_key: API key for the model
        """
        self.model = model
        self.api_key = api_key
        self._logger = logging.getLogger(self.__class__.__name__)

        self._logger.info(f"Initialized AssistantAgent with model: {model}")
        self._logger.info(f"Query self.api_key: {self.api_key}")

    def query(self, prompt: str, **kwargs: Any) -> str:
        """
        Query the LLM with a prompt.

        Args:
            prompt: The text prompt to send
            **kwargs: Additional parameters for the query (e.g., temperature, max_tokens)

        Returns:
            The generated text response
        """
        self._logger.debug(f"Querying {self.model} with prompt: {prompt[:100]}...")
       
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                api_key=self.api_key,
                **kwargs
            )

            self._logger.info(f"Received response: {response.choices[0].message.content}")

            return response.choices[0].message.content
        except Exception as e:
            self._logger.error(f"Failed to query {self.model}: {e}")
            raise
