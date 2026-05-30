"""
Base MLLM class with structured Pydantic output validation.
"""

import base64
import io
import json
import logging
import re
from typing import Generic, Optional, Type, TypeVar

import litellm
from PIL import Image
from pydantic import BaseModel, ValidationError

from config.config import Config

T = TypeVar("T", bound=BaseModel)

_SCHEMA_HINT = """

You must respond with a valid JSON object that strictly matches the following schema.
Output ONLY the JSON object — no explanation, no markdown, no extra text.

Schema:
```json
{schema}
```"""


class MllmOutputError(Exception):
    """Raised when the MLLM response cannot be parsed or validated against the output class."""


class BaseMllm(Generic[T]):
    """
    Base class for a single structured MLLM completion task.

    Model credentials and timeout are loaded automatically from the project
    .env file via ``Config`` — no parameters needed for configuration.

    The system prompt is fixed at construction time and is augmented with a
    JSON schema hint derived from ``output_class`` so the model knows the
    exact shape it must return. ``complete()`` calls litellm, strips any
    markdown fences from the response, validates the JSON against the Pydantic
    class, and returns a fully typed instance.

    All litellm API errors and validation failures are logged with full context
    before being re-raised, so callers can handle them at the right layer.

    ---
    Dev guide
    ---

    1. Define a Pydantic model for the expected output::

        from pydantic import BaseModel

        class ActionDecision(BaseModel):
            action: str
            target_element: str
            confidence: float

    2. Subclass ``BaseMllm`` (or use it directly) with a fixed system prompt::

        class ActionAgent(BaseMllm[ActionDecision]):
            def __init__(self) -> None:
                super().__init__(
                    system_prompt=(
                        "You are a GUI agent. Analyse the screenshot and "
                        "decide the next action to take."
                    ),
                    output_class=ActionDecision,
                )

    3. Call ``complete()`` with optional text and/or image input::

        agent = ActionAgent()

        # Text only
        decision = agent.complete(user_message="Current screen: login page")

        # With screenshot
        decision = agent.complete(
            user_message="What should I do next?",
            image_bytes=screenshot_bytes,   # raw PNG/JPEG bytes
            mime_type="image/png",          # default
        )

        print(decision.action)          # typed — ActionDecision instance

    4. Handle errors at the call site::

        from mllm.mllm import MllmOutputError
        import litellm

        try:
            decision = agent.complete(image_bytes=screenshot_bytes)
        except MllmOutputError:
            # Response could not be parsed or failed schema validation.
            # Full details already logged — handle gracefully or retry.
            ...
        except litellm.RateLimitError:
            # API quota hit — back off and retry.
            ...
        except litellm.AuthenticationError:
            # Bad API_KEY in .env
            ...
    """

    def __init__(
        self,
        system_prompt: str,
        output_class: Type[T],
    ) -> None:
        self.output_class = output_class
        self._logger = logging.getLogger(self.__class__.__name__)

        _config = Config()
        self.model = _config.model
        self.api_key = _config.api_key
        self.request_timeout = _config.request_timeout

        schema_json = json.dumps(output_class.model_json_schema(), indent=2)
        self.system_prompt = system_prompt.rstrip() + _SCHEMA_HINT.format(
            schema=schema_json
        )

    def complete(
        self,
        user_message: str = "",
        image: Optional[Image.Image] = None,
    ) -> T:
        """Call the MLLM and return a validated instance of ``output_class``."""
        messages = self._build_messages(user_message, image)
        raw = self._call_litellm(messages)
        return self._parse_and_validate(raw)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_message: str,
        image: Optional[Image.Image],
    ) -> list:
        content: list = []
        if user_message:
            content.append({"type": "text", "text": user_message})
        if image is not None:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )
        if not content:
            content.append({"type": "text", "text": "Analyze and respond."})

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": content},
        ]

    def _call_litellm(self, messages: list) -> str:
        try:
            response = litellm.completion(
                model=self.model,
                messages=messages,
                api_key=self.api_key,
                timeout=self.request_timeout,
            )
            return response.choices[0].message.content

        except litellm.AuthenticationError as e:
            self._logger.error(
                "Authentication failed for model '%s': %s", self.model, e
            )
            raise

        except litellm.RateLimitError as e:
            self._logger.error("Rate limit reached for model '%s': %s", self.model, e)
            raise

        except litellm.ContextWindowExceededError as e:
            self._logger.error(
                "Context window exceeded for model '%s': %s", self.model, e
            )
            raise

        except litellm.ContentPolicyViolationError as e:
            self._logger.error(
                "Content policy violation for model '%s': %s", self.model, e
            )
            raise

        except litellm.ServiceUnavailableError as e:
            self._logger.error("Service unavailable for model '%s': %s", self.model, e)
            raise

        except litellm.BadGatewayError as e:
            self._logger.error("Bad gateway for model '%s': %s", self.model, e)
            raise

        except litellm.APIConnectionError as e:
            self._logger.error("API connection error for model '%s': %s", self.model, e)
            raise

        except litellm.Timeout as e:
            self._logger.error(
                "Request timed out after %ss for model '%s': %s",
                self.request_timeout,
                self.model,
                e,
            )
            raise

        except litellm.BadRequestError as e:
            self._logger.error("Bad request to model '%s': %s", self.model, e)
            raise

        except litellm.NotFoundError as e:
            self._logger.error("Model '%s' not found: %s", self.model, e)
            raise

        except litellm.PermissionDeniedError as e:
            self._logger.error("Permission denied for model '%s': %s", self.model, e)
            raise

        except litellm.UnprocessableEntityError as e:
            self._logger.error("Unprocessable entity for model '%s': %s", self.model, e)
            raise

        except litellm.InternalServerError as e:
            self._logger.error(
                "Internal server error from model '%s': %s", self.model, e
            )
            raise

        except litellm.APIError as e:
            self._logger.error(
                "API error from model '%s' (status=%s): %s",
                self.model,
                getattr(e, "status_code", "unknown"),
                e,
            )
            raise

    def _parse_and_validate(self, raw: str) -> T:
        json_str = self._extract_json(raw)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            self._logger.error(
                "JSON decode failed for %s — line %d col %d.\n  Raw (first 300 chars): %.300s",
                self.output_class.__name__,
                e.lineno,
                e.colno,
                raw,
            )
            raise MllmOutputError(
                f"Response is not valid JSON for {self.output_class.__name__}: {e}"
            ) from e

        try:
            return self.output_class.model_validate(data)
        except ValidationError as e:
            self._logger.error(
                "Validation failed for %s (%d error(s)):\n%s",
                self.output_class.__name__,
                e.error_count(),
                e,
            )
            raise MllmOutputError(
                f"Response does not match {self.output_class.__name__}: {e}"
            ) from e

    @staticmethod
    def _extract_json(text: str) -> str:
        """Strip markdown code fences and return the bare JSON string."""
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return text.strip()
