# projectChat

> **One-liner:** Tool-orchestrated LLM backend with **MCP-style tool surfaces**, **hybrid RAG** (Qdrant + embeddings + Mongo), and a **React** chat UI—built to route real workspace APIs (Gmail, Slack, Calendar, Docs, Notion, Trello, …) behind a single `/chat` contract.

Personal codebase; not a product. The interesting bits are the **routing**, **retrieval**, and **integration** discipline—not a notebook demo.

---

## Overview

Built an **agentic backend** (Flask) where the model **plans and executes multi-step tool loops** against a large, versioned tool registry—same architectural idea as “supervisor routes work to specialists,” except the “specialists” are **typed tools** (HTTP + SaaS APIs + DB), not separate LLM agents. That keeps cost predictable and avoids consensus-hallucination between models.

Stack in plain terms:

- **Orchestration:** `POST /chat` → `assistant_handler` → `invoke_ai_with_fallback` (OpenAI and/or **AWS Bedrock** via switches in `app/switches.py`). Multi-turn **tool_use / tool_result** loop until `end_turn` or limits—classic **ReAct-style** execution, production-style error boundaries around tool dispatch.
- **Tools (MCP-flavored):** **`FastMCP`** per domain in `app/server.py` (Gmail, Calendar, Slack, Docs, Sheets, Slides, Notion, Trello, …), unified in **`server_parts.py`** with JSON schemas in **`structures.py`**—one **function-calling** surface for the LLM.
- **Hybrid RAG:** **`vector_context_search`** → **`clients/qdrant_vector_client.py`**: query embeddings (**OpenAI** `text-embedding-3-small`, L2-normalized), **Qdrant** per-domain collections, similarity **threshold** (`VECTOR_THRESHOLD`) to cap noise; Mongo stores **`embedding_text`** (read) vs **`embedding_vector`** (match) with careful **projections** (see `docs/MONGODB_PROJECTION_FIX.md`). Not “slap Chroma on a PDF folder”—**tenant-scoped**, **multi-collection**, wired into the same auth as the rest of the app.
- **Context budget:** **Tool filtering** (`utils/tool_filter.py`, documented in `docs/TOOL_FILTERING_FLOW_EXPLANATION.md`) so we don’t feed 130+ tools on every request when the query only needs email + calendar.
- **Frontend:** **Vite + React + TypeScript** SPA; Bearer auth to backend; dev **proxy** to `/chat`.

Designed with **production-oriented** constraints in mind: explicit **fallback** between providers, **structured** assistant responses (`success`, `type`, `message`, `data`), **health** endpoint, **CORS** for local dev, **secrets** out of git (`.gitignore` + no keys in source).

---

## Engineering decisions (trade-offs, not buzzwords)

**Why a single orchestrator + tool loop instead of a multi-agent graph (e.g. LangGraph-style swarm)?**  
For this problem, most “agents” would share the same memory and the same APIs—extra LLM hops mostly add **latency**, **cost**, and **drift** without improving grounding. One strong model with a **strict tool schema** and **retrieval** gives better **traceability**: every external effect goes through a named tool with arguments you can log. If I need true role separation later, I’d split at **process** boundaries (e.g. isolated worker + queue), not three chatty models in one loop.

**Why Qdrant + embeddings instead of only Mongo regex / full-text?**  
Cross-platform “what’s related to this *concept*?” breaks keyword search. Vector recall is **fuzzy by design**—so I combine it with **thresholding**, **per-tool collections**, and **prompt rules** (when to call `vector_context_search`, single **rephrase retry** if recall is empty) to reduce garbage-in-garbage-out. Mongo holds canonical text and metadata; Qdrant holds **search geometry**. That’s **hybrid RAG** in practice: structured filters from tools + semantic recall from vectors.

**Provider fallback (OpenAI ↔ Bedrock)?**  
`invoke_ai_with_fallback` centralizes policy: OpenAI-only, Bedrock-only, or **quota-driven fallback**. Trade-off: **two stacks to test**, but I don’t go dark when one API throttles—important for anything you’d demo on a bad network day.

**Hallucination & grounding:**  
The assistant is **tool-grounded** for side effects (send email, create event, …). For retrieval, I **don’t** pretend Qdrant hits are ground truth—I expose them as **context** and keep **tool errors** structured so the UI/model can recover (see `utils/error_handler.py` patterns in the codebase).

**What I’d measure in a “real” prod line:** latency p95 per `/chat`, tool error rate, empty-retrieval rate on `vector_context_search`, token usage per session (hooks exist in-repo for usage logging—see `cosi_app` / token clients). This repo is optimized for **debuggability** first, dashboards second.

---

## Table of contents

- [Overview](#overview) · [Engineering decisions](#engineering-decisions-trade-offs-not-buzzwords)
- [MCP-style design & vector search](#mcp-style-design--vector-search)
- [Platforms & tools](#platforms--tools)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [HTTP API](#http-api)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Docs & tests](#docs--tests)
- [Notes](#notes)

---

## MCP-style design & vector search

Goal: treat each SaaS as a **modular tool surface** (MCP-style), not a spaghetti of ad-hoc `requests` in the handler.

### MCP patterns in this repo

- **`FastMCP`** (`mcp.server.fastmcp`) models **one logical server per domain** in `agent_backend/app/server.py`.
- Everything lands in one **registry** (`app/server_parts.py`) + **schemas** (`app/structures.py`) so the LLM sees a **single function-calling contract**.
- **Tool filtering** shrinks the active set per request so context and latency stay sane.

### Vector search (Qdrant + embeddings)

- Tool name: **`vector_context_search`**.
- Implementation: **`clients/qdrant_vector_client.py`** — **Qdrant** (`QDRANT_URL`), **OpenAI** embeddings, normalized vectors, **similarity threshold**, **per-domain collection map**, auth aligned with the rest of the stack.
- **Mongo:** text + vectors with **projection discipline** (don’t fetch huge embedding arrays unless needed).
- **Prompting:** `assistant_handler.py` instructs *when* to retrieve and when to **retry once** with rephrasing—intentional policy, not accidental spam.

Optional: **Bedrock Titan** embedding experiments documented in `docs/TEST_EMBEDDINGS_README.md` (separate from the live Qdrant path).

If Qdrant/embeddings aren’t configured, the client **fails loud**—no fake “semantic” results.

---

## Platforms & tools

| Area | Examples |
|------|----------|
| **Gmail** | Search, drafts, send, attachments |
| **Google Calendar** | Events, availability, Meet / transcripts (where enabled) |
| **Slack** | Channels, DMs, read/send |
| **Google Docs / Sheets / Slides** | Read/write/list |
| **Notion** | Pages, databases, blocks |
| **Trello** | Boards, cards, lists |
| **Web** | Public web search when configured |

Source of truth: `app/server_parts.py`, `app/structures.py`, `services/`, `clients/`.

---

## Architecture

```
┌─────────────────────┐
│  frontend/ (React)  │  optional; or any HTTP client
└──────────┬──────────┘
           │ POST /chat  +  Authorization: Bearer …
           ▼
┌─────────────────────┐
│  Flask (cosi_app)   │
│  assistant_handler  │
└──────────┬──────────┘
           │ invoke_ai_with_fallback (OpenAI / Bedrock)
           ▼
┌─────────────────────┐     ┌──────────────────────────────┐
│  Tool loop          │────▶│  services/ + FastMCP modules │
│  tools[name](…)     │     │  clients/ (Mongo, APIs, …)   │
└─────────────────────┘     └────────┬─────────────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
       SaaS APIs               MongoDB              Qdrant (vector_context_search)
```

- **Run:** `agent_backend/app.py`
- **Chat:** `agent_backend/app/assistant_handler.py`
- **Model & fallback:** `agent_backend/app/cosi_app.py`
- **Switches:** `agent_backend/app/switches.py`

---

## Quick start

**Backend**

```bash
cd projectChat
python3 -m venv .venv
source .venv/bin/activate
pip install -r agent_backend/requirements.txt
cp agent_backend/.env.example agent_backend/.env   # then edit — never commit secrets
cd agent_backend && python3 app.py
```

Default: **http://127.0.0.1:8000** (check `app.py` for overrides).

**Frontend (optional)**

```bash
cd frontend && npm install && npm run dev
```

Paste Bearer token in **Connect**. Vite dev server proxies `/chat` → backend.

**Health**

```bash
curl -s http://127.0.0.1:8000/health
```

---

## HTTP API

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"query": "Hello", "session_id": "optional-string-or-uuid"}'
```

Multipart (images/PDFs): same route, `multipart/form-data` + `query` — details in `assistant_handler.py` and `docs/POSTMAN_TESTING_GUIDE.md`.

---

## Configuration

- **`.env`**: local only; see `agent_backend/.env.example` for variable names.
- **Models:** `app/switches.py` + env (`BEDROCK_MODEL_ID`, `OPENAI_MODEL`, …).
- **Vector:** `QDRANT_URL`, `VECTOR_THRESHOLD`, OpenAI key for embeddings.
- **Integrations:** only what you configure will work; failures surface as structured tool errors where possible.

---

## Project layout

```
projectChat/
├── README.md
├── .gitignore
├── .venv/                    # local
├── agent_backend/
│   ├── app.py
│   ├── app/                  # Flask, handlers, cosi_app, server_parts
│   ├── clients/              # Qdrant, Mongo, …
│   ├── services/
│   ├── docs/
│   └── requirements.txt
└── frontend/
    ├── vite.config.ts
    └── src/
```

---

## Docs & tests

- **Index:** `agent_backend/docs/DOCUMENTATION_INDEX.md`
- **Tests:** `agent_backend/tests/` — read before running (keys/env required for some).

---

## Notes

- Renamed upstream tree from `unified_mcp` → **`agent_backend`** for clarity.
- If you fork: **rotate** any credential that ever touched a public remote.

---

*Personal / research-grade code — use at your own risk.*
