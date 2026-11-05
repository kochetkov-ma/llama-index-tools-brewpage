"""Minimal synchronous client for the public BrewPage API (https://brewpage.app)."""

from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

DEFAULT_BASE_URL = "https://brewpage.app"
USER_AGENT = "llama-index-tools-brewpage/0.1.0"


class BrewPageError(RuntimeError):
    """Raised when the BrewPage API answers with a non-2xx status."""


class BrewPageClient:
    """Publishes pages, JSON, KV stores and files; reuses one owner token for all of them."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        owner_token: Optional[str] = None,
        namespace: Optional[str] = None,
        timeout: float = 60.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("BREWPAGE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.owner_token = owner_token or os.environ.get("BREWPAGE_OWNER_TOKEN") or None
        self.namespace = namespace or os.environ.get("BREWPAGE_NAMESPACE") or None
        self._http = httpx.Client(timeout=timeout, transport=transport, headers={"User-Agent": USER_AGENT})

    def publish_page(self, content: str, format: str = "html", ttl_days: Optional[int] = None,
                     password: Optional[str] = None, namespace: Optional[str] = None) -> Dict[str, Any]:
        body = {"content": content, "format": format}
        return self._post("/api/html", namespace, ttl_days, password, json_body=body)

    def publish_json(self, data: Any, ttl_days: Optional[int] = None, password: Optional[str] = None,
                     namespace: Optional[str] = None) -> Dict[str, Any]:
        return self._post("/api/json", namespace, ttl_days, password, json_body=data)

    def create_kv_store(self, key: str, value: str, ttl_days: Optional[int] = None,
                        password: Optional[str] = None, namespace: Optional[str] = None) -> Dict[str, Any]:
        return self._post("/api/kv", namespace, ttl_days, password, json_body={"key": key, "value": value})

    def upload_file(self, path: str, ttl_days: Optional[int] = None, password: Optional[str] = None,
                    namespace: Optional[str] = None) -> Dict[str, Any]:
        file = Path(path)
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        files = {"file": (file.name, file.read_bytes(), mime)}
        return self._post("/api/files", namespace, ttl_days, password, files=files)

    def _post(self, path: str, namespace: Optional[str], ttl_days: Optional[int], password: Optional[str],
              json_body: Any = None, files: Any = None) -> Dict[str, Any]:
        params = {}
        ns = namespace or self.namespace
        if ns:
            params["ns"] = ns
        if ttl_days is not None:
            params["ttl"] = str(ttl_days)
        headers = {}
        if self.owner_token:
            headers["X-Owner-Token"] = self.owner_token
        if password:
            headers["X-Password"] = password
        if files is None:
            headers["Content-Type"] = "application/json"
            response = self._http.post(self.base_url + path, params=params, headers=headers,
                                       content=json.dumps(json_body).encode("utf-8"))
        else:
            response = self._http.post(self.base_url + path, params=params, headers=headers, files=files)
        if response.status_code >= 300:
            raise BrewPageError(f"BrewPage {path} failed with HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        if not self.owner_token and payload.get("ownerToken"):
            self.owner_token = payload["ownerToken"]
        return {
            "url": payload.get("link"),
            "id": payload.get("id"),
            "namespace": payload.get("namespace"),
            "owner_token": payload.get("ownerToken") or self.owner_token,
            "management_link": payload.get("managementLink"),
            "expires_at": payload.get("expiresAt"),
        }
