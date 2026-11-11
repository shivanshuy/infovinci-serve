# infovinci-serve

Two services for local dev:

| Service | Command | Port | Purpose |
|---------|---------|------|---------|
| **Blog REST API** (this repo) | `poetry run infovinci-serve` | `8080` | `GET /posts`, `GET /post/{id}`, `GET /health` |
| **LangGraph Agent Server** | `langgraph dev` | `2024` | Chat agent, threads, Studio — see [LangGraph local server](https://docs.langchain.com/oss/python/langgraph/local-server) |

The Infovinci UI proxies `/api/*` → blog API and `/agent/*` → Agent Server.

## Install

```bash
cd infovinci-serve
poetry install
cp .env.example .env
# Add LANGSMITH_API_KEY to .env (required for langgraph dev)
```

## 1. Blog REST API

```bash
poetry run infovinci-serve
```

Endpoints:

- `GET /health`
- `GET /posts?page=1&pageSize=10&q=search`
- `GET /post/{uuid}`

## 2. LangGraph Agent Server (chat + RAG)

Embed blog posts into Chroma (once, or after content changes):

```bash
poetry run infovinci-embed-blogs
```

Start Ollama and the agent server:

```bash
ollama run llama3.1:8b
# Use --no-reload on Windows if chat stalls after Ollama (Chroma writes trigger hot reload).
poetry run langgraph dev --no-reload
```

- API: http://127.0.0.1:2024 (OpenAPI at `/docs`)
- Studio: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

Graph id in `langgraph.json` is **`agent`**. Stream via `POST /runs/stream` with `"assistant_id": "agent"`.

## 3. Infovinci frontend

```bash
cd ../infovinci
npm run dev
```

Vite proxies `/api` → `:8080` and `/agent` → `:2024`.

## Environment

| Variable | Default | Used by |
|----------|---------|---------|
| `LANGSMITH_API_KEY` | — | `langgraph dev` |
| `INFOVINCI_CHAT_MODEL` | `ollama:llama3.1:8b` | Agent graph |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Agent graph |
| `INFOVINCI_SKIP_RAG` | unset | Set `1` to skip Chroma retrieval (faster local dev) |
| `INFOVINCI_VECTOR_DB_PATH` | `data/infovinci_chroma` | RAG in graph |
| `CHAT_BFF_HOST` / `CHAT_BFF_PORT` | `127.0.0.1` / `8080` | Blog API |
| `CORS_ALLOW_ORIGINS` | Vite dev origins | Blog API |
