# System Overview for AI Understanding

Use this document to give any AI a concise understanding of this codebase: how the LLM is used, where updates vs retrieval live, and how imports and structures are organized.

---

## 1. High-Level Architecture

- **App entry / LLM orchestration**: `app/cosi_app.py` — Flask app, Bedrock/OpenAI invocation, conversation memory, summarization.
- **HTTP handlers**: `app/assistant_handler.py` (`/chat`), `app/autopilot_handler.py` (`/autoPilot`, `/autoPilot/execute`). They use the app’s `invoke_ai_with_fallback`, `tools`, and `function_defs`.
- **Update operations (write/API side)**: Implemented in `services/*.py` (Gmail, Calendar, Slack, Docs, Sheets, Slides, Notion, Trello MCPs). These are the real “do something” implementations (send email, create event, update doc, etc.).
- **Retrieval (read side)**: Implemented in `clients/*.py`. Many “search/list/get” flows use MongoDB-backed clients (`mongo_email_client`, `mongo_docs_client`, `mongo_calendar_client`, etc.) and other clients (`qdrant_vector_client`, `mongo_briefing_client`, etc.) instead of calling external APIs directly from the chat path.
- **Wiring**: `app/server.py` imports from both `services/*` and `clients/*`, defines the MCP-style tool functions (e.g. `send_email`, `create_event`, `list_databases`), and re-exports them. `app/server_parts.py` re-imports from `server.py` and from the Mongo/vector clients, then builds the **tools registry** (name → callable) used by the chat loop.
- **Tool schemas (for the LLM)**: `app/structures.py` holds the static **function_defs** (name, description, parameters). The runtime **tools** dict (name → callable) is built in `server_parts.py`; `structures.py` only has a placeholder `tools = {}`.

So: **services/** = updation (APIs, MCPs), **clients/** = retrieval (Mongo, vector, etc.), **server.py** = glue that exposes both as tools, **server_parts.py** = tools registry + retrieval wiring for the app.

---

## 2. How the LLM Is Used (`app/cosi_app.py`)

- **Unified API**: The app uses a single internal “Bedrock-style” body: `system`, `messages`, `tools`, `temperature`, `max_tokens`. Both AWS Bedrock and OpenAI are supported via a wrapper so the rest of the app does not care which provider runs.
- **Routing**: `invoke_ai_with_fallback(body, token=..., purpose=..., ip_address=..., start_time=...)`:
  - **Mode 0**: OpenAI only (no fallback).
  - **Mode 1**: Try OpenAI; on 429/quota errors, fall back to Bedrock.
  - **Mode 2**: Bedrock only.
- **Bedrock**: `invoke_bedrock(body, ...)` — POST to `https://bedrock-runtime.{REGION}.amazonaws.com/model/{BEDROCK_MODEL_ID}/invoke`, auth via `AWS_BEARER_TOKEN_BEDROCK`, exponential backoff on 429.
- **OpenAI**: `invoke_openai(body, ...)` — translates Bedrock-style messages/tools into OpenAI format (including image content and tool_use/tool_result), calls `client.chat.completions.create(..., stream=True)`, then normalizes the streamed response back into Bedrock-like `content` blocks and `stop_reason` (`tool_use` or `end_turn`). Token usage is estimated and attached as `_token_usage` on the result.
- **Conversation memory**: In-memory `user_conversations` (deque, maxlen 12) and `long_term_memory` (list of summaries). When the deque is full, the oldest messages are summarized via the same LLM (`summarize_conversation`) and the result is stored in `long_term_memory`; that summary is then injected as `[PAST SUMMARY]` text in later requests.
- **Personality / user**: User personality (email/Slack style) and profile come from `get_user_personality_profile(token)` and `get_user_profile_collection(token)` (backed by `clients/mongo_personalization_client`). They are injected into the system prompt in `assistant_handler`.

Snippet — fallback and routing:

```python
# cosi_app.py (concept)
def invoke_ai_with_fallback(body, token=None, purpose="cosilive", ip_address=None, start_time=None):
    bedrock_mode = switches.USE_BEDROCK_FALLBACK
    if bedrock_mode == 2:
        return invoke_bedrock(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
    if bedrock_mode == 0:
        return invoke_openai(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
    try:
        return invoke_openai(...)
    except (RateLimitError, APIError) as e:
        if "429" in str(e).lower() or "quota" in str(e).lower():
            switches.USE_BEDROCK_FALLBACK = 1
            return invoke_bedrock(...)
        raise
```

Snippet — summarization (same LLM, internal call):

```python
# cosi_app.py
def summarize_conversation(messages, token=None):
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    # ... build summary_prompt with JSON format ...
    body = {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 1000, "temperature": 0.2, "messages": [...]}
    response = invoke_ai_with_fallback(body, token=token, purpose="cosilive", ip_address=None)
    # parse JSON from response content and return
```

---

## 3. Imports and Where Things Live

**`app/cosi_app.py`**

- `from app.server_parts import *` — brings in all symbols re-exported by server_parts (update functions, error helpers, Mongo/vector clients, and the **tools** registry).
- `from app.structures import function_defs, tools as structures_tools` — schemas only; the real callable registry is **tools** from server_parts (imported again later as `from app.server_parts import tools` and `from app.structures import function_defs`).
- Also: `invoke_ai_with_fallback`, `invoke_bedrock`, `invoke_openai`, token counting, `get_token`, user cache, personality/profile helpers, and at the end `from app import assistant_handler, autopilot_handler` so routes register.

**`app/server_parts.py`**

- Imports **update** logic from `app.server`: e.g. `send_email`, `draft_email`, `create_event`, `update_calendar_event`, Slack/Notion/Trello/Docs/Sheets/Slides tools. Many commented imports are “removed - now using MongoDB” (retrieval moved to clients).
- Imports **retrieval** from clients:
  - `clients.mongo_email_client`: `mongo_query_emails`, `mongo_get_emails`
  - `clients.mongo_docs_client`: `mongo_search_docs`, `mongo_query_docs`, `mongo_get_docs`, `search_docs_by_date`, `list_docs`
  - `clients.mongo_calendar_client`: `mongo_search_events`, `mongo_query_events`, `mongo_get_events`
  - `clients.mongo_briefing_client`: `get_latest_briefing`, `get_all_latest_briefings`
  - `clients.qdrant_vector_client`: `vector_context_search`
  - `clients.db_method`: `get_distinct_gmail_senders`, `user_info`
  - `clients.mongo_personalization_client`: `get_user_personality`, `get_user_profile_collection`
  - `clients.mongo_history_client`: `save_chat_history`
- Imports `wrap_tool_execution`, `handle_api_error`, etc. from `utils.error_handler`.
- Builds **tools** dict: maps tool name (string) to a lambda that calls the right function (e.g. `"search_emails": lambda **kwargs: mongo_query_emails(**kwargs)`, `"create_event": lambda **kwargs: create_event(**kwargs)`). So retrieval tools point to Mongo/vector clients; update tools point to server.py (which uses services).

**`app/structures.py`**

- Only data: **function_defs** is a long list of dicts, each with `name`, `description`, `parameters` (JSON schema). Used to build `claude_tools` in the handler (name, description, input_schema).
- **tools** in structures is just `tools = {}`; the real registry is in server_parts.

**`app/server.py`**

- Imports MCP/service implementations from `services/*` (gmail_mcp, calendar_mcp, slack_mcp, docs_mcp, sheets_mcp, slides_mcp, notion_mcp, trello_mcp) and from `clients/mongo_*` for email/docs/calendar retrieval.
- Defines FastMCP instances and `@mcp_*.tool()` functions that delegate to those services (e.g. `send_email` → `gmail_send_email`, `list_databases` → `notion_list_databases`). So **server.py** is the single place that ties **services** (updation) and **clients** (retrieval) into the tool names used by the app.

---

## 4. Chat Loop and Tool Execution (`app/assistant_handler.py`)

- **Route**: `POST /chat`. Uses `get_token()`, builds user context (contacts, personality, profile), handles multipart (query + optional files). Image/PDF analysis is done by building a Bedrock-style body and calling `invoke_ai_with_fallback` once per file.
- **Conversation context**: Short-term = `user_conversations[token]` (deque). When full, oldest messages are summarized (same as in cosi_app), summaries go to `long_term_memory[token]`, and up to 2 previous summaries + current summary are injected as `[PAST SUMMARY]` / `[PAST CONTEXT]` user messages. Then the current `combined_query` is appended.
- **Tools for this request**: Either all of **function_defs** or a filtered subset (e.g. `filter_tools(..., max_tools=20)`) is turned into **claude_tools** (name, description, input_schema). The **body** is `system`, `messages`, `tools`: claude_tools, plus max_tokens/temperature.
- **Loop**: In a `while step_count < max_steps` loop:
  - Call `invoke_ai_with_fallback(body, token=..., ...)`.
  - If `stop_reason == "tool_use"`: collect all `tool_use` blocks; for each, `args["token"] = token`, then call `wrap_tool_execution(tool_func=tools[name], tool_name=name, args=args, user_id=token)`. Append `tool_result` blocks (JSON-serialized result) with the same `tool_use_id`. Append assistant turn (content with tool_use blocks) and user turn (tool_result blocks) to **messages**, update **body["messages"]**, increment step, continue.
  - If not tool_use: treat content as final text; parse JSON from the text; add ui_hint, chat_id, etc.; optionally save history and token usage; return JSON response.

Snippet — tool execution and appending back to the conversation:

```python
# assistant_handler.py
if stop_reason == "tool_use":
    tool_use_blocks = [b for b in content if b.get("type") == "tool_use"]
    tool_result_blocks = []
    for block in tool_use_blocks:
        name = block.get("name")
        args = block.get("input", {})
        args["token"] = token
        result = wrap_tool_execution(tool_func=tools[name], tool_name=name, args=args, user_id=token)
        tool_result_blocks.append({
            "type": "tool_result",
            "tool_use_id": block.get("id"),
            "content": [{"type": "text", "text": json.dumps(result)}],
        })
    messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content": tool_result_blocks})
    body["messages"] = messages
    step_count += 1
    continue
```

So: **tools** (from server_parts) and **function_defs** (from structures) are the two inputs for the LLM tool loop; **services** perform the actual updates; **clients** perform the actual retrieval when a tool is “search/get/list” style.

---

## 5. Services (Updation) — Summary

| Service file         | Role |
|----------------------|------|
| `services/gmail_mcp.py`     | Gmail: send, draft, labels, modify message (used by server.py; search/list often via mongo_email_client). |
| `services/calendar_mcp.py`  | Calendar: create/delete/update event, search (server also uses mongo_calendar_client for query/get). |
| `services/slack_mcp.py`     | Slack: channels, messages, DMs, pin, invite, etc. |
| `services/docs_mcp.py`      | Google Docs: create, update, delete, share, search in document. |
| `services/sheets_mcp.py`    | Google Sheets: list, create, read/update data, charts, pivot. |
| `services/slides_mcp.py`    | Google Slides: list, share, extract text, replace, add slide/text box, etc. |
| `services/notion_mcp.py`    | Notion: databases, pages, blocks, comments, query. |
| `services/trello_mcp.py`    | Trello: boards, lists, cards, comments, labels, checklists. |

These are the modules that **change** state (send email, create doc, update block, etc.). They are called from **server.py** tool wrappers, which are then referenced by **server_parts** in the **tools** registry.

---

## 6. Clients (Retrieval) — Summary

| Client file                    | Role |
|--------------------------------|------|
| `clients/mongo_email_client.py`    | Email search/query/get (used for search_emails, get_emails in tools). |
| `clients/mongo_docs_client.py`     | Docs search/query/get/list (used for query_docs, get_document_content, list_docs, etc.). |
| `clients/mongo_calendar_client.py` | Calendar event search/query/get. |
| `clients/mongo_briefing_client.py` | get_latest_briefing, get_all_latest_briefings. |
| `clients/qdrant_vector_client.py` | vector_context_search (semantic/correlation). |
| `clients/mongo_personalization_client.py` | User personality and profile for system prompt. |
| `clients/mongo_history_client.py` | save_chat_history. |
| `clients/mongo_token_usage_client.py` | upsert_ai_usage (token tracking). |
| `clients/db_method.py`             | get_distinct_gmail_senders, user_info. |

So: **Retrieval** = mostly **clients** (Mongo, Qdrant, db_method). **Updation** = **services** (MCPs), exposed via **server.py** and then via **server_parts** **tools** registry.

---

## 7. Important Snippets (Copy-Paste Reference)

**Body shape used for the LLM (Bedrock-style):**

```python
body = {
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 4096,
    "temperature": 0.3,
    "system": SYSTEM_PROMPT,
    "messages": messages,  # list of {"role": "user"|"assistant", "content": [{"type": "text"|"tool_use"|"tool_result", ...}]}
    "tools": claude_tools,  # [{"name", "description", "input_schema": <JSON schema>}]
}
```

**Building claude_tools from function_defs (assistant_handler):**

```python
claude_tools = [
    {"name": tool["name"], "description": tool["description"], "input_schema": tool["parameters"]}
    for tool in function_defs
    if tool["name"] in filtered_tool_names   # or no filter: for tool in function_defs
]
```

**Where tools registry is defined (server_parts.py):**

```python
tools = {
    "send_email": lambda **kwargs: send_email(**kwargs),
    "search_emails": lambda **kwargs: mongo_query_emails(**kwargs),
    "get_emails": lambda **kwargs: mongo_get_emails(**kwargs),
    "create_event": lambda **kwargs: create_event(**kwargs),
    "search_calendar_events": lambda **kwargs: mongo_search_events(**kwargs),
    "query_docs": lambda **kwargs: mongo_query_docs(**kwargs),
    "get_document_content": lambda **kwargs: mongo_get_docs(**kwargs),
    # ... many more: Slack, Notion, Trello, Sheets, Slides, etc.
}
```

**structures.py — one function_def entry shape:**

```python
{
    "name": "search_emails",
    "description": "Search emails using the user's query as-is.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keyword or text to search in subject, body, or snippet."},
            "is_unread": {"type": "boolean", "description": "Filter for unread emails only. Default is false."},
            # ...
        },
    },
}
```

---

## 8. One-Sentence Summary

**LLM:** Orchestrated in `cosi_app.py` via `invoke_ai_with_fallback` (OpenAI and/or Bedrock); **tools** and **function_defs** are built from `server_parts` and `structures`; the `/chat` handler in `assistant_handler.py` runs a multi-step loop that calls `tools[name]` on each `tool_use` and appends tool results back into the conversation. **Updation** is implemented in **services/** and exposed through **server.py**; **retrieval** is implemented in **clients/** (Mongo, vector, etc.) and wired into the same **tools** registry in **server_parts.py**, so the LLM sees a single set of tool names and the runtime routes each name to either a service (update) or a client (retrieval).
