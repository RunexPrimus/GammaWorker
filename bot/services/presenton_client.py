from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx

from config import Settings
from models import PresentonTask, UploadResult

logger = logging.getLogger(__name__)

_RETRYABLE = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


class PresentonAPIError(Exception):
    """Raised when Presenton returns a non-2xx status."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Presenton API {status_code}: {body[:300]}")


class PresentonClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._timeout = httpx.Timeout(
            settings.request_timeout_seconds,
            connect=settings.connect_timeout_seconds,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.presenton_api_key:
            headers["Authorization"] = f"Bearer {self.settings.presenton_api_key}"
        return headers

    async def _post_with_retry(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST with exponential-backoff retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(1, self.settings.api_max_retries + 2):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, **kwargs)
                    if resp.status_code >= 500 and attempt <= self.settings.api_max_retries:
                        delay = self.settings.api_retry_delay_seconds * (2 ** (attempt - 1))
                        logger.warning(
                            "Presenton returned %s, retrying in %.1fs (attempt %d)",
                            resp.status_code, delay, attempt,
                            extra={"job_id": None, "user_id": None, "stage": "retry"},
                        )
                        await asyncio.sleep(delay)
                        continue
                    _raise_for_status(resp)
                    return resp
            except _RETRYABLE as exc:
                last_exc = exc
                if attempt > self.settings.api_max_retries:
                    break
                delay = self.settings.api_retry_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Presenton network error (%s), retrying in %.1fs (attempt %d)",
                    type(exc).__name__, delay, attempt,
                    extra={"job_id": None, "user_id": None, "stage": "retry"},
                )
                await asyncio.sleep(delay)
        raise last_exc or RuntimeError("Max retries exceeded")  # type: ignore

    async def generate_async(self, payload: dict[str, Any]) -> PresentonTask:
        url = f"{self.settings.presenton_api_root}/api/v3/presentation/generate/async"
        resp = await self._post_with_retry(
            url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        return self._parse_task(resp.json())

    async def get_task_status(self, task_id: str) -> PresentonTask:
        url = f"{self.settings.presenton_api_root}/api/v3/async-task/status/{task_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers())
            _raise_for_status(resp)
        return self._parse_task(resp.json())

    async def download_file(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Prepend API root if path is relative
        if url.startswith("/"):
            url = self.settings.presenton_api_root + url
        async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=self._headers())
            _raise_for_status(resp)
        destination.write_bytes(resp.content)
        return destination

    async def upload_files(self, file_paths: list[Path]) -> UploadResult:
        url = f"{self.settings.presenton_api_root}/api/v3/files/upload"
        files: list[tuple[str, tuple[str, bytes, str]]] = []
        for path in file_paths:
            content = path.read_bytes()
            files.append(("files", (path.name, content, self._guess_mime(path))))

        resp = await self._post_with_retry(url, headers=self._headers(), files=files)
        data = resp.json()
        result = UploadResult(file_ids=self._extract_file_ids(data), raw=data)
        if not result.file_ids:
            logger.warning(
                "Upload succeeded but no file IDs found in response",
                extra={"job_id": None, "user_id": None, "stage": "upload"},
            )
        return result

    # ── Parsing helpers ────────────────────────────────────────────────────────

    def _parse_task(self, data: Any) -> PresentonTask:
        if not isinstance(data, dict):
            return PresentonTask(task_id="", status="unknown", message=str(data), data={}, error={}, raw=data)

        task_id = self._first_non_empty_string(
            data.get("id"),
            data.get("task_id"),
            data.get("async_task_id"),
            self._deep_find_first(data, {"id", "task_id", "async_task_id"}),
        )
        status = self._first_non_empty_string(
            data.get("status"),
            data.get("state"),
            self._deep_find_first(data, {"status", "state"}),
            default="unknown",
        )
        message = self._first_non_empty_string(
            data.get("message"),
            data.get("detail"),
            self._deep_find_first(data, {"message", "detail"}),
            default="",
        )

        payload_data = self._find_best_data_dict(data)
        error = self._find_error_dict(data)
        return PresentonTask(task_id=task_id, status=status, message=message, data=payload_data, error=error, raw=data)

    def _find_best_data_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for key in ("data", "result", "task", "presentation", "output"):
            value = data.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        candidates.append(data)
        for candidate in candidates:
            if any(k in candidate for k in ("path", "edit_path", "presentation_id", "output_url", "url")):
                return candidate
        return candidates[0] if candidates else {}

    def _find_error_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        for key in ("error", "errors"):
            value = data.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                return {"items": value}
            if isinstance(value, str) and value.strip():
                return {"message": value.strip()}
        if isinstance(data.get("detail"), str) and data["detail"].strip():
            return {"detail": data["detail"].strip()}
        return {}

    def _extract_file_ids(self, data: Any) -> list[str]:
        ids: list[str] = []

        def visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in {"id", "file_id"} and isinstance(value, str):
                        ids.append(value)
                    else:
                        visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)
            elif isinstance(node, str):
                if len(node) >= 6:
                    ids.append(node)

        visit(data)
        uniq: list[str] = []
        seen: set[str] = set()
        for item in ids:
            if item and item not in seen:
                seen.add(item)
                uniq.append(item)
        return uniq

    def _guess_mime(self, path: Path) -> str:
        ext = path.suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }.get(ext, "application/octet-stream")

    def _deep_find_first(self, node: Any, keys: set[str]) -> str | None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in keys and isinstance(value, str) and value.strip():
                    return value.strip()
                found = self._deep_find_first(value, keys)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = self._deep_find_first(item, keys)
                if found:
                    return found
        return None

    def _first_non_empty_string(self, *values: Any, default: str = "") -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise PresentonAPIError(resp.status_code, resp.text)
