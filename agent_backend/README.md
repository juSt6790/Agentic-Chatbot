# agent_backend

My personal Flask service for the workspace assistant: one HTTP API that talks to the LLM, runs MCP-style tools (Gmail, Calendar, Slack, Docs, Notion, Trello, etc.), and keeps everything behind a unified auth token.

I run this next to a small React UI (`../frontend`) when I want a browser chat; the only route that UI needs is **`POST /chat`**.

## What I use it for

- Natural-language questions over email, calendar, docs, Slack, and the rest of the integrations wired in here.
- Trying prompts and tool routing locally before pointing anything else at it.

## Run it

From this folder (with your venv activated and `.env` filled in):

```bash
cd agent_backend
source ../.venv/bin/activate   # or your own venv path
python3 app.py
```

Default dev server: **http://127.0.0.1:8000** (see `app.py` / `app/cosi_app.py` if you change host or port).

Health check: `GET /health`

## Chat API (what matters for the UI)

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"query": "Hello", "session_id": "optional-uuid"}'
```

Responses are JSON (e.g. `message`, `data`, `success`, `type`, `chat_id`). The handler lives in `app/assistant_handler.py`.

## Stack (roughly)

- **Python 3**, **Flask**, **CORS** enabled for local frontends.
- **OpenAI** and/or **AWS Bedrock** (see `app/switches.py` and env vars).
- **MongoDB** and other clients under `clients/` — only what you configure will actually work.

## Env

Copy or adapt from whatever you already use: Mongo URI, OpenAI key, Bedrock bearer token if applicable, AWS region, etc. No secrets belong in git.

## Docs

Longer internal write-ups are still under `docs/` if I need to dig into architecture or testing — I don’t treat them as a product manual, just notes.

## Note

This tree was renamed from `unified_mcp` to **`agent_backend`** so it reads like my own repo layout. If you have old paths (systemd, CI), update them to match.

---

*Personal project — not a supported product.*
