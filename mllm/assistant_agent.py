"""
Assistant Agent for MLLM Module

Generic interface for interacting with various LLM providers (e.g., Gemini, OpenAI, Claude).
Uses litellm for dynamic provider support with vision capabilities.
"""

import base64
import logging
from typing import Dict, Any, Optional
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

    def query(self, prompt: str, image_bytes: Optional[bytes] = None, mime_type: str = "image/png", **kwargs: Any) -> str:
        """
        Query the LLM with a prompt/image.

        Args:
            prompt: The text prompt to send
            image_bytes: Optional image data as bytes
            mime_type: MIME type of the image (default: image/png)
            **kwargs: Additional parameters for the query (e.g., temperature, max_tokens)

        Returns:
            The generated text response
        """
        self._logger.debug(f"Querying {self.model} with prompt: {prompt[:100]}...")
        
        # Build message content
        content = [{"type": "text", "text": prompt}]
        
        # Add image if provided
        if image_bytes:
            self._logger.debug(f"Adding image to query (MIME type: {mime_type})")
            image_base64 = base64.b64encode(image_bytes).decode("utf-8")
            image_data = f"data:{mime_type};base64,{image_base64}"
            
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": image_data
                }
            })
        
        try:
            response = litellm.completion(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": content
                }],
                api_key=self.api_key,
                **kwargs
            )

            result = response.choices[0].message.content

            return result
            
        except Exception as e:
            self._logger.error(f"Failed to query {self.model}: {e}")
            raise
