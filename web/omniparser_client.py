from __future__ import annotations

import time
import uuid
import mimetypes
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib import error, request


class OmniParserClientError(Exception):
    """Raised when OmniParser API call fails."""


@dataclass
class ParseScreenResult:
    request_id: Optional[str]
    parsed_screen: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


class OmniParserClient:
    """HTTP client for calling remote OmniParser parse endpoints."""

    def __init__(
        self,
        base_url: str,
        timeout_sec: float = 10.0,
        retry_count: int = 1,
        retry_backoff_ms: int = 250,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.retry_count = max(0, retry_count)
        self.retry_backoff_ms = max(0, retry_backoff_ms)

    async def close(self) -> None:
        return

    async def probe(self) -> Dict[str, Any]:
        payload = await self._request_json("GET", f"{self.base_url}/probe/")
        if not isinstance(payload, dict):
            raise OmniParserClientError("Invalid probe response format")
        return payload

    async def parse_screen(self, image_bytes: bytes, filename: str = "screen.png") -> ParseScreenResult:
        if not image_bytes:
            raise OmniParserClientError("Empty image bytes")

        last_error: Optional[Exception] = None
        for attempt in range(self.retry_count + 1):
            started = time.perf_counter()
            try:
                body, content_type = self._build_multipart_body("image", filename, image_bytes)
                payload = await self._request_json(
                    "POST",
                    f"{self.base_url}/api/parse",
                    body=body,
                    headers={"Content-Type": content_type},
                )
                latency_ms = (time.perf_counter() - started) * 1000

                if not isinstance(payload, dict):
                    raise OmniParserClientError("Invalid parse response format")

                parsed_content = payload.get("parsed_content_list")
                if parsed_content is None:
                    parsed_content = []
                if not isinstance(parsed_content, list):
                    raise OmniParserClientError("Invalid parsed_content_list format")

                normalized_parsed_content = self._normalize_parsed_content(parsed_content)

                return ParseScreenResult(
                    request_id=payload.get("request_id"),
                    parsed_screen=normalized_parsed_content,
                    raw_response=payload,
                    latency_ms=latency_ms,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.retry_count:
                    break
                await self._sleep_backoff()

        if isinstance(last_error, OmniParserClientError):
            raise last_error
        raise OmniParserClientError(f"OmniParser request failed: {last_error}")

    async def _sleep_backoff(self) -> None:
        if self.retry_backoff_ms <= 0:
            return
        # Tiny non-blocking backoff for transient network failures.
        import asyncio

        await asyncio.sleep(self.retry_backoff_ms / 1000.0)

    async def _request_json(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        import asyncio

        return await asyncio.to_thread(self._request_json_sync, method, url, body, headers)

    def _request_json_sync(
        self,
        method: str,
        url: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        req = request.Request(url=url, data=body, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, value)

        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                status = getattr(resp, "status", 200)
                raw = resp.read().decode("utf-8")
                if status != 200:
                    raise OmniParserClientError(f"OmniParser request failed with status={status}: {raw}")
                return json.loads(raw)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if exc.fp else str(exc)
            raise OmniParserClientError(f"OmniParser request failed with status={exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise OmniParserClientError(f"OmniParser connection failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise OmniParserClientError(f"Invalid JSON response: {exc}") from exc

    def _build_multipart_body(self, field_name: str, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
        boundary = f"----guiagent-{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        lines = [
            f"--{boundary}",
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"',
            f"Content-Type: {mime}",
            "",
        ]

        prefix = "\r\n".join(lines).encode("utf-8") + b"\r\n"
        suffix = f"\r\n--{boundary}--\r\n".encode("utf-8")
        body = prefix + file_bytes + suffix
        content_type = f"multipart/form-data; boundary={boundary}"
        return body, content_type

    def _normalize_parsed_content(self, parsed_content: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []

        for element_index, item in enumerate(parsed_content):
            if isinstance(item, dict):
                parsed_item = dict(item)
            else:
                parsed_item = {"content": str(item)}

            parsed_item["element_index"] = element_index

            normalized.append(parsed_item)

        return normalized
