# projectChat

A personal project: a **Flask** backend that orchestrates an LLM plus a big pile of workspace tools (email, calendar, docs, Slack, Notion, Trello, etc.), and a small **React + Vite** UI that talks to it over HTTP. I use this to experiment with agents and to have one place to ask questions across the integrations I’ve wired up.

---

## Table of contents

- [What this is](#what-this-is)
- [What’s in the repo](#whats-in-the-repo)
- [Features (high level)](#features-high-level)
- [Platforms & tools](#platforms--tools)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [HTTP API](#http-api)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Docs & tests](#docs--tests)
- [Notes](#notes)

---

## What this is

I got tired of jumping between Gmail, Calendar, Slack, Docs, and the rest every time I needed context. This repo is my attempt to **expose those systems through one assistant**: natural-language in, tool calls + structured JSON out. The heavy lifting lives in `agent_backend/` (Flask, Mongo, Bedrock/OpenAI, MCP-style services). The `frontend/` folder is optional chrome—a fullscreen chat that hits `POST /chat` so I don’t have to curl everything.

This is **not** a product, SLA, or supported service. It’s my sandbox; breakages are expected if I change env or upstream APIs.

---

## What’s in the repo

| Part | Role |
|------|------|
| **`agent_backend/`** | Flask app (`app.py` → `app/cosi_app.py`), `/chat`, tool registry, clients, services, docs. |
| **`frontend/`** | React + TypeScript + Vite chat UI; dev server proxies `/chat` to the backend. |
| **`.venv/`** | Local Python venv—**not** committed. Create your own at the repo root or wherever you prefer. |

---

## Features (high level)

- **Natural language** → model decides which tools to call; multi-step loops until it has an answer.
- **Many integrations** behind one auth model (unified token on `/chat`).
- **Semantic / vector-style context** where configured (see backend docs).
- **Optional UI** for quick prompts without Postman.
- **Personalization hooks** (e.g. style profiles) when the data exists in Mongo.

---

## Platforms & tools

The backend bundles a large set of tools (search, send, create, update) across roughly:

| Area | Examples |
|------|----------|
| **Gmail** | Search, drafts, send, attachments |
| **Google Calendar** | Events, availability, Meet / transcript flows where enabled |
| **Slack** | Channels, DMs, send/fetch |
| **Google Docs / Sheets / Slides** | Read, write, list |
| **Notion** | Pages, databases, blocks |
| **Trello** | Boards, cards, lists |
| **Web** | Public web search tool when configured |

Exact tool names and behavior are in `agent_backend/app/server_parts.py`, `app/structures.py`, and the `services/` + `clients/` trees. Counts change when I add or trim integrations.

---

## Architecture

Rough data flow:

```
┌─────────────────────┐
│  frontend/ (React)  │  optional; or any HTTP client
└──────────┬──────────┘
           │ POST /chat  +  Authorization: Bearer …
           ▼
┌─────────────────────┐
│  Flask (cosi_app)   │  CORS open for local dev
│  assistant_handler  │
└──────────┬──────────┘
           │ invoke_ai_with_fallback (OpenAI / Bedrock per switches)
           ▼
┌─────────────────────┐     ┌──────────────────┐
│  Tool loop          │────▶│  services/       │
│  tools[name](…)     │     │  clients/        │
└─────────────────────┘     └────────┬─────────┘
                                     ▼
                            Mongo, external APIs, vectors, …
```

- **Entry**: `agent_backend/app.py` runs the Flask app.
- **Chat route**: `agent_backend/app/assistant_handler.py` → `POST /chat`.
- **Orchestration & model calls**: `agent_backend/app/cosi_app.py` and related helpers.
- **Switches** (e.g. Bedrock vs OpenAI): `agent_backend/app/switches.py`.

---

## Quick start

**1. Python backend**

```bash
cd projectChat
python3 -m venv .venv
source .venv/bin/activate
pip install -r agent_backend/requirements.txt
```

Copy secrets from `agent_backend/.env.example` to `agent_backend/.env` and fill in real values (never commit `.env`).

```bash
cd agent_backend
python3 app.py
```

By default the app listens on **port 8000** (see `app.py` if you need another host/port).

**2. Frontend (optional)**

```bash
cd frontend
npm install
npm run dev
```

Open the printed URL (e.g. `http://127.0.0.1:5173`). Use **Connect** to paste the same Bearer token the backend expects. In dev, Vite proxies `/chat` to `http://127.0.0.1:8000`.

**3. Health**

```bash
curl -s http://127.0.0.1:8000/health
```

---

## HTTP API

**Chat (what the UI uses)**

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"query": "Hello", "session_id": "optional-string-or-uuid"}'
```

Responses are JSON (`message`, `data`, `success`, `type`, `chat_id`, etc.—see handler for the full shape).

**Multipart** uploads (images/PDFs) are supported by the same route when you use `multipart/form-data` and a `query` field; see `agent_backend/app/assistant_handler.py` and the Postman doc if you need the exact form.

---

## Configuration

- **Env files**: keep them **local**—`.gitignore` covers `.env` and variants. Use `agent_backend/.env.example` as a checklist of names, not real values.
- **Model routing**: Bedrock vs OpenAI and fallbacks are controlled via env and `app/switches.py`.
- **Mongo / AWS / OAuth**: only the integrations you configure will actually work; missing creds usually surface as tool errors in the response.

---

## Project layout

```
projectChat/
├── README.md                 ← you are here
├── .gitignore
├── .venv/                    # local only
├── agent_backend/
│   ├── app.py
│   ├── app/                  # Flask routes, cosi_app, handlers
│   ├── clients/              # DB & external APIs
│   ├── services/             # MCP-style service modules
│   ├── config/
│   ├── docs/                 # long-form architecture & testing notes
│   ├── requirements.txt
│   └── ...
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
```

---

## Docs & tests

- Deeper architecture, endpoint notes, and debugging: **`agent_backend/docs/`** (start with `DOCUMENTATION_INDEX.md` if overwhelmed).
- Smoke / integration scripts: **`agent_backend/tests/`** (read each file before running—some expect env and keys).

---

## Notes

- If you fork this, treat **secrets** as radioactive: rotate anything that ever lived in a committed file or a public remote.
- Questions and PRs aren’t expected—this is primarily for my own machines—but you’re welcome to read and adapt.

---

*Personal project — use at your own risk.*
