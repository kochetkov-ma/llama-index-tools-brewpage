import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock, local

import httpx
import pytest

from llama_index.tools.brewpage import BrewPageClient, BrewPageToolSpec

BOUNDARY = re.compile(r"[0-9a-f]{32}")
HANDOFF = (" Give the user 'url' and 'management_link' (private: anyone who has it can edit or delete the "
           "publication). Keep 'owner_token' for later updates; show it when asked. Never post either publicly.")


def _api_reply(segment, minted):
    return {
        "link": "https://brewpage.app/my/abc123",
        "id": "abc123",
        "namespace": "my",
        "ownerToken": "tok-1",
        "ownerLink": f"https://brewpage.app/api/{segment}/my/abc123",
        "managementLink": f"https://brewpage.app/manage/{segment}/my/abc123",
        "expiresAt": "2026-11-20T00:00:00Z",
        **minted,
    }


def _result(management_link):
    return {
        "url": "https://brewpage.app/my/abc123",
        "id": "abc123",
        "namespace": "my",
        "owner_token": "tok-1",
        "management_link": management_link,
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


class _ConcurrentOwnerClient(BrewPageClient):
    def __init__(self, **kwargs):
        self.owner_reads = local()
        self.initial_owner_reads = Barrier(1)
        super().__init__(**kwargs)

    @property
    def owner_token(self):
        # Snapshot each worker's initial owner read before either call continues.
        snapshot = self.stored_owner_token
        wait = getattr(self.owner_reads, "wait", self.initial_owner_reads.wait)
        self.owner_reads.wait = lambda timeout=None: None
        wait(timeout=5)
        return snapshot

    @owner_token.setter
    def owner_token(self, value):
        self.stored_owner_token = value


@pytest.mark.parametrize(
    ("tool_index", "schema", "args", "expected_request", "segment", "minted", "management_link"),
    [
        (0, ("publish_page", ["content"]), {"content": "# Hi", "format": "markdown", "ttl_days": 3},
         {"method": "POST", "url": "https://brewpage.app/api/html?ns=my&ttl=3", "content_type": "application/json",
          "owner_token": "tok-1", "password": None, "body": '{"content": "# Hi", "format": "markdown"}'},
         "html", {"manageUrl": "https://brewpage.app/manage/html/my/abc123#k=bpm_FixtureKey0000000000000000000000"},
         "https://brewpage.app/manage/html/my/abc123#k=bpm_FixtureKey0000000000000000000000"),
        (1, ("publish_json", ["json_text"]), {"json_text": '{"a": [1, 2]}', "password": "pw"},
         {"method": "POST", "url": "https://brewpage.app/api/json?ns=my", "content_type": "application/json",
          "owner_token": "tok-1", "password": "pw", "body": '{"a": [1, 2]}'},
         "json", {"manageUrl": "https://brewpage.app/manage/json/my/abc123#k=bpm_FixtureKey0000000000000000000000"},
         "https://brewpage.app/manage/json/my/abc123#k=bpm_FixtureKey0000000000000000000000"),
        (2, ("create_kv_store", ["key", "value"]), {"key": "status", "value": "green"},
         {"method": "POST", "url": "https://brewpage.app/api/kv?ns=my", "content_type": "application/json",
          "owner_token": "tok-1", "password": None, "body": '{"key": "status", "value": "green"}'},
         "kv", {"manageUrl": "https://brewpage.app/manage/kv/my/abc123#k=bpm_FixtureKey0000000000000000000000"},
         "https://brewpage.app/manage/kv/my/abc123#k=bpm_FixtureKey0000000000000000000000"),
        (3, ("upload_file", ["path"]), {"path": "{tmp}/notes.txt"},
         {"method": "POST", "url": "https://brewpage.app/api/files?ns=my", "content_type": "multipart/form-data; boundary=B",
          "owner_token": "tok-1", "password": None,
          "body": '--B\r\nContent-Disposition: form-data; name="file"; filename="notes.txt"\r\n'
                  'Content-Type: text/plain\r\n\r\nhello\r\n--B--\r\n'},
         "files", {"manageUrl": "https://brewpage.app/manage/files/my/abc123#k=bpm_FixtureKey0000000000000000000000"},
         "https://brewpage.app/manage/files/my/abc123#k=bpm_FixtureKey0000000000000000000000"),
        (0, ("publish_page", ["content"]), {"content": "<p>again</p>"},
         {"method": "POST", "url": "https://brewpage.app/api/html?ns=my", "content_type": "application/json",
          "owner_token": "tok-1", "password": None, "body": '{"content": "<p>again</p>", "format": "html"}'},
         "html", {}, None),
    ],
    ids=["page", "json", "kv", "file", "page-without-minted-key"],
)
def test_tool_posts_exact_request_and_returns_links(tmp_path, tool_index, schema, args, expected_request, segment,
                                                    minted, management_link):
    # GIVEN a tool spec whose client answers every POST with the API reply: key-less managementLink, manageUrl if minted
    (tmp_path / "notes.txt").write_text("hello")
    seen = []
    tool = BrewPageToolSpec(client=_recording_client(201, _api_reply(segment, minted), seen)).to_tool_list()[tool_index]
    resolved = json.loads(json.dumps(args).replace("{tmp}", str(tmp_path)))

    # WHEN the agent calls the tool
    result = tool.call(**resolved).raw_output

    # THEN the schema and the single request match, and management_link is the keyed manageUrl, never the key-less page
    assert ((tool.metadata.name, tool.metadata.get_parameters_dict()["required"]), seen, result) == (schema, [expected_request], _result(management_link)), f"tool {tool.metadata.name} sent {seen} and returned {result}"


def test_tool_descriptions_tell_agent_to_hand_over_links():
    # GIVEN the tool spec as an agent receives it
    tools = BrewPageToolSpec(client=_recording_client(201, {}, [])).to_tool_list()

    # WHEN the agent reads the tool descriptions
    descriptions = [tool.metadata.description for tool in tools]

    # THEN every description ends with the hand-over rule for the page link, management link and owner token
    assert descriptions == [
        "Publish an HTML page or Markdown document on brewpage.app; returns its URL." + HANDOFF,
        "Host a JSON document on brewpage.app; returns a URL that serves it." + HANDOFF,
        "Create a key-value store on brewpage.app with one initial key; returns its URL." + HANDOFF,
        "Upload a local file (image, PDF, archive, document, HTML, Markdown) to brewpage.app; returns its URL." + HANDOFF,
    ], f"tool descriptions {descriptions}"


def test_api_error_becomes_tool_message():
    # GIVEN an API that rate-limits the caller
    seen = []
    tool = BrewPageToolSpec(client=_recording_client(429, {"message": "slow down"}, seen)).to_tool_list()[2]

    # WHEN the tool is called
    result = tool.call(key="k", value="v").raw_output

    # THEN the agent receives the error text instead of an exception
    assert result == {"error": 'BrewPage /api/kv failed with HTTP 429: {"message":"slow down"}'}, f"unexpected tool output {result!r}"



DOMAIN = {
    "hostname": "www.example.com", "displayHostname": "www.example.com", "apex": False,
    "createdAt": "2026-11-18T00:00:00Z", "status": "pending_dns", "serving": False, "suspended": False,
    "records": [
        {"type": "TXT", "name": "_brewpage.www.example.com", "host": "_brewpage.www",
         "value": "bp-verify=fixture123", "state": "missing"},
        {"type": "CNAME", "name": "www.example.com", "host": "www",
         "value": "domains.brewpage.app", "state": "missing"},
    ],
    "nextStep": "Create the DNS records, check once, then read status until active.",
}

@pytest.mark.parametrize(
    ("args", "reply_fields", "query", "body", "details"),
    [
        ({}, {"notices": [{"code": "owner-token-new", "message": "Save your owner token."}]}, "",
         '{"content": "<h1>Answers</h1>", "format": "html"}', {}),
        ({"state": None, "domain": None}, {"customDomain": {"status": "pending_dns"}}, "",
         '{"content": "<h1>Answers</h1>", "format": "html"}', {}),
        ({"state": {}}, {"ownerToken": None, "effectiveDeliveryMode": "subdomain",
                        "deliveryModeReason": "policy:state-declared", "deliveryNotice": "Page data uses its own address.",
                        "notices": []}, "",
         '{"content": "<h1>Answers</h1>", "format": "html", "state": {}}',
         {"delivery_mode": "subdomain", "delivery_mode_reason": "policy:state-declared",
          "delivery_notice": "Page data uses its own address.", "notices": []}),
        ({"state": {"collections": {"answers": {}}}}, {}, "",
         '{"content": "<h1>Answers</h1>", "format": "html", "state": {"collections": {"answers": {}}}}', {}),
        ({"domain": "www.example.com"}, {"customDomain": DOMAIN, "notices": []}, "&domain=www.example.com",
         '{"content": "<h1>Answers</h1>", "format": "html"}', {"custom_domain": DOMAIN, "notices": []}),
        ({"state": {"collections": {"answers": {}}}, "domain": "www.example.com"},
         {"customDomain": DOMAIN, "effectiveDeliveryMode": "subdomain", "notices": []}, "&domain=www.example.com",
         '{"content": "<h1>Answers</h1>", "format": "html", "state": {"collections": {"answers": {}}}}',
         {"custom_domain": DOMAIN, "delivery_mode": "subdomain", "notices": []}),
        ({"domain": "www.example.com"},
         {"notices": [{"code": "domain-needs-account", "message": "Link the owner token to a free profile."}]},
         "&domain=www.example.com", '{"content": "<h1>Answers</h1>", "format": "html"}',
         {"notices": [{"code": "domain-needs-account", "message": "Link the owner token to a free profile."}]}),
    ],
    ids=["absent", "null", "default-data", "declared-data", "domain", "data-and-domain", "domain-not-attached"],
)
def test_page_options_preserve_wire_receipts_and_owner_reuse(args, reply_fields, query, body, details):
    # GIVEN the page tool, exact legacy defaults and a service reply with optional feature outcomes.
    seen = []
    client = _recording_client(201, _api_reply("html", reply_fields), seen)
    tool = BrewPageToolSpec(client=client).to_tool_list()[0]
    schema = tool.metadata.get_parameters_dict()
    assert {"required": schema["required"],
            "defaults": {name: schema["properties"][name]["default"]
                         for name in ("format", "ttl_days", "password", "namespace", "state", "domain")}} == {
        "required": ["content"],
        "defaults": {"format": "html", "ttl_days": None, "password": None, "namespace": None,
                     "state": None, "domain": None},
    }, "Only content remains required; new page options leave existing defaults intact"

    # WHEN a page is published with omitted, null or explicitly configured options.
    result = tool.call(content="<h1>Answers</h1>", **args).raw_output

    # THEN one request carries state in JSON and domain in the query; actual optional outcomes survive.
    assert (seen, result, client.owner_token) == (
        [{"method": "POST", "url": "https://brewpage.app/api/html?ns=my" + query,
          "content_type": "application/json", "owner_token": "tok-1", "password": None, "body": body}],
        {**_result(None), **details},
        "tok-1",
    ), "Configured outcomes are additive, absent options preserve the exact receipt, and owner proof is retained"


@pytest.mark.parametrize(
    ("owner_token", "transport_parties", "expected_tokens"),
    [(None, 1, [None, "tok-1", "tok-1"]), ("tok-1", 2, ["tok-1", "tok-1", "tok-1"])],
    ids=["anonymous-bootstrap", "already-owned-parallel"],
)
def test_concurrent_publications_share_bootstrap_owner_without_serializing_owned_calls(
    monkeypatch, owner_token, transport_parties, expected_tokens
):
    # GIVEN both workers observe the same initial owner; owned requests must overlap at transport.
    monkeypatch.delenv("BREWPAGE_OWNER_TOKEN", raising=False)
    seen = []
    seen_lock = Lock()
    transport_gate = Barrier(transport_parties)

    def handler(request):
        token = request.headers.get("x-owner-token")
        with seen_lock:
            sequence = len(seen) + 1
            seen.append({"method": request.method, "url": str(request.url), "owner_token": token,
                         "body": json.loads(request.content)})
        transport_gate.wait(timeout=5)
        return httpx.Response(201, json=_api_reply("html", {"ownerToken": {None: f"tok-{sequence}"}.get(token)}))

    client = _ConcurrentOwnerClient(owner_token=owner_token, namespace="my", transport=httpx.MockTransport(handler))
    assert (client.owner_token, seen) == (owner_token, []), "Concurrent fixture starts with the exact owner and no requests"
    client.initial_owner_reads = Barrier(2)

    # WHEN two page creates start together, then a third create uses the retained owner.
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: client.publish_page("<p>same</p>", state={}), range(2)))
    transport_gate = Barrier(1)
    results.append(client.publish_page("<p>same</p>", state={}))
    client._http.close()

    # THEN one bootstrap owner covers every receipt; supplied-owner calls reach transport together.
    assert (seen, results, client.owner_token) == (
        [{"method": "POST", "url": "https://brewpage.app/api/html?ns=my", "owner_token": token,
          "body": {"content": "<p>same</p>", "format": "html", "state": {}}} for token in expected_tokens],
        [_result(None) for _ in range(3)], "tok-1",
    ), "Concurrent creates keep one owner, exact receipts and request count, while owned transport stays parallel"


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("BREWPAGE_LIVE") != "1", reason="set BREWPAGE_LIVE=1 to hit production")
def test_live_private_markdown_page():
    # GIVEN the real API and the private 'my' namespace
    tool = BrewPageToolSpec(client=BrewPageClient(namespace="my")).to_tool_list()[0]

    # WHEN a short Markdown page is published for one day
    result = tool.call(content="# llama-index-tools-brewpage smoke\n\nPrivate test page.", format="markdown", ttl_days=1).raw_output

    # THEN a private brewpage.app link, a keyed management link and an owner token come back
    shape = {
        "namespace": result["namespace"],
        "url": bool(re.fullmatch(r"https://([a-z0-9-]+\.)*brewpage\.app/\S+", result["url"])),
        "owner_token": bool(re.fullmatch(r"\S{16,}", result["owner_token"])),
        "management_link": bool(re.fullmatch(r"https://brewpage\.app/manage/html/my/\w+#k=bpm_[A-Za-z0-9]{32}",
                                             str(result["management_link"]))),
    }
    assert shape == {"namespace": "my", "url": True, "owner_token": True, "management_link": True}, f"live result {json.dumps(result)}"
