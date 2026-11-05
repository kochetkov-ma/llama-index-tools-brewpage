import json
import os
import re

import httpx
import pytest

from llama_index.tools.brewpage import BrewPageClient, BrewPageToolSpec

API_REPLY = {
    "link": "https://brewpage.app/my/abc123",
    "id": "abc123",
    "namespace": "my",
    "ownerToken": "tok-1",
    "managementLink": "https://brewpage.app/my/abc123?manage=k1",
    "expiresAt": "2026-11-20T00:00:00Z",
}
BOUNDARY = re.compile(r"[0-9a-f]{32}")
RESULT = {
    "url": "https://brewpage.app/my/abc123",
    "id": "abc123",
    "namespace": "my",
    "owner_token": "tok-1",
    "management_link": "https://brewpage.app/my/abc123?manage=k1",
    "expires_at": "2026-11-20T00:00:00Z",
}


def _recording_client(status, reply, seen):
    def handler(request):
        seen.append({
            "method": request.method,
            "url": str(request.url),
            "content_type": BOUNDARY.sub("B", request.headers["content-type"]),
            "owner_token": request.headers.get("x-owner-token"),
            "password": request.headers.get("x-password"),
            "body": BOUNDARY.sub("B", request.content.decode("utf-8")),
        })
        return httpx.Response(status, json=reply)

    return BrewPageClient(owner_token="tok-1", namespace="my", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("tool_index", "schema", "args", "expected_request"),
    [
        (0, ("publish_page", ["content"]), {"content": "# Hi", "format": "markdown", "ttl_days": 3},
         {"method": "POST", "url": "https://brewpage.app/api/html?ns=my&ttl=3", "content_type": "application/json",
          "owner_token": "tok-1", "password": None, "body": '{"content": "# Hi", "format": "markdown"}'}),
        (1, ("publish_json", ["json_text"]), {"json_text": '{"a": [1, 2]}', "password": "pw"},
         {"method": "POST", "url": "https://brewpage.app/api/json?ns=my", "content_type": "application/json",
          "owner_token": "tok-1", "password": "pw", "body": '{"a": [1, 2]}'}),
        (2, ("create_kv_store", ["key", "value"]), {"key": "status", "value": "green"},
         {"method": "POST", "url": "https://brewpage.app/api/kv?ns=my", "content_type": "application/json",
          "owner_token": "tok-1", "password": None, "body": '{"key": "status", "value": "green"}'}),
        (3, ("upload_file", ["path"]), {"path": "{tmp}/notes.txt"},
         {"method": "POST", "url": "https://brewpage.app/api/files?ns=my", "content_type": "multipart/form-data; boundary=B",
          "owner_token": "tok-1", "password": None,
          "body": '--B\r\nContent-Disposition: form-data; name="file"; filename="notes.txt"\r\n'
                  'Content-Type: text/plain\r\n\r\nhello\r\n--B--\r\n'}),
    ],
    ids=["page", "json", "kv", "file"],
)
def test_tool_posts_exact_request_and_returns_link(tmp_path, tool_index, schema, args, expected_request):
    # GIVEN a toolkit whose client answers every POST with a fixed API reply
    (tmp_path / "notes.txt").write_text("hello")
    seen = []
    tool = BrewPageToolSpec(client=_recording_client(201, API_REPLY, seen)).to_tool_list()[tool_index]
    resolved = json.loads(json.dumps(args).replace("{tmp}", str(tmp_path)))

    # WHEN the agent calls the tool
    result = tool.call(**resolved).raw_output

    # THEN the tool schema, the single request and the mapped result match exactly
    assert ((tool.metadata.name, tool.metadata.get_parameters_dict()["required"]), seen, result) == (schema, [expected_request], RESULT), f"tool {tool.metadata.name} sent {seen} and returned {result}"


def test_api_error_becomes_tool_message():
    # GIVEN an API that rate-limits the caller
    seen = []
    tool = BrewPageToolSpec(client=_recording_client(429, {"message": "slow down"}, seen)).to_tool_list()[2]

    # WHEN the tool is called
    result = tool.call(key="k", value="v").raw_output

    # THEN the agent receives the error text instead of an exception
    assert result == {"error": 'BrewPage /api/kv failed with HTTP 429: {"message":"slow down"}'}, f"unexpected tool output {result!r}"


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("BREWPAGE_LIVE") != "1", reason="set BREWPAGE_LIVE=1 to hit production")
def test_live_private_markdown_page():
    # GIVEN the real API and the private 'my' namespace
    tool = BrewPageToolSpec(client=BrewPageClient(namespace="my")).to_tool_list()[0]

    # WHEN a short Markdown page is published for one day
    result = tool.call(content="# llama-index-tools-brewpage smoke\n\nPrivate test page.", format="markdown", ttl_days=1).raw_output

    # THEN a private brewpage.app link and an owner token come back
    shape = {
        "namespace": result["namespace"],
        "url": bool(re.fullmatch(r"https://([a-z0-9-]+\.)*brewpage\.app/\S+", result["url"])),
        "owner_token": bool(re.fullmatch(r"\S{16,}", result["owner_token"])),
    }
    assert shape == {"namespace": "my", "url": True, "owner_token": True}, f"live result {json.dumps(result)}"
