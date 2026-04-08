from flask import request, jsonify
from datetime import datetime, timezone
import base64
import fitz
import json
import os
import re
import time
import uuid
from collections import deque
import os
from .verify_scret import verify_hmac_and_get_user

SIVERY_SCORE_MAPPING=os.getenv("SEVERITY_SCORE_MAPPING")
# Import app and required shared utilities/state from cosi_app
from app.cosi_app import (
    app,
    logger,
    get_autopilot_token,
    get_distinct_gmail_senders,
    get_cached_user,
    get_user_personality_profile,
    get_user_profile_collection,
    invoke_openai_autopilot,
    log_error_to_terminal,
    get_user_friendly_error_message,
    summarize_conversation,
    user_conversations,
    long_term_memory,
    function_defs,
    tools,
    save_chat_history,
    RateLimitError,
    APIError,
    handle_api_error,
    wrap_tool_execution,
)

from dotenv import load_dotenv

load_dotenv()
SIVERY_SCORE_MAPPING = os.getenv("SEVERITY_SCORE_MAPPING", "0.00 TO 0.39 → Low - 0.40 TO 0.69 → Medium - 0.70 TO 1.00 → High")
from app.switches import (
    USE_BEDROCK_FALLBACK,
    ENABLE_IMAGE_ANALYSIS,
    ENABLE_PDF_ANALYSIS,
    ENABLE_AUTOPILOT_LOGS,
)

from utils.tool_filter import filter_tools

from clients.mongo_context_client import (
    get_email_context,
    get_calendar_context,
    get_docs_context,
    get_slides_context,
    get_notion_context,
    get_trello_context,
    get_slack_context,
    search_context_by_text,
)

from clients.mongo_token_usage_client import upsert_ai_usage

# Conditional logging wrapper
def autopilot_log(level, *args, **kwargs):
    """Wrapper for logger calls that respects ENABLE_AUTOPILOT_LOGS flag"""
    if ENABLE_AUTOPILOT_LOGS:
        if level == "info":
            logger.info(*args, **kwargs)
        elif level == "warning":
            logger.warning(*args, **kwargs)
        elif level == "error":
            logger.error(*args, **kwargs)
        elif level == "debug":
            logger.debug(*args, **kwargs)

# Conditional print wrapper
def autopilot_print(*args, **kwargs):
    """Wrapper for print calls that respects ENABLE_AUTOPILOT_LOGS flag"""
    if ENABLE_AUTOPILOT_LOGS:
        print(*args, **kwargs)


def console_autopilot_execute_response(autopilot_id, response_body: dict, max_chars: int = 200_000) -> None:
    """Print /autoPilot/execute JSON to stdout (always; not gated by ENABLE_AUTOPILOT_LOGS)."""
    try:
        text = json.dumps(response_body, default=str, ensure_ascii=False)
    except Exception:
        text = str(response_body)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"
    print(
        "\n========== [autoPilot/execute] ==========\n"
        f"autopilot_id: {autopilot_id!r}\n"
        f"execution_response:\n{text}\n"
        "==========================================\n",
        flush=True,
    )


def _planned_tool_from_execute_payload(data: dict) -> str:
    """First non-empty tool from planned_action (generate_autopilot sends one action per request)."""
    pa = data.get("planned_action") or {}
    if not isinstance(pa, dict):
        return ""
    for _st, actions in pa.items():
        if not isinstance(actions, list):
            continue
        for a in actions:
            if isinstance(a, dict) and (a.get("tool") or "").strip():
                return str(a.get("tool") or "").strip()
    return ""


def _infer_tool_for_executed_action(ea: dict, planned_tool: str) -> str:
    """Mirror generate_autopilot._resolved_tool_from_execution_action so Mongo/UI tool matches execution_type."""
    if not isinstance(ea, dict):
        return (planned_tool or "").strip()
    et = str(ea.get("execution_type") or "").strip().lower()
    type_map = {
        "gmail_draft": "gmail",
        "slack_draft": "slack",
        "comment_reply": "comment_reply",
        "trello_task": "trello_doc",
        "trello_comment": "trello_doc",
        "calendar_event": "calendar",
    }
    if et in type_map:
        return type_map[et]
    if et == "g_slides":
        return "g_slides"
    if et == "doc_task":
        doc = ea.get("draft") or ea.get("doc") or ea.get("doc_task") or {}
        if isinstance(doc, dict):
            dt = str(doc.get("doc_type") or "").strip().lower()
            if dt == "g_slides":
                return "g_slides"
            if dt == "g_sheets":
                return "g_sheets"
            if dt in ("notion", "notion_doc"):
                return "notion_doc"
            if dt == "g_docs":
                return "g_docs"
        pt = (planned_tool or "").strip().lower()
        if pt in ("notion", "notion_doc"):
            return "notion_doc"
        return (planned_tool or "g_docs").strip() or "g_docs"
    rt = str(ea.get("tool") or "").strip()
    if rt and rt.lower() not in ("unknown", ""):
        if rt.lower() == "notion":
            return "notion_doc"
        return rt
    pt = str(planned_tool or "").strip()
    if pt.lower() == "notion":
        return "notion_doc"
    return pt


def _autopilot_draft_vector_context_enabled() -> bool:
    v = (os.getenv("AUTOPILOT_DRAFT_VECTOR_CONTEXT") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _looks_like_http_url(val) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    return s.lower().startswith(("http://", "https://"))


def _primary_url_from_vector_match(m: dict) -> str | None:
    """Best-effort public URL for a vector_context_search match (docs, sheets, slides, etc.)."""
    if not isinstance(m, dict):
        return None
    for key in ("link", "url", "html_link", "meeting_link"):
        v = m.get(key)
        if _looks_like_http_url(v):
            return str(v).strip()
    src = str(m.get("source") or "").lower()
    pres = (m.get("presentation_id") or "").strip()
    did = (m.get("document_id") or "").strip()
    sid = (m.get("spreadsheet_id") or "").strip()
    if src in ("slides", "gslides"):
        pid = pres or did
        if pid:
            return f"https://docs.google.com/presentation/d/{pid}/edit"
    if src in ("sheets", "gsheets") and sid:
        return f"https://docs.google.com/spreadsheets/d/{sid}/edit"
    if src in ("docs", "gdocs") and did:
        return f"https://docs.google.com/document/d/{did}/edit"
    if src == "trello":
        cid = m.get("card_id")
        if cid and str(cid).strip():
            return f"https://trello.com/c/{str(cid).strip()}"
    if src in ("notion", "notiondocs") and _looks_like_http_url(m.get("url")):
        return str(m.get("url")).strip()
    return None


def _format_doc_links_lines_from_matches(matches: list, *, max_links: int = 14) -> str:
    if not matches:
        return ""
    seen: set[str] = set()
    lines: list[str] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        url = _primary_url_from_vector_match(m)
        if not url or url in seen:
            continue
        seen.add(url)
        label = (
            (m.get("title") or m.get("summary") or m.get("source") or "Document")
            .strip()[:120]
            or "Document"
        )
        lines.append(f"- {label}: {url}")
        if len(lines) >= max_links:
            break
    return "\n".join(lines)


def _build_execute_payload_vector_keywords(data: dict) -> str:
    """Build search keywords from /autoPilot/execute JSON before the execution LLM runs."""
    if not isinstance(data, dict):
        return ""
    bits: list[str] = []
    seen: set[str] = set()

    def add(val) -> None:
        if val is None:
            return
        t = str(val).strip()
        if not t:
            return
        if len(t) > 450:
            t = t[:450]
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        bits.append(t)

    pa = data.get("planned_action") or {}
    if isinstance(pa, dict):
        for _st, actions in pa.items():
            if not isinstance(actions, list):
                continue
            for a in actions[:16]:
                if isinstance(a, dict):
                    add(a.get("action"))
                    add(a.get("tool"))
    for it in (data.get("items") or [])[:10]:
        if not isinstance(it, dict):
            continue
        add(it.get("source_type"))
        sd = it.get("source_data") or {}
        for row in (sd.get("items") or [])[:4]:
            if isinstance(row, dict):
                add(
                    row.get("title")
                    or row.get("summary")
                    or row.get("subject")
                )
                add(row.get("snippet") or row.get("body"))
    ca = data.get("changes_analysis")
    if isinstance(ca, dict):
        for svc in (
            "gmail",
            "calendar",
            "g_docs",
            "g_sheets",
            "g_slides",
            "slack_channel_messages",
            "trello_doc",
            "notion_doc",
        ):
            block = ca.get(svc)
            if not isinstance(block, dict):
                continue
            for row in (block.get("items") or [])[:3]:
                if isinstance(row, dict):
                    add(
                        row.get("title")
                        or row.get("summary")
                        or row.get("subject")
                    )
    return " ".join(bits)[:500]


def _format_vector_search_matches_for_draft(
    search_result: dict,
    *,
    max_items: int = 6,
    max_line_len: int = 260,
    max_total: int = 1500,
) -> tuple[str, int]:
    """Turn vector_context_search response into short bullet text; returns (text, line_count)."""
    if not isinstance(search_result, dict):
        return "", 0
    if search_result.get("error"):
        return "", 0
    matches = search_result.get("matches") or []
    if not matches:
        return "", 0
    lines = []
    used = 0
    for m in matches[:max_items]:
        if not isinstance(m, dict):
            continue
        src = str(m.get("source") or "workspace").strip()
        title = (m.get("title") or "").strip()
        emb = (m.get("embedding_text") or m.get("summary") or "").strip()
        emb_one = re.sub(r"\s+", " ", emb)[:max_line_len].strip()
        bit = title or emb_one
        if title and emb_one and emb_one.lower() not in title.lower():
            bit = f"{title}: {emb_one}"
        if not bit:
            continue
        sim = m.get("similarity")
        suf = ""
        try:
            if sim is not None:
                suf = f" ({float(sim):.2f})"
        except (TypeError, ValueError):
            pass
        line = f"• [{src}]{suf} {bit}"
        if used + len(line) + 1 > max_total:
            break
        lines.append(line)
        used += len(line) + 1
    return ("\n".join(lines), len(lines))


def _autopilot_vector_context_for_draft(
    *,
    tools_dict: dict,
    token: str,
    user_id: str,
    keywords: str,
    tool_hint: str | None,
    limit: int = 5,
    max_items: int = 6,
    max_total: int = 1500,
) -> tuple[str, dict, str]:
    """
    Run vector_context_search; return (context bullets, meta, doc link lines).
    On failure returns ("", {}, ""). Never raises.
    """
    meta: dict = {}
    kw = (keywords or "").strip()
    if not kw:
        return "", meta, ""
    kw = kw[:500]
    fn = tools_dict.get("vector_context_search")
    if not fn:
        return "", meta, ""
    args = {"keywords": kw, "token": token, "limit": limit}
    if tool_hint:
        args["tool"] = tool_hint
    try:
        res = wrap_tool_execution(
            tool_func=fn,
            tool_name="vector_context_search",
            args=args,
            user_id=user_id,
        )
    except Exception as e:
        autopilot_log("debug", "vector_context_search exception: %s", e)
        meta["vector_context_error"] = str(e)[:240]
        return "", meta, ""
    if not isinstance(res, dict):
        return "", meta, ""
    text, n = _format_vector_search_matches_for_draft(
        res, max_items=max_items, max_total=max_total
    )
    meta["vector_context_query"] = kw[:240]
    meta["vector_context_match_count"] = int(res.get("total_matches") or n or 0)
    if res.get("error") and not text:
        meta["vector_context_error"] = str(res.get("error"))[:240]
    elif text:
        meta["vector_context_enriched"] = True
    raw_matches = res.get("matches") or []
    links_block = _format_doc_links_lines_from_matches(
        raw_matches if isinstance(raw_matches, list) else [],
        max_links=14,
    )
    if links_block:
        meta["vector_context_doc_links"] = True
    return text, meta, links_block or ""


# ------------------------------
# Fetch relevant context based on query
# ------------------------------
def fetch_relevant_context(query_text: str, token: str) -> str:
    """
    Fetch relevant context from MongoDB context collections based on the query.
    Returns formatted context string to be included in the prompt.
    """
    context_sections = []

    # Validate that query_text is not JSON data
    query_stripped = query_text.strip() if query_text else ""
    if query_stripped.startswith(('{', '[')):
        autopilot_log("warning", f"Query appears to be JSON data, skipping context search. Query starts with: {query_stripped[:50]}...")
        return ""

    try:
        # Try text-based search first to find relevant context
        text_search_result = search_context_by_text(
            query=query_text[:200],  # Limit query length
            token=token,
            limit=5
        )
        
        if text_search_result.get("total_matches", 0) > 0:
            contexts = text_search_result.get("matched_contexts", [])
            context_sections.append("=== RELEVANT EMAIL CONTEXT ===")
            for ctx in contexts[:3]:  # Limit to top 3
                correlation = ctx.get("correlation_text", "")[:500]  # Truncate
                if correlation:
                    context_sections.append(f"- {correlation}")
    except Exception as e:
        autopilot_log("warning", f"Failed to fetch context via text search: {e}")
    
    # If we have context, format it nicely
    if context_sections:
        return "\n\n".join(context_sections) + "\n\n"
    return ""


@app.route("/autoPilot", methods=["POST"])
def auto_assistant():
    autopilot_log("info", "Received /autoPilot request")
   
    # Capture start time for response time tracking
    request_start_time = time.time()

    # ------------------------------
    # Token & user info
    # ------------------------------
    token, error_response, status_code = get_autopilot_token()
    if error_response:
        autopilot_log("error", "Token error: %s", error_response.get_json())
        return error_response, status_code
    
    # Get user IP address for token tracking
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    if isinstance(ip_address, str) and ',' in ip_address:
        # Handle multiple IPs in X-Forwarded-For header
        ip_address = ip_address.split(',')[0].strip()

    # Track API call number for this request
    api_call_counter = 0
    
    # Accumulate token usage across all API calls
    accumulated_token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "system_prompt_tokens": 0,
        "total_tokens": 0,
        "model": None,
    }

    now = datetime.now()
    # print(f"Now: {now}")
    now_iso = now.strftime("%Y-%m-%d")
    # print(f"Now ISO: {now_iso}")
    user_list = get_distinct_gmail_senders(token)
    # print(f"User list: {user_list}")
    user_info = get_cached_user(token)
    # print(f"User info: {user_info}")
    # Get user's email writing personality using token
    user_personality = get_user_personality_profile(token)
    # print(f"Us//er personality: {user_personality}")
    # Get user's profile document from MongoDB
    user_profile = get_user_profile_collection(token)
    # print(f"User profile: {user_profile}")

    # ------------------------------
    # Handle user input (text / files)
    # ------------------------------
    data: dict = {}
    relevant_context = ""

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        user_query = request.form.get("query", "")
        user_id = token
        uploaded_files = request.files.getlist("file")
        file_analyses = []

        if uploaded_files:
            supported_image_extensions = [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".webp",
            ]
            supported_pdf_extensions = [".pdf"]

            for uploaded_file in uploaded_files:
                filename = uploaded_file.filename.lower()
                file_extension = (
                    "." + filename.split(".")[-1] if "." in filename else ""
                )

                if (
                    file_extension in supported_image_extensions
                    and ENABLE_IMAGE_ANALYSIS
                ):
                    try:
                        # Direct image analysis without separate service
                        image_bytes = uploaded_file.read()
                        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                        # Use query from form data or default prompt
                        image_prompt = (
                            user_query
                            if user_query
                            else "Please describe this image and suggest what it could represent."
                        )

                        # Determine media type based on file extension
                        media_type_map = {
                            ".jpg": "image/jpeg",
                            ".jpeg": "image/jpeg",
                            ".png": "image/png",
                            ".gif": "image/gif",
                            ".bmp": "image/bmp",
                            ".webp": "image/webp",
                        }
                        media_type = media_type_map.get(file_extension, "image/jpeg")

                        # Build Claude request with image + text
                        body = {
                            "anthropic_version": "bedrock-2023-05-31",
                            "max_tokens": 4096,
                            "temperature": 0.3,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": image_prompt},
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": media_type,
                                                "data": image_base64,
                                            },
                                        },
                                    ],
                                }
                            ],
                        }

                        # Call OpenAI (autopilot invoker)
                        api_call_counter += 1
                        response = invoke_openai_autopilot(body, token=token, ip_address=ip_address, start_time=request_start_time)
                        
                        # Extract and accumulate token usage
                        if "_token_usage" in response:
                            token_usage = response["_token_usage"]
                            accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
                            accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
                            if accumulated_token_usage["model"] is None:
                                accumulated_token_usage["model"] = token_usage.get("model", "")
                            # System prompt tokens should be the same across calls, so only set once
                            if accumulated_token_usage["system_prompt_tokens"] == 0:
                                accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
                        
                        content = response.get("content", [])
                        if content and isinstance(content, list) and len(content) > 0:
                            analysis_text = content[0].get(
                                "text", "No analysis available"
                            )
                            file_analyses.append(
                                f"Image Analysis ({filename}):\n{analysis_text[:500]}"
                            )  # Truncate to 500 chars
                        else:
                            file_analyses.append(
                                f"❌ Error analyzing image {filename}: No valid analysis returned"
                            )

                    except Exception as e:
                        # Log full error to terminal
                        log_error_to_terminal(
                            error=e,
                            context=f"Image analysis failed for file: {filename}",
                            user_id=token
                        )
                        # Show user-friendly message
                        user_message = get_user_friendly_error_message(e, "general")
                        file_analyses.append(
                            f"❌ Unable to analyze image {filename}. Please try again."
                        )

                elif file_extension in supported_pdf_extensions and ENABLE_PDF_ANALYSIS:
                    try:
                        pdf_bytes = uploaded_file.read()
                        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                        pdf_text = ""
                        for page in doc:
                            pdf_text += page.get_text()
                        doc.close()
                        pdf_text = pdf_text[:2000]  # Truncate to 1000 chars
                        pdf_prompt = (
                            "Analyze and summarize the following PDF content. Focus on key information, main points, and important details:\n\n"
                            + pdf_text
                        )
                        # print(pdf_text)
                        body = {
                            "anthropic_version": "bedrock-2023-05-31",
                            "max_tokens": 4096,
                            "temperature": 0.3,
                            "system": pdf_prompt,
                            "messages": [{"role": "user", "content": pdf_prompt}],
                        }
                        api_call_counter += 1
                        response = invoke_openai_autopilot(body, token=token, ip_address=ip_address, start_time=request_start_time)
                        
                        # Extract and accumulate token usage
                        if "_token_usage" in response:
                            token_usage = response["_token_usage"]
                            accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
                            accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
                            if accumulated_token_usage["model"] is None:
                                accumulated_token_usage["model"] = token_usage.get("model", "")
                            # System prompt tokens should be the same across calls, so only set once
                            if accumulated_token_usage["system_prompt_tokens"] == 0:
                                accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
                        
                        content = response.get("content", [])
                        if (
                            content
                            and isinstance(content, list)
                            and content[0].get("text")
                        ):
                            file_analyses.append(
                                f"PDF Analysis ({filename}):\n{content[0]['text'][:500]}"
                            )  # Truncate to 500 chars
                        else:
                            file_analyses.append(
                                f"❌ Error analyzing PDF {filename}: No valid content returned"
                            )
                    except Exception as e:
                        # Log full error to terminal
                        log_error_to_terminal(
                            error=e,
                            context=f"PDF analysis failed for file: {filename}",
                            user_id=token
                        )
                        # Show user-friendly message
                        user_message = get_user_friendly_error_message(e, "general")
                        file_analyses.append(
                            f"❌ Unable to analyze PDF {filename}. Please try again."
                        )
                else:
                    return (
                        jsonify(
                            {
                                "response": f"❌ Unsupported file type: {file_extension}. Only images ({', '.join(supported_image_extensions)}) and PDFs are supported."
                            }
                        ),
                        400,
                    )
    else:
        data = request.get_json(force=True) or {}
        # print(f"Data: {data}")
        user_query = data.get("query", "")
        # print(f"User query: {user_query}")
        user_id = token
        print(f"User ID: {user_id}")
        file_analyses = []

        relevant_context = fetch_relevant_context(user_query, token) if user_query else ""
        print(f"Context: {relevant_context}")

    # ------------------------------
    # Combine query + file analysis + context
    # ------------------------------
    file_analysis = "\n\n".join(file_analyses) if file_analyses else ""
    combined_query = ""

    # Inject scheduler / client payload (changes_analysis, instructions) for planning
    if isinstance(data, dict) and data:
        prefix_bits = []
        if data.get("changes_analysis") is not None:
            prefix_bits.append(
                "WORKSPACE_CHANGES_ANALYSIS:\n"
                + json.dumps(data["changes_analysis"], default=str)[:200000]
            )
        if data.get("general_instruction"):
            prefix_bits.append(
                "GENERAL_INSTRUCTION:\n" + str(data["general_instruction"])[:50000]
            )
        if data.get("executed_actions_history") is not None:
            prefix_bits.append(
                "EXECUTED_ACTIONS_HISTORY:\n"
                + json.dumps(data["executed_actions_history"], default=str)[:100000]
            )
        if data.get("multi_step_instruction"):
            prefix_bits.append(
                "MULTI_STEP_INSTRUCTION:\n" + str(data["multi_step_instruction"])[:20000]
            )
        if prefix_bits:
            combined_query = "\n\n".join(prefix_bits) + "\n\n"

    if relevant_context:
        combined_query += f"RELEVANT CONTEXT:\n{relevant_context}\n"
    
    if file_analysis:
        combined_query += f"File Analyses:\n{file_analysis}\n\n"
    
    if user_query:
        combined_query += f"User Query: {user_query}"
    elif file_analysis:
        combined_query += f"File Analyses:\n{file_analysis}"

    # print(f"Combined query: {combined_query}")


    # ------------------------------
    # Conversation history
    # ------------------------------
    conversation_history = user_conversations[token]
    SUMMARIZE_WINDOW = 4
    MAX_INJECTED_SUMMARIES = 2

    # === STEP 1: Summarize oldest messages when deque is full ===
    current_memory_block = None

    if len(conversation_history) == conversation_history.maxlen:
        to_summarize = list(conversation_history)[:SUMMARIZE_WINDOW]
        to_keep = list(conversation_history)[SUMMARIZE_WINDOW:]

        summary_json = summarize_conversation(to_summarize, token=token)

        if summary_json.get("success", False):
            long_term_memory[token].append(summary_json)
            if len(long_term_memory[token]) > 20:
                long_term_memory[token] = long_term_memory[token][-20:]

            current_memory_block = {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"[PAST SUMMARY]\n{json.dumps(summary_json, indent=2)}"}
                            ]
                        }
        else:
            fallback_msg = summary_json.get("message", "Previous context unavailable.")
            current_memory_block = {
                "role": "user",
                "content": [{"type": "text", "text": f"[PAST CONTEXT]\n{fallback_msg}"}]
            }

        # Update short-term
        user_conversations[token] = deque(to_keep, maxlen=conversation_history.maxlen)
    # === STEP 2: Build from short-term ===
    sanitized_history = [
        m for m in list(conversation_history) if isinstance(m.get("content"), str)
    ]
    history_messages = [
        {
            "role": m.get("role", "user"),
            "content": [{"type": "text", "text": m.get("content", "")}]
        }
        for m in sanitized_history
    ]

    # === STEP 3: Inject current + up to 2 previous summaries as TEXT ===
    # Start with current (new/fallback) — already a valid block
    if current_memory_block:
        history_messages.insert(0, current_memory_block)

    if current_memory_block:
          previous_summaries = long_term_memory[token][:-1][-MAX_INJECTED_SUMMARIES + 1:]
    else:
        previous_summaries = long_term_memory[token][-MAX_INJECTED_SUMMARIES:]

    # Add up to 2 previous summaries as plain text (no tool_use_id!)
     
    for summary in reversed(previous_summaries):
        history_messages.insert(0, {
            "role": "user",
            "content": [{"type": "text", "text": f"[PAST SUMMARY]\n{json.dumps(summary, indent=2)}"}]
        })

    # === FINAL: Add current query ===
    messages = history_messages + [
        {"role": "user", "content": [{"type": "text", "text": combined_query}]}
    ]

    # Filter tools before building claude_tools
    filtered_tool_names = filter_tools(
        user_query=combined_query,
        conversation_context=history_messages[-5:],  # Last 5 messages for context
        max_tools=20,
        token=token
    )

    # Build filtered tool list with full schemas (only selected service functions)
    claude_tools = [
        {
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"],
        }
        for tool in function_defs
        if tool["name"] in filtered_tool_names  # Only include filtered tools
    ]

    # ------------------------------
    # AUTOPILOT SYSTEM PROMPT (STRICT JSON CONTRACT)
    # ------------------------------
    Analyse_QUERY = """
    You are an AUTONOMOUS AUTOPILOT SYSTEM that analyzes workspace data and generates urgent actions.

    AUTOPILOT MODE - YOU ARE ACTING AUTONOMOUSLY:
    - Analyze calendar events, emails, documents, and workspace context
    - Generate actions for ALL items that have changes, prioritizing urgent ones first
    - Generate DIFFERENT actions for EACH source type (g_docs, gmail, calendar, trello_doc, notion_doc, slack_channel_messages, etc.)

    OUTPUT FORMAT (MANDATORY CONTRACT):
    - Return ONLY a JSON object with this exact structure:
    {
      "planned action": {
        "g_docs": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Google Docs (e.g., 'Review document: {title}' or 'Reply to comment on {title}')",
            "tool": "gmail",
            "confidence": "high"
          },
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Second action for Google Docs if needed",
            "tool": "comment_reply",
            "confidence": "medium"
          }
        ],
        "g_sheets": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Google Sheets (e.g., 'Review spreadsheet: {title}' or 'Reply to comment on {title}')",
            "tool": "comment_reply",
            "confidence": "high"
          }
        ],
        "g_slides": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Google Slides (e.g., 'Review presentation: {title}' or 'Reply to comment on {title}')",
            "tool": "comment_reply",
            "confidence": "high"
          }
        ],
        "gmail": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Gmail (e.g., 'Reply to email from {sender} about {subject}')",
            "tool": "gmail",
            "confidence": "high"
          }
        ],
        "calendar": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Calendar (e.g., 'Send reminder for {event_title} to {attendee_email}' or 'Follow up on {event_title} - {attendee_email} needs to respond')",
            "tool": "calendar",
            "confidence": "high"
          }
        ],
        "trello_doc": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Trello (e.g., 'Update card: {title}' or 'Add comment to card: {title}')",
            "tool": "trello",
            "confidence": "high"
          }
        ],
        "notion_doc": [
          {
            "autopilot_id": "<uuid from source item>",
            "action": "Action for Notion (e.g., 'Review page: {title}')",
            "tool": "notion",
            "confidence": "medium"
          }
        ],
        "slack_channel_messages": [
          {
            "autopilot_id": "<channel-level uuid from source item>",
            "action": "Action for Slack channel (e.g., 'Draft reply for channel {channel_name}: {message_summary}')",
            "tool": "slack",
            "confidence": "high"
          }
        ]
      }
    }

    CRITICAL RULES FOR autopilot_id (MANDATORY - VALIDATION WILL FAIL IF VIOLATED):
    - 🚨 EVERY planned action MUST include the autopilot_id from the source item it was derived from
    - 🚨 The autopilot_id MUST match EXACTLY the autopilot_id field in the source item's data - NO EXCEPTIONS
    - 🚨 If a source item has autopilot_id: "abc-123", ALL actions generated for that item MUST use "abc-123"
    - 🚨 If you generate multiple actions for the same source item, they MUST all use the SAME autopilot_id
    - 🚨 CRITICAL: Every source item WILL contain an autopilot_id field (this is guaranteed by the system)
    - 🚨 You MUST reuse the autopilot_id exactly as provided - do NOT invent, transform, or replace it
    - 🚨 You MUST NOT create new autopilot_ids - if autopilot_id is missing from a source item, return an empty planned_action object for that source type
    - 🚨 This autopilot_id is used to track and deduplicate actions - it is MANDATORY and must match exactly
    - 🚨 HOW TO FIND autopilot_id:
      * Look in the changes_analysis data structure you receive
      * For each source type (gmail, g_docs, calendar, etc.), find the "items" array
      * Each item in that array has an "autopilot_id" field - USE THAT EXACT VALUE
      * Example: If gmail.items[0].autopilot_id = "9d0f4a09-8618-45c8-9e00-3bbdd184bc37", then ALL actions for that email MUST use "9d0f4a09-8618-45c8-9e00-3bbdd184bc37"
    - 🚨 FOR EMAILS WITH CROSS-TOOL ACTIONS (SPECIAL CASE):
      * When an email requires actions across multiple tools (Trello, Slack, Gmail, etc.), ALL those actions MUST use the email's autopilot_id
      * Example: If email has autopilot_id "abc-123" and requires Trello tasks + Slack notifications, then:
        - Trello action: {"autopilot_id": "abc-123", "action": "...", "tool": "trello", ...}
        - Slack action: {"autopilot_id": "abc-123", "action": "...", "tool": "slack", ...}
        - Gmail action: {"autopilot_id": "abc-123", "action": "...", "tool": "gmail", ...}
      * ALL actions triggered by the same email MUST use the SAME email autopilot_id
    - FOR SLACK (SPECIAL CASE):
      * CHANNEL-LEVEL ACTIONS (RECOMMENDED): Use the channel's autopilot_id (from channel object, not individual messages)
      * MESSAGE-LEVEL ACTIONS (ALTERNATIVE): Use each message's autopilot_id (one action per message)
      * Choose ONE approach per channel - either channel-level OR message-level, not both
      * Channel-level is recommended for efficiency (one action per channel addressing all messages)

    EXECUTED ACTIONS HISTORY (CRITICAL - PREVENT DUPLICATE ACTIONS):
    - If you see "executed_actions_history" in the input, this contains actions that were already executed in previous runs
    - Format: {"autopilot_id": [{"execution_type": "gmail_draft", "status": "completed", "tool": "gmail", "executed_at": "..."}, ...]}
    - 🚨 MANDATORY: Before planning any action, check if it was already executed:
      * Look up the autopilot_id in "executed_actions_history"
      * Check if an action with the same tool and execution_type was already completed (status: "completed")
      * If an action was already executed, DO NOT plan it again - skip it entirely
      * Example: If executed_actions_history shows {"email-123": [{"execution_type": "gmail_draft", "status": "completed", "tool": "gmail"}]}, 
        then DO NOT create a gmail action for autopilot_id "email-123"
    - For multi-step actions (email with task assignments):
      * Check if ALL related actions were already executed (Gmail + Trello + Slack)
      * If ALL actions were executed, DO NOT plan any actions for that autopilot_id - return empty arrays
      * If SOME actions were executed, only plan the MISSING actions (do not duplicate completed ones)
      * Example: If executed_actions_history shows:
        {"email-123": [
          {"execution_type": "gmail_draft", "status": "completed", "tool": "gmail"},
          {"execution_type": "trello_task", "status": "completed", "tool": "trello"},
          {"execution_type": "slack_draft", "status": "completed", "tool": "slack"}
        ]}
        Then DO NOT plan any actions for autopilot_id "email-123" - all actions are already done
      * If only Gmail was executed, plan only Trello and Slack actions (skip Gmail)
    - 🚨 CRITICAL: If all actions for an autopilot_id were already executed, return empty arrays for that autopilot_id
      Do NOT create duplicate actions - this prevents re-execution of already-completed work

    ACTION FORMATS (MANDATORY):
    - Each action MUST be an object with: autopilot_id, action, tool, confidence, category
    - autopilot_id: MUST match the autopilot_id from the source item (MANDATORY)
    - action: Description of the action (string)
    - tool: Tool name (e.g., "gmail", "comment_reply", "trello", "calendar", "slack", "notion")
    - confidence: "high", "medium", or "low"
    - category: One of the following strings ONLY (lowercase, snake_case):
      * "must_act"
      * "should_progress"
      * "respond"
      * "awarness"

    CATEGORY DEFINITIONS (USE SOURCE DATA TO DECIDE):
    - Category "must_act":
      * Ignoring today causes real consequences, OR
      * Someone is blocked without the user’s decision, OR
      * Deadline is within 24 hours or task is overdue and user is responsible, OR
      * Impacts revenue, reputation, delivery, or key relationships, OR
      * Preparation needed for a meeting today or tomorrow, OR
      * Approval/sign-off significantly affects direction.
      * Interpretation: Requires executive judgment, risk awareness, or strategic clarity.

    - Category "should_progress":
      * User owns the work AND
      * Important but not urgent AND
      * Nobody is blocked today AND
      * Deadline is more than 2–3 days away AND
      * Delay only slows momentum but causes no immediate damage.
      * Interpretation: Execution, drafting, planning, or structured progress.

    - Category "respond":
      * Someone clearly expects a reply (email, comment, Slack message) AND
      * Response can be quick (< 15 minutes) AND
      * It is mostly clarification, coordination, acknowledgment, or lightweight approval.
      * Exception: If the response significantly changes direction or carries real risk, classify as "must_act" instead.

    - Category "awarness":
      * No reply is expected AND
      * No decision is required AND
      * No blockers are created AND
      * Content is informational only (updates, reports, CC messages, status notifications).

    ACTION FORMATS:
    - For SLACK messages: Use format: "{channel_id}: {message}". The drafted reply MUST be brief and to the point (1-3 short sentences).
      * You MUST ONLY use channel_id values that appear in the Slack source data (slack_channel_messages.items[].channel_id).
      * NEVER invent, guess, or hallucinate a Slack channel_id. If you cannot map an action to a real channel_id from the source data, DO NOT create a Slack action for it.
    - For GMAIL: Describe reply action (e.g., "Reply to {sender} about {subject}")
    - For GOOGLE DOCS: Describe review/reply action (e.g., "Review document: {title}" or "Reply to comment on {title}")
    - For GOOGLE SHEETS: Describe review/reply action (e.g., "Review spreadsheet: {title}" or "Reply to comment on {title}") - IMPORTANT: If there are comments, generate actions to reply to them
    - For GOOGLE SLIDES: Describe review/reply action (e.g., "Review presentation: {title}" or "Reply to comment on {title}") - IMPORTANT: If there are comments, generate actions to reply to them
    - For CALENDAR: 
      * ALWAYS check for attendees with "responseStatus": "needsAction" - these are URGENT and require immediate follow-up
      * If an event has attendees who haven't responded (needsAction), generate actions like "Send reminder for {event_title} to {attendee_email}" or "Follow up on {event_title} - {attendee_email} needs to respond"
      * For UPDATED events, check if there are new attendees or changes that require action
      * For NEW events, generate actions to send reminders or confirmations
      * Examples: "Send reminder for Weekly Connect to dsuzaunified@gmail.com", "Follow up on {event_title} - pending attendee responses"
    - For TRELLO: Describe card update action (e.g., "Update card: {title}")
    - For NOTION: Describe page review action (e.g., "Review page: {title}")
    - Generate actions for ALL items that have changes, not just urgent ones
    - For documents (g_docs, g_sheets, g_slides): 
      * If there are comments, you MUST generate actions to reply to those comments
      * If there are no comments but the document was modified, generate a review action (e.g., "Review document: {title}")
      * If the document was newly created, generate a review action
    - For calendar events:
      * CRITICAL: If a calendar event has attendees with "responseStatus": "needsAction", you MUST generate actions to follow up with those attendees
      * If an event was created without start/end times, generate an action to update the event with meeting details
      * If an event was updated, check if any action is needed
    - For emails: Generate reply actions for all new emails
    - For Trello cards: Generate review/update actions for new or modified cards
    - For Notion pages: Generate review actions for modified pages
    - IMPORTANT: Generate at least one action for each source type that has items, even if it's just a review action
    - Only omit a source type if it truly has no items (count: 0)

    # 🚨 SEVERITY CLASSIFICATION (MANDATORY)

    For EVERY planned action, you MUST assign a severity level and score based on the source data.

    Severity reflects impact + urgency + dependency risk, not just tone.

    You MUST compute for each planned action:
    - a categorical severity: Low | Medium | High
    - a numeric severityScore between 0.0 – 1.0

    ### Decision Matrix (STRICT)

    Evaluate the underlying source item (email, calendar event, document, Trello card, Slack message, etc.) across these dimensions:

    1. Time Sensitivity
    - Action required today or before a meeting → +0.4
    - Action required within 1–2 days → +0.2
    - No time constraint → +0.0

    2. Dependency Risk
    - Blocks others / meeting / decision → +0.3
    - Part of a workflow but not blocking → +0.15
    - Standalone / FYI → +0.0

    3. Sender / Context Importance
    - Manager, executive, client, or key stakeholder → +0.2
    - Internal team / peer → +0.1
    - Automated / low influence → +0.0

    4. User Preference Alignment
    - Matches the user's critical_def or priority_domains → +0.1
    - Neutral → +0.05
    - Historically ignored → +0.0

    ### Severity Score Calculation
    - severityScore = sum of applicable factors (cap at 1.0)

    ### Severity Mapping
    {SIVERY_SCORE_MAPPING}

    ### Rules
    - Severity MUST be logically consistent with:
      - the type of action (tool + execution_type),
      - any deadlines or meeting times in the source data,
      - whether the item blocks others or affects delivery/revenue/clients.
    - High severity actions should correspond to items that, if ignored today, create real risk or blockers.
    - Low severity actions should be optional, non-blocking, or pure awareness.
    - Severity must be explicit — never implied.

    MULTI-STEP ACTIONS AND CROSS-TOOL ACTIONS:
    - When you see "multi_step_requirements" or "multi_step_instruction" in the input, this indicates that multiple related actions are needed
    - When an email has "action_requirements" or "task_assignments" in its change_details, it requires actions across multiple tools
    - 🚨 CRITICAL: If an email has task_assignments, you MUST create MULTIPLE actions (1 Gmail + N Trello + N Slack), NOT just one Gmail action
    - 🚨 CRITICAL ACTION ORDER (MANDATORY - FOLLOW THIS EXACT SEQUENCE):
      For emails with task assignments, you MUST create actions in this order:
      1. FIRST: Gmail reply draft acknowledging the email (tool: "gmail")
         - Create EXACTLY ONE Gmail action
      2. SECOND: Create Trello tasks for EACH task assignment (tool: "trello")
         - For each task assignment (Role → Assignee), create ONE Trello task
         - If there are 4 task assignments, create 4 Trello actions
         - Example: If task_assignments shows "Backend → Amit", create: {"autopilot_id": "email-123", "action": "Create Trello task for Backend - Amit", "tool": "trello", "confidence": "high"}
      3. THIRD: Send Slack notifications to EACH team member about their assigned tasks (tool: "slack")
         - For each task assignment, send ONE Slack notification to the assignee
         - If there are 4 task assignments, create 4 Slack actions
         - Example: If task_assignments shows "Backend → Amit", create: {"autopilot_id": "email-123", "action": "Send Slack notification to Amit about Backend task assignment", "tool": "slack", "confidence": "high"}
      * ALL these actions MUST use the SAME email autopilot_id
      * Extract task assignments from the email's change_details.task_assignments (if present)
      * The task_assignments array will show you exactly how many actions to create
    - 🚨 VALIDATION: If an email has N task assignments, your response MUST include:
      * 1 action in the "gmail" array
      * N actions in the "trello_doc" array (one for each assignment)
      * N actions in the "slack_channel_messages" array (one for each assignee)
      * TOTAL: 1 + (N * 2) actions
    - Example: If email has autopilot_id "email-123" and task_assignments shows "Backend → Amit", "Testing → Soma":
      * Your response MUST include:
        {
          "gmail": [
            {"autopilot_id": "email-123", "action": "Reply to email about task assignments", "tool": "gmail", "confidence": "high"}
          ],
          "trello_doc": [
            {"autopilot_id": "email-123", "action": "Create Trello task for Backend - Amit", "tool": "trello", "confidence": "high"},
            {"autopilot_id": "email-123", "action": "Create Trello task for Testing - Soma", "tool": "trello", "confidence": "high"}
          ],
          "slack_channel_messages": [
            {"autopilot_id": "email-123", "action": "Send Slack notification to Amit about Backend task assignment", "tool": "slack", "confidence": "high"},
            {"autopilot_id": "email-123", "action": "Send Slack notification to Soma about Testing task assignment", "tool": "slack", "confidence": "high"}
          ]
        }
      * If you only return the "gmail" action, your response is INCOMPLETE and will be rejected

    IMPORTANT:
    - Return ONLY the JSON object, no additional text, greetings, or explanations
    - Do NOT include recommendations or informative insights
    - Do NOT plan to call any tools - only create action descriptions
    - Generate DIFFERENT actions for EACH source type based on their specific data
    - Include specific details from the source data (titles, senders, subjects, etc.) in the actions
    - 🔐 STEP 4: For each source item, generate at most one action per execution_type, unless strictly necessary.
      This prevents duplicate actions and reduces redundancy by ~70%.
    - CRITICAL: You MUST use the NEW FORMAT with arrays of objects containing autopilot_id. 
      DO NOT use the old format with action_1, action_2 keys. The old format is deprecated and will cause errors.
      Each action MUST be an object in an array with: {"autopilot_id": "...", "action": "...", "tool": "...", "confidence": "..."}
    - 🚨 FINAL WARNING: If you use an autopilot_id that doesn't exist in the source data, validation will FAIL and your response will be rejected.
      Always verify the autopilot_id exists in the changes_analysis.items[].autopilot_id before using it.
    """

    # FIX 1: Use AUTOPILOT_SYSTEM_PROMPT for strict JSON contract in autopilot endpoint
    # Set temperature to 0 for deterministic autopilot responses
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0,  # Deterministic for autopilot
        "system": Analyse_QUERY,  # FIX 1: Strict JSON contract for autopilot
        "messages": messages,
        "tools": claude_tools,
    }
    # print(f"Body: -----------------------------{body}")
    
    try:
        api_call_counter += 1
        response = invoke_openai_autopilot(body, token=token, ip_address=ip_address, start_time=request_start_time)
        
        # Extract and accumulate token usage
        if "_token_usage" in response:
            token_usage = response["_token_usage"]
            accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
            accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
            if accumulated_token_usage["model"] is None:
                accumulated_token_usage["model"] = token_usage.get("model", "")
            # System prompt tokens should be the same across calls, so only set once
            if accumulated_token_usage["system_prompt_tokens"] == 0:
                accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
        
        # print(f"Response: -----------------------------{response}")  # includes _token_usage; keep off
    except Exception as e:
        # ✅ ENHANCEMENT: Enhanced error handling with rate limit detection
        error_str = str(e).lower()
        is_bedrock_rate_limit = (
            "bedrock" in error_str and ("429" in error_str or "too many requests" in error_str or "rate limit" in error_str)
        )
        
        if is_bedrock_rate_limit:
            autopilot_log("warning", "⚠️ Bedrock rate limit (429) detected in /autoPilot planning")
            return jsonify({
                "error": "Rate limit exceeded. Please wait 30-60 seconds and try again.",
                "planned_action": {}
            }), 429
        
        # ✅ ENHANCEMENT: Comprehensive error logging
        log_error_to_terminal(
            error=e,
            context="Error calling Bedrock in /autoPilot planning",
            user_id=token,
        )
        user_message = get_user_friendly_error_message(e, "general")
        return jsonify({
            "error": user_message,
            "planned_action": {}
        }), 500

    # ✅ ENHANCEMENT: Robust JSON parsing function (similar to assistant_handler.py)
    def _extract_and_parse_json(text):
        """Extract and parse JSON from text with multiple fallback strategies."""
        # LLMs often wrap JSON in markdown code fences; strip those first.
        if isinstance(text, str):
            t = text.strip()
            t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
            t = re.sub(r"\s*```$", "", t)
            text = t
        # 1) Try direct parse
        try:
            return json.loads(text)
        except Exception:
            pass

        # 2) Extract first JSON block by balancing braces/brackets.
        # This avoids greedy/non-greedy regex issues with nested objects/arrays.
        def _balanced_extract(t: str):
            start_obj = t.find("{")
            start_arr = t.find("[")
            if start_obj == -1 and start_arr == -1:
                return None
            if start_obj == -1 or (start_arr != -1 and start_arr < start_obj):
                start = start_arr
                open_ch, close_ch = "[", "]"
            else:
                start = start_obj
                open_ch, close_ch = "{", "}"

            depth = 0
            in_str = False
            escape = False
            for i in range(start, len(t)):
                ch = t[i]
                if in_str:
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_str = False
                    continue
                else:
                    if ch == '"':
                        in_str = True
                        continue
                    if ch == open_ch:
                        depth += 1
                    elif ch == close_ch:
                        depth -= 1
                        if depth == 0:
                            return t[start : i + 1]
            return None

        candidate = _balanced_extract(text)
        if not candidate:
            return None
        try:
            return json.loads(candidate)
        except Exception:
            # 3) Try simple cleanup: remove trailing commas before } or ]
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                return json.loads(cleaned)
            except Exception:
                return None

    # Extract and parse the JSON from the response
    content = response.get("content", [])
    if content and len(content) > 0:
        text_content = content[0].get("text", "")
        # ✅ ENHANCEMENT: Use robust JSON parsing
        parsed_json = _extract_and_parse_json(text_content)
        if parsed_json is not None:
            # ✅ ENHANCEMENT: Validate that parsed_json is a dict, not a list
            if not isinstance(parsed_json, dict):
                autopilot_log("warning", f"Parsed JSON is not a dict (type: {type(parsed_json)}), treating as invalid")
                parsed_json = None
        
        if parsed_json is not None:
            planned_action = parsed_json.get("planned action") or parsed_json.get("planned_action", {})
            
            # Upsert (update or insert) AI usage document for today
            if accumulated_token_usage["model"]:
                # Calculate total tokens correctly: input + output + system_prompt (counted once)
                total_tokens = (
                    accumulated_token_usage["input_tokens"] +
                    accumulated_token_usage["output_tokens"] +
                    accumulated_token_usage["system_prompt_tokens"]
                )
                upsert_ai_usage(
                    token=token,
                    purpose="autopilot",
                    model=accumulated_token_usage["model"],
                    input_tokens=accumulated_token_usage["input_tokens"],
                    output_tokens=accumulated_token_usage["output_tokens"],
                    system_prompt_tokens=accumulated_token_usage["system_prompt_tokens"],
                    total_tokens=total_tokens,
                    ip_address=ip_address,
                    total_api_calls=api_call_counter,
                )
            
            # # Log final token usage summary if enabled (disabled: noisy)
            # if ENABLE_TOKEN_USAGE_LOGGING and accumulated_token_usage["model"]:
            #     total_tokens = (
            #         accumulated_token_usage["input_tokens"] +
            #         accumulated_token_usage["output_tokens"] +
            #         accumulated_token_usage["system_prompt_tokens"]
            #     )
            #     print(f"\n📊 Token Usage Summary (Autopilot):")
            #     print(f"   Input Tokens: {accumulated_token_usage['input_tokens']}")
            #     print(f"   System Prompt Tokens: {accumulated_token_usage['system_prompt_tokens']}")
            #     print(f"   Output Tokens: {accumulated_token_usage['output_tokens']}")
            #     print(f"   Total Tokens: {total_tokens}")
            #     print(f"   Model: {accumulated_token_usage['model']}")
            #     print(f"   Purpose: autopilot")
            #     print(f"   Total Response Time: {total_response_time:.3f}s")
            #     print(f"   API Calls: {api_call_counter}")
            #     print()
            
            if planned_action:
                return jsonify({"planned_action": planned_action})
            else:
                autopilot_log("warning", "Planning response has empty planned_action")
                return jsonify({"planned_action": {}})
        else:
            # ✅ ENHANCEMENT: Better error logging with context
            autopilot_log("warning", "No valid JSON found in planning response. Text preview: %s", text_content[:500] if text_content else "Empty")
            return jsonify({"error": "Failed to parse JSON from response", "planned_action": {}})
    else:
        autopilot_log("warning", "Empty content in planning response: %s", str(response))
        return jsonify({"planned_action": {}})


def _strip_owner_name_from_draft_body(body_text: str, owner_name: str) -> str:
    """
    Remove the account owner's name from draft body to avoid salutation/sign-off
    like "Hi Parth and Anmol," or "Best regards, Anmol". Owner must not appear in the draft.
    """
    if not body_text or not owner_name:
        return body_text or ""
    text = body_text
    escaped = re.escape(owner_name)
    # Salutation (first line): remove owner from "Hi Parth and Anmol," -> "Hi Parth,"
    # Remove ", Anmol" or " and Anmol" from the first line
    first_line_end = text.find("\n")
    first_line = text[: first_line_end] if first_line_end != -1 else text
    rest = text[len(first_line) :] if first_line_end != -1 else ""
    first_line = re.sub(re.compile(r",\s*" + escaped + r"\s*,?\s*$", re.IGNORECASE), ",", first_line)
    first_line = re.sub(re.compile(r"\s+and\s+" + escaped + r"\s*,?\s*$", re.IGNORECASE), ",", first_line)
    first_line = re.sub(re.compile(r"," + escaped + r"\s*$", re.IGNORECASE), "", first_line)
    # "Hi Anmol," only -> "Hi,"
    first_line = re.sub(
        re.compile(r"^(Hi|Hello|Hey)\s*,\s*" + escaped + r"\s*,?\s*", re.IGNORECASE),
        r"\1, ",
        first_line,
        count=1,
    )
    first_line = re.sub(
        re.compile(r"^(Hi|Hello|Hey)\s+" + escaped + r"\s*,?\s*", re.IGNORECASE),
        r"\1, ",
        first_line,
        count=1,
    )
    text = first_line + rest
    # Sign-off: "Best regards, Anmol" or "Regards,\nAnmol"
    text = re.sub(
        re.compile(
            r"(Best\s+regards|Regards|Thanks|Thank\s+you|Sincerely|Cheers)\s*,?\s*" + escaped + r"\s*$",
            re.IGNORECASE | re.MULTILINE,
        ),
        r"\1,",
        text,
    )
    # Standalone line that is only the owner's name (e.g. after "Best regards,")
    text = re.sub(
        re.compile(r"^" + escaped + r"\s*$", re.MULTILINE),
        "",
        text,
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@app.route("/autoPilot/execute", methods=["POST"])
def auto_autopilot_execute():
    """
    Phase 2 - EXECUTION endpoint.
    Input JSON (from generate_autopilot Phase 2):
    {
      "user_id": "...",
      "timestamp": "...",
      "items": [
        {
          "source_type": "slack_channel_messages",
          "source_data": { ... },
          "planned_action": { "action_1": "...", ... }
        },
        ...
      ],
      "planned_action": { "action_1": "...", ... }
    }

    This endpoint sends the payload to Bedrock with an EXECUTION prompt so the AI
    can return a structured description of how to perform each action.
    (Actual tool calls/execution can be added later based on this output.)
    """
    autopilot_log("info", "Received /autoPilot/execute request")

    # Reuse token handling for consistency (even if we don't need user context heavily yet)
    token, error_response, status_code = get_autopilot_token()
    if error_response:
        autopilot_log("error", "Token error (execute): %s", error_response.get_json())
        return error_response, status_code
    
    # Capture start time for response time tracking
    request_start_time = time.time()
    
    # Get user IP address for token tracking
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    if isinstance(ip_address, str) and ',' in ip_address:
        # Handle multiple IPs in X-Forwarded-For header
        ip_address = ip_address.split(',')[0].strip()

    # Track API call number for this request
    api_call_counter = 0
    
    # Accumulate token usage across all API calls
    accumulated_token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "system_prompt_tokens": 0,
        "total_tokens": 0,
        "model": None,
    }

    data = request.get_json(force=True) or {}

    # Resolve execution identity for tool calls.
    # Without HMAC: scheduler may send unified token in header and workspace user_id in body.
    # With AUTOPILOT_SECRET_KEY: header user is authoritative; ignore body user_id overrides.
    auth_token = token
    payload_user_id = (data.get("user_id") or "").strip() if isinstance(data.get("user_id"), str) else ""
    hmac_mode = bool((os.getenv("AUTOPILOT_SECRET_KEY") or "").strip())
    if hmac_mode:
        token = auth_token
    else:
        execution_token = payload_user_id or auth_token
        if payload_user_id and payload_user_id != auth_token:
            autopilot_log(
                "info",
                "autoPilot/execute using payload user_id for tool execution (auth token differs).",
            )
        token = execution_token
    autopilot_print(f"/autoPilot/execute payload: {json.dumps(data, default=str)[:1000]}")

    # ---------------------------------------------
    # Build lookup maps for server-side autopilot_id enrichment
    # ---------------------------------------------
    items = data.get("items", []) or []

    def _get_source_item_id_for_execution(source_type: str, item: dict):
        """
        Derive a stable source_item_id for an item based on its source type.
        Mirrors the logic in generate_autopilot._get_source_item_id so that
        we can reliably map executed actions back to source items.
        """
        if not isinstance(item, dict):
            return None

        if source_type == "g_docs":
            return item.get("document_id")
        if source_type == "g_sheets":
            return item.get("spreadsheet_id")
        if source_type == "g_slides":
            return item.get("presentation_id")
        if source_type == "gmail":
            return item.get("id")
        if source_type == "calendar":
            return item.get("id") or item.get("event_id")
        if source_type == "trello_doc":
            return item.get("page_id") or item.get("card_id")
        if source_type == "notion_doc":
            return item.get("page_id")
        if source_type == "slack_channel_messages":
            # Channel-level actions use channel_id as the stable identifier
            return item.get("channel_id")

        return None

    # Maps (source_type, source_item_id) -> autopilot_id, based on incoming payload
    source_autopilot_map = {}
    # Maps source_type -> set of autopilot_ids present in this payload (single-item fallback)
    source_type_autopilot_ids = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        st = item.get("source_type")
        if not st:
            continue

        source_data = item.get("source_data", {}) or {}
        item_level_ap = item.get("autopilot_id")

        for src in source_data.get("items", []) or []:
            if not isinstance(src, dict):
                continue

            ap_id = src.get("autopilot_id") or item_level_ap
            if not ap_id:
                continue

            sid = _get_source_item_id_for_execution(st, src)
            if not sid:
                continue

            st_key = str(st)
            sid_key = str(sid)
            ap_key = str(ap_id)

            source_autopilot_map[(st_key, sid_key)] = ap_key
            if st_key not in source_type_autopilot_ids:
                source_type_autopilot_ids[st_key] = set()
            source_type_autopilot_ids[st_key].add(ap_key)

    def _fallback_executed_actions_from_planned(data: dict) -> list:
        """If the execution model returns no executed_actions, build minimal rows from planned_action."""
        planned = data.get("planned_action") or {}
        if not isinstance(planned, dict) or not planned:
            return []
        items_list = data.get("items") or []
        out = []

        def _resolve_sid_for(st_key: str, ap_id):
            for it in items_list:
                if not isinstance(it, dict) or str(it.get("source_type")) != str(st_key):
                    continue
                for src in (it.get("source_data") or {}).get("items") or []:
                    if not isinstance(src, dict):
                        continue
                    if ap_id is not None and str(src.get("autopilot_id") or "") != str(ap_id):
                        continue
                    sid = _get_source_item_id_for_execution(st_key, src)
                    if sid:
                        return str(sid)
            return None

        for st_key, actions in planned.items():
            if not isinstance(actions, list):
                continue
            for i, pact in enumerate(actions):
                if not isinstance(pact, dict):
                    continue
                ap_id = pact.get("autopilot_id")
                action_desc = (pact.get("action") or "").strip()
                tool = (pact.get("tool") or "").strip().lower()
                sid = _resolve_sid_for(st_key, ap_id) or _resolve_sid_for(st_key, None)
                ea = {
                    "action_key": f"action_{i + 1}",
                    "source_type": st_key,
                    "source_item_id": sid,
                    "autopilot_id": ap_id,
                    "category": pact.get("category") or "must_act",
                    "reasons": f"Plan fallback (model returned no executed_actions): {action_desc}",
                }
                stl = str(st_key).lower()
                adl = action_desc.lower()
                # Planner may key trello as "trello" or "trello_doc"
                if stl == "trello":
                    stl = "trello_doc"
                if stl == "slack_channel_messages" or tool in ("slack", "slack_channel_messages"):
                    ea["execution_type"] = "slack_draft"
                    ch = sid
                    msg = action_desc
                    if action_desc and ":" in action_desc:
                        head, tail = action_desc.split(":", 1)
                        h = head.strip()
                        if h.startswith("C") and len(h) >= 8:
                            ch = h
                            msg = tail.strip()
                    ea["draft"] = {"channel_id": ch, "message": msg or "Acknowledged."}
                elif stl == "trello_doc" or tool in ("trello", "trello_doc"):
                    if "reply" in adl and "comment" in adl:
                        ea["execution_type"] = "trello_comment"
                        ea["trello_comment"] = {
                            "card_id": sid,
                            "text": f"Autopilot reply: {action_desc[:1500]}",
                        }
                    else:
                        ea["execution_type"] = "trello_task"
                        ea["task"] = {
                            "title": (action_desc[:200] or "Trello task"),
                            "description": action_desc,
                        }
                elif stl == "g_slides" or tool == "g_slides":
                    ea["execution_type"] = "doc_task"
                    ea["doc"] = {
                        "title": (action_desc[:120] or "Presentation"),
                        "body_text": action_desc,
                        "doc_type": "g_slides",
                    }
                elif stl == "g_docs" or tool == "g_docs":
                    ea["execution_type"] = "doc_task"
                    ea["doc"] = {
                        "title": (action_desc[:120] or "Document"),
                        "body_text": action_desc,
                        "doc_type": "g_docs",
                    }
                elif stl == "g_sheets" or tool == "g_sheets":
                    ea["execution_type"] = "doc_task"
                    ea["doc"] = {
                        "title": (action_desc[:120] or "Spreadsheet"),
                        "body_text": action_desc,
                        "doc_type": "g_sheets",
                    }
                elif stl == "notion_doc" or tool in ("notion", "notion_doc"):
                    ea["execution_type"] = "doc_task"
                    ea["doc"] = {
                        "title": (action_desc[:120] or "Notion page"),
                        "body_text": action_desc,
                        "doc_type": "notion",
                    }
                else:
                    continue
                out.append(ea)
        return out

    def _s_exec_id(val):
        if val is None or val == "":
            return None
        return str(val)

    def _merge_tool_payload_ids_into_created_ids(created_ids: dict, result) -> None:
        """
        Fill missing id fields from typical MCP/tool dict shapes (success responses only).
        Does not overwrite existing non-empty created_ids entries.
        """
        if not isinstance(created_ids, dict) or not isinstance(result, dict):
            return
        if result.get("status") == "error" or result.get("success") is False:
            return
        data = result.get("data") if isinstance(result.get("data"), dict) else None
        blocks = [b for b in (result, data) if isinstance(b, dict)]
        event = None
        for b in blocks:
            ev = b.get("event")
            if isinstance(ev, dict):
                event = ev
                break
        if event:
            blocks.append(event)

        def _set_if_missing(key: str, val):
            if val is None or val == "":
                return
            s = _s_exec_id(val)
            if not s:
                return
            if not created_ids.get(key):
                created_ids[key] = s

        for b in blocks:
            _set_if_missing("document_id", b.get("document_id"))
            _set_if_missing("doc_id", b.get("document_id") or b.get("doc_id"))
            _set_if_missing("spreadsheet_id", b.get("spreadsheet_id"))
            _set_if_missing("presentation_id", b.get("presentation_id"))
            _set_if_missing("page_id", b.get("page_id"))
            # card_id: never use bare "id" — calendar/event payloads also use "id" and would pollute Trello fields.
            _set_if_missing("card_id", b.get("card_id"))
            _set_if_missing("event_id", b.get("event_id") or b.get("id"))
            _set_if_missing("comment_id", b.get("comment_id"))
            # Gamma → Google Slides: file id lives on drive_info / driveInfo (see slides_mcp.gamma_create_presentation)
            for _dk in ("drive_info", "driveInfo"):
                _di = b.get(_dk)
                if isinstance(_di, dict):
                    _fid = _di.get("id") or _di.get("presentation_id") or _di.get("file_id")
                    if _fid:
                        _set_if_missing("presentation_id", _fid)
                        _set_if_missing("document_id", _fid)
                        _set_if_missing("doc_id", _fid)
                        break
            tid = b.get("thread_id") or b.get("threadId")
            if tid:
                _set_if_missing("thread_id", tid)
                _set_if_missing("gmail_thread_id", tid)
                _set_if_missing("threadId", tid)
            link = b.get("htmlLink") or b.get("html_link") or b.get("meeting_link")
            if link:
                _set_if_missing("html_link", link)
                _set_if_missing("meeting_link", link)

        if isinstance(data, dict):
            emails = data.get("emails")
            if isinstance(emails, list) and emails and isinstance(emails[0], dict):
                e0 = emails[0]
                _set_if_missing("gmail_draft_id", e0.get("id") or e0.get("draft_id"))
                _set_if_missing("draft_id", e0.get("id") or e0.get("draft_id"))
                tid = e0.get("threadId") or e0.get("thread_id")
                if tid:
                    _set_if_missing("thread_id", tid)
                    _set_if_missing("gmail_thread_id", tid)
                    _set_if_missing("threadId", tid)

    def _normalize_execution_created_ids(created_ids: dict, ea: dict) -> None:
        """
        Canonical id aliases for Mongo/UI (mutates created_ids in place).
        """
        if not isinstance(created_ids, dict):
            return

        g = created_ids.get("gmail_draft_id") or created_ids.get("draft_id")
        if g:
            s = _s_exec_id(g)
            created_ids["gmail_draft_id"] = s
            created_ids["draft_id"] = s

        ev = created_ids.get("event_id") or created_ids.get("calendar_event_id")
        if ev:
            s = _s_exec_id(ev)
            created_ids["event_id"] = s
            created_ids["calendar_event_id"] = s

        c = created_ids.get("card_id") or created_ids.get("trello_card_id")
        if c:
            s = _s_exec_id(c)
            created_ids["card_id"] = s
            created_ids["trello_card_id"] = s

        if created_ids.get("document_id"):
            created_ids["document_id"] = _s_exec_id(created_ids["document_id"])
            if not created_ids.get("doc_id"):
                created_ids["doc_id"] = created_ids["document_id"]
        elif created_ids.get("doc_id") and not created_ids.get("spreadsheet_id") and not created_ids.get("presentation_id"):
            # Google Doc / generic doc id
            if not created_ids.get("document_id"):
                created_ids["document_id"] = _s_exec_id(created_ids["doc_id"])

        if created_ids.get("spreadsheet_id"):
            created_ids["spreadsheet_id"] = _s_exec_id(created_ids["spreadsheet_id"])
            if not created_ids.get("doc_id"):
                created_ids["doc_id"] = created_ids["spreadsheet_id"]

        if created_ids.get("presentation_id"):
            created_ids["presentation_id"] = _s_exec_id(created_ids["presentation_id"])
            if not created_ids.get("doc_id"):
                created_ids["doc_id"] = created_ids["presentation_id"]

        if created_ids.get("page_id"):
            created_ids["page_id"] = _s_exec_id(created_ids["page_id"])
            # Notion executions often only set doc_id
            if ea.get("source_type") == "notion_doc" and not created_ids.get("doc_id"):
                created_ids["doc_id"] = created_ids["page_id"]

        tid = (
            created_ids.get("thread_id")
            or created_ids.get("gmail_thread_id")
            or created_ids.get("threadId")
        )
        if tid:
            s = _s_exec_id(tid)
            created_ids["thread_id"] = s
            created_ids["gmail_thread_id"] = s
            created_ids["threadId"] = s

        if ea.get("channel_id") and not created_ids.get("channel_id"):
            created_ids["channel_id"] = _s_exec_id(ea["channel_id"])

        # comment_reply: resource id lives in document_id — mirror type-specific keys for UI
        ex_t = ea.get("execution_type")
        st = ea.get("source_type") or ""
        if ex_t == "comment_reply" and created_ids.get("document_id"):
            base = _s_exec_id(created_ids["document_id"])
            if st == "g_sheets":
                created_ids.setdefault("spreadsheet_id", base)
            elif st == "g_slides":
                created_ids.setdefault("presentation_id", base)
            elif st == "g_docs":
                created_ids.setdefault("doc_id", base)

    # Resolve owner email and name for comment_reply (append to comment text + set on executed action so author shows correctly)
    # (Notion/Drive API may show "Unified Dashboard" as creator; we store real owner in executed_actions.)
    owner_email_for_comments = None
    owner_name_for_comments = None
    try:
        from db.mongo_client import get_mongo_client_by_db
        user_id_for_lookup = data.get("user_id") or token
        uw_db = get_mongo_client_by_db("unified_workspace")
        users_coll = uw_db["users"]
        udoc = users_coll.find_one({"user_id": str(user_id_for_lookup)}, {"email": 1, "name": 1, "full_name": 1, "display_name": 1})
        if udoc:
            if udoc.get("email"):
                owner_email_for_comments = (udoc["email"] or "").strip()
            owner_name_for_comments = (udoc.get("name") or udoc.get("full_name") or udoc.get("display_name") or "").strip() or owner_email_for_comments
    except Exception as e:
        autopilot_log("debug", f"Could not resolve owner email for comments: {e}")

    def _find_gmail_thread_id_for_execution(
        items_list, source_item_id, payload=None, autopilot_id=None
    ):
        """
        Resolve Gmail thread id for reply drafting and Mongo/UI persistence.

        Checks (in order):
        1) Gmail message id == source_item_id inside items[].source_data.items
        2) Any gmail row in items sharing the same autopilot_id (cross-tool runs)
        3) Top-level changes_analysis.gmail.items (generate_autopilot sends this)
        """
        def _tid_from_src(src):
            if not isinstance(src, dict):
                return None
            return (
                src.get("threadId")
                or src.get("thread_id")
                or src.get("thread")
            )

        # (1) Match by message id in items
        if source_item_id:
            sid = str(source_item_id)
            for it in items_list or []:
                if not isinstance(it, dict) or it.get("source_type") != "gmail":
                    continue
                src_block = it.get("source_data") or {}
                for src in src_block.get("items", []) or []:
                    if isinstance(src, dict) and str(src.get("id")) == sid:
                        tid = _tid_from_src(src)
                        if tid:
                            return str(tid)

        # (2) Same autopilot_id on any gmail item in items (e.g. doc-triggered plan, shared id)
        if autopilot_id:
            ap = str(autopilot_id)
            for it in items_list or []:
                if not isinstance(it, dict) or it.get("source_type") != "gmail":
                    continue
                src_block = it.get("source_data") or {}
                for src in src_block.get("items", []) or []:
                    if isinstance(src, dict) and str(src.get("autopilot_id") or "") == ap:
                        tid = _tid_from_src(src)
                        if tid:
                            return str(tid)

        # (3) changes_analysis on the execute payload
        if isinstance(payload, dict):
            ca = payload.get("changes_analysis")
            if isinstance(ca, dict):
                gblk = ca.get("gmail")
                if isinstance(gblk, dict):
                    g_items = gblk.get("items", []) or []
                    if source_item_id:
                        sid = str(source_item_id)
                        for src in g_items:
                            if isinstance(src, dict) and str(src.get("id")) == sid:
                                tid = _tid_from_src(src)
                                if tid:
                                    return str(tid)
                    if autopilot_id:
                        ap = str(autopilot_id)
                        for src in g_items:
                            if isinstance(src, dict) and str(src.get("autopilot_id") or "") == ap:
                                tid = _tid_from_src(src)
                                if tid:
                                    return str(tid)

        return None

    def _calendar_row_ids(src: dict) -> list:
        if not isinstance(src, dict):
            return []
        out = []
        for k in ("id", "event_id", "meeting_id", "eventId"):
            v = src.get(k)
            if v is not None and str(v).strip():
                out.append(str(v).strip())
        return out

    def _thread_from_calendar_row(src: dict):
        if not isinstance(src, dict):
            return None
        t = (
            src.get("threadId")
            or src.get("thread_id")
            or src.get("gmail_thread_id")
            or src.get("invite_thread_id")
        )
        if t is None or not str(t).strip():
            return None
        return str(t).strip()

    def _iter_calendar_source_rows(items_list, payload):
        for it in items_list or []:
            if not isinstance(it, dict):
                continue
            if str(it.get("source_type") or "").lower() != "calendar":
                continue
            sd = it.get("source_data") or {}
            for src in sd.get("items") or []:
                if isinstance(src, dict):
                    yield src
        if isinstance(payload, dict):
            ca = payload.get("changes_analysis") or {}
            if isinstance(ca, dict):
                cal = ca.get("calendar") or {}
                if isinstance(cal, dict):
                    for src in cal.get("items") or []:
                        if isinstance(src, dict):
                            yield src

    def _find_calendar_row_for_execution(items_list, payload, source_item_id, autopilot_id) -> dict | None:
        sid = str(source_item_id).strip() if source_item_id else ""
        ap = str(autopilot_id).strip() if autopilot_id else ""
        rows = list(_iter_calendar_source_rows(items_list, payload))
        for src in rows:
            if sid:
                for rid in _calendar_row_ids(src):
                    if rid == sid:
                        return src
        for src in rows:
            if ap and str(src.get("autopilot_id") or "").strip() == ap:
                return src
        return None

    def _find_gmail_thread_from_calendar_source(items_list, payload, source_item_id, autopilot_id):
        row = _find_calendar_row_for_execution(items_list, payload, source_item_id, autopilot_id)
        if not row:
            return None
        return _thread_from_calendar_row(row)

    def _header_email_lower(s) -> str:
        if not s:
            return ""
        m = re.search(r"<([^>]+)>", str(s))
        addr = m.group(1).strip() if m else str(s).strip()
        return addr.lower() if addr else ""

    def _try_resolve_calendar_invite_thread_via_query_emails(calendar_row, token_arg, user_id_arg):
        """
        Best-effort: find a Gmail thread_id in Mongo for the calendar invite / updates
        (same meeting title, preferably from organizer). Used when calendar row has no threadId.
        """
        qe = tools.get("search_emails")
        if not qe or not isinstance(calendar_row, dict):
            return None
        title = (calendar_row.get("title") or calendar_row.get("summary") or "").strip()
        if len(title) < 3:
            return None
        org_raw = calendar_row.get("organiser") or calendar_row.get("organizer") or ""
        if isinstance(org_raw, dict):
            org_raw = org_raw.get("email") or org_raw.get("emailAddress") or ""
        org_email = str(org_raw).strip().lower()

        try:
            res = wrap_tool_execution(
                tool_func=qe,
                tool_name="search_emails",
                args={"query": title, "max_results": 15, "token": token_arg},
                user_id=user_id_arg,
            )
        except Exception:
            return None
        if not isinstance(res, dict):
            return None
        if res.get("status") == "error" or res.get("success") is False:
            return None
        msgs = res.get("messages") or []
        if not msgs:
            return None

        title_l = title.lower()
        invite_kw = ("invitation:", "invited you", "calendar", "accepted:", "declined:", "updated invitation")

        def org_matches(msg: dict) -> bool:
            if not org_email:
                return True
            return org_email in _header_email_lower(msg.get("from"))

        # Strong: event title appears in subject + thread + organizer matches from header
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            tid = str(msg.get("thread_id") or "").strip()
            if not tid:
                continue
            subj = str(msg.get("subject") or "").lower()
            if title_l not in subj:
                continue
            if org_matches(msg):
                return tid

        # Title in subject, any sender
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            tid = str(msg.get("thread_id") or "").strip()
            if not tid:
                continue
            subj = str(msg.get("subject") or "").lower()
            if title_l in subj:
                return tid

        # Calendar-notification subject + organizer
        for msg in msgs:
            if not isinstance(msg, dict):
                continue
            tid = str(msg.get("thread_id") or "").strip()
            if not tid:
                continue
            subj = str(msg.get("subject") or "").lower()
            if not any(k in subj for k in invite_kw):
                continue
            if org_matches(msg) and (title_l in subj or title_l in str(msg.get("body") or "").lower()):
                return tid

        return None

    EXECUTION_QUERY = """
    You are an AUTONOMOUS AUTOPILOT EXECUTION AGENT - PHASE 2.

    You receive:
    - items: array of workspace changes, each with:
      * source_type: the type (gmail, calendar, g_docs, trello_doc, slack_channel_messages, etc.)
      * source_data: the actual data for that source (items array, etc.)
      * planned_action: a JSON object with action_1, action_2, ... describing urgent actions for THIS source type
    - planned_action: (legacy/fallback) a shared JSON object with action_1, action_2, ... if per-item actions are not available
    - autopilot_workspace_vector_context: (optional) Pre-computed semantic search bullets across the user's workspace (Gmail, Slack, Docs, Calendar, etc.). When present, you MUST use the relevant parts when drafting gmail_draft body_text and slack_draft message — weave facts into the prose; do not dump the list as a raw appendix.
    - autopilot_workspace_doc_links: (optional) Lines like "- Title: https://..." with real document URLs from that search. When present, include each URL verbatim in gmail_draft and/or slack_draft where it helps the recipient (inline or on its own line). Never invent or alter URLs.

    Your job:
    - Iterate through EACH item in the items array:
      - For EACH action in that item's planned_action (action_1, action_2, ...):
        - Interpret what the action means.
        - Link it to the source_type and source item (by id) from that item's source_data.
      - Decide the execution_type:
        * "gmail_draft" for any email reply or follow-up.
        * "slack_draft" for any Slack reply.
        * "doc_task" for any document CREATION task (Google Docs/Sheets/Slides/Notion) - NOT for comment replies.
        * "comment_reply" for replying to comments in Google Docs/Sheets/Slides - this posts the reply directly in the original document.
        * "trello_task" for any Trello/card/task creation or update.
        * "calendar_event" for creating or updating calendar events (NOT for sending reminders - use gmail_draft for that).
      - For gmail_draft:
        * Prepare a draft object with fields: to, subject, body_text.
        * to: derive from the original email's sender or participants. CRITICAL: NEVER set "to" or "cc" to the account owner's email. Reply drafts are for replying TO other people only, not to the owner.
        * subject: a clear subject line, usually reusing or refining the original subject.
        * body_text: a well-formed plain text email reply. CRITICAL: Do NOT include the account owner's name in the body: no "Hi [owner name]" in salutation and no "Best regards, [owner name]" (or similar) in sign-off. If the input includes owner_identity.name, do not use that name in body_text.
        * If autopilot_workspace_vector_context or autopilot_workspace_doc_links is in the input JSON, incorporate that context and include the listed URLs in body_text where appropriate.
      - For slack_draft:
        * Prepare a draft object with fields: channel_id, message.
        * channel_id: Slack channel id where the reply should go.
        * message: BRIEF, to-the-point reply only. Use 1-3 short sentences. No long paragraphs, no lengthy explanations, no repetition of the original message. Get straight to the response (e.g., acknowledgment, answer, or next step). Do NOT include the account owner's name in the message (no "Hi [owner]" or "Best regards, [owner]").
        * If autopilot_workspace_vector_context or autopilot_workspace_doc_links is in the input JSON, incorporate that context and include the listed URLs in message where appropriate (keep compact).
      - For doc_task:
        * IMPORTANT: When the action is about replying to a COMMENT on a document (g_docs, g_sheets, g_slides):
          - DO NOT create a new document
          - Instead, use execution_type "comment_reply" (see below)
        * For document CREATION (not comment replies): Prepare a doc object with title, body_text, and doc_type
        * CRITICAL: The doc_type MUST match the intended output. Google Slides creation IS supported:
          - If source_type is "notion_doc" → use doc_type "notion"
          - If source_type is "g_docs" → use doc_type "g_docs"
          - If source_type is "g_sheets" → use doc_type "g_sheets" (for new sheets) or "g_docs" (for summary docs)
          - If source_type is "g_slides" OR the action says "create presentation", "create slides", "Google Slides" → use doc_type "g_slides"
          - DO NOT use "g_docs" when the action explicitly requests a presentation or slides. Use "g_slides" and the create_slide_deck tool will create a real Google Slides presentation.
          - DO NOT default to "g_docs" for Notion pages - always use "notion" when source_type is "notion_doc"
      - For comment_reply (NEW - for replying to comments in Google Docs/Sheets/Slides):
        * Prepare a comment_reply object with: document_id (the original document ID from source_item_id), comment_text (the reply text)
        * document_id: Use the source_item_id from the item (e.g., document_id for g_docs, spreadsheet_id for g_sheets, presentation_id for g_slides)
        * comment_text: The actual reply text to post as a comment in the original document
        * This will post the reply directly as a comment in the original document using the Drive API, not create a new document
      - For trello_task:
        * Prepare a task object with: board_name, list_name, title, description, and optional due date.
        * If not board_name by default take the first board in the user's workspace and list_name always consider "Doing" if its not present, create a new list with name "Doing".
      - For calendar_event:
        * ONLY use this for creating NEW calendar events or updating EXISTING calendar events (changing time, attendees, etc.)
        * Prepare an event object with: title, start_time, end_time, and optional attendees/emails.
        * IMPORTANT: For sending reminders or follow-ups about calendar events (e.g., when attendees haven't responded), use "gmail_draft" instead, NOT "calendar_event".
      - Compose a ONE-LINE explanation in natural language (reasons) describing:
        * who it involves, what is being done, when (relative to now or dates), and why (motivation/purpose).
        * IMPORTANT: Include specific details from the source_data in the reasons field:
          - For emails: Include subject, sender name/email, and date (e.g., "An email with subject 'Unified Update' was received from John Doe (john@example.com) on 2026-01-27, so a reply is created acknowledging the email receipt")
          - For documents: Include document title, modification date, and who modified it (e.g., "Document 'Project Plan' was modified by Jane Smith on 2026-01-27, so a review document is created to track changes")
          - For calendar events: Include event title, date/time, and attendee details (e.g., "Calendar event 'Weekly Meeting' scheduled for 2026-01-27 at 2:00 PM has attendees who haven't responded, so a reminder email is sent")
          - For Slack: Include channel name, message sender, and timestamp (e.g., "A message was posted in #general by Alice on 2026-01-27, so a reply draft is created")
          - For Trello: Include card title, board name, and creation/modification date (e.g., "Trello card 'Task Review' was created in board 'Project Board' on 2026-01-27, so a review comment is added")
          - For comments: Include document title, comment author, and comment text snippet (e.g., "A comment was added by Bob on document 'Report' saying 'Need review', so a reply comment is posted")

    OUTPUT FORMAT:
    - Return ONLY a JSON object with this structure:
    {
      "executed_actions": [
        {
          "action_key": "action_1",
          "source_type": "gmail",
          "source_item_id": "gmail_message_id_or_other_id",
          "autopilot_id": "exact_autopilot_id_from_planned_action_or_source_item",
          "execution_type": "gmail_draft",
          "category": "must_act | should_progress | respond | awarness",
          "reasons": "An email with subject 'Q1 project plan' was received from Alice (alice@example.com) on 2026-01-27, so a reply is created acknowledging the email receipt and confirming next steps.",
          "draft": {
            "to": "alice@example.com",
            "subject": "Re: Q1 project plan",
            "body_text": "Hi Alice, ..."
          }
        },
        {
          "action_key": "action_1",
          "source_type": "g_docs",
          "source_item_id": "document_id_here",
          "autopilot_id": "exact_autopilot_id_from_planned_action_or_source_item",
          "execution_type": "comment_reply",
          "category": "must_act | should_progress | respond | awarness",
          "reasons": "On 2026-01-27, replied to comment on document to address the question.",
          "comment_reply": {
            "document_id": "document_id_here",
            "comment_text": "Thank you for your comment. Here's my response..."
          }
        }
      ],
      "meta": {
        "notes": "Any overall notes about conflicts, dependencies, or assumptions"
      }
    }

    RULES:
    - If the planned actions asks to create a clendar event, then always call create_event tool, never call update_calendar_event tool for creating new events.
    - OWNER RULE (CRITICAL): The account owner must NEVER be the recipient of a reply draft. For gmail_draft, never set "to" or "cc" to the owner's email. Do NOT put the owner's name in the draft body (no "Hi [owner]", no "Best regards, [owner]"). For slack_draft, do not address the message solely to the owner and do not include the owner's name in the message. Reply drafts are for replying to OTHER people only.
    - WORKSPACE CONTEXT RULE: When autopilot_workspace_vector_context and/or autopilot_workspace_doc_links appear in the input, they were computed before this response — use them to make gmail_draft and slack_draft accurate and helpful; include document URLs from autopilot_workspace_doc_links exactly as given.
    - Process ALL items in the items array and ALL actions in each item's planned_action.
    - Generate executed_actions for ALL source types (gmail, calendar, g_docs, trello_doc, slack_channel_messages, etc.), not just Slack.
    - Each item's planned_action contains actions specific to that source_type - use them accordingly.
    - DO NOT duplicate outcomes: for each autopilot_id, output at most ONE action per outcome type — one presentation (g_slides/doc_task), one comment_reply, one gmail_draft. If the input already includes executed_actions with a completed action of that type for the same autopilot_id, do NOT add another; the need is already satisfied.
    - For EVERY object in executed_actions, you MUST include an autopilot_id field:
      * Copy autopilot_id EXACTLY from the corresponding planned_action entry when available.
      * If not available in planned_action, copy it from the matching source item in items[].source_data.items[].autopilot_id.
      * NEVER invent, transform, or change autopilot_id values; they must match the values used in the planning phase.
      * For cross-tool actions (e.g., Trello / Slack actions triggered by an email), reuse the SAME email autopilot_id as in the planning output.
    - Do NOT include any greetings, explanations, or markdown.
    - Do NOT include text before or after the JSON.
    - If you are unsure about an action, still include it with execution_type = "uncertain" and explain in reasons.
    """

    # Preflight: vector search BEFORE the execution LLM so drafts are produced in one Bedrock call.
    execute_llm_payload = dict(data) if isinstance(data, dict) else {}
    execute_vector_preflight_meta: dict = {}
    if isinstance(data, dict) and _autopilot_draft_vector_context_enabled():
        kw_exec = _build_execute_payload_vector_keywords(data)
        if kw_exec.strip():
            _vbullets, _vmeta, _vlinks = _autopilot_vector_context_for_draft(
                tools_dict=tools,
                token=token,
                user_id=token,
                keywords=kw_exec,
                tool_hint=None,
                limit=8,
                max_items=10,
                max_total=6000,
            )
            execute_vector_preflight_meta = dict(_vmeta or {})
            if _vbullets:
                execute_llm_payload["autopilot_workspace_vector_context"] = _vbullets[:12000]
            if _vlinks:
                execute_llm_payload["autopilot_workspace_doc_links"] = _vlinks[:8000]
            autopilot_log(
                "debug",
                "execute preflight vector_context: query=%r matches=%s links=%s",
                kw_exec[:120],
                execute_vector_preflight_meta.get("vector_context_match_count"),
                bool(_vlinks),
            )

    # Build Bedrock body
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0,  # deterministic execution planning
        "system": EXECUTION_QUERY,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(execute_llm_payload, default=str),
                    }
                ],
            }
        ],
        # No tools for now; this phase just describes execution steps.
    }

    try:
        # Preload Slack channels for this user so that we never
        # accept hallucinated / non-existent channel_ids in slack_draft actions.
        # We also keep basic metadata (member_count) so we can prefer real group
        # channels over self/DM channels when falling back.
        valid_slack_channel_ids = set()
        slack_channel_index: dict[str, dict] = {}
        try:
            from db.mongo_client import get_mongo_client_by_db  # local import to avoid circular issues
            user_id_for_db = data.get("user_id") or token
            user_db = get_mongo_client_by_db(str(user_id_for_db))
            slack_channels_col = user_db["slack_channels"]
            for ch in slack_channels_col.find({}, {"channel_id": 1, "member_count": 1, "members": 1, "name": 1, "type": 1}):
                cid = ch.get("channel_id")
                if not cid:
                    continue
                valid_slack_channel_ids.add(cid)
                slack_channel_index[cid] = ch
        except Exception as e:
            autopilot_log("warning", f"⚠️ Could not load slack_channels for channel validation: {e}")
            valid_slack_channel_ids = set()
        api_call_counter += 1
        response = invoke_openai_autopilot(body, token=token, ip_address=ip_address, start_time=request_start_time)
        
        # Extract and accumulate token usage
        if "_token_usage" in response:
            token_usage = response["_token_usage"]
            accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
            accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
            if accumulated_token_usage["model"] is None:
                accumulated_token_usage["model"] = token_usage.get("model", "")
            # System prompt tokens should be the same across calls, so only set once
            if accumulated_token_usage["system_prompt_tokens"] == 0:
                accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
        
        # autopilot_print(f"/autoPilot/execute Bedrock response: {response}")  # includes _token_usage; keep off
        content = response.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text_content = content[0].get("text", "")
            # ✅ ENHANCEMENT: Use robust JSON parsing (reuse function from planning endpoint)
            def _extract_and_parse_json_execute(text):
                """Extract and parse JSON from text with multiple fallback strategies."""
                # LLMs often wrap JSON in markdown code fences; strip those first.
                if isinstance(text, str):
                    t = text.strip()
                    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
                    t = re.sub(r"\s*```$", "", t)
                    text = t
                # 1) Try direct parse
                try:
                    return json.loads(text)
                except Exception:
                    pass

                # 2) Extract first JSON block by balancing braces/brackets.
                def _balanced_extract(t: str):
                    start_obj = t.find("{")
                    start_arr = t.find("[")
                    if start_obj == -1 and start_arr == -1:
                        return None
                    if start_obj == -1 or (start_arr != -1 and start_arr < start_obj):
                        start = start_arr
                        open_ch, close_ch = "[", "]"
                    else:
                        start = start_obj
                        open_ch, close_ch = "{", "}"

                    depth = 0
                    in_str = False
                    escape = False
                    for i in range(start, len(t)):
                        ch = t[i]
                        if in_str:
                            if escape:
                                escape = False
                            elif ch == "\\":
                                escape = True
                            elif ch == '"':
                                in_str = False
                            continue
                        else:
                            if ch == '"':
                                in_str = True
                                continue
                            if ch == open_ch:
                                depth += 1
                            elif ch == close_ch:
                                depth -= 1
                                if depth == 0:
                                    return t[start : i + 1]
                    return None

                candidate = _balanced_extract(text)
                if not candidate:
                    return None
                try:
                    return json.loads(candidate)
                except Exception:
                    # 3) Try simple cleanup: remove trailing commas before } or ]
                    cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
                    try:
                        return json.loads(cleaned)
                    except Exception:
                        return None
            
            parsed = _extract_and_parse_json_execute(text_content)
            if parsed is not None:
                # ✅ ENHANCEMENT: Validate that parsed is a dict, not a list
                if not isinstance(parsed, dict):
                    autopilot_log("warning", f"Parsed JSON is not a dict (type: {type(parsed)}), treating as invalid")
                    parsed = None
            
            if parsed is not None:
                if execute_vector_preflight_meta:
                    pm = parsed.get("meta")
                    if not isinstance(pm, dict):
                        pm = {}
                        parsed["meta"] = pm
                    pm["vector_preflight"] = execute_vector_preflight_meta
                executed_actions = parsed.get("executed_actions", []) or []
                if not executed_actions:
                    fb = _fallback_executed_actions_from_planned(data)
                    if fb:
                        autopilot_log(
                            "warning",
                            "Empty executed_actions from Bedrock; using %s fallback row(s) from planned_action",
                            len(fb),
                        )
                        executed_actions = fb

                enriched_actions = []
                for ea in executed_actions:
                    if not isinstance(ea, dict):
                        continue

                    # Default read_status for each executed action (e.g. for UI "read/unread")
                    if not ea.get("read_status"):
                        ea["read_status"] = "false"
                    # Default delete_status flag (e.g. for soft-delete UI)
                    if "delete_status" not in ea:
                        ea["delete_status"] = False

                    # ---------------------------------------------
                    # Server-side autopilot_id enrichment (safety net)
                    # ---------------------------------------------
                    if not ea.get("autopilot_id"):
                        st = ea.get("source_type")
                        sid = ea.get("source_item_id")
                        ap_id = None

                        # Primary lookup: by (source_type, source_item_id)
                        if st and sid:
                            ap_id = source_autopilot_map.get((str(st), str(sid)))

                        # Fallback: if exactly one autopilot_id exists for this source_type in the payload
                        if not ap_id and st:
                            st_key = str(st)
                            candidates = list(source_type_autopilot_ids.get(st_key, []))
                            if len(candidates) == 1:
                                ap_id = candidates[0]

                        if ap_id:
                            ea["autopilot_id"] = ap_id

                    # Add execution timestamp to each executed action
                    if not ea.get("executed_at"):
                        ea["executed_at"] = datetime.now(timezone.utc).isoformat()
                    ex_type = ea.get("execution_type")
                    created_ids = ea.get("created_ids") or {}
                    # Default status before execution; run execution when not already completed/failed
                    if not ea.get("status"):
                        ea["status"] = "planned"
                    # Run execution for planned/pending actions (LLM may return status "planned")
                    _run_execution = ea.get("status") not in ("completed", "failed")

                    # Normalize: LLM sometimes returns execution_type "g_slides" for create-presentation actions.
                    # Treat as doc_task with doc_type g_slides so create_slide_deck runs and we get presentation_id.
                    if ex_type == "g_slides":
                        draft_or_doc = ea.get("draft") or ea.get("doc") or ea.get("doc_task") or {}
                        if not isinstance(draft_or_doc, dict):
                            draft_or_doc = {}
                        # Always coerce to doc_task for g_slides so we never fall through with no handler
                        if not draft_or_doc.get("title"):
                            draft_or_doc["title"] = (ea.get("action") or "Presentation")[:200]
                        if not draft_or_doc.get("doc_type"):
                            draft_or_doc["doc_type"] = "g_slides"
                        ex_type = "doc_task"
                        ea["doc"] = {k: v for k, v in draft_or_doc.items() if v is not None}
                        if ea.get("doc") and not ea["doc"].get("doc_type"):
                            ea["doc"]["doc_type"] = "g_slides"

                    # Gmail drafts: always create draft and store draft id
                    if ex_type == "gmail_draft":
                            draft = ea.get("draft") or {}
                            to_raw = draft.get("to")
                            cc_raw = draft.get("cc") or ""
                            subject = draft.get("subject")
                            body_text = draft.get("body_text")
                            # Owner must never be in reply draft recipients
                            owner_email_lower = None
                            if data.get("owner_identity") and data["owner_identity"].get("email"):
                                owner_email_lower = (data["owner_identity"]["email"] or "").strip().lower()
                            if not owner_email_lower and owner_email_for_comments:
                                owner_email_lower = (owner_email_for_comments or "").strip().lower()
                            def _parse_and_filter_recipients(recipients_str, owner):
                                if not recipients_str or not owner:
                                    return (recipients_str or "").strip()
                                kept = []
                                for part in (recipients_str or "").split(","):
                                    part = part.strip()
                                    if not part:
                                        continue
                                    email = part
                                    match = re.search(r"<([^>]+)>", part)
                                    if match:
                                        email = match.group(1).strip()
                                    if email and email.lower() != owner:
                                        kept.append(part)
                                return ", ".join(kept) if kept else ""
                            to = _parse_and_filter_recipients(to_raw, owner_email_lower) if to_raw else ""
                            cc = _parse_and_filter_recipients(cc_raw, owner_email_lower) if cc_raw else ""
                            if owner_email_lower and (to_raw or cc_raw) and not to and to_raw:
                                created_ids["error"] = "Reply draft must not be addressed to the account owner only. Remove owner from 'to' and use the original sender or other participants."
                                ea["status"] = "failed"
                            elif to and subject and body_text:
                                # Strip owner's name from draft body (salutation / sign-off)
                                owner_name = (data.get("owner_identity") or {}).get("name") or ""
                                if isinstance(owner_name, str) and owner_name.strip():
                                    body_text = _strip_owner_name_from_draft_body(body_text, owner_name.strip())
                                compose_args = {
                                    "to": to,
                                    "subject": subject,
                                    "body_text": body_text,
                                    "token": token,
                                }
                                # Thread id: model may pass it; else resolve from Gmail payload (message id / autopilot_id).
                                thread_id = None
                                for _src in (draft, ea):
                                    if not isinstance(_src, dict):
                                        continue
                                    for _k in ("thread_id", "threadId", "gmail_thread_id"):
                                        _v = _src.get(_k)
                                        if _v is not None and str(_v).strip():
                                            thread_id = str(_v).strip()
                                            break
                                    if thread_id:
                                        break
                                if not thread_id:
                                    try:
                                        thread_id = _find_gmail_thread_id_for_execution(
                                            items,
                                            ea.get("source_item_id"),
                                            data,
                                            ea.get("autopilot_id"),
                                        )
                                    except Exception:
                                        thread_id = None

                                _src_type = str(ea.get("source_type") or "").strip().lower()
                                _gmail_source = _src_type == "gmail"

                                # Calendar-triggered gmail_draft: prefer thread from calendar row, then Mongo
                                # invite search (title + organizer), so reminders can reply in the invite thread.
                                if not thread_id and _src_type == "calendar":
                                    try:
                                        thread_id = _find_gmail_thread_from_calendar_source(
                                            items,
                                            data,
                                            ea.get("source_item_id"),
                                            ea.get("autopilot_id"),
                                        )
                                    except Exception:
                                        thread_id = None
                                if not thread_id and _src_type == "calendar":
                                    cal_row = _find_calendar_row_for_execution(
                                        items,
                                        data,
                                        ea.get("source_item_id"),
                                        ea.get("autopilot_id"),
                                    )
                                    if cal_row:
                                        try:
                                            thread_id = _try_resolve_calendar_invite_thread_via_query_emails(
                                                cal_row, token, token
                                            )
                                        except Exception:
                                            thread_id = None
                                        if thread_id:
                                            created_ids["gmail_thread_resolved_via"] = (
                                                "calendar_invite_mongo"
                                            )

                                if thread_id:
                                    thread_id = str(thread_id).strip() or None

                                # With thread_id: Gmail drafts.create attaches message.threadId → in-thread reply.
                                # Without thread_id: draft_email still succeeds — Gmail creates a new draft with no
                                # thread (first message in a new conversation when sent). Use this when the source
                                # item has no threadId (first email, or metadata gap).
                                if thread_id:
                                    compose_args["thread_id"] = thread_id
                                    created_ids["thread_id"] = str(thread_id)
                                    created_ids["gmail_thread_id"] = str(thread_id)
                                    created_ids["threadId"] = str(thread_id)
                                    ea["thread_id"] = str(thread_id)
                                    created_ids["gmail_draft_mode"] = "thread_reply"
                                else:
                                    created_ids["gmail_draft_mode"] = "standalone"
                                    if _gmail_source:
                                        created_ids["gmail_thread_note"] = (
                                            "No threadId on source; draft is a new message (not in-reply-to thread)."
                                        )
                                        autopilot_log(
                                            "warning",
                                            "gmail_draft: no thread_id for gmail source; creating standalone draft",
                                        )
                                    else:
                                        autopilot_log(
                                            "info",
                                            "gmail_draft: no thread_id; creating standalone draft (source_type=%s)",
                                            _src_type or "(unset)",
                                        )
                                if cc:
                                    compose_args["cc"] = cc
                                try:
                                    if ea.get("status") == "failed" and created_ids.get("error"):
                                        result = None
                                    else:
                                        result = wrap_tool_execution(
                                            tool_func=tools["draft_email"],
                                            tool_name="draft_email",
                                            args=compose_args,
                                            user_id=token,
                                        )
                                    gmail_draft_id = None
                                    if isinstance(result, dict):
                                        # Check for error in multiple possible formats
                                        if result.get("status") == "error" or result.get("success") == False:
                                            # Tool-level error already logged by wrap_tool_execution
                                            error_msg = result.get("message") or result.get("error") or "Unknown error"
                                            created_ids["error"] = error_msg
                                            ea["status"] = "failed"
                                            autopilot_log("error", f"Gmail draft creation failed: {error_msg}")
                                        else:
                                            # Success case - extract draft ID
                                            data_block = result.get("data", {})
                                            if isinstance(data_block, dict):
                                                emails = data_block.get("emails") or []
                                                if emails and isinstance(emails, list) and len(emails) > 0:
                                                    gmail_draft_id = emails[0].get("id")
                                                # Also try direct draft_id field as fallback
                                                if not gmail_draft_id:
                                                    gmail_draft_id = data_block.get("draft_id") or data_block.get("id")
                                            # Fallback: try top-level fields
                                            if not gmail_draft_id:
                                                gmail_draft_id = result.get("draft_id") or result.get("id")
                                            
                                            created_ids["gmail_draft_id"] = gmail_draft_id
                                            if gmail_draft_id:
                                                created_ids["draft_id"] = str(gmail_draft_id)
                                                ea["draft_id"] = str(gmail_draft_id)
                                                _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                                if not created_ids.get("thread_id"):
                                                    tid_from_result = (
                                                        (result.get("data", {}) or {})
                                                        .get("emails", [{}])[0]
                                                        .get("threadId")
                                                        if isinstance((result.get("data", {}) or {}).get("emails"), list)
                                                        and (result.get("data", {}) or {}).get("emails")
                                                        else result.get("threadId")
                                                    )
                                                    if tid_from_result:
                                                        created_ids["thread_id"] = str(tid_from_result)
                                                        created_ids["gmail_thread_id"] = str(tid_from_result)
                                                        created_ids["threadId"] = str(tid_from_result)
                                                        ea["thread_id"] = str(tid_from_result)
                                                ea["status"] = "completed"
                                                autopilot_log("debug", f"Gmail draft created successfully with ID: {gmail_draft_id}")
                                            else:
                                                ea["status"] = "failed"
                                                created_ids["error"] = "Gmail draft created but no draft ID found in response"
                                                autopilot_log("warning", f"Gmail draft response missing ID. Response: {json.dumps(result, default=str)[:500]}")
                                    elif result is not None:
                                        created_ids["error"] = f"Unexpected response type from draft_email: {type(result)}"
                                        ea["status"] = "failed"
                                except Exception as tool_err:
                                    log_error_to_terminal(
                                        error=tool_err,
                                        context="Error creating Gmail draft in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    ea["status"] = "failed"

                    # Slack drafts: always text-only drafts, no sending
                    elif ex_type == "slack_draft":
                            _d_raw = ea.get("draft") if isinstance(ea.get("draft"), dict) else {}
                            _sd_raw = (
                                ea.get("slack_draft")
                                if isinstance(ea.get("slack_draft"), dict)
                                else {}
                            )
                            # Models often return slack_draft {channel_id, message}; canonical key is draft.
                            draft = {**_sd_raw, **_d_raw}
                            channel_id = draft.get("channel_id") or ea.get("channel_id")
                            message = (draft.get("message") or draft.get("text") or "").strip()
                            if not message and isinstance(ea.get("draft_message"), str):
                                message = ea.get("draft_message", "").strip()
                            if not channel_id and str(
                                ea.get("source_type") or ""
                            ).lower() == "slack_channel_messages":
                                sid = ea.get("source_item_id")
                                if sid is not None and str(sid).strip():
                                    channel_id = str(sid).strip()
                            if channel_id:
                                draft["channel_id"] = channel_id
                            if message:
                                draft["message"] = message
                            ea["draft"] = draft
                            ea["slack_draft"] = draft
                            if channel_id and message:
                                # Validate channel_id against real Slack channels from DB.
                                # Never allow hallucinated / non-existent channel IDs in the final payload.
                                if not valid_slack_channel_ids:
                                    created_ids["error"] = "No Slack channels available for validation; skipping Slack draft to avoid using a hallucinated channel_id."
                                    ea["status"] = "failed"
                                    ea["channel_id"] = channel_id
                                    ea["draft_message"] = message
                                elif channel_id not in valid_slack_channel_ids:
                                    # Fallback: if requested channel_id is not a real Slack channel for this user,
                                    # route the draft to a real group channel from slack_channels.
                                    # Prefer channels where member_count > 1 (avoid self/DM channels).
                                    fallback_channel_id = None
                                    try:
                                        # slack_channel_index is populated when loading valid_slack_channel_ids
                                        group_candidates = [
                                            (cid, ch)
                                            for cid, ch in (slack_channel_index or {}).items()
                                            if (ch.get("member_count") or len(ch.get("members") or [])) > 1
                                        ]
                                        if group_candidates:
                                            # Choose the first group channel deterministically (sorted by channel_id)
                                            group_candidates.sort(key=lambda t: t[0])
                                            fallback_channel_id = group_candidates[0][0]
                                        elif valid_slack_channel_ids:
                                            # As a last resort, fall back to any valid channel id
                                            fallback_channel_id = sorted(valid_slack_channel_ids)[0]
                                    except Exception as _slack_fallback_err:
                                        autopilot_log(
                                            "warning",
                                            f"Error while selecting Slack fallback channel: {_slack_fallback_err}"
                                        )
                                    if not fallback_channel_id:
                                        created_ids["error"] = f"Invalid Slack channel_id '{channel_id}' (not present in slack_channels) and no fallback channel available."
                                        ea["status"] = "failed"
                                        ea["channel_id"] = channel_id
                                        ea["draft_message"] = message
                                    else:
                                        autopilot_log(
                                            "warning",
                                            f"Slack draft channel_id '{channel_id}' not found; falling back to '{fallback_channel_id}' from slack_channels."
                                        )
                                        created_ids["original_channel_id"] = channel_id
                                        created_ids["resolved_channel_id"] = fallback_channel_id
                                        # Update draft + local variable so the rest of the pipeline uses the real channel_id
                                        draft["channel_id"] = fallback_channel_id
                                        channel_id = fallback_channel_id
                                        # and then proceed as a valid Slack draft using the resolved channel_id
                                        draft_key = f"{channel_id}::{abs(hash(message))}"
                                        created_ids["slack_draft_key"] = draft_key
                                        created_ids["channel_id"] = str(channel_id)
                                        ea["status"] = "completed"
                                        # Ensure top-level fields never expose the hallucinated channel id
                                        ea["channel_id"] = channel_id
                                        ea["draft_message"] = message
                                        draft["channel_id"] = channel_id
                                        draft["message"] = message
                                        ea["draft"] = draft
                                        ea["slack_draft"] = draft
                                        if not ea.get("id"):
                                            ea["id"] = channel_id
                                else:
                                    # Stable draft key per channel + message hash
                                    draft_key = f"{channel_id}::{abs(hash(message))}"
                                    created_ids["slack_draft_key"] = draft_key
                                    created_ids["channel_id"] = str(channel_id)
                                    ea["status"] = "completed"
                                    # Propagate validated channel to top-level fields
                                    ea["channel_id"] = channel_id
                                    ea["draft_message"] = message
                                    draft["channel_id"] = channel_id
                                    draft["message"] = message
                                    ea["draft"] = draft
                                    ea["slack_draft"] = draft
                                    if not ea.get("id"):
                                        ea["id"] = channel_id
                            else:
                                # Missing channel_id or message – mark as failed; still surface partial fields for UI
                                created_ids["error"] = "Missing channel_id or message for Slack draft"
                                ea["status"] = "failed"
                                ea["channel_id"] = channel_id if channel_id else None
                                ea["draft_message"] = message if message else None

                    # Comment replies: reply directly to comments in Google Docs/Sheets/Slides
                    elif ex_type == "comment_reply":
                            comment_reply = ea.get("comment_reply") or {}
                            document_id = comment_reply.get("document_id") or ea.get("source_item_id")
                            comment_text = comment_reply.get("comment_text") or comment_reply.get("reply_text") or comment_reply.get("text")
                            source_type = ea.get("source_type", "")
                            
                            if not document_id:
                                created_ids["error"] = "Missing required field: document_id or source_item_id"
                                ea["status"] = "failed"
                            elif not comment_text:
                                created_ids["error"] = "Missing required field: comment_text or reply_text"
                                ea["status"] = "failed"
                            else:
                                # Use the dedicated Google Docs comment tool (via MCP / tools registry)
                                # This posts a top-level comment on the original document as the authenticated user.
                                # Append the commenter's email so it is visible in the document (Drive API does not expose author email in the request).
                                text_to_post = (comment_text or "").strip()
                                if owner_email_for_comments:
                                    text_to_post = text_to_post + "\n\n— " + owner_email_for_comments
                                try:
                                    if source_type == "g_sheets":
                                        comment_args = {
                                            "spreadsheet_id": document_id,
                                            "text": text_to_post,
                                            "token": token,
                                        }
                                        tool_func = tools.get("add_sheet_comment")
                                        tool_name = "add_sheet_comment"
                                    elif source_type == "notion_doc":
                                        # Notion: use notion_add_comment (page_id = document_id). Do NOT use add_document_comment.
                                        comment_args = {
                                            "page_id": document_id,
                                            "content": text_to_post,
                                            "token": token,
                                            "target_type": "page",
                                        }
                                        block_id = comment_reply.get("block_id")
                                        if block_id:
                                            comment_args["target_type"] = "block"
                                            comment_args["block_id"] = block_id
                                        tool_func = tools.get("notion_add_comment")
                                        tool_name = "notion_add_comment"
                                        if not tool_func:
                                            created_ids["error"] = "Notion comment tool (notion_add_comment) not available. Notion integration may not be configured."
                                            ea["status"] = "failed"
                                    else:
                                        # Google Docs / g_docs, g_slides
                                        comment_args = {
                                            "document_id": document_id,
                                            "text": text_to_post,
                                            "token": token,
                                        }
                                        tool_func = tools.get("add_document_comment")
                                        tool_name = "add_document_comment"

                                    if tool_func:
                                        result = wrap_tool_execution(
                                            tool_func=tool_func,
                                            tool_name=tool_name,
                                            args=comment_args,
                                            user_id=token,
                                        )

                                        comment_id = None
                                        if isinstance(result, dict):
                                            # Check for error in multiple possible formats
                                            if result.get("status") == "error" or result.get("success") is False:
                                                error_msg = result.get("message") or result.get("error") or "Unknown error"
                                                created_ids["error"] = error_msg
                                                ea["status"] = "failed"
                                                autopilot_log("error", f"Comment reply failed: {error_msg}")
                                            elif source_type == "notion_doc":
                                                # Notion API returns {"status": "success", "message": "..."} with no comment_id
                                                if result.get("status") == "success":
                                                    created_ids["page_id"] = str(document_id)
                                                    created_ids["document_id"] = str(document_id)
                                                    created_ids["doc_id"] = str(document_id)
                                                    ea["status"] = "completed"
                                                    # So stored executed_actions show real owner, not "Unified Dashboard"
                                                    if owner_email_for_comments:
                                                        ea["author_email"] = owner_email_for_comments
                                                    if owner_name_for_comments or owner_email_for_comments:
                                                        ea["author"] = owner_name_for_comments or owner_email_for_comments
                                                    autopilot_log("debug", "Notion comment posted successfully")
                                                else:
                                                    if not created_ids.get("error"):
                                                        created_ids["error"] = result.get("message") or "Notion comment API did not return success"
                                                    ea["status"] = "failed"
                                            else:
                                                data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                                comment_id = (
                                                    data_block.get("comment_id")
                                                    or data_block.get("id")
                                                    or result.get("comment_id")
                                                )

                                        if source_type != "notion_doc":
                                            if comment_id:
                                                created_ids["comment_id"] = str(comment_id)
                                                created_ids["document_id"] = str(document_id)
                                                if source_type == "g_sheets":
                                                    created_ids["spreadsheet_id"] = str(document_id)
                                                elif source_type == "g_slides":
                                                    created_ids["presentation_id"] = str(document_id)
                                                elif source_type == "g_docs":
                                                    created_ids["doc_id"] = str(document_id)
                                                ea["status"] = "completed"
                                                if owner_email_for_comments:
                                                    ea["author_email"] = owner_email_for_comments
                                                if owner_name_for_comments or owner_email_for_comments:
                                                    ea["author"] = owner_name_for_comments or owner_email_for_comments
                                            else:
                                                # No explicit error, but no ID returned either
                                                if not created_ids.get("error"):
                                                    created_ids["error"] = "Comment created but no ID returned"
                                                ea["status"] = "failed"

                                except ImportError:
                                    created_ids["error"] = "Could not import comment tool" + (" (Notion)" if source_type == "notion_doc" else " (Docs/Sheets)")
                                    ea["status"] = "failed"
                                except Exception as api_err:
                                    log_error_to_terminal(
                                        error=api_err,
                                        context=f"Error adding comment to {source_type} in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    # For Notion, do not fall back to creating a Google Doc; report failure only.
                                    if source_type == "notion_doc":
                                        created_ids["error"] = f"Notion comment failed: {str(api_err)}"
                                        ea["status"] = "failed"
                                    else:
                                        # If Drive API comment creation fails, fall back to creating a document with the reply
                                        try:
                                            reply_doc_title = f"Comment Reply for {source_type.replace('_', ' ').title()}"
                                            create_args = {
                                                "title": reply_doc_title,
                                                "initial_text": f"REPLY TO COMMENT IN ORIGINAL DOCUMENT:\n\nDocument ID: {document_id}\n\nReply Text:\n{text_to_post}\n\n[Please post this as a comment reply in the original document]",
                                                "token": token,
                                            }
                                            result = wrap_tool_execution(
                                                tool_func=tools.get("create_document"),
                                                tool_name="create_document",
                                                args=create_args,
                                                user_id=token,
                                            )
                                            doc_id = None
                                            if isinstance(result, dict) and result.get("status") != "error":
                                                data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                                doc_id = data_block.get("document_id") or data_block.get("id") or result.get("document_id")
                                                created_ids["doc_id"] = doc_id
                                                if doc_id:
                                                    created_ids["document_id"] = str(doc_id)
                                                created_ids["original_document_id"] = document_id
                                                created_ids["note"] = f"Comment API failed ({str(api_err)}). Reply document created. Please post as comment reply manually."
                                                _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                                ea["status"] = "completed" if doc_id else "failed"
                                            else:
                                                created_ids["error"] = f"Comment API failed: {str(api_err)}. Document creation also failed."
                                                ea["status"] = "failed"
                                        except Exception as fallback_err:
                                            created_ids["error"] = f"Comment API failed: {str(api_err)}. Fallback document creation also failed: {str(fallback_err)}"
                                            ea["status"] = "failed"

                    # Document tasks (e.g., create Google Doc or Notion page)
                    elif ex_type == "doc_task":
                            # Some models may return the payload under 'draft', 'doc', or 'doc_task'.
                            # Normalize so we always have title/body_text/doc_type.
                            doc = ea.get("doc") or ea.get("draft") or ea.get("doc_task") or {}
                            title = doc.get("title")
                            body_text = doc.get("body_text") or doc.get("description")
                            
                            # 🔧 FIX: Determine doc_type from source_type if not provided in doc
                            source_type = ea.get("source_type", "")
                            doc_type = doc.get("doc_type")
                            if not doc_type:
                                # Map source_type to doc_type
                                if source_type == "notion_doc":
                                    doc_type = "notion"
                                elif source_type == "g_sheets":
                                    doc_type = "g_sheets"
                                elif source_type == "g_slides":
                                    doc_type = "g_slides"
                                elif source_type == "g_docs":
                                    doc_type = "g_docs"
                                else:
                                    # Default fallback
                                    doc_type = "g_docs"

                            # 🔧 SAFEGUARD: Override to g_slides when action/title clearly request Slides — not reasons.
                            # Reasons often say "review the summary presentation" for a *document* task; matching
                            # "presentation" there incorrectly sent review notes through Gamma (see Slack doc_task logs).
                            action_text = (ea.get("action") or "").lower()
                            title_lower = (title or "").lower()
                            _wants_slides_creation = (
                                "google slides" in action_text
                                or "google slides" in title_lower
                                or "slide deck" in action_text
                                or "slide deck" in title_lower
                                or "create presentation" in action_text
                                or "create a presentation" in action_text
                                or "new presentation" in action_text
                                or "powerpoint" in action_text
                                or "powerpoint" in title_lower
                                or (
                                    "presentation" in title_lower
                                    and ("slide" in title_lower or "slides" in title_lower)
                                )
                            )
                            if doc_type == "g_docs" and _wants_slides_creation:
                                doc_type = "g_slides"
                                autopilot_log("debug", "doc_task: Overriding doc_type to g_slides (presentation/slides detected)")

                            autopilot_log("debug", f"doc_task: source_type={source_type}, doc_type={doc_type}")
                            
                            # Check for missing required fields
                            if not title:
                                created_ids["error"] = "Missing required field: title"
                                ea["status"] = "failed"
                            elif not body_text and doc_type != "g_slides":
                                # body_text optional for g_slides (create_slide_deck only needs title)
                                created_ids["error"] = "Missing required field: body_text or description"
                                ea["status"] = "failed"
                            elif doc_type == "g_docs":
                                # Create Google Doc via create_document
                                # NOTE: create_document expects 'initial_text', not 'content'
                                create_args = {
                                    "title": title,
                                    "initial_text": body_text,
                                    "token": token,
                                }
                                try:
                                    result = wrap_tool_execution(
                                        tool_func=tools.get("create_document"),
                                        tool_name="create_document",
                                        args=create_args,
                                        user_id=token,
                                    )
                                    doc_id = None
                                    if isinstance(result, dict) and result.get("status") == "error":
                                        # Tool returned an explicit error
                                        created_ids["error"] = result.get("message")
                                        ea["status"] = "failed"
                                    elif isinstance(result, dict):
                                        # Handle both flat and data-wrapped shapes
                                        data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                        doc_id = data_block.get("document_id") or data_block.get("id") or result.get("document_id")
                                        created_ids["doc_id"] = doc_id
                                        if doc_id:
                                            created_ids["document_id"] = str(doc_id)
                                        _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                        ea["status"] = "completed" if doc_id else "failed"
                                    else:
                                        created_ids["error"] = "Unexpected response format from create_document"
                                        ea["status"] = "failed"
                                except KeyError:
                                    created_ids["error"] = "create_document tool not found"
                                    ea["status"] = "failed"
                                except Exception as tool_err:
                                    log_error_to_terminal(
                                        error=tool_err,
                                        context="Error creating document in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    created_ids["error"] = str(tool_err)
                                    ea["status"] = "failed"
                            elif doc_type == "notion":
                                # Handle Notion document creation
                                # Prefer create_parent_page (doesn't require parent) over create_page (requires parent/database)
                                notion_tool = tools.get("create_parent_page")
                                if not notion_tool:
                                    # Fallback to create_page if create_parent_page is not available
                                    notion_tool = tools.get("create_page")
                                
                                if not notion_tool:
                                    created_ids["error"] = "Notion creation tool not found (create_parent_page or create_page)"
                                    ea["status"] = "failed"
                                else:
                                    try:
                                        # Prefer create_parent_page which doesn't require a parent_id
                                        # But if source_item_id is available, use it as parent to create as child page
                                        if tools.get("create_parent_page"):
                                            create_args = {
                                                "title": title,
                                                "content": body_text,
                                                "token": token,
                                            }
                                            # If we have a source_item_id (the original Notion page), use it as parent
                                            source_item_id = ea.get("source_item_id")
                                            if source_item_id:
                                                create_args["parent_page_id"] = source_item_id
                                            tool_name = "create_parent_page"
                                        else:
                                            # create_page requires parent_id, database_id, or database_name
                                            # Try to use the source_item_id as parent
                                            parent_id = ea.get("source_item_id")  # Use the source Notion page as parent if available
                                            create_args = {
                                                "title": title,
                                                "content": body_text,
                                                "token": token,
                                            }
                                            if parent_id:
                                                create_args["parent_id"] = parent_id
                                            else:
                                                # Try to use database_name as fallback
                                                create_args["database_name"] = "AutoPilot Pages"  # Default database name
                                            tool_name = "create_page"
                                        
                                        result = wrap_tool_execution(
                                            tool_func=notion_tool,
                                            tool_name=tool_name,
                                            args=create_args,
                                            user_id=token,
                                        )
                                        page_id = None
                                        if isinstance(result, dict):
                                            # Check for error status
                                            if result.get("status") == "error" or result.get("success") == False:
                                                error_msg = result.get("error") or result.get("message") or "Unknown error"
                                                created_ids["error"] = error_msg
                                                ea["status"] = "failed"
                                            else:
                                                # Try multiple possible response formats
                                                data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                                page_id = (
                                                    data_block.get("page_id") 
                                                    or data_block.get("id") 
                                                    or result.get("page_id")
                                                    or result.get("id")
                                                    or (data_block.get("page") and data_block["page"].get("id"))
                                                )
                                                if page_id:
                                                    created_ids["doc_id"] = page_id
                                                    created_ids["page_id"] = str(page_id)
                                                    _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                                    ea["status"] = "completed"
                                                else:
                                                    created_ids["error"] = f"No page_id found in response. Response: {str(result)[:200]}"
                                                    ea["status"] = "failed"
                                        else:
                                            created_ids["error"] = f"Unexpected response format from Notion tool. Got: {type(result)}"
                                            ea["status"] = "failed"
                                    except Exception as tool_err:
                                        log_error_to_terminal(
                                            error=tool_err,
                                            context="Error creating Notion document in /autoPilot/execute",
                                            user_id=token,
                                        )
                                        created_ids["error"] = f"Exception: {str(tool_err)}"
                                        ea["status"] = "failed"
                            elif doc_type == "g_sheets":
                                # Create Google Sheet via create_sheet
                                create_args = {
                                    "title": title,
                                    "token": token,
                                }
                                try:
                                    result = wrap_tool_execution(
                                        tool_func=tools.get("create_sheet"),
                                        tool_name="create_sheet",
                                        args=create_args,
                                        user_id=token,
                                    )
                                    sheet_id = None
                                    if isinstance(result, dict) and result.get("status") == "error":
                                        created_ids["error"] = result.get("message")
                                        ea["status"] = "failed"
                                    elif isinstance(result, dict):
                                        # Handle both flat and data-wrapped shapes
                                        data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                        sheet_id = data_block.get("spreadsheet_id") or data_block.get("id") or result.get("spreadsheet_id") or result.get("id")
                                        created_ids["doc_id"] = sheet_id
                                        created_ids["spreadsheet_id"] = sheet_id
                                        if sheet_id:
                                            created_ids["document_id"] = str(sheet_id)
                                        _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                        ea["status"] = "completed" if sheet_id else "failed"
                                    else:
                                        created_ids["error"] = "Unexpected response format from create_sheet"
                                        ea["status"] = "failed"
                                except KeyError:
                                    created_ids["error"] = "create_sheet tool not found"
                                    ea["status"] = "failed"
                                except Exception as tool_err:
                                    log_error_to_terminal(
                                        error=tool_err,
                                        context="Error creating Google Sheet in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    created_ids["error"] = str(tool_err)
                                    ea["status"] = "failed"
                            elif doc_type == "g_slides":
                                # Prefer Gamma pipeline; on failure fall back to native Google Slides (create_slide_deck).
                                create_args = {
                                    "title": title,
                                    "input_text": body_text or f"Create a presentation titled: {title}",
                                    "token": token,
                                }

                                def _merge_tool_err_into_created_ids(res: dict) -> None:
                                    if not isinstance(res, dict):
                                        return
                                    if res.get("detail"):
                                        created_ids["error_detail"] = res["detail"]
                                    elif res.get("error_details"):
                                        created_ids["error_detail"] = res["error_details"]
                                    elif res.get("message"):
                                        # Friendly message alone is not enough for Mongo debug; keep full text
                                        created_ids["error_detail"] = str(res.get("message"))
                                    if res.get("error_type"):
                                        created_ids["error_type"] = res["error_type"]

                                def _slide_id_from_gamma_dict(res: dict):
                                    """Resolve Google Slides file id from Gamma/create_gamma_presentation payloads.

                                    Drive export stores the real Slides file under data.drive_info or data.driveInfo
                                    (camelCase appears after JSON round-trips). Prefer that over data.id, which is
                                    often Gamma's doc/generation id or empty.
                                    """
                                    if not isinstance(res, dict):
                                        return None

                                    def _id_from_drive(di: dict):
                                        if not isinstance(di, dict):
                                            return None
                                        rid = (
                                            di.get("presentation_id")
                                            or di.get("id")
                                            or di.get("file_id")
                                        )
                                        return str(rid) if rid else None

                                    def _from_block(block: dict):
                                        if not isinstance(block, dict):
                                            return None
                                        for dk in ("drive_info", "driveInfo"):
                                            got = _id_from_drive(block.get(dk))
                                            if got:
                                                return got
                                        if block.get("presentation_id"):
                                            return str(block["presentation_id"])
                                        if block.get("id"):
                                            return str(block["id"])
                                        return None

                                    for b in (
                                        res,
                                        res.get("data") if isinstance(res.get("data"), dict) else None,
                                    ):
                                        if isinstance(b, dict):
                                            got = _from_block(b)
                                            if got:
                                                return got
                                    inner = res.get("data") if isinstance(res.get("data"), dict) else None
                                    if isinstance(inner, dict) and isinstance(inner.get("data"), dict):
                                        got = _from_block(inner["data"])
                                        if got:
                                            return got
                                    return None

                                def _try_native_slides_deck():
                                    """Return Google Slides file id via Slides API (empty deck). Most reliable for autopilot."""
                                    deck_tool = tools.get("create_slide_deck")
                                    if not deck_tool:
                                        return None
                                    fb = wrap_tool_execution(
                                        tool_func=deck_tool,
                                        tool_name="create_slide_deck",
                                        args={"title": title, "token": token},
                                        user_id=token,
                                    )
                                    if not isinstance(fb, dict):
                                        return None
                                    if fb.get("status") == "error" or fb.get("success") is False:
                                        _merge_tool_err_into_created_ids(fb)
                                        return None
                                    blk = fb.get("data") if isinstance(fb.get("data"), dict) else fb
                                    raw = (
                                        blk.get("presentation_id")
                                        or blk.get("presentationId")
                                        or blk.get("id")
                                        or fb.get("presentation_id")
                                        or fb.get("presentationId")
                                        or fb.get("id")
                                    )
                                    return str(raw) if raw else None

                                def _build_slide_outline() -> list:
                                    """Build meaningful slide sections from available action/doc context."""
                                    draft_text = (body_text or "").strip()
                                    reason_text = str(ea.get("reasons") or "").strip()
                                    action_line = str(ea.get("action") or "").strip()

                                    # Prefer explicit "Slide N: ..." outlines when provided by planner/LLM.
                                    explicit = []
                                    current = None
                                    for raw_line in draft_text.splitlines():
                                        line = raw_line.strip()
                                        if not line:
                                            continue
                                        m = re.match(r"(?i)^slide\s*\d+\s*:\s*(.+)$", line)
                                        if m:
                                            if current:
                                                explicit.append(current)
                                            current = {"heading": m.group(1).strip(), "bullets": []}
                                            continue
                                        if current and (line.startswith("-") or line.startswith("•")):
                                            bullet = line.lstrip("-• ").strip()
                                            if bullet:
                                                current["bullets"].append(bullet)
                                    if current:
                                        explicit.append(current)
                                    if explicit:
                                        return explicit[:8]

                                    src_parts = [p for p in [draft_text, reason_text, action_line] if p]
                                    source_text = "\n".join(src_parts)
                                    bullet_pool = []
                                    for raw_line in source_text.splitlines():
                                        line = (raw_line or "").strip()
                                        if (
                                            not line
                                            or line.lower().startswith("http")
                                            or "calendar.google.com" in line.lower()
                                        ):
                                            continue
                                        # Skip meta-instructions that shouldn't appear on slides.
                                        if re.search(r"(?i)\bplease\s+add\b", line):
                                            continue
                                        # Normalize numbered lists: "1. Something" / "2) Something"
                                        mnum = re.match(r"^\s*\d+\s*[.)]\s*(.+)$", line)
                                        if mnum:
                                            line = mnum.group(1).strip()
                                        # Drop common lead-in phrases.
                                        line = re.sub(
                                            r"(?i)^create (a|an)?\s*presentation\b.*?:\s*",
                                            "",
                                            line,
                                        ).strip()
                                        # Remove leading bullet markers and extra separators.
                                        line = line.lstrip("-•* ").strip()
                                        if len(line) < 8:
                                            continue
                                        if line not in bullet_pool:
                                            bullet_pool.append(line)

                                    if not bullet_pool:
                                        bullet_pool = [
                                            "Objective and expected outcomes for this presentation",
                                            "Current context and why this item requires attention now",
                                            "Key facts extracted from the source message",
                                            "Recommended approach and sequencing",
                                            "Risks, dependencies, and open questions",
                                            "Immediate next actions before the meeting",
                                        ]

                                    slides = []
                                    slides.append(
                                        {
                                            "heading": "Purpose and Context",
                                            "bullets": [
                                                action_line or f"Presentation for: {title}",
                                                reason_text or "Prepared from autopilot source context",
                                            ],
                                        }
                                    )

                                    chunk_size = 3
                                    chunk_index = 0
                                    section_number = 1
                                    while chunk_index < len(bullet_pool) and len(slides) < 7:
                                        chunk = bullet_pool[chunk_index : chunk_index + chunk_size]
                                        slides.append(
                                            {
                                                "heading": f"Key Points {section_number}",
                                                "bullets": chunk,
                                            }
                                        )
                                        chunk_index += chunk_size
                                        section_number += 1

                                    slides.append(
                                        {
                                            "heading": "Next Steps",
                                            "bullets": [
                                                "Review and refine content for audience relevance",
                                                "Add supporting visuals/examples for each key point",
                                                "Finalize speaker notes and meeting decisions",
                                            ],
                                        }
                                    )
                                    return slides[:8]

                                def _populate_native_slides_deck(presentation_id: str) -> dict:
                                    """Populate a native Slides deck with generated, meaningful content."""
                                    add_slide_tool = tools.get("add_slide_to_presentation")
                                    add_text_tool = tools.get("add_text_box_to_slide")
                                    if not add_text_tool:
                                        return {
                                            "success": False,
                                            "error": "add_text_box_to_slide tool not available",
                                        }

                                    outline = _build_slide_outline()
                                    if not outline:
                                        return {"success": False, "error": "No slide outline available"}

                                    def _add_text(slide_index: int, text: str, x: float, y: float, w: float, h: float):
                                        return wrap_tool_execution(
                                            tool_func=add_text_tool,
                                            tool_name="add_text_box_to_slide",
                                            args={
                                                "presentation_id": presentation_id,
                                                "slide_index": slide_index,
                                                "text": text,
                                                "x": x,
                                                "y": y,
                                                "width": w,
                                                "height": h,
                                                "token": token,
                                            },
                                            user_id=token,
                                        )

                                    # Use first slide as title slide.
                                    subtitle = str(ea.get("reasons") or "").strip() or "Auto-generated by Autopilot"
                                    _add_text(0, title, 60, 60, 840, 80)
                                    _add_text(0, subtitle[:600], 80, 170, 800, 180)

                                    populated = 1
                                    errors = []
                                    for idx, section in enumerate(outline, start=1):
                                        if add_slide_tool:
                                            add_res = wrap_tool_execution(
                                                tool_func=add_slide_tool,
                                                tool_name="add_slide_to_presentation",
                                                args={
                                                    "presentation_id": presentation_id,
                                                    "layout": "TITLE_AND_BODY",
                                                    "token": token,
                                                },
                                                user_id=token,
                                            )
                                            if (
                                                isinstance(add_res, dict)
                                                and (
                                                    add_res.get("status") == "error"
                                                    or add_res.get("success") is False
                                                )
                                            ):
                                                errors.append(str(add_res.get("message") or "Failed to add slide"))

                                        heading = section.get("heading") or f"Section {idx}"
                                        bullets = section.get("bullets") or []
                                        bullets_text = "\n".join(
                                            [f"• {b}" for b in bullets if str(b).strip()]
                                        )[:4000]
                                        _add_text(idx, heading, 60, 45, 860, 70)
                                        if bullets_text:
                                            _add_text(idx, bullets_text, 80, 140, 820, 360)
                                        populated += 1

                                    return {
                                        "success": True,
                                        "slides_added": max(populated - 1, 0),
                                        "slides_populated": populated,
                                        "errors": errors[:5],
                                    }

                                try:
                                    # Native Slides FIRST: avoids Mongo errors when Gamma is down, misconfigured, or returns no Drive id.
                                    native_id = _try_native_slides_deck()
                                    if native_id:
                                        created_ids["doc_id"] = native_id
                                        created_ids["presentation_id"] = native_id
                                        created_ids["document_id"] = native_id
                                        created_ids["slides_creation_mode"] = "google_slides_native"
                                        populate_res = _populate_native_slides_deck(native_id)
                                        if isinstance(populate_res, dict) and populate_res.get("success"):
                                            created_ids["slides_populated"] = populate_res.get("slides_populated")
                                            if populate_res.get("errors"):
                                                created_ids["slides_population_warnings"] = populate_res.get("errors")
                                            created_ids["info"] = (
                                                "Created and populated Google Slides presentation (native) "
                                                "with AI-generated content from task context."
                                            )
                                        else:
                                            created_ids["slides_population_error"] = (
                                                (populate_res or {}).get("error")
                                                if isinstance(populate_res, dict)
                                                else "Unknown population error"
                                            )
                                            created_ids["info"] = (
                                                "Created Google Slides presentation (native), but auto-content "
                                                "population was partial/failed."
                                            )
                                        ea["status"] = "completed"
                                    else:
                                        # Optional: Gamma when native Slides failed (e.g. token / API error)
                                        gamma_tool = tools.get("create_gamma_presentation")
                                        if not gamma_tool:
                                            created_ids["error"] = (
                                                "create_slide_deck failed and create_gamma_presentation is not available"
                                            )
                                            ea["status"] = "failed"
                                        else:
                                            result = wrap_tool_execution(
                                                tool_func=gamma_tool,
                                                tool_name="create_gamma_presentation",
                                                args=create_args,
                                                user_id=token,
                                            )
                                            slide_id = None
                                            gamma_failed = False
                                            gamma_err_msg = None

                                            if not isinstance(result, dict):
                                                created_ids["error"] = "Unexpected response format from create_gamma_presentation"
                                                gamma_failed = True
                                            elif (
                                                result.get("status") == "error"
                                                or result.get("success") is False
                                                or result.get("type") == "error"
                                            ):
                                                gamma_failed = True
                                                gamma_err_msg = (
                                                    result.get("message")
                                                    or result.get("error")
                                                    or "Failed to create gamma presentation"
                                                )
                                                created_ids["error"] = gamma_err_msg
                                                _merge_tool_err_into_created_ids(result)
                                            else:
                                                slide_id = _slide_id_from_gamma_dict(result)
                                                if not slide_id:
                                                    gamma_failed = True
                                                    created_ids["error"] = (
                                                        "Gamma presentation created but no presentation id returned"
                                                    )
                                                    if isinstance(result.get("data"), dict):
                                                        created_ids["gamma_response_excerpt"] = str(result.get("data"))[:2000]
                                                    _merge_tool_err_into_created_ids(result)

                                            if slide_id:
                                                created_ids.pop("error", None)
                                                created_ids["doc_id"] = slide_id
                                                created_ids["presentation_id"] = slide_id
                                                created_ids["document_id"] = slide_id
                                                _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                                created_ids["slides_creation_mode"] = "gamma"
                                                ea["status"] = "completed"
                                            elif gamma_failed:
                                                if not created_ids.get("error"):
                                                    created_ids["error"] = (
                                                        gamma_err_msg or "Gamma presentation step failed"
                                                    )
                                                nd = created_ids.get("error_detail") or ""
                                                if nd and str(nd) not in str(
                                                    created_ids.get("error") or ""
                                                ):
                                                    created_ids["error"] = (
                                                        f"{created_ids['error']} | native_slides_error: {nd}"
                                                    )
                                                ea["status"] = "failed"
                                except KeyError:
                                    created_ids["error"] = "create_gamma_presentation tool not found"
                                    ea["status"] = "failed"
                                except Exception as tool_err:
                                    log_error_to_terminal(
                                        error=tool_err,
                                        context="Error creating slides in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    created_ids["error"] = str(tool_err)
                                    created_ids["error_detail"] = str(tool_err)
                                    ea["status"] = "failed"
                            else:
                                # Unknown doc_type - for review tasks on existing sheets/slides, create a Google Doc with review notes
                                # This handles cases where doc_type might be something else or when reviewing existing documents
                                if title and body_text:
                                    # Create a Google Doc with review notes instead
                                    create_args = {
                                        "title": f"Review Notes: {title}",
                                        "initial_text": body_text,
                                        "token": token,
                                    }
                                    try:
                                        result = wrap_tool_execution(
                                            tool_func=tools.get("create_document"),
                                            tool_name="create_document",
                                            args=create_args,
                                            user_id=token,
                                        )
                                        doc_id = None
                                        if isinstance(result, dict) and result.get("status") == "error":
                                            created_ids["error"] = result.get("message")
                                            ea["status"] = "failed"
                                        elif isinstance(result, dict):
                                            data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                            doc_id = data_block.get("document_id") or data_block.get("id") or result.get("document_id")
                                            created_ids["doc_id"] = doc_id
                                            if doc_id:
                                                created_ids["document_id"] = str(doc_id)
                                            _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                            ea["status"] = "completed" if doc_id else "failed"
                                        else:
                                            created_ids["error"] = f"Unsupported doc_type: {doc_type}. Created review document instead."
                                            ea["status"] = "failed"
                                    except Exception as tool_err:
                                        log_error_to_terminal(
                                            error=tool_err,
                                            context=f"Error handling doc_type {doc_type} in /autoPilot/execute",
                                            user_id=token,
                                        )
                                        created_ids["error"] = f"Unsupported doc_type: {doc_type}. Supported types: g_docs, g_sheets, g_slides, notion"
                                        ea["status"] = "failed"
                                else:
                                    created_ids["error"] = f"Unsupported doc_type: {doc_type}. Supported types: g_docs, g_sheets, g_slides, notion"
                                    ea["status"] = "failed"

                    # Trello: add comment on card (add_task_comment)
                    elif ex_type == "trello_comment":
                            tc = ea.get("trello_comment") or {}
                            card_id = tc.get("card_id") or ea.get("source_item_id")
                            text = (tc.get("text") or tc.get("comment_text") or "").strip()
                            if not card_id:
                                created_ids["error"] = "Missing card_id for Trello comment (source_item_id or trello_comment.card_id)"
                                ea["status"] = "failed"
                            elif not text:
                                created_ids["error"] = "Missing text for Trello comment"
                                ea["status"] = "failed"
                            else:
                                if owner_email_for_comments:
                                    text = text + "\n\n— " + owner_email_for_comments
                                try:
                                    add_tc = tools.get("add_task_comment")
                                    if not add_tc:
                                        created_ids["error"] = "add_task_comment tool not available"
                                        ea["status"] = "failed"
                                    else:
                                        result = wrap_tool_execution(
                                            tool_func=add_tc,
                                            tool_name="add_task_comment",
                                            args={
                                                "card_id": str(card_id),
                                                "text": text,
                                                "token": token,
                                            },
                                            user_id=token,
                                        )
                                        if isinstance(result, dict) and (
                                            result.get("status") == "error"
                                            or result.get("success") is False
                                        ):
                                            created_ids["error"] = (
                                                result.get("message")
                                                or result.get("error")
                                                or "Trello comment failed"
                                            )
                                            if result.get("detail"):
                                                created_ids["error_detail"] = result["detail"]
                                            ea["status"] = "failed"
                                        elif isinstance(result, dict):
                                            data_block = (
                                                result.get("data")
                                                if isinstance(result.get("data"), dict)
                                                else result
                                            )
                                            cid = data_block.get("id") or result.get("id")
                                            if cid:
                                                created_ids["comment_id"] = str(cid)
                                            created_ids["card_id"] = str(card_id)
                                            created_ids["trello_card_id"] = str(card_id)
                                            ea["status"] = "completed"
                                        else:
                                            created_ids["error"] = "Unexpected response from add_task_comment"
                                            ea["status"] = "failed"
                                except Exception as api_err:
                                    log_error_to_terminal(
                                        error=api_err,
                                        context="Error adding Trello comment in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    created_ids["error"] = str(api_err)
                                    ea["status"] = "failed"

                    # Trello / task board tasks
                    elif ex_type == "trello_task":
                            task = ea.get("task") or {}
                            board_name = task.get("board_name")
                            list_name = task.get("list_name")
                            title = task.get("title")
                            description = task.get("description")
                            due = task.get("due")

                            if not title:
                                created_ids["error"] = "Missing required field: title"
                                ea["status"] = "failed"
                            else:
                                try:
                                    # Resolve board: if not provided or not found, use first available board
                                    resolved_board_name = board_name
                                    resolved_board_id = None
                                    
                                    # Check if Trello tools are available
                                    task_find_board_tool = tools.get("find_task_board")
                                    task_list_boards_tool = tools.get("list_task_boards")
                                    
                                    if not task_find_board_tool and not task_list_boards_tool:
                                        created_ids["error"] = "Trello tools not available (find_task_board, list_task_boards). Trello integration may not be configured."
                                        ea["status"] = "failed"
                                        _normalize_execution_created_ids(created_ids, ea)
                                        ea["created_ids"] = created_ids
                                        continue
                                    
                                    if board_name and task_find_board_tool:
                                        # Try to find the board by name
                                        try:
                                            find_board_result = wrap_tool_execution(
                                                tool_func=task_find_board_tool,
                                                tool_name="find_task_board",
                                                args={"board_name": board_name, "token": token},
                                                user_id=token,
                                            )
                                            if isinstance(find_board_result, dict) and (
                                                find_board_result.get("idboard") or find_board_result.get("id")
                                            ):
                                                resolved_board_id = find_board_result.get("idboard") or find_board_result.get("id")
                                                resolved_board_name = find_board_result.get("board_name") or find_board_result.get("name", board_name)
                                        except Exception as find_err:
                                            autopilot_log("warning", f"Failed to find Trello board '{board_name}': {find_err}")
                                            # Continue to try listing boards
                                    
                                    # If board not found, get the first available board
                                    if not resolved_board_id and task_list_boards_tool:
                                        try:
                                            list_boards_result = wrap_tool_execution(
                                                tool_func=task_list_boards_tool,
                                                tool_name="list_task_boards",
                                                args={"token": token},
                                                user_id=token,
                                            )
                                            if isinstance(list_boards_result, list) and len(list_boards_result) > 0:
                                                first_board = list_boards_result[0]
                                                resolved_board_id = first_board.get("idboard") or first_board.get("id")
                                                resolved_board_name = first_board.get("board_name") or first_board.get("name", "Default Board")
                                            else:
                                                created_ids["error"] = "No Trello boards found. Please create a board first."
                                                ea["status"] = "failed"
                                                _normalize_execution_created_ids(created_ids, ea)
                                                ea["created_ids"] = created_ids
                                                continue
                                        except Exception as list_err:
                                            autopilot_log("warning", f"Failed to list Trello boards: {list_err}")
                                            created_ids["error"] = f"Failed to access Trello boards: {str(list_err)}"
                                            ea["status"] = "failed"
                                            _normalize_execution_created_ids(created_ids, ea)
                                            ea["created_ids"] = created_ids
                                            continue
                                    
                                    if not resolved_board_id:
                                        created_ids["error"] = "Could not resolve Trello board. Trello tools may not be configured or accessible."
                                        ea["status"] = "failed"
                                        _normalize_execution_created_ids(created_ids, ea)
                                        ea["created_ids"] = created_ids
                                        continue
                                    
                                    # Resolve list:
                                    # - If a list_name is provided, try it first.
                                    # - Otherwise/search fallback: use list named "doing" (case-insensitive).
                                    # - If still missing, create a new list named "doing".
                                    resolved_list_name = None
                                    resolved_list_id = None
                                    
                                    # Check if list tools are available
                                    task_find_list_tool = tools.get("find_task_list")
                                    task_list_create_tool = tools.get("create_task_list")
                                    
                                    target_list_name = (list_name or "").strip() if isinstance(list_name, str) else None

                                    # 1) Try the provided list name first
                                    if target_list_name and task_find_list_tool:
                                        try:
                                            find_list_result = wrap_tool_execution(
                                                tool_func=task_find_list_tool,
                                                tool_name="find_task_list",
                                                args={"board_id": resolved_board_id, "list_name": target_list_name, "token": token},
                                                user_id=token,
                                            )
                                            if isinstance(find_list_result, dict) and (
                                                find_list_result.get("idlist") or find_list_result.get("id")
                                            ):
                                                resolved_list_id = find_list_result.get("idlist") or find_list_result.get("id")
                                                resolved_list_name = find_list_result.get("list_name") or find_list_result.get("name", target_list_name)
                                        except Exception as find_list_err:
                                            autopilot_log("warning", f"Failed to find Trello list '{target_list_name}': {find_list_err}")

                                    # 2) If list not found, try to find "doing" (case-insensitive)
                                    if not resolved_list_id and task_find_list_tool:
                                        try:
                                            find_doing_result = wrap_tool_execution(
                                                tool_func=task_find_list_tool,
                                                tool_name="find_task_list",
                                                args={"board_id": resolved_board_id, "list_name": "doing", "token": token},
                                                user_id=token,
                                            )
                                            if isinstance(find_doing_result, dict) and (
                                                find_doing_result.get("idlist") or find_doing_result.get("id")
                                            ):
                                                resolved_list_id = find_doing_result.get("idlist") or find_doing_result.get("id")
                                                resolved_list_name = find_doing_result.get("list_name") or find_doing_result.get("name", "doing")
                                        except Exception as find_doing_err:
                                            autopilot_log("warning", f"Failed to find Trello list 'doing': {find_doing_err}")

                                    # 3) If still not found, create "doing" list on the resolved board_id
                                    if not resolved_list_id and task_list_create_tool and resolved_board_id:
                                        try:
                                            create_list_result = wrap_tool_execution(
                                                tool_func=task_list_create_tool,
                                                tool_name="create_task_list",
                                                args={"board_id": resolved_board_id, "name": "doing", "token": token},
                                                user_id=token,
                                            )
                                            if isinstance(create_list_result, dict) and create_list_result.get("status") != "error":
                                                resolved_list_id = (
                                                    create_list_result.get("idlist")
                                                    or create_list_result.get("id")
                                                    or (
                                                        create_list_result.get("data", {}).get("id")
                                                        if isinstance(create_list_result.get("data"), dict)
                                                        else None
                                                    )
                                                )
                                                resolved_list_name = "doing"
                                        except Exception as create_err:
                                            autopilot_log("warning", f"Failed to create Trello list 'doing': {create_err}")
                                    
                                    if not resolved_list_id:
                                        created_ids["error"] = f"Could not find or create list 'doing' on board '{resolved_board_name}'. Trello list tools may not be available."
                                        ea["status"] = "failed"
                                    else:
                                        # Create the task with resolved board and list
                                        create_args = {
                                            # Use list_id to avoid any additional board-name resolution issues.
                                            "list_id": resolved_list_id,
                                            "name": title,
                                            "desc": description or "",
                                            "due": due,
                                            "token": token,
                                        }
                                        
                                        # Check if task creation tools are available
                                        create_task_tool = tools.get("create_task")

                                        if not create_task_tool:
                                            created_ids["error"] = "Trello task creation tool not available (create_task). Trello integration may not be configured."
                                            ea["status"] = "failed"
                                        else:
                                            tool_name = "create_task"
                                            task_creation_tool = create_task_tool
                                            
                                            try:
                                                result = wrap_tool_execution(
                                                    tool_func=task_creation_tool,
                                                    tool_name=tool_name,
                                                    args=create_args,
                                                    user_id=token,
                                                )
                                                card_id = None
                                                if isinstance(result, dict) and result.get("status") == "error":
                                                    created_ids["error"] = result.get("message")
                                                    ea["status"] = "failed"
                                                elif isinstance(result, dict):
                                                    data_block = result.get("data", {})
                                                    card_id = (
                                                        data_block.get("id")
                                                        or data_block.get("card_id")
                                                        or result.get("idcard")
                                                        or result.get("idCard")
                                                        or result.get("id")
                                                    )

                                                    # Trello MCP returns flattened ids: idboard/idlist/idcard.
                                                    board_id_val = (
                                                        result.get("idboard") or result.get("idBoard") or resolved_board_id
                                                    )
                                                    list_id_val = (
                                                        result.get("idlist") or result.get("idList") or resolved_list_id
                                                    )
                                                    card_id_val = card_id or result.get("idcard") or result.get("idCard")

                                                    created_ids["trello_card_id"] = card_id_val
                                                    if card_id_val:
                                                        created_ids["card_id"] = str(card_id_val)
                                                    if board_id_val:
                                                        created_ids["board_id"] = str(board_id_val)
                                                    if list_id_val:
                                                        created_ids["list_id"] = str(list_id_val)
                                                    created_ids["board_name"] = resolved_board_name
                                                    created_ids["list_name"] = resolved_list_name
                                                    _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                                    ea["status"] = "completed" if card_id_val else "failed"
                                                else:
                                                    created_ids["error"] = "Unexpected response format from Trello tool"
                                                    ea["status"] = "failed"
                                            except Exception as create_task_err:
                                                log_error_to_terminal(
                                                    error=create_task_err,
                                                    context="Error creating Trello task in /autoPilot/execute",
                                                    user_id=token,
                                                )
                                                created_ids["error"] = f"Failed to create Trello task: {str(create_task_err)}"
                                                ea["status"] = "failed"
                                except KeyError as key_err:
                                    created_ids["error"] = f"Required Trello tool not found: {str(key_err)}"
                                    ea["status"] = "failed"
                                except Exception as tool_err:
                                    log_error_to_terminal(
                                        error=tool_err,
                                        context="Error creating Trello task in /autoPilot/execute",
                                        user_id=token,
                                    )
                                    created_ids["error"] = str(tool_err)
                                    ea["status"] = "failed"

                    # Calendar events
                    elif ex_type == "calendar_event":
                            # Check if this is actually a reminder email (has draft instead of event)
                            if ea.get("draft") and not ea.get("event"):
                                # This is a reminder email, not a calendar event creation/update
                                # Convert to gmail_draft execution
                                draft = ea.get("draft")
                                to = draft.get("to")
                                subject = draft.get("subject")
                                body_text = draft.get("body_text")
                                
                                if to and subject and body_text:
                                    try:
                                        compose_args = {
                                            "to": to,
                                            "subject": subject,
                                            "body": body_text,
                                            "token": token,
                                        }
                                        result = wrap_tool_execution(
                                            tool_func=tools.get("draft_email"),
                                            tool_name="draft_email",
                                            args=compose_args,
                                            user_id=token,
                                        )
                                        draft_id = None
                                        if isinstance(result, dict) and result.get("status") == "error":
                                            created_ids["error"] = result.get("message")
                                            ea["status"] = "failed"
                                        elif isinstance(result, dict):
                                            data_block = result.get("data") if isinstance(result.get("data"), dict) else result
                                            draft_id = data_block.get("draft_id") or data_block.get("id") or result.get("draft_id")
                                            created_ids["gmail_draft_id"] = draft_id
                                            if draft_id:
                                                created_ids["draft_id"] = str(draft_id)
                                            _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                            ea["status"] = "completed" if draft_id else "failed"
                                        else:
                                            created_ids["error"] = "Unexpected response format from draft_email"
                                            ea["status"] = "failed"
                                    except KeyError:
                                        created_ids["error"] = "draft_email tool not found"
                                        ea["status"] = "failed"
                                    except Exception as tool_err:
                                        log_error_to_terminal(
                                            error=tool_err,
                                            context="Error creating Gmail draft (calendar reminder) in /autoPilot/execute",
                                            user_id=token,
                                        )
                                        ea["status"] = "failed"
                                        created_ids["error"] = str(tool_err)
                                else:
                                    created_ids["error"] = "Missing required fields for reminder email: to, subject, or body_text"
                                    ea["status"] = "failed"
                            else:
                                # Actual calendar event creation/update
                                event = ea.get("event") or {}
                                title = event.get("title")
                                start_time = event.get("start_time")
                                end_time = event.get("end_time")
                                attendees = event.get("attendees") or []

                                # Check if event already exists.
                                # IMPORTANT:
                                # - For events coming from Calendar, planner will set source_type="calendar"
                                #   and source_item_id to the real calendar event id → we should UPDATE.
                                # - For events triggered from Gmail (like "schedule a meeting"), source_type will
                                #   typically be "gmail" and source_item_id will be the Gmail message id → we must
                                #   NOT treat that as an existing calendar event id, otherwise update will 404.
                                existing_event_id = None
                                source_type = ea.get("source_type")
                                if source_type == "calendar":
                                    existing_event_id = event.get("event_id") or event.get("id")
                                    
                                else:
                                    existing_event_id = ea.get("source_item_id")
                                    # Optionally allow planner to pass an explicit event_id inside the event payload

                                # Force INSERT (create new event) when the planner intent is to
                                # create/schedule a brand-new calendar event. This prevents accidental
                                # PATCH/404 when the action is mis-classified as source_type="calendar"
                                # while the provided id is not a real Google Calendar event id.
                                action_text = " ".join(
                                    [str(ea.get("action") or ""), str(ea.get("reasons") or "")]
                                ).strip().lower()
                                force_create = False
                                if action_text:
                                    has_calendar_event = re.search(r"(google\s+)?calendar\s+event", action_text) is not None
                                    wants_create = re.search(r"\bcreate(d)?\b", action_text) is not None
                                    wants_schedule = re.search(r"\b(schedule\s*time|allocate\s*time)\b", action_text) is not None
                                    force_create = has_calendar_event and (wants_create or wants_schedule)
                                if force_create:
                                    existing_event_id = None


                                if title and start_time and end_time:
                                    try:
                                        if existing_event_id:
                                            # Update existing event
                                            update_args = {
                                                "event_id": existing_event_id,
                                                "summary": title,
                                                "start_time": start_time,
                                                "end_time": end_time,
                                                "attendees": attendees,
                                                "token": token,
                                            }
                                            # Try to find the update tool (may be named differently)
                                            update_tool = tools.get("update_calendar_event") or tools.get("update_event") or tools.get("update_calendar")
                                            if not update_tool:
                                                raise ValueError("update_calendar_event tool not found in available tools")
                                            result = wrap_tool_execution(
                                                tool_func=update_tool,
                                                tool_name="update_calendar_event",
                                                args=update_args,
                                                user_id=token,
                                            )
                                            event_id = existing_event_id
                                        else:
                                            # Create new event
                                            create_args = {
                                                "summary": title,
                                                "start_time": start_time,
                                                "end_time": end_time,
                                                "attendees": attendees,
                                                "token": token,
                                            }
                                            result = wrap_tool_execution(
                                                tool_func=tools["create_event"],
                                                tool_name="create_event",
                                                args=create_args,
                                                user_id=token,
                                            )
                                            event_id = None
                                        
                                        # Handle response for both create and update
                                        if isinstance(result, dict) and result.get("status") == "error":
                                            created_ids["error"] = result.get("message")
                                            ea["status"] = "failed"
                                        elif isinstance(result, dict):
                                            # Handle both create and update response formats.
                                            # Different implementations may nest the event under "event" or "data",
                                            # or return the id directly on the top-level object.
                                            if existing_event_id:
                                                # Update response: event data is in result directly or result.data/event
                                                event_data = result.get("event") or result.get("data", {})
                                                event_id = event_data.get("id") or event_data.get("event_id") or existing_event_id
                                            else:
                                                # Create response: event data may be in result.data OR result.event OR top-level id
                                                data_block = result.get("data") or result.get("event") or {}
                                                event_id = (
                                                    data_block.get("id")
                                                    or data_block.get("event_id")
                                                    or result.get("id")
                                                )
                                            
                                            created_ids["calendar_event_id"] = event_id
                                            if event_id:
                                                created_ids["event_id"] = str(event_id)
                                            _merge_tool_payload_ids_into_created_ids(created_ids, result)
                                            ea["status"] = "completed" if event_id else "failed"
                                        else:
                                            # Unexpected response format
                                            created_ids["error"] = "Unexpected response format from calendar tool"
                                            ea["status"] = "failed"
                                    except Exception as tool_err:
                                        log_error_to_terminal(
                                            error=tool_err,
                                            context=f"Error {'updating' if existing_event_id else 'creating'} calendar event in /autoPilot/execute",
                                            user_id=token,
                                        )
                                        created_ids["error"] = str(tool_err)
                                        ea["status"] = "failed"
                                else:
                                    # Missing required fields
                                    missing = []
                                    if not title: missing.append("title")
                                    if not start_time: missing.append("start_time")
                                    if not end_time: missing.append("end_time")
                                    created_ids["error"] = f"Missing required fields: {', '.join(missing)}"
                                    ea["status"] = "failed"

                    _planned_tool = _planned_tool_from_execute_payload(data)
                    ea["tool"] = _infer_tool_for_executed_action(ea, _planned_tool)
                    _normalize_execution_created_ids(created_ids, ea)
                    ea["created_ids"] = created_ids
                    enriched_actions.append(ea)

                # After all actions: one snapshot update, one token upsert (was incorrectly inside per-action loop)
                autopilot_print(f"/autoPilot/execute enriched {len(enriched_actions)} action(s) total")
                for _dbg in enriched_actions:
                    autopilot_print(
                        f"  - {_dbg.get('action_key')} ({_dbg.get('source_type')}): "
                        f"tool={_dbg.get('tool')} status={_dbg.get('status')}, created_ids={_dbg.get('created_ids')}"
                    )

                # Update unified_autopilot snapshot in Mongo with execution_response
                snapshot_id = data.get("snapshot_id")
                user_id_for_db = data.get("user_id") or token
                if snapshot_id:
                    try:
                        from bson import ObjectId  # local import to avoid circular issues
                        from db.mongo_client import get_mongo_client_by_db

                        user_db = get_mongo_client_by_db(str(user_id_for_db))
                        unified_coll = user_db["unified_autopilot"]
                        
                        # Load the existing snapshot document
                        existing_doc = unified_coll.find_one({"_id": ObjectId(snapshot_id)})
                        if not existing_doc:
                            autopilot_print(f"⚠️ Snapshot {snapshot_id} not found in MongoDB")
                        else:
                            # Group executed_actions by source_type
                            executed_by_source = {}
                            for snap_ea in enriched_actions:
                                source_type = snap_ea.get("source_type")
                                if source_type:
                                    if source_type not in executed_by_source:
                                        executed_by_source[source_type] = []
                                    executed_by_source[source_type].append(snap_ea)
                            
                            # Update each item in snapshot.items to include its executed_actions and timestamps
                            snapshot = existing_doc.get("snapshot", {})
                            items = snapshot.get("items", [])
                            
                            for item in items:
                                item_source_type = item.get("source_type")
                                if item_source_type in executed_by_source:
                                    item["executed_actions"] = executed_by_source[item_source_type]
                                    # Set per-item execution timestamp as latest executed_at among its actions
                                    try:
                                        latest_exec = max(
                                            x.get("executed_at")
                                            for x in executed_by_source[item_source_type]
                                            if x.get("executed_at")
                                        )
                                    except ValueError:
                                        latest_exec = None
                                    if latest_exec:
                                        item["execution_timestamp"] = latest_exec
                                else:
                                    item["executed_actions"] = []
                            
                            # Update the snapshot with modified items
                            snapshot["items"] = items
                            snapshot["execution_response"] = {
                                "executed_actions": enriched_actions,
                                "meta": parsed.get("meta", {}),
                            }
                            
                            # Save the updated document
                            update_result = unified_coll.update_one(
                                {"_id": ObjectId(snapshot_id)},
                                {
                                    "$set": {
                                        "snapshot_type": "planning_and_execution_complete",
                                        "execution_completed_at": datetime.now(timezone.utc).isoformat(),
                                        "snapshot": snapshot
                                    }
                                },
                            )
                            autopilot_print(
                                f"/autoPilot/execute updated unified_autopilot: matched={update_result.matched_count}, modified={update_result.modified_count}"
                            )
                    except Exception as mongo_err:
                        log_error_to_terminal(
                            error=mongo_err,
                            context="Error updating unified_autopilot in /autoPilot/execute",
                            user_id=user_id_for_db,
                        )

                # Upsert (update or insert) AI usage document for today
                if accumulated_token_usage["model"]:
                    # Calculate total tokens correctly: input + output + system_prompt (counted once)
                    total_tokens = (
                        accumulated_token_usage["input_tokens"] +
                        accumulated_token_usage["output_tokens"] +
                        accumulated_token_usage["system_prompt_tokens"]
                    )
                    upsert_ai_usage(
                        token=token,
                        purpose="autopilot",
                        model=accumulated_token_usage["model"],
                        input_tokens=accumulated_token_usage["input_tokens"],
                        output_tokens=accumulated_token_usage["output_tokens"],
                        system_prompt_tokens=accumulated_token_usage["system_prompt_tokens"],
                        total_tokens=total_tokens,
                        ip_address=ip_address,
                        total_api_calls=api_call_counter,
                    )
                
                # # Log final token usage summary if enabled (disabled: noisy)
                # if ENABLE_TOKEN_USAGE_LOGGING and accumulated_token_usage["model"]:
                #     total_tokens = (
                #         accumulated_token_usage["input_tokens"] +
                #         accumulated_token_usage["output_tokens"] +
                #         accumulated_token_usage["system_prompt_tokens"]
                #     )
                #     print(f"\n📊 Token Usage Summary (Autopilot Execute):")
                #     print(f"   Input Tokens: {accumulated_token_usage['input_tokens']}")
                #     print(f"   System Prompt Tokens: {accumulated_token_usage['system_prompt_tokens']}")
                #     print(f"   Output Tokens: {accumulated_token_usage['output_tokens']}")
                #     print(f"   Total Tokens: {total_tokens}")
                #     print(f"   Model: {accumulated_token_usage['model']}")
                #     print(f"   Purpose: autopilot")
                #     print(f"   Total Response Time: {total_response_time:.3f}s")
                #     print(f"   API Calls: {api_call_counter}")
                #     print()
                
                # Console: full execution response (generate_autopilot sends context.autopilot_id)
                _ap_id = None
                ctx = data.get("context")
                if isinstance(ctx, dict):
                    _ap_id = ctx.get("autopilot_id")
                if not _ap_id:
                    for _ea in enriched_actions or []:
                        if isinstance(_ea, dict) and _ea.get("autopilot_id"):
                            _ap_id = _ea.get("autopilot_id")
                            break
                _ok_body = {
                    "executed_actions": enriched_actions,
                    "meta": parsed.get("meta", {}),
                }
                console_autopilot_execute_response(_ap_id, _ok_body)

                # Return enriched execution result to caller as well
                return jsonify(_ok_body)
            else:
                # ✅ ENHANCEMENT: Better error logging with context
                autopilot_log("warning", "No valid JSON found in execution response. Text preview: %s", text_content[:500] if text_content else "Empty")
                _err_body = {
                    "success": False,
                    "type": "error",
                    "message": "Failed to parse JSON from execution response",
                    "text_preview": (text_content[:1200] if text_content else ""),
                }
                console_autopilot_execute_response(None, _err_body)
                return jsonify(
                    {
                        "success": False,
                        "type": "error",
                        "message": "Failed to parse JSON from execution response",
                    }
                )

        # Fallback if no valid content/JSON
        _empty_body = {
            "success": False,
            "type": "error",
            "message": "Empty or invalid execution response from Bedrock",
        }
        console_autopilot_execute_response(None, _empty_body)
        return jsonify(_empty_body)
    except Exception as e:
        # ✅ ENHANCEMENT: Enhanced error handling with rate limit detection (similar to assistant_handler.py)
        error_str = str(e).lower()
        # Check if it's a quota/rate limit error (429) - for Bedrock
        is_bedrock_rate_limit = (
            "bedrock" in error_str and ("429" in error_str or "too many requests" in error_str or "rate limit" in error_str)
        )
        
        if is_bedrock_rate_limit:
            autopilot_log("warning", "⚠️ Bedrock rate limit (429) detected in /autoPilot/execute")
            _rl = {
                "success": False,
                "type": "error",
                "message": "❌ We're experiencing high demand right now. Please wait 30-60 seconds and try again.",
            }
            console_autopilot_execute_response(None, _rl)
            return jsonify(_rl), 429
        
        # ✅ ENHANCEMENT: Comprehensive error logging
        log_error_to_terminal(
            error=e,
            context="Error in /autoPilot/execute",
            user_id=token,
        )
        user_message = get_user_friendly_error_message(e, "general")
        _ex_body = {
            "success": False,
            "type": "error",
            "message": user_message,
            "error_detail": str(e),
        }
        console_autopilot_execute_response(None, _ex_body)
        return (
            jsonify(
                {
                    "success": False,
                    "type": "error",
                    "message": user_message,
                }
            ),
            500,
        )
    # ------------------------------
    # Multi-step tool execution (AUTOPILOT)
    # ------------------------------
    # step_count = 0
    # max_steps = 100  # Increased from 6 to 10 for more complex workflows
    # retries = 0
    # max_retries = 2
    # # Accumulate UI hints for all tools invoked during this request
    # ui_hints_accumulated = []
    # # Track planning phase for two-phase execution
    # planning_response = None
    # execution_complete = False
    # # Track executed items with their IDs
    # executed_items = []

    # while retries < max_retries:
    #     try:
    #         while step_count < max_steps:   
    #             final_json_enforcement = {
    #                 "role": "user",
    #                 "content": [{
    #                     "type": "text",
    #                     "text": (
    #                         "FINAL RESPONSE RULE:\n"
    #                         "Return ONLY a single valid JSON object.\n"
    #                         "Do NOT include explanations.\n"
    #                         "Do NOT include markdown.\n"
    #                         "Do NOT include text before or after JSON.\n"
    #                         "If unsure, return empty arrays per schema."
    #                     )
    #                 }]
    #             }
    #             body["messages"] = body["messages"] + [final_json_enforcement]
                
    #             response = invoke_bedrock(body)
    #             content = response.get("content", [])
    #             stop_reason = response.get("stop_reason", "")

    #             if not content:
    #                 return jsonify(
    #                     {
    #                         "success": False,
    #                         "type": "error",
    #                         "data": {},
    #                         "ui_hint": "chat",
    #                         "message": "⚠️ Unexpected assistant output.",
    #                     }
    #                 )

    #             #------------------------------
    #             # Handle tool calls
    #             # ------------------------------
    #             if stop_reason == "tool_use":
    #                 tool_use_blocks = [
    #                     b for b in content if b.get("type") == "tool_use"
    #                 ]
    #                 tool_result_blocks = []

    #                 for block in tool_use_blocks:
    #                     name = block.get("name")
    #                     args = block.get("input", {})
    #                     # print(name,args)
    #                     args["token"] = token
    #                     autopilot_print(f"Calling tool: {name} with args: {args}")
    #                     # Infer UI hint from tool name and accumulate unique entries
    #                     try:
    #                         inferred = None
    #                         lname = (name or "").lower()
    #                         if any(k in lname for k in ["email", "gmail", "mail"]):
    #                             inferred = "open_emails_panel"
    #                         elif any(
    #                             k in lname for k in ["calendar", "event", "meeting"]
    #                         ):
    #                             inferred = "open_meetings_panel"
    #                         elif any(
    #                             k in lname
    #                             for k in [
    #                                 "doc",
    #                                 "document",
    #                                 "notion_page",
    #                                 "page",
    #                                 "notion",
    #                             ]
    #                         ):
    #                             # Prefer docs panel for docs-like tools; Notion pages treated as docs
    #                             inferred = "open_docs_panel"
    #                         elif any(
    #                             k in lname for k in ["sheet", "sheets", "spreadsheet"]
    #                         ):
    #                             inferred = "open_sheets_panel"
    #                         elif any(k in lname for k in ["trello", "task"]):
    #                             inferred = "open_trello_panel"
    #                         elif any(
    #                             k in lname for k in ["slack", "channel", "message"]
    #                         ):
    #                             inferred = "open_slack_panel"
    #                         elif any(k in lname for k in ["drive", "file", "upload"]):
    #                             inferred = "open_docs_panel"
    #                         elif any(k in lname for k in ["slide", "slides"]):
    #                             inferred = "open_slides_panel"
    #                         if inferred and inferred not in ui_hints_accumulated:
    #                             ui_hints_accumulated.append(inferred)
    #                     except Exception:
    #                         pass
    #                     try:
    #                         # CRITICAL: Block Slack sending tools in autopilot mode
    #                         # Slack messages should NEVER be sent directly - only drafts are allowed
    #                         forbidden_slack_tools = [
    #                             "send_dm", "send_slack_messages", "post_message", 
    #                             "send_group_messages", "slack_reply_message", "send_message"
    #                         ]
    #                         if name.lower() in [t.lower() for t in forbidden_slack_tools]:
    #                             error_msg = f"❌ AUTOPILOT ERROR: Tool '{name}' is FORBIDDEN for Slack messages in autopilot mode. Slack responses must be drafted as text in urgent_actions, not sent directly. Skipping this tool call."
    #                             autopilot_log("warning", error_msg)
    #                             # Return error result instead of executing
    #                             tool_result_blocks.append(
    #                                 {
    #                                     "type": "tool_result",
    #                                     "tool_use_id": block.get("id"),
    #                                     "content": [
    #                                         {"type": "text", "text": json.dumps({
    #                                             "status": "error",
    #                                             "tool": name,
    #                                             "error": "Slack sending tools are forbidden in autopilot mode. Slack responses must be drafted as text in urgent_actions, not sent directly.",
    #                                             "note": "This tool call was blocked. Slack drafts should be in urgent_actions as text (format: 'Draft Slack reply for channel {channel_id}: {message}')"
    #                                         })}
    #                                     ],
    #                                 }
    #                             )
    #                             continue  # Skip this tool and continue with next
    #                     except Exception:
    #                         pass
    #                     # Check if tool exists in tools dictionary
    #                         if name not in tools:
    #                             # Try alternative names for Slack tools
    #                             if name == "post_message" or name == "send_message":
    #                                 # Use send_slack_messages as fallback
    #                                 if "send_slack_messages" in tools:
    #                                     name = "send_slack_messages"
    #                                     # Adjust args to match send_slack_messages signature
    #                                     if "channel" in args:
    #                                         channel = args.pop("channel")
    #                                         message = args.pop("message", "")
    #                                         args = {"channel": channel, "message": message, "token": args.get("token")}
    #                                 else:
    #                                     raise KeyError(f"Tool '{name}' not found and no fallback available")
    #                             else:
    #                                 raise KeyError(f"Tool '{name}' not found in tools dictionary")
                            
    #                     # Execute tool call
    #                     try:
    #                         tool_result = invoke_tool(name, args)
    #                         tool_result_blocks.append(tool_result)
    #                     except Exception as e:
    # if not user_query and not file_analyses:
    #     autopilot_log("error", "Missing query or file")
    #     return jsonify({"error": "Missing query or file"}), 400

    




























    


    # AUTOPILOT_SYSTEM_PROMPT = """
    # You are an AUTONOMOUS AUTOPILOT SYSTEM that proactively analyzes workspace data and suggests/executes actions.

    # AUTOPILOT MODE - YOU ARE ACTING AUTONOMOUSLY:
    # - You are NOT waiting for user questions or requests
    # - You are ACTIVELY analyzing calendar events, emails, documents, and workspace context
    # - You AUTOMATICALLY identify what needs attention, what actions should be taken, and what recommendations to make
    # - You act as an intelligent assistant that works in the background, analyzing and planning
    # - Think of yourself as a proactive executive assistant who reviews everything and suggests actions

    # TWO-PHASE OPERATION:

    # PHASE 1 - PLANNING (First Response):
    # - Analyze the provided calendar events, context, and workspace data
    # - Identify urgent items that need immediate attention
    # - Generate an action plan in JSON format with:
    #   * urgent_actions: Actions that need immediate execution
    #     - For SLACK messages: Put draft replies as text strings in urgent_actions with format: "Draft Slack reply for channel {channel_id}: {message}"
    #     - For other actions: Describe what needs to be done (e.g., "Create document", "Send email reminder")
    #   * recommendations: Suggested actions that should be taken
    #   * informative: Insights about what's happening
    # - Return ONLY the planning JSON, no tool calls yet
    # - CRITICAL FOR SLACK: If Slack messages need replies, put them in urgent_actions as text drafts (format: "Draft Slack reply for channel {channel_id}: {message}") - DO NOT plan to call any Slack sending tools

    # PHASE 2 - EXECUTION (After Planning):
    # - You will receive your own planning response with an EXECUTION PROMPT
    # - CRITICAL: When you see "🚀 EXECUTION PHASE" in the user message, you MUST CALL TOOLS, NOT RETURN JSON
    # - NOTE: /autoPilot/execute runs vector_context_search once before the execution LLM and injects results into the payload (AUTOPILOT_DRAFT_VECTOR_CONTEXT). Legacy tool-loop execution below is unrelated.
    # - You already have all the context you need from the planning phase
    # - Execute the actions using available tools DIRECTLY:
    #   * For SLACK: NEVER send messages directly - ONLY create text drafts in urgent_actions (format: "Draft Slack reply for channel {channel_id}: {message}")
    #   * For GMAIL: Use draft_email tool to create drafts - DO NOT send directly
    #   * For DOCS/CALENDAR/TRELLO/SHEETS/SLIDES: Use create/update tools directly (create_document, create_event, etc.)
    # - Call tools to perform each action from your plan IMMEDIATELY
    # - DO NOT search for more information - EXECUTE DIRECTLY
    # - DO NOT return JSON during execution phase - CALL TOOLS INSTEAD
    # - Continue calling tools until all executable actions are completed
    # - Only return JSON at the very end after all tools have been called

    # EXECUTION RULES:
    # - For emails: Use draft_email tool to create drafts (user will review before sending)
    # - For Slack messages: NEVER call send_dm, send_slack_messages, post_message, send_group_messages, or any Slack sending tools
    #   * Slack responses must be drafted as plain text in urgent_actions array with format: "Draft Slack reply for channel {channel_id}: {message}"
    #   * DO NOT use draft_email for Slack responses - Slack drafts are text only, no draft IDs
    #   * DO NOT call any Slack API tools that send messages - they will fail
    # - For documents: Use create_document, create_page tools directly
    # - For calendar events: Use create_event tool directly
    # - For Trello tasks: Use create_card, update_card tools directly
    # - For sheets/slides: Use create_spreadsheet, create_presentation tools directly
    # - Execute actions autonomously - don't ask for confirmation (except email/Slack drafts)

    # CRITICAL RULES (MANDATORY):
    # - PHASE 1 (Planning): You MUST return ONLY valid JSON (no tool calls)
    # - PHASE 2 (Execution): You MUST CALL TOOLS (do NOT return JSON until all tools are executed)
    # - When you see "🚀 EXECUTION PHASE" in user message, immediately start calling tools
    # - NO markdown in JSON responses
    # - NO explanations in JSON responses
    # - NO text before or after JSON (in planning phase)
    # - NO trailing commas
    # - All strings must be escaped
    # - Always return ALL actions found
    # - If no actions exist, return empty arrays

    # CONTEXT AWARENESS:
    # - You will receive RELEVANT CONTEXT about emails, calendar events, documents, and other workspace items
    # - USE this context to make informed decisions about actions
    # - Consider relationships, priorities, and patterns mentioned in the context
    # - The context provides AI-generated correlations and insights about workspace items
    # - When suggesting actions, reference relevant context when applicable
    # - Cross-reference information across different sources (emails, calendar, docs, etc.)

    # JSON SCHEMA (STRICT) - For Planning Phase:

    # {
    # "urgent_actions": [],
    # "informative": [],
    # "recommendations": [],
    # "meta": {
    #     "confidence": "high|medium|low",
    #     "sources_used": []
    # }
    # }

    # If you violate this schema, the response will be rejected.

    # **CRITICAL INSTRUCTION FOR SLACK MESSAGE IDs:**
    #     When you call send_slack_messages, send_dm, or slack_reply_message, the tool response will contain:
    #     - `message_ts`: Slack's timestamp (e.g., "1762694647.940049") - DO NOT use this for the id field
    #     - `id`: UUID-based message ID (e.g., "slack-msg-2d30284e-32ea-4a0c-9a97-eab4b6d075ee") - USE THIS for the id field
        
    #     You MUST extract the `id` field from the tool response JSON and use it exactly as-is in your response.
    #     NEVER construct the id as "slack-msg-" + message_ts. Always use the `id` field from the tool result.
        
    #     **CRITICAL:** Do not include any extra text or explanation outside the JSON. 
    # """
