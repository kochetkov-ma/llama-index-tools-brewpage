# llama-index-tools-brewpage

LlamaIndex tool spec for [BrewPage](https://brewpage.app): let an agent publish an HTML page, a Markdown document, a JSON document, a key-value store or a file and get back a shareable URL. No account and no API key are needed.

Each call returns the URL plus an owner token. The spec reuses that token for later publications, so everything the agent creates belongs to one owner. Publications are private and unlisted by default and expire after 15 days unless you set `ttl_days` (1-30).

## Install

```bash
pip install llama-index-tools-brewpage
```

## Tools

`BrewPageToolSpec().to_tool_list()` returns:

| Tool | API | Use |
|---|---|---|
| `publish_page` | `POST /api/html` | HTML or Markdown page -> URL |
| `publish_json` | `POST /api/json` | JSON document -> URL |
| `create_kv_store` | `POST /api/kv` | Key-value store with one initial key -> URL |
| `upload_file` | `POST /api/files` | Local file -> download or page URL |

Every tool also accepts `ttl_days`, `password` and `namespace`. Leave `namespace` empty for a private link. `public` lists pages in the public gallery and search engines, so never put secrets or personal data there.

## Usage

```python
from llama_index.tools.brewpage import BrewPageToolSpec

spec = BrewPageToolSpec()
page = spec.publish_page("# Weekly report\n\nAll green.", format="markdown")
print(page["url"], page["owner_token"])
```

With an agent:

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.tools.brewpage import BrewPageToolSpec

agent = FunctionAgent(tools=BrewPageToolSpec().to_tool_list(), llm=llm)  # any function-calling LLM
response = await agent.run("Write a one-page HTML changelog and publish it.")
```

Each tool returns a dict: `url`, `id`, `namespace`, `owner_token`, `management_link`, `expires_at`. API errors (rate limits, refused content) come back as `{"error": "..."}` so the agent can react.

## Configuration

| Setting | Constructor | Environment |
|---|---|---|
| API base URL | `BrewPageClient(base_url=...)` | `BREWPAGE_BASE_URL` (default `https://brewpage.app`) |
| Owner token to reuse | `BrewPageClient(owner_token=...)` | `BREWPAGE_OWNER_TOKEN` |
| Default namespace | `BrewPageClient(namespace=...)` | `BREWPAGE_NAMESPACE` |

```python
from llama_index.tools.brewpage import BrewPageClient, BrewPageToolSpec

spec = BrewPageToolSpec(client=BrewPageClient(owner_token="..."))
```

## Links

- API reference: https://kochetkov-ma.github.io/brewpage-openapi/
- OpenAPI contract: https://github.com/kochetkov-ma/brewpage-openapi
- Limits and terms: https://brewpage.app

## Development

```bash
uv sync --group test
uv run pytest
BREWPAGE_LIVE=1 uv run pytest -m live   # one private page on production
```

## License

MIT
