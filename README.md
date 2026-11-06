# llama-index-tools-brewpage

LlamaIndex tool spec that publishes HTML, Markdown, JSON, key-value stores and files to [BrewPage](https://brewpage.app) and returns a shareable URL. Free, no account, no API key.

<p>
<a href="https://pypi.org/project/llama-index-tools-brewpage/"><img height="18" alt="PyPI" src="https://img.shields.io/pypi/v/llama-index-tools-brewpage"></a>
<a href="https://github.com/kochetkov-ma/llama-index-tools-brewpage/blob/main/LICENSE"><img height="18" alt="License" src="https://img.shields.io/pypi/l/llama-index-tools-brewpage"></a>
<a href="https://github.com/kochetkov-ma/llama-index-tools-brewpage/actions/workflows/ci.yml"><img height="18" alt="CI" src="https://github.com/kochetkov-ma/llama-index-tools-brewpage/actions/workflows/ci.yml/badge.svg"></a>
</p>

## Install

```bash
pip install llama-index-tools-brewpage
```

## Usage

```python
from llama_index.tools.brewpage import BrewPageToolSpec

spec = BrewPageToolSpec()
page = spec.publish_page("# Weekly report\n\nAll green.", format="markdown")
print(page["url"])
```

With an agent (any function-calling LLM):

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.tools.brewpage import BrewPageToolSpec

agent = FunctionAgent(tools=BrewPageToolSpec().to_tool_list(), llm=llm)
response = await agent.run("Write a one-page HTML changelog and publish it.")
```

## Tools

| Tool | API | Result |
|---|---|---|
| `publish_page` | `POST /api/html` | HTML or Markdown page URL |
| `publish_json` | `POST /api/json` | JSON document URL |
| `create_kv_store` | `POST /api/kv` | Key-value store URL, one initial key |
| `upload_file` | `POST /api/files` | Download or page URL for a local file |

Every tool also takes `ttl_days`, `password` and `namespace` and returns a dict with `url`, `id`, `namespace`, `owner_token`, `management_link`, `expires_at`. API errors (rate limits, refused content) come back as `{"error": "..."}` so the agent can react.

The first call gets an owner token; the spec reuses it, so all publications share one owner. To keep it across runs, pass it in:

```python
from llama_index.tools.brewpage import BrewPageClient, BrewPageToolSpec

spec = BrewPageToolSpec(client=BrewPageClient(owner_token="..."))
```

Environment: `BREWPAGE_OWNER_TOKEN`, `BREWPAGE_NAMESPACE`, `BREWPAGE_BASE_URL` (default `https://brewpage.app`).

## Limits

- Hosting is temporary: publications expire after 15 days by default, `ttl_days` 1-30.
- Without `namespace` a publication is private: unlisted and not indexed, but anyone with the link can open it. Add `password` to restrict reads.
- `namespace="public"` lists pages in the public gallery and search engines. Never put secrets or personal data there.
- Size caps: HTML 5 MB, JSON 1 MB, KV value 1 MB, file 5 MB (video 20 MB). Current values: [brewpage.app/api/limits](https://brewpage.app/api/limits).

## Related

- [BrewPage](https://brewpage.app) and its [API](https://brewpage.app/api)
- [API reference](https://kochetkov-ma.github.io/brewpage-openapi/)
- [langchain-brewpage](https://github.com/kochetkov-ma/langchain-brewpage): the same tools for LangChain ([PyPI](https://pypi.org/project/langchain-brewpage/))
- [brewpage-publish-plugins](https://github.com/kochetkov-ma/brewpage-publish-plugins): other integrations
- [brewpage-mcp](https://www.npmjs.com/package/brewpage-mcp): MCP server on npm; source and OpenAPI contract in [brewpage-openapi](https://github.com/kochetkov-ma/brewpage-openapi)
- [brewpage-action](https://github.com/kochetkov-ma/brewpage-action): GitHub Action that publishes CI artifacts ([Marketplace](https://github.com/marketplace/actions/publish-to-brewpage))
- [brewpage-cookbook](https://github.com/kochetkov-ma/brewpage-cookbook): interactive recipes published on BrewPage
- [brewpage-obsidian](https://github.com/kochetkov-ma/brewpage-obsidian): Obsidian plugin that publishes notes ([Obsidian community](https://community.obsidian.md/plugins/brewpage-publisher))
- [brewpage-browser-extension](https://github.com/kochetkov-ma/brewpage-browser-extension): browser extension that publishes pages, selections and files
- [brewpage-codex-plugin](https://github.com/kochetkov-ma/brewpage-codex-plugin): Codex plugin with the publishing skill and remote MCP

## Development

```bash
uv sync --group test
uv run pytest
BREWPAGE_LIVE=1 uv run pytest -m live   # publishes one private page on production
```

## Support

info@brewpage.app or [GitHub issues](https://github.com/kochetkov-ma/llama-index-tools-brewpage/issues).

## License

[MIT](https://github.com/kochetkov-ma/llama-index-tools-brewpage/blob/main/LICENSE)
