"""HTTP client for the OwnerRez v2 API.

Features:
  * OAuth Bearer auth, with HTTP Basic / Personal Access Token as a fallback.
  * Automatic retries with backoff on 429 (honoring Retry-After) and 5xx.
  * Secret redaction so tokens never leak into error messages.
  * Optional read-only mode that hard-blocks write methods.
  * OwnerRez v2 pagination helper.

API reference: https://api.ownerrez.com/help/v2
"""

from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings

DEFAULT_USER_AGENT = "ownerrez-mcp/0.2 (+https://github.com/)"
_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


class OwnerRezError(RuntimeError):
    """Raised when the OwnerRez API returns an error response."""

    def __init__(self, status_code: int, message: str, url: str, body: Any = None):
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"OwnerRez API {status_code} for {url}: {message}")


class ReadOnlyError(RuntimeError):
    """Raised when a write is attempted while the server is in read-only mode."""


def _redactor(secrets: List[str]):
    def redact(text: str) -> str:
        out = text
        for s in secrets:
            if s:
                out = out.replace(s, "***")
        return out

    return redact


class OwnerRezClient:
    """Minimal synchronous client for the OwnerRez v2 API."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        http_client: Optional[httpx.Client] = None,
        sleep=time.sleep,
    ):
        self.settings = settings or Settings.from_env()
        if not self.settings.has_credentials():
            raise ValueError(
                "No OwnerRez credentials found. Set OWNERREZ_ACCESS_TOKEN (OAuth) "
                "or OWNERREZ_USERNAME + OWNERREZ_TOKEN (Personal Access Token)."
            )
        self._redact = _redactor(self.settings.secrets())
        self._sleep = sleep
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            timeout=self.settings.timeout, headers=self._base_headers()
        )

    # ------------------------------------------------------------------ auth
    @property
    def base_url(self) -> str:
        return self.settings.base_url

    def _base_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.settings.access_token:
            headers["Authorization"] = f"Bearer {self.settings.access_token}"
        else:
            raw = f"{self.settings.username}:{self.settings.token}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    # --------------------------------------------------------------- request
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        method = method.upper()
        if method in _WRITE_METHODS and self.settings.read_only:
            raise ReadOnlyError(
                f"Refusing {method} {path}: server is in read-only mode "
                "(unset OWNERREZ_READ_ONLY to allow writes)."
            )

        if path.startswith("http"):
            url = path
        else:
            clean_path = path.lstrip("/")
            if clean_path.startswith("v2/"):
                clean_path = clean_path[3:]
            url = f"{self.base_url}/{clean_path}"
        clean_params = (
            {k: v for k, v in params.items() if v is not None} if params else None
        )

        resp = self._send_with_retries(method, url, clean_params, json)

        if resp.status_code == 204 or not resp.content:
            return None
        try:
            data = resp.json()
        except ValueError:
            data = resp.text

        if resp.status_code >= 400:
            message = data
            if isinstance(data, dict):
                message = data.get("message") or data.get("error") or data
            raise OwnerRezError(
                resp.status_code, self._redact(str(message)), url, body=data
            )
        return data

    def _send_with_retries(self, method, url, params, json) -> httpx.Response:
        attempts = self.settings.max_retries + 1
        last_exc: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                resp = self._client.request(method, url, params=params, json=json)
            except httpx.TransportError as exc:  # network blip
                last_exc = exc
                if attempt < attempts - 1:
                    self._sleep(self._backoff(attempt))
                    continue
                raise
            if attempt < attempts - 1 and self._should_retry(resp):
                self._sleep(self._retry_delay(resp, attempt))
                continue
            return resp
        # Unreachable, but keeps type checkers happy.
        raise last_exc if last_exc else RuntimeError("request failed")

    @staticmethod
    def _should_retry(resp: httpx.Response) -> bool:
        return resp.status_code == 429 or 500 <= resp.status_code < 600

    def _retry_delay(self, resp: httpx.Response, attempt: int) -> float:
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        return self._backoff(attempt)

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2.0 ** attempt, 30.0)

    # --------------------------------------------------------------- verbs
    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("POST", path, json=json)

    def patch(self, path: str, json: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("PATCH", path, json=json)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    # ------------------------------------------------------------ pagination
    def get_all(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        max_items: int = 500,
    ) -> List[Dict[str, Any]]:
        """Follow OwnerRez v2 paging (``items`` + ``next_page_url``) up to a cap."""
        items: List[Dict[str, Any]] = []
        page = self.get(path, params=params)
        while page is not None:
            if isinstance(page, dict) and "items" in page:
                items.extend(page.get("items") or [])
                next_url = page.get("next_page_url")
                if not next_url or len(items) >= max_items:
                    break
                page = self.get(next_url)
            elif isinstance(page, list):
                items.extend(page)
                break
            else:
                items.append(page)
                break
        return items[:max_items]

    # ------------------------------------------------------------- lifecycle
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OwnerRezClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
