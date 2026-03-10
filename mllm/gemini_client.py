"""
Gemini Client for MLLM Module

Low-level interface to Google Gemini REST API.
Handles authentication, requests, responses, and error handling.

TODO - Implementation Instructions:
    1. Define GeminiClient class:
        - Load API key from environment variable GEMINI_API_KEY
        - Initialize base URL and model name (gemini-2.0-flash or similar)
        - Set up logger
    2. Implement __init__(self, config):
        - Get API key from env or config
        - Set model name from config (default: gemini-2.0-flash)
        - Initialize request session
        - Set timeout and retry settings
    3. Implement query_text(prompt: str, temperature: float = 0.7) -> str:
        - Make REST call to Gemini API
        - Send text prompt
        - Handle response
        - Return response text
    4. Implement query_with_image(prompt: str, image_bytes: bytes, temperature: float = 0.7) -> str:
        - Encode image_bytes to base64
        - Make REST call with image
        - Return response text
    5. Implement error handling:
        - Handle API errors (500, 429, etc.)
        - Implement exponential backoff retry
        - Log errors
    6. Implement rate limiting:
        - Track requests per minute
        - Delay if approaching limit
    7. Add response caching (optional)
    8. Add comprehensive logging
"""

import os
from typing import Optional


class GeminiClient:
    """
    TODO - Implementation Instructions:
        1. Define __init__(self, config=None):
            - Load API key from GEMINI_API_KEY env var (required)
            - Set model from config or default to gemini-2.0-flash
            - Initialize base_url (https://generativelanguage.googleapis.com/v1beta/models)
            - Set up logger
            - Initialize request session with timeout
        2. Implement query_text(prompt: str) -> str:
            - Create request dict with model, prompt, generationConfig
            - Make POST request to /generateContent endpoint
            - Extract and return text from response
            - Handle errors
        3. Implement query_with_image(prompt: str, image_bytes: bytes) -> str:
            - Encode image_bytes to base64
            - Create multipart request
            - Make POST request with image
            - Return response text
        4. Implement _make_request(endpoint, request_body) -> dict:
            - Add API key to URL
            - Make request with retries
            - Parse JSON response
            - Return response dict
        5. Implement retry logic with exponential backoff
    """
    pass


def create_gemini_client(config=None) -> GeminiClient:
    """Create and return a configured Gemini client."""
    return GeminiClient(config)
