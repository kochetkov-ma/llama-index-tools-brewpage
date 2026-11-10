"""LlamaIndex tool spec for BrewPage publishing."""

import json
from typing import Annotated, Any, Dict, List, Literal, Optional

from llama_index.core.tools import FunctionTool
from llama_index.core.tools.tool_spec.base import BaseToolSpec
from pydantic import Field

from llama_index.tools.brewpage.client import BrewPageClient, BrewPageError

Ttl = Annotated[Optional[int], Field(description="Lifetime in days (1-30); omit for the 15-day default.")]
Password = Annotated[Optional[str], Field(description="Optional password readers must enter.")]
Namespace = Annotated[Optional[str], Field(
    description="Omit for a private unlisted link; 'public' lists pages in the public gallery and search. "
                "Never put secrets or personal data in 'public'.")]
_HANDOFF = (" Give the user 'url' and 'management_link' (private: anyone who has it can edit or delete the "
            "publication). Keep 'owner_token' for later updates; show it when asked. Never post either publicly.")


class BrewPageToolSpec(BaseToolSpec):
    """Publish pages, JSON, KV stores and files on brewpage.app; all share one owner token."""

    spec_functions = ["publish_page", "publish_json", "create_kv_store", "upload_file"]

    def __init__(self, client: Optional[BrewPageClient] = None) -> None:
        self.client = client or BrewPageClient()

    def publish_page(
        self,
        content: Annotated[str, Field(description="HTML document or Markdown text to publish.")],
        format: Annotated[Literal["html", "markdown"], Field(description="'html' or 'markdown'.")] = "html",
        ttl_days: Ttl = None,
        password: Password = None,
        namespace: Namespace = None,
    ) -> Dict[str, Any]:
        """Publish an HTML page or Markdown document on brewpage.app; returns its URL."""
        return self._call("publish_page", content=content, format=format, ttl_days=ttl_days,
                          password=password, namespace=namespace)

    def publish_json(
        self,
        json_text: Annotated[str, Field(description="A valid JSON document as text.")],
        ttl_days: Ttl = None,
        password: Password = None,
        namespace: Namespace = None,
    ) -> Dict[str, Any]:
        """Host a JSON document on brewpage.app; returns a URL that serves it."""
        try:
            data = json.loads(json_text)
        except ValueError as error:
            return {"error": f"json_text is not valid JSON: {error}"}
        return self._call("publish_json", data=data, ttl_days=ttl_days, password=password, namespace=namespace)

    def create_kv_store(
        self,
        key: Annotated[str, Field(description="Initial key name.")],
        value: Annotated[str, Field(description="Value for the initial key (max 1 MB).")],
        ttl_days: Ttl = None,
        password: Password = None,
        namespace: Namespace = None,
    ) -> Dict[str, Any]:
        """Create a key-value store on brewpage.app with one initial key; returns its URL."""
        return self._call("create_kv_store", key=key, value=value, ttl_days=ttl_days,
                          password=password, namespace=namespace)

    def upload_file(
        self,
        path: Annotated[str, Field(description="Local path of the file to upload.")],
        ttl_days: Ttl = None,
        password: Password = None,
        namespace: Namespace = None,
    ) -> Dict[str, Any]:
        """Upload a local file (image, PDF, archive, document, HTML, Markdown) to brewpage.app; returns its URL."""
        return self._call("upload_file", path=path, ttl_days=ttl_days, password=password, namespace=namespace)

    def to_tool_list(self, *args: Any, **kwargs: Any) -> List[FunctionTool]:
        """Build tools described by the plain docstring plus the hand-over rule (no signature dump)."""
        return [FunctionTool.from_defaults(fn=getattr(self, name), name=name,
                                           description=getattr(self, name).__doc__ + _HANDOFF)
                for name in self.spec_functions]

    def _call(self, method: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            return getattr(self.client, method)(**kwargs)
        except (BrewPageError, OSError) as error:
            return {"error": str(error)}
