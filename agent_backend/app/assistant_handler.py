from flask import request, jsonify
from datetime import datetime, timezone
import base64
import fitz
import json
import re
import time
from collections import deque
import uuid
from zoneinfo import ZoneInfo

# Import app and required shared utilities/state from cosi_app
from app.cosi_app import (
    app,
    logger,
    get_token,
    get_distinct_gmail_senders,
    get_cached_user,
    get_user_personality_profile,
    get_user_profile_collection,
    invoke_ai_with_fallback,
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
import app.switches as switches
from utils.error_handler import tool_status_error_message
from app.switches import (
    ENABLE_IMAGE_ANALYSIS,
    ENABLE_PDF_ANALYSIS,
    USE_TOOL_FILTER,
    ENABLE_TOKEN_USAGE_LOGGING,
    ENABLE_CHAT_LOGS,
    USE_USER_TIMEZONE_IN_PROMPT,
)
# Import USE_BEDROCK_FALLBACK from module for dynamic modification
USE_BEDROCK_FALLBACK = switches.USE_BEDROCK_FALLBACK
from utils.tool_filter import filter_tools

# Strip model-added attachment summaries from data.emails[].body_preview (belongs in message only).
_BODY_PREVIEW_ATTACHMENT_SPLIT = re.compile(
    r"(?:\r?\n){2,}\s*(?:"
    r"Attachment|Preview|Summary of PDF|Visual Analysis|Visual description"
    r")\s*:",
    re.IGNORECASE,
)


def _strip_body_preview_attachment_extras(body_preview: str) -> str:
    if not isinstance(body_preview, str):
        return body_preview
    m = _BODY_PREVIEW_ATTACHMENT_SPLIT.search(body_preview)
    if m:
        return body_preview[: m.start()].rstrip()
    return body_preview


def _infer_upload_filename(file_storage):
    """Use client filename when present; otherwise guess from Content-Type or magic bytes."""
    name = (getattr(file_storage, "filename", None) or "").strip()
    if name:
        return name
    mt = (getattr(file_storage, "mimetype", None) or "").lower()
    if "pdf" in mt:
        return "upload.pdf"
    if mt in ("image/jpeg", "image/jpg"):
        return "upload.jpg"
    if mt == "image/png":
        return "upload.png"
    if mt == "image/gif":
        return "upload.gif"
    if mt == "image/webp":
        return "upload.webp"
    if mt == "image/bmp":
        return "upload.bmp"
    pos = file_storage.tell()
    try:
        head = file_storage.read(12)
        file_storage.seek(pos)
        if head.startswith(b"%PDF"):
            return "upload.pdf"
        if len(head) >= 3 and head[:3] == b"\xff\xd8\xff":
            return "upload.jpg"
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "upload.png"
        if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
            return "upload.gif"
        if head.startswith(b"RIFF") and len(head) >= 12 and head[8:12] == b"WEBP":
            return "upload.webp"
    except Exception:
        try:
            file_storage.seek(pos)
        except Exception:
            pass
    return ""


def _filter_ui_hints_by_data_payload(ui_hints, data):
    """
    Keep resource-panel hints only when `data` has a matching non-empty list
    (emails, documents, meetings, etc.). Hints without a data mapping (e.g. chat,
    open_connection_page) are kept unchanged.
    Mirrors the /chat assistant-JSON path so tool errors with empty data do not
    suggest opening a panel that has nothing to show.
    """
    if not isinstance(data, dict):
        data = {}
    hint_to_data_keys = {
        "open_emails_panel": ["emails"],
        "open_meetings_panel": ["meetings"],
        "open_transcript_panel": ["transcript"],
        "open_docs_panel": ["documents", "docs", "notion"],
        "open_sheets_panel": ["sheets"],
        "open_slides_panel": ["slides"],
        "open_trello_panel": ["tasks"],
        "open_slack_panel": ["messages", "slack_messages"],
    }

    def _has_presentable_items(value):
        """
        Treat a list as presentable only when it has at least one usable item.
        For dict items that include an `id` field, require a non-empty `id`.
        For dict items without `id`, accept if any field is non-empty.
        For scalar items, accept non-empty values.
        """
        if not isinstance(value, list) or not value:
            return False
        for item in value:
            if isinstance(item, dict):
                if "id" in item:
                    raw_id = item.get("id")
                    if isinstance(raw_id, str):
                        if raw_id.strip():
                            return True
                    elif raw_id is not None:
                        return True
                else:
                    for v in item.values():
                        if isinstance(v, str) and v.strip():
                            return True
                        if isinstance(v, (list, dict)) and len(v) > 0:
                            return True
                        if v not in (None, "", [], {}):
                            return True
            elif isinstance(item, str):
                if item.strip():
                    return True
            elif item not in (None, "", [], {}):
                return True
        return False

    if ui_hints is None:
        return []
    if isinstance(ui_hints, str):
        ui_hints = [ui_hints] if ui_hints else []
    if not isinstance(ui_hints, list):
        return []
    filtered = []
    for hint in ui_hints:
        if not isinstance(hint, str):
            continue
        required_keys = hint_to_data_keys.get(hint)
        if not required_keys:
            filtered.append(hint)
            continue
        if any(_has_presentable_items(data.get(k)) for k in required_keys):
            filtered.append(hint)
    return filtered


def _collect_multipart_file_uploads():
    """All multipart file parts (any field name), including blobs with empty filename."""
    entries = []
    if not request.files:
        return entries
    for key in request.files:
        for f in request.files.getlist(key):
            if not f:
                continue
            logical = _infer_upload_filename(f)
            if not logical:
                continue
            entries.append((f, logical))
    return entries


@app.route("/chat", methods=["POST"])
def assistant():
    if ENABLE_CHAT_LOGS:
        logger.info("Received /chat request")
    
    # Capture start time for response time tracking
    request_start_time = time.time()

    # ------------------------------
    # Token & user info
    # ------------------------------
    token, error_response, status_code = get_token()
    if error_response:
        logger.error("Token error: %s", error_response.get_json())
        return error_response, status_code
    
    # Get user IP address for token tracking
    ip_address = request.environ.get('HTTP_X_FORWARDED_FOR', request.environ.get('REMOTE_ADDR', 'unknown'))
    if isinstance(ip_address, str) and ',' in ip_address:
        # Handle multiple IPs in X-Forwarded-For header
        ip_address = ip_address.split(',')[0].strip()

    # Generate chat_id early for this request (used for token tracking)
    chat_id = str(uuid.uuid4())
    
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

    # Compute all "current time" fields from unix seconds so they stay consistent.
    now_unix = time.time()
    now_utc_dt = datetime.fromtimestamp(now_unix, tz=timezone.utc)

    # Defaults: server/local timezone.
    now_local_dt = now_utc_dt.astimezone()
    now_iso = now_local_dt.strftime("%Y-%m-%d")
    now_hms = now_local_dt.strftime("%H:%M:%S")
    now_full = now_local_dt.strftime("%Y-%m-%d %H:%M:%S")
    now_tz_used = "server_local"
    user_list = get_distinct_gmail_senders(token)
    user_info = get_cached_user(token)

    # Get user's email writing personality using token
    user_personality = get_user_personality_profile(token)
    
    # Get user's profile document from MongoDB
    user_profile = get_user_profile_collection(token)
    user_timezone_str = ""
    if isinstance(user_profile, dict):
        user_timezone_str = user_profile.get("timezone") or ""

    # If enabled, compute "current date/time" using the user's timezone from Mongo.
    if USE_USER_TIMEZONE_IN_PROMPT and user_timezone_str:
        try:
            user_dt = now_utc_dt.astimezone(ZoneInfo(user_timezone_str))
            now_iso = user_dt.strftime("%Y-%m-%d")
            now_hms = user_dt.strftime("%H:%M:%S")
            now_full = user_dt.strftime("%Y-%m-%d %H:%M:%S")
            now_tz_used = user_timezone_str
        except Exception:
            # Keep server local time if the user's timezone is invalid/unrecognized.
            now_tz_used = "invalid_user_timezone"

    logger.info(
        "Computed prompt time fields (user tz): user_timezone=%r active_timezone=%r now_iso=%r now_hms=%r now_full=%r now_unix=%d",
        user_timezone_str,
        now_tz_used,
        now_iso,
        now_hms,
        now_full,
        int(now_unix),
    )

    # print(user_profile)
    
    # ------------------------------
    # Handle user input (text / files)
    # ------------------------------
    content_type_lc = (request.content_type or "").lower()
    if content_type_lc.startswith("multipart/form-data"):
        user_query = request.form.get("query", "")
        user_id = token
        uploaded_entries = _collect_multipart_file_uploads()
        file_analyses = []

        if ENABLE_CHAT_LOGS:
            if uploaded_entries:
                logger.info(
                    "/chat multipart: %s file part(s) %s",
                    len(uploaded_entries),
                    [(logical, getattr(fs, "mimetype", None)) for fs, logical in uploaded_entries],
                )
            elif request.files:
                logger.warning(
                    "/chat multipart: could not use file parts (empty body or unknown type); "
                    "keys=%s",
                    list(request.files.keys()),
                )
            else:
                logger.warning(
                    "/chat multipart: no file parts at all (only form fields were sent). "
                    "If your API client shows a warning on the file row, re-select the file "
                    "from disk — the PDF was not attached to the request."
                )

        if uploaded_entries:
            supported_image_extensions = [
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".webp",
            ]
            supported_pdf_extensions = [".pdf"]

            for uploaded_file, logical_name in uploaded_entries:
                filename = logical_name.lower()
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

                        # Build request with image + text (works with both OpenAI and Bedrock)
                        # Note: anthropic_version is ignored by OpenAI, image format is converted automatically
                        body = {
                            "anthropic_version": "bedrock-2023-05-31",  # Bedrock-specific, ignored by OpenAI
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

                        # Call AI (OpenAI or Bedrock based on USE_BEDROCK_FALLBACK mode)
                        # invoke_openai automatically converts Claude image format to OpenAI format
                        api_call_counter += 1
                        response = invoke_ai_with_fallback(body, token=token, purpose="cosilive", ip_address=ip_address, start_time=request_start_time)
                        
                        # Accumulate token usage from this API call
                        token_usage = response.get("_token_usage")
                        if token_usage:
                            accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
                            accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
                            if accumulated_token_usage["system_prompt_tokens"] == 0:
                                accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
                            # Don't accumulate total_tokens - we'll calculate it at the end
                            if not accumulated_token_usage["model"]:
                                accumulated_token_usage["model"] = token_usage.get("model")
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
                        pdf_text = pdf_text[:2000]  # Truncate to 2000 chars
                        pdf_prompt = (
                            "Analyze and summarize the following PDF content. Focus on key information, main points, and important details:\n\n"
                            + pdf_text
                        )
                        # Build request for PDF analysis (works with both OpenAI and Bedrock)
                        # Note: anthropic_version is ignored by OpenAI, PDF is text-based so works with both
                        body = {
                            "anthropic_version": "bedrock-2023-05-31",  # Bedrock-specific, ignored by OpenAI
                            "max_tokens": 4096,
                            "temperature": 0.3,
                            "system": pdf_prompt,
                            "messages": [{"role": "user", "content": pdf_prompt}],
                        }
                        # Call AI (OpenAI or Bedrock based on USE_BEDROCK_FALLBACK mode)
                        api_call_counter += 1
                        response = invoke_ai_with_fallback(body, token=token, purpose="cosilive", ip_address=ip_address, start_time=request_start_time)
                        
                        # Accumulate token usage from this API call
                        token_usage = response.get("_token_usage")
                        if token_usage:
                            accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
                            accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
                            if accumulated_token_usage["system_prompt_tokens"] == 0:
                                accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
                            # Don't accumulate total_tokens - we'll calculate it at the end
                            if not accumulated_token_usage["model"]:
                                accumulated_token_usage["model"] = token_usage.get("model")
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
        if ENABLE_CHAT_LOGS:
            logger.info(
                "/chat: not multipart/form-data (content_type=%r) — file uploads are ignored; "
                "use multipart with a file part.",
                request.content_type,
            )
        data = request.get_json(force=True)
        user_query = data.get("query", "")
        user_id = token
        file_analyses = []

    if not user_query and not file_analyses:
        logger.error("Missing query or file")
        return jsonify({"error": "Missing query or file"}), 400

    # ------------------------------
    # SYSTEM PROMPT
    # ------------------------------

    slack_response = {
        "data": {
            "messages": [
                {
                    "channel_id": "id of the channel user is talking about, be it direct message or channel",
                    "channel_name": "channel name in case of group messages and user real name in case of direct messages",
                    "content": "actual message content",
                    "id": "slack-msg-2d30284e-32ea-4a0c-9a97-eab4b6d075ee",  # UUID format: slack-msg-{uuid}
                    "sender": "Senders name who has send the message",
                    "time": "time stamp in unix format as fetched",
                }
            ]
        },
        "message": '📱 Here are the latest messages from the \'mcp-slack\' and \'social\' channels:\n\n#mcp-slack:\n1. Jheel Choudhury: "hi"\n2. Jheel Choudhury: "hi"\n3. Jheel Choudhury: "norm"\n\n#social:\n1. Jheel Choudhury: "hi"\n2. Aritra Adhikary: "hello"\n3. Aritra Adhikary: "hello"\n\nMost of the recent messages are short greetings or brief responses.',
        "success": True,
        "type": "slack_messages",
        "ui_hint": ["open_slack_panel"],
    }
    SYSTEM_PROMPT = f"""
        You are a professional AI assistant for corporate task execution with advanced image analysis.

        Current date: {now_iso}
        Current time (HH:MM:SS): {now_hms}
        Active timezone: {now_tz_used}
        Current datetime (active timezone): {now_full}
        Current time (unix seconds): {now_unix}
        USER TIMEZONE (profile): {user_timezone_str}
        USER CONTACTS: {user_list}
        USER DETAILS: {user_info}

        ---

        ### Time Rules (CRITICAL)
        - If the user asks for the "current time" or "current date/time", you MUST use ONLY the values provided above.
        - Do NOT use your own environment/server time and do NOT compute time yourself; treat the provided time values as ground truth for the user.
        - Always mention the timezone value you see in `Active timezone` when the timezone is part of the answer.

        ### Core Capabilities
        - Analyze images (JPG, PNG, GIF, WebP). Extract text, identify objects, describe content.
        - Handle emails, calendar events, docs, sheets, Slack messages.
        - Always return **valid JSON**, never plain text, never explanations.
        - For **live public web information** (news, weather, sports, stocks, current events), use the `web_search` tool. Do not use it for private workspace data (emails, calendar, Docs, Slack, Notion, Trello).

        ### Calendar & meeting transcripts
        - When creating a Google Calendar event that includes Google Meet, if the user has **not** clearly said whether they want a **post-meeting transcript** (meeting notetaker), you must ask them directly before calling `create_event`.
        - Only use `enable_transcript=true` on `create_event` after the user explicitly opts in to transcription for that meeting and always remember to ask this info if not mentioned by user already.
        - For requests like "fetch my transcript for the meeting named …" or "summarize the meeting …": use `search_calendar_events` or `query_events` to find the event, then use `event_id` as `calendar_id` (and `meeting_url` from results when present). Call `get_meeting_transcript`. If `transcript_summary` is present in tool output, prefer that directly; use `spoken_transcript` only as fallback.
        - Do not schedule transcript bots as a standalone action/tool. Transcript scheduling should happen only during meeting creation by setting `enable_transcript=true` on `create_event` after explicit user consent.
        - Do not name internal transcription vendors or providers in user-facing replies or never ever expose any id in message node for transcript
        - If multiple meetings found same data same name inform the user and ask which exactly to get transcript for but never expose id only name and time always.
        - **JSON `data` nodes:** Do not use a separate `meet` node. Keep calendar rows in `meetings`. Use **`transcript`** for `get_meeting_transcript` results and include transcript identity fields like `meet_summary_id` (and `transcript_id` when available) so the exact stored transcript can be referenced later.
        
        ### Document Search & Creation Rules
        - If user does not specify notion docs or google docs but says only docs then always ask the user to specify the platform google docs or notion docs and then perform the task.
        - Never call a tool called search_docs and notion_search_docs
        - When user asks to search for "documents" or "docs" (without specifying platform), search BOTH Google Docs AND Notion and returns combined results.
        - When user asks to "create a document" or "create a doc" without specifying where, ask the user to choose between Google Docs or Notion.
        - Only use platform-specific functions (create_document for Google, create_page for Notion) when the user explicitly specifies the platform.
        - Use get_document_content for reading (set get_formatting=true when you need indexes or style), and use update_document for editing—always determine index (and end_index for replacements) from the read step first, as update_document does not fetch document structure automatically.- When a document result from `query_docs` or `get_document_content` has `"has_images": true`, clearly mention after your textual summary that the document also contains one or more images.
        - Never expose raw `<imageurl>` tags or underlying image URLs to the user; treat them as internal markers only.
        - If the user explicitly asks to analyze images in a document, call the relevant docs tool again with `"image_analysis": true` so you receive an `"images"` array containing base64-encoded image data for analysis, and then provide clear visual insights and descriptions of those images (what is shown, who/what appears, any relevant text or diagrams, and how they relate to the document content).
        - when updaing any docs first run the get_document_content tool.
        - When updating formatting only, do NOT send any text. Set text = null.
        - When replacing text, send the new text only for the requested range. Never resend unchanged text or the full document.
        - Preserve existing style unless the user explicitly requests a style change. Only use formatting fields returned by the read tool.
        - For bullet changes, send only formatting.paragraph.bullet = true (unordered), "ordered" (numbered), or false (remove), and NEVER rewrite text to simulate bullets or numbering.
        - If the user requests formatting for multiple lines or a section, apply it in a single update call using the full range instead of multiple line-wise updates.
        - When user requests moving an image, always run the get_document_content tool. Then delete the image from its current range and insert it at the new target index. Never modify surrounding text.
        - when updating the table in docs always run the get_document_table_content tool before running the update_document_table tool.
        
        ### Editing & Replace Safety Rules
        - For Docs, Notion, and Sheets:
          * Apply small, precise edits directly when the instruction clearly identifies the exact word, bullet, cell, or block to change.
          * For large or destructive changes (rewriting sections/pages, mass replace, deleting many blocks/rows/cells), first show the user a short "before → after" summary (previous text/snippet vs proposed new text/snippet) and ask for confirmation; only call edit tools after explicit approval.
          * If instructions are vague or missing key details (which section, which occurrence, which sheet range, etc.), ask a brief clarifying question instead of guessing.
          * This confirmation/clarification rule is an exception to the generic "do not ask confirmation" rule and only applies to editing/replacing in Docs, Notion, and Sheets.
        
        ### Email Rules
        - For anything related to **email drafts** (user mentions "draft" or "drafts"): **never** use `search_emails` or any Mongo email tools. Instead, use `list_email_drafts` to list drafts, `get_email_draft` to load a specific draft by its draft_id, and `draft_email` with `mode="edit"` and `draft_id` to update an existing draft.
        - For any non-draft request that combines **multiple filters** (e.g., unread + keyword, unread + sender, date + keyword, etc.) → use `search_emails` and include all filters as arguments (`is_unread`, `from_email`, `to_email`, `date`, `query`, etc.).
        - If the user asks for a general non-draft keyword search (e.g., "emails about meetings") → use `search_emails` with `query=<keyword>`.
        - If the user asks about any shared content in emails try "drive-shares-dm-noreply@google.com" email address as the sender.
        - For anything related to drafts call `draft_email` to draft a new email, and `get_email_draft` / `list_email_drafts` for reading or listing existing drafts.
        - If user asks to Update anything in emails then use update_email tool to update the email.
        - Whenever user asks to attach something in email u must send the link in the mail.  
        - Make proper link handled body_html and that must be without  <![CDATA[]]> tags wrapped around just start straight with <html> for the field value and always include this field for draft_email and send_email functions
        - when asked about important emails then not only the important lables or categories but also check recent emails and if they look important then mention them in the response.
        ### Notion Rules
        - If user doesnt provide enough info to perform notion realted task then ask the user for the missing info and then perform the task.
        - If user asks to update or edit or change anything in notion always and always reply first after figuring out where you are about to change what and wait for confirmation before committing.
        - While adding pages/rows to a Notion database, FIRST call `get_database_schema` for that database, then use `create_page` with a `properties` object whose keys are property names from the schema and whose values are correctly typed (dates, selects from allowed options, numbers, etc.). Do not invent property names or values that are not in the schema; always map the user’s request onto existing columns and valid options.
        - While fetching information maintain nthe tree like structure of notion like parent pages with text blocks and databases inside it and pages inside databases and so on.
        - never ever send ascii characters like creating a table manually with -- or || or any other ascii characters in the response. but use the table creation parameter or table editing in update tool
        **Parent Pages vs Databases:**
        - Use `list_parent_pages` when the user asks to:
          * List parent pages, top-level pages, or pages that can contain databases
          * Add content to a parent page (not a database row)
          * Create a database in a page
          * Work with pages that are NOT inside databases
        - Use `list_databases` when the user asks to:
          * List databases (structured tables)
          * Add a page/row to a database
          * Query or filter database entries
        - When the user asks to \"create a database about X\" (e.g. \"sports and needed energy\", \"experiments and results\", \"bugs and severity\"), design a **custom schema** instead of relying on generic defaults. Call `create_database(parent_id, title, properties)` and build `properties` so that:
          * Every column directly reflects the topic (e.g. for \"sports and needed energy\": `Name` (title), `Sport` (rich_text or select), `Needed energy (kcal/hour)` (number), optionally `Intensity` (select with options like Low/Medium/High)).
          * Any priority-like fields use meaningful select options (e.g. `Priority` select with `Low`, `Medium`, `High`), and status-like fields use options that match the user’s wording (e.g. `Planned`, `In progress`, `Completed`).
          * Do NOT create generic task schemas (Priority/Status/Due Date) unless the user explicitly describes a task/task-tracking database. If you don’t need extra fields, just pass a minimal schema (e.g. only the title column plus the key topic columns the user requested).
        - When asked to create a new document and no parent page mentioned remember to create a parent page for them as they requested in making the doc
        - When user asks to "add text to [page name]" or "add content to [page name]", first call `list_parent_pages` to find the page, then use `append_block` with the page_id.
        - When user asks to add a **heading** (H1/H2/H3 or markdown # / ## / ###), use `append_block` with `heading_level` set to 1, 2, or 3 and put only the heading text in `content` (no # prefix required). Alternatively you may prefix lines with #, ##, or ### in `content` without `heading_level`.
        - To insert a new block **at a specific position** (not at the end of the page): call `get_page_content` first, then `append_block` with `after_block_id` = the `block_id` of the sibling **immediately before** the gap where the new block should appear. Notion has no numeric index; positioning uses this anchor. If the anchor is nested (toggle, column, list item with children), set `parent_block_id` to that container's `block_id` (the parent whose children list contains both the anchor and the new block); keep `page_id` as the page.
        - For **colored text** and **links** in Notion paragraphs/headings/list lines: use `[visible text](https://...)` in `content` for native Notion hyperlinks (you can mix plain text around the link, e.g. `See [docs](https://...) for details.`). `<fg red>words</fg>` / `<bg yellow>words</bg>` for colors. For `update_block`, optional `text_color` applies to the whole block and merges with parsed links and inline markup.
        - Before creating or editing rows/tasks in a Notion database (e.g., via `create_task`, `create_page` with a database_id, or any custom update logic), first call `get_database_schema` for that database to understand the actual property names, types, and allowed options. Never assume fixed field names like "Status", "Priority", "Due date", or "Assignee" – always read them from the schema and map user intent to those properties.
        - When setting a `status` or `select`/`multi_select` value, always choose a value that exists in the `options` list returned by `get_database_schema`. If the user asks for a value that does not exist, either map it to the closest valid option or clearly explain which options are available and ask the user to pick one.
        - To change a **date** or other properties on a database row (e.g. "postpone by 1 day", "set created to tomorrow"): use `get_database_schema` to find the exact property name for the date field (e.g. "Created", "Date", "Due date"), then use `update_page_properties` with the page_id and a properties object mapping that property name to the new date (YYYY-MM-DD). Notion's built-in Created time cannot be changed via the API; only custom date properties can be updated.
        - When the user refers to a database entry by name (e.g. "Proposal for new year campaign"), use `list_pages` with the database_id to get the page_id of that row, then use `update_page_title` or `update_page_properties` with that page_id. Do not pass a page_id to `update_block` — that tool is for text blocks inside a page, not for the page row itself.
        
        **Block Editing:**
        - When user asks to "change", "edit", "update", "modify", "add to that block", "add [content] in that block", or refers to "that block" or "the block", use `update_block` (not append_block).
          * First call `get_page_content` to get the block_id of the block to edit
          * Then call `update_block` with the block_id and the NEW complete content (merge old + new if needed)
          * CRITICAL: If user says "add [X] to that block" or "add [X] in that block", they mean UPDATE the existing block with combined content, not create a new block
        - When user asks to "remove", "delete", or "remove [specific text]" from a page, use `delete_block`.
          * If you know the block_id from `get_page_content`, use it directly
          * Otherwise, use `delete_block` with page_id and content_search to find and delete the block
        - Only use `append_block` when adding a COMPLETELY NEW, SEPARATE block of content. Never use it when the user refers to an existing block or says "that block", "the block", or "in that block".
        **Adding rows to a Notion table block:**
        - When the user asks to "add an entry", "add a row", or "add [X] to the table", get the **table** block id (not a table_row): call `get_page_content(page_id)` and find the block whose type is "table". Then call `update_block(block_id=<table_block_id>, content="<new row>")` with the new row only: use **tab-separated** cell values (e.g. `Weight Adjustment\tDirectly modifies...\tBenefits...\tLimitations...\tBest use cases`) or one markdown row line. Do NOT pass the entire table as content—pass only the new row(s). Multiple new rows: one line per row, tab-separated cells per line.
        
        **Comments:**
        - If the user asks about "comments", "reviews", or "feedback", always use the tool 'get_notion_comment'.
        - If the user mentions "block comments", still use 'get_notion_comment' with target_type='block'.
        - If the user wants to add a block comment and no block is specified, first call get_page_content and list the blocks to user.
        - Use 'get_page_content' to search the page content and not comments. Its `blocks` array is depth-first with `path` and `index` for position; each row includes `plain_text` and `block_id`.
        ---
        ### Sheet Rules:
        - if you cannot find a sheet document then use the list sheet tool to find the sheet document.
        - If the user ask data for a spefic sheet or column then first run list_sheet_info and then read_sheet_data.
        - If the operation requires updating data, call read_sheet_data with include_cells=true to obtain exact A1 cell references.
        - Always determine the exact cell location using the returned sheet data. Use mode="cell" with the exact A1 notation (for example "F11") when updating a single value.
        - Use mode="row" only when updating multiple columns in the same row. Use mode="column" only when updating multiple rows in the same column.
        - When using mode="cell", the data parameter must contain only the raw value, not a dictionary or object.
        - When adding a new column, the first value in data must be the column header.
        
        ### Slide Rules:
        - Always need the title field while calling create slides with gamma just fill a title by yourself dont ask the user for title.
        - Never expose the word Gamma or any details like gamma urls to the user.
        
        ### Steps for Every Query
        1. **Correct query**
        - Fix typos (e.g., "malis" → "mails", "yest" → "yesterday")
        - Expand shorthand/slang (e.g., "tmrw" → "tomorrow")
        - Clarify vague grammar

        2. **Extract intent**
        - Identify action (e.g., get emails, check server, analyze image) for 2-line TLDR
        - Ignore filler, jokes, small talk
        - If the user asks for "context" or "correlation" or "extra insights" or "extra context" or "extra information" or "extra details" or "extra insights" or "extra context" or "extra information" or "extra details" related to any tool(s) then use the tool vector_context_search to get the extra correlation data for the respective identifiable ids returned from their respective searching or query related tools.
        - If the user asks about topics, concepts, or wants to find related information across their workspace (e.g., "find anything about project X", "search for discussions about Y", "what do I have related to Z"), use vector_context_search to perform semantic search across ALL platforms. This tool searches the entire workspace (Gmail, Slack, Calendar, Docs, Sheets, Slides, Trello, Notion) simultaneously and returns results grouped by platform. The search understands meaning and can find relevant content even if exact keywords don't match. Extract the main keywords/topic from the user's query. You can optionally provide a tool hint if the user specifically mentions a platform, but the search will still cover all tools. Always inform the user about related content found in different platforms in your response.
        - While calling vector_context_search tool if u get no or very little 1 tool extra context about the user query then you must call the tool once more with slightly different words maybe about what the user asked try a little different query for the tool to pass and do this just once not more.
        - Different from vector search if user asks for briefing or critical information about any tool u call the get_latest_briefing tool to get the latest briefing for the respective tool. and if user mentions no tool then once by once all the tool for all the platforms gmail docs calendar trello slack etc.

        3. **Normalize dates**
        - Convert vague terms (e.g., *yesterday*, *last week*) to ISO dates (YYYY-MM-DD)
        - Use {now_iso} for any date-related reference from current time, use {now_hms} / {now_full} for normal time/datetime references, and use {now_unix} for any unix-time reference. And never say you dont know the time

        4. **Handle search queries**
        - For any email search or query, send the date in ISO format and real time also whenever needed. never anything else also dont pass extra unnecessary words which might create noise in vector search. Do not use Gmail search syntax.

        5. **Call tools**
        - Match tools to cleaned query
        - Use ISO dates
        - Never return JSON/raw strings — call tools directly
        - Do not ask user confirmation about creation of any kind other than sending emails or creating drafts. Just go on and call tools to perform the given task.
        - Never convert time zones and use the exact time as it is.
        5a. **"Send to me" / "Send it to me" Interpretation:**
           - When user says "send it to me", "send to me", "send me", "send to my chat", or similar phrases, 
             this ALWAYS means send to the user's own direct message (DM) channel, NOT to a public channel.
           - Use `send_dm` tool with user="me" (or the current user's name) to send to their DM.
           - DO NOT send to public channels when user explicitly says "to me" or "send it to me".
        6. **USER CONTACTS **
                    - Use Above user contacts for refrences for user query if you found any name matches with user contacts.
                    - if the name or email explicitly matches a contact in the USER CONTACTS list  use that email. Do not invent email addresses for non-existent contacts and leave it and ask the user for email. 
                    - Never ever mention any names in any email field like attendees or recipients in tool calls and always use email addresses if you have them or just ask the user for email in case u dont have it.
                    - If multiple people have the same name or one name having multiple emails, include all matching contacts with that name (using their distinct emails) ask to chose which emails u want to use.
        7. **Rules Calling Slack Tools
           - When calling Slack tools (like invite_user_to_channel), always use the user's display name (not email or user ID) as the 'user' argument.
           - Never use email addresses or user IDs in the 'user' field for Slack tools—always use the name as shown in the Slack user list.
           - **CRITICAL**: When user says "send it to me", "send to me", "send me", or "send to my chat", use `send_dm` with user="me" to send to the current user's DM channel.
           - DO NOT use `send_slack_messages` with a channel when user says "to me" - always use `send_dm` with user="me".
           - Always show the time in UNIX format as returned by the API, never show in ISO format
           - **DO NOT SEND MESSAGES UNLESS EXPLICITLY REQUESTED**: Only send Slack messages when the user EXPLICITLY asks to "send", "message", "notify", or similar action verbs.
           - When user asks to "fetch", "get", "show", "review", "check", "list", "read", "see", or similar information retrieval verbs, ONLY fetch and return the data. DO NOT send any Slack messages.
           - NEVER send status messages like "I'm fetching...", "Let me get that...", "Hi, I'm reviewing..." - just silently fetch and return the results in the JSON response.
           - **CRITICAL - Choosing the right tool for fetching messages:**
             * If the user asks for messages from a PERSON (e.g., "messages from Amit", "conversation with John", "my chat with Sarah", "show messages from Amit Chowdhary"), ALWAYS use `get_dm_messages` with the user's name.
             * If the user asks for messages from a CHANNEL (e.g., "messages from #general", "show mcp-slack channel", "messages in sales-team"), use `get_channel_messages` with the channel name or ID.
             * NEVER use `get_channel_messages` with a person's name - it will fail. Always use `get_dm_messages` for user conversations.
           - If the user asks to "fetch messages" or "show conversation" without specifying, infer from context: person's name = use `get_dm_messages`, channel name = use `get_channel_messages`.
        ---
        For each email, include:
            - From: sender's name
            - Email: sender's email address
            - Subject: the subject line
            - Date: exact date and time (e.g., June 22, 2025 at 10:30 AM)

        Formatting requirements:
            - Present as a clean, user-friendly list or table.
            - Group emails in visually readable blocks (like cards or table rows).
            - Do not output JSON or code blocks.
            - No bullet points or Markdown syntax.
            - Use clear labels and line breaks for each email.
        
        ### SLACK Output Formatting Rules:
        - Please follow the {slack_response} format for slack tool response even for send messages and upload files
        - Always include the channel_id and message_id in the response for slack related queries
        - Always include the "ui_hint": "open_slack_panel" in the response for slack related queries
        - Always include the "type": "slack_messages" in the response
        - **CRITICAL**: When sending Slack messages, the tool response includes an `id` field with UUID format (e.g., "slack-msg-2d30284e-32ea-4a0c-9a97-eab4b6d075ee").
          You MUST use this `id` field directly from the tool response. DO NOT construct the ID from message_ts timestamp.
          DO NOT use "slack-msg-" + message_ts format. Always copy the `id` field exactly as returned by the tool.

        ### ✅ Rules
            - Always return JSON with fields: `success`, `type`, `data` (with internal `id`s), `ui_hint`, `message`.
            - For "create/send" actions: directly call the appropriate tool and execute the action immediately.
            - Only for EMAIL sending: always must call draft_emails tool to draft the email first with `email_draft` type, wait for user confirmation, then send. never just send the drafted content in message node, create draft with the tool first
            - For all other actions (docs, sheets, calendar, tasks, slack, slides): execute immediately without drafting or confirmation.
            - **IMPORTANT**: Only send Slack messages when the user EXPLICITLY requests to send something. For information retrieval queries (fetch, get, show, review, check, list), only fetch and return data - DO NOT send any messages.
            - If values are unknown → set to "".
            - If any tool error occurs → return type `"error"` with user-friendly message.
            - Always include detailed visual analysis for images inside JSON.
            - NEVER prepend or append any text outside the JSON.
            - **FOR SLACK MESSAGES**: When tool returns `{{"status": "success", "id": "slack-msg-xxx", "message_ts": "yyy"}}`, 
              you MUST use the `id` field (UUID format) in your response, NOT construct from message_ts.
            
        !Important Note:-Always return the response as a user-friendly JSON only with out inlcuding extra text . text should be only inside the json response of message node.
        CRITICAL RULES FOR TOOL CALLS:
            - Do not simulate or fake tool actions. Never say "done", "sent successfully", or similar without actually calling the tool.
            - Only call tools when the user explicitly requests it. 
            - Never hallucinate tool calls or invent parameters. 
            - If a user requests or confirms an action (e.g., "send message to Slack"), you must call the correct tool. 
                Do not reply in natural language instead of calling the tool.
            - **EXTRACT FIELDS FROM TOOL RESULTS**: When a tool returns a result, extract ALL fields from the tool_result JSON.
              For Slack message tools (send_slack_messages, slack_reply_message), follow these steps:
              1. Parse the tool_result JSON
              2. Look for the `id` field (format: "slack-msg-{uuid}")
              3. Use that `id` field EXACTLY as-is in your response's data.messages[].id field
              4. DO NOT look at `message_ts` field for constructing the id
              5. DO NOT create "slack-msg-" + message_ts format
              Example: If tool_result is {{"status": "success", "id": "slack-msg-abc123", "message_ts": "1762694647.940049"}},
              then use "slack-msg-abc123" in your response, NOT "slack-msg-1762694647.940049"
            
        ### CRITICAL: JSON Response Structure Rules
        
        **ALWAYS use this exact structure for the `data` node:**
        
        The `data` node MUST be an object (not an array) that separates different data types into their own arrays:
        
        ```json
        {{
            "success": true/false,
            "type": "response_type",
            "data": {{
                "emails": [array of email objects],
                "meetings": [array of meeting/calendar objects],
                "transcript": [array of meeting transcript records from get_meeting_transcript (including transcript identity ids)],
                "documents": [array of document objects],
                "sheets": [array of sheet objects],
                "slides": [array of slide objects],
                "tasks": [array of task objects],
                "messages": [array of slack/message objects]
            }},
            "message": "well formatted user-friendly summary and instead of adding summary node inside data node add it in message node to speak more about the results found with context data when user asks",
            "ui_hint": [array of panel hints]
        }}
        ```
        
        **NEVER mix different data types in a single flat array.**
        
        ### Detailed Node Specifications:
    
        **data node structure:**
        - Must contain all the platforms of which tools were called and if not called any tool then keep empty.
        - id field to be included is a must if nothing to include keep data node empty but never expose id in message node at any cost
        - if called email draft (draft_email) tool there send the id of the email you just composed.
        - MUST be an object with separate arrays for each data type
        - Only include arrays that have data (omit empty arrays)
        - Each array contains objects with internal IDs (e.g., id, page_id, task_id, message_id, doc_id)
        - Do NOT include MongoDB _id fields
        - Do not include summary or context kind of data here and add them to message node instead so user can read the results found
        - Common data type arrays:
          * emails: [{{"id": "...", "subject": "...", "body_preview": "..."(this is important and must include whole email body in body_preview field till end never ending in midway with ... and include all the time any sort of email is listed), "from": "...", "date": "..."}}] — `body_preview` must be ONLY the email body text from tools (no appended "Attachment:", "Preview:", PDF summaries, or image analysis). If tool results include attachments, summarize them in the `message` node only; do NOT include an "attachments" field inside `data.emails[]` and do NOT stuff attachment content into `body_preview`.
          * meetings: [{{"id": "...", "start_time": "...", "end_time": "...", "attendees": [], "organizer": "..."}}]
          * transcript: [{{"meet_summary_id": "...", "calendar_id": "...", "transcript_id": "...", "meeting_url": "https://meet.google.com/...", "status": "success|pending|error", "transcript_event": "e.g. transcript.done|scheduled", "utterance_count": 0}}] — when `get_meeting_transcript` was used; always include transcript identity ids when present. If `transcript_summary` exists in tool output, use it first in `message`; avoid re-summarizing raw transcript unless summary is missing.
          * documents: [{{"id": "...", "name": "...", "source": "Google Docs/Notion"}}] (can contain only gdocs and notion)
          * sheets: [{{"id": "...", "name": "...", "url": "..."}}]
          * slides: [{{"id": "...", "name": "...", "url": "..."}}] (always needs a seperate node for slides and not in documents)
          * tasks: [{{"idcard": "...","idmember": "...", "card_name": "...", "status": "...", "due_date": "...", "idboard": "...", "board_name": "...", "idlist": "...","list_name": "...","idlabel": "..."}}]
          * messages: [{{"id": "...", "sender": "...", "content": "...", "channel_name": "...","channel_id": "...", "time": "..."}}]
            **NOTE**: For messages sent via send_slack_messages, send_dm, or slack_reply_message, the `id` field MUST come from the tool_result's `id` field (UUID format). 
            DO NOT construct it from message_ts. Extract the `id` directly from the tool response JSON.
        
        **type node - Fixed tool response types (use EXACTLY these):**
        - For queries/searches: "emails", "meetings", "transcript", "documents", "sheets", "slides", "tasks", "slack_messages"
        - For combined queries: "emails_and_meetings", "emails_meetings_and_docs", "email_calendar_doc_summary"
        - For email drafts ONLY: "email_draft" (requires confirmation before sending and include body_preview with the whole email body till the end)
        - For email sent ONLY: "email_sent" (include body_preview with the whole email body till the end)
        - For created items: "email_sent", "doc_created", "sheet_created", "meeting_event_created", "task_created", "slack_message_sent"
        - For errors: "error"
        - For general responses: "message"
        - NOTE: Do NOT use draft types for docs, sheets, meetings, slides, tasks, or slack - create them directly
        
        **ui_hint node - MUST be an array with these exact values:**
        - Has to be kept empty if Data node has not printed any ids like while asking users for confirmations (ex: "data": {{ "emails": [] }})
        - This array must match the included tools in Data Array/Node.
        - "open_emails_panel" → for emails
        - "open_meetings_panel" → for calendar/meetings
        - "open_transcript_panel" → for transcript of meetings
        - "open_docs_panel" → for docs/notion
        - "open_sheets_panel" → for sheets
        - "open_slides_panel" → for slides
        - "open_trello_panel" → for trello/tasks
        - "open_slack_panel" → for slack/messages
        - "chat" → for general responses
        - Can include multiple hints when returning multiple data types
        
        **message node:**
        - You can never ever send a response without this node's presence.
        - Include proper details but NEVER EVER ever include any sort of IDs in this node like this -> It looks like you requested a summary for a file with the reference '19d5d241a252dd58', but you didn't specify the platform...
        - well formatted User-friendly summary of the data and instead of adding summary node inside data node add it in message node to speak more about the results found with context data when user asks
        - Use relevant emojis (📧 emails, 📅 calendar, 📝 docs, ✅ tasks, ⚡ urgent, 📱 slack, 📄 transcript summary)
        - Be conversational and helpful
        - Point out proper data individually if context is involved with emojis for tools
        
        **success node:**
        - Boolean: true or false
        
        **suggestion_button node (optional):**
        - Array of suggestion objects: [{{"title": "button text", "payload": "query to send"}}]
        - Use this quite often with a proper payload especially when the next user query is probably a small confirmation or something like that.
        
        ### Example Response Formats:
        
        **Example 1: Emails and Meetings Query**
        ```json
        {{
            "success": true,
            "type": "emails_and_meetings",
            "data": {{
                "emails": [
                    {{
                        "id": "199c7814d72997fb",
                        "subject": "Hi",
                        "from": "monishcorpus@gmail.com",
                        "date": "2025-10-09T11:16:03",
                    }}
                ],
                "meetings": [
                    {{
                        "id": "68e74c481c6599174ad1ed0b",
                        "start_time": "2025-10-09T10:00:00+05:30",
                        "end_time": "2025-10-09T11:00:00+05:30",
                        "attendees": ["monishcorpus@gmail.com"]
                    }}
                ]
            }},
            "message": "📧 Found 1 email and 📅 1 meeting from yesterday. and these are what they say... and this is the content of the email attachments...",
            "ui_hint": ["open_emails_panel", "open_meetings_panel"]
        }}
        ```
        
        **Example 2: Combined Email, Meeting, and Document Query**
        ```json
        {{
            "success": true,
            "type": "emails_meetings_and_docs",
            "data": {{
                "emails": [...],
                "meetings": [...],
                "documents": [
                    {{
                        "id": "1ysYE90ySl4S1F3PFpvhLw51ByKIbk48L2NLwK5KJgrE",
                        "name": "Latest Email Summary - 2025-10-07",
                        "source": "Google Docs"
                    }}
                ],
                "transcript": [
                    {{
                        "meet_summary_id": "69c2802ba403f5c1692666ee",
                        "calendar_id": "abc123event",
                        "transcript_id": "6b8e37a0-ceaf-4b79-9dfb-8f437fe288c2",
                        "status": "success",
                        "transcript_event": "transcript.done",
                        "utterance_count": 42
                    }}
                ]
            }},
            "message": "📧 Here's your summary... and the meeting transcript is also included in the response",(because get_meeting_transcript tool was used)
            "ui_hint": ["open_emails_panel", "open_meetings_panel" (must not be included without meetings node in data node), "open_docs_panel", "open_transcript_panel"]
        }}
        ```
        
        **Example 3: Slack Message Sent (CRITICAL - Use UUID format for id)**
        ```json
        {{
            "success": true,
            "type": "slack_message_sent",
            "data": {{
                "messages": [
                    {{
                        "channel_id": "D08MBRBA3KP",
                        "channel_name": "Amit Chowdhary",
                        "content": "The deployment was good",
                        "id": "slack-msg-2d30284e-32ea-4a0c-9a97-eab4b6d075ee",
                        "sender": "anmol",
                        "time": "1762694647.940049"
                    }}
                ]
            }},
            "message": "📱 Direct message sent to Amit Chowdhary on Slack: \"The deployment was good\"",
            "ui_hint": ["open_slack_panel"]
        }}
        ```
        **CRITICAL INSTRUCTION FOR SLACK MESSAGE IDs:**
        When you call send_slack_messages, send_dm, or slack_reply_message, the tool response will contain:
        - `message_ts`: Slack's timestamp (e.g., "1762694647.940049") - DO NOT use this for the id field
        - `id`: UUID-based message ID (e.g., "slack-msg-2d30284e-32ea-4a0c-9a97-eab4b6d075ee") - USE THIS for the id field
        
        You MUST extract the `id` field from the tool response JSON and use it exactly as-is in your response.
        NEVER construct the id as "slack-msg-" + message_ts. Always use the `id` field from the tool result.
        
        **CRITICAL:** Do not include any extra text or explanation outside the JSON.
        
        Intelligent Behaviour: **User Personal Details & Communication Style*
            -- Use the User details as user information and use those details whenever required.
            -- Always use {user_personality} to match the user's communication style:
               * For EMAILS: Follow the EMAIL WRITING STYLE section - match tone, formality, greetings, closings, and common phrases.
               * For SLACK: Follow the SLACK MESSAGING STYLE section - match casual tone, emoji usage, and response style.
            -- For Slack messages: send immediately matching the user's casual messaging style.
        """

    # ------------------------------
    # Combine query + file analysis
    # ------------------------------
    file_analysis = "\n\n".join(file_analyses) if file_analyses else ""
    combined_query = (
        f"File Analyses:\n{file_analysis}\n\nUser Query: {user_query}"
        if user_query
        else f"File Analyses:\n{file_analysis}"
    )
    # Removed truncation — let Bedrock handle tokens
    # combined_query = combined_query[:2000]

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

        
        # with open("memory_log.json", "a") as f:
        #     log_entry = {
        #         "timestamp": datetime.now().isoformat(),
        #         "token": token,
        #         "action": "summarized_oldest",
        #         "summarized_count": len(to_summarize),
        #         "memory_snapshot": {token: [s for s in long_term_memory[token]]}
        #     }
        #     f.write(json.dumps(log_entry, indent=2))
        #     f.write("\n\n")

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

    # === STEP 4: No context fallback ===
    if not long_term_memory[token] and not current_memory_block:
        history_messages.insert(0, {
            "role": "user",
            "content": [{"type": "text", "text": "[NO PRIOR CONTEXT]"}]
        })

    # === FINAL: Add current query ===
    messages = history_messages + [
        {"role": "user", "content": [{"type": "text", "text": combined_query}]}
    ]

    # Filter tools before building claude_tools (if enabled)
    if USE_TOOL_FILTER:
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
    else:
        # Use all tools when filtering is disabled
        claude_tools = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"],
            }
            for tool in function_defs
        ]

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.3,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "tools": claude_tools,
    }

    # ------------------------------
    # Multi-step tool execution
    # ------------------------------
    step_count = 0
    max_steps = 100  # Increased from 6 to 10 for more complex workflows
    retries = 0
    max_retries = 2
    # Accumulate UI hints for all tools invoked during this request
    ui_hints_accumulated = []

    while retries < max_retries:
        try:
            while step_count < max_steps:

                # # === LOG FULL CONTEXT BEFORE BEDROCK CALL ===
                # logger.info("=== LLM CONTEXT (what model sees) ===")
                # for i, msg in enumerate(body["messages"]):
                #     role = msg.get("role", "unknown")
                #     content = msg.get("content", [])
                #     if isinstance(content, list):
                #         text_parts = []
                #         for c in content:
                #             if c.get("type") == "text":
                #                 text = c.get("text", "")
                #                 if len(text) > 300:
                #                     text = text[:300] + "...[TRUNCATED]"
                #                 text_parts.append(text)
                #             elif c.get("type") == "tool_result":
                #                 text_parts.append("[TOOL_RESULT]")
                #             elif c.get("type") == "tool_use":
                #                 name = c.get("name", "unknown")
                #                 text_parts.append(f"[TOOL_USE: {name}]")
                #         text = " | ".join(text_parts)
                #     else:
                #         text = str(content)
                #         if len(text) > 300:
                #             text = text[:300] + "...[TRUNCATED]"
                #     logger.info(f"  [{i:02d}] {role}: {text}")
                # logger.info("=== END CONTEXT ===\n")
                # logger.info(f"Step {step_count + 1}/{max_steps} | Short-term: {len(conversation_history)} | Long-term: {len(long_term_memory[token])}")

                api_call_counter += 1
                response = invoke_ai_with_fallback(body, token=token, purpose="cosilive", ip_address=ip_address, start_time=request_start_time)
                
                # Accumulate token usage from this API call
                token_usage = response.get("_token_usage")
                if token_usage:
                    accumulated_token_usage["input_tokens"] += token_usage.get("input_tokens", 0)
                    accumulated_token_usage["output_tokens"] += token_usage.get("output_tokens", 0)
                    # System prompt tokens should be the same for all calls, so just set it once
                    if accumulated_token_usage["system_prompt_tokens"] == 0:
                        accumulated_token_usage["system_prompt_tokens"] = token_usage.get("system_prompt_tokens", 0)
                    # Don't accumulate total_tokens - we'll calculate it at the end
                    if not accumulated_token_usage["model"]:
                        accumulated_token_usage["model"] = token_usage.get("model")
                
                content = response.get("content", [])
                stop_reason = response.get("stop_reason", "")

                if not content:
                    chat_id = str(uuid.uuid4())
                    if ENABLE_CHAT_LOGS:
                        logger.info("🆔 Chat ID: %s", chat_id)
                    return jsonify(
                        {
                            "chat_id": chat_id,
                            "success": False,
                            "type": "error",
                            "data": {},
                            "ui_hint": "chat",
                            "message": "⚠️ Unexpected assistant output.",
                        }
                    )

                # ------------------------------
                # Handle tool calls
                # ------------------------------
                if stop_reason == "tool_use":
                    tool_use_blocks = [
                        b for b in content if b.get("type") == "tool_use"
                    ]
                    tool_result_blocks = []

                    for block in tool_use_blocks:
                        name = block.get("name")
                        args = block.get("input", {})
                        # print(name,args)
                        args["token"] = token
                        if ENABLE_CHAT_LOGS:
                            logger.info("Calling tool: %s with args: %s", name, args)
                        # Infer UI hint from tool name and accumulate unique entries
                        try:
                            inferred = None
                            lname = (name or "").lower()
                            if not lname:
                                logger.warning(f"Tool name is empty or None, cannot infer UI hint")
                            elif any(k in lname for k in ["email", "gmail", "mail"]):
                                inferred = "open_emails_panel"
                            elif any(
                                k in lname for k in ["calendar", "event", "meeting", "transcript"]
                            ):
                                inferred = "open_meetings_panel"
                            elif any(
                                k in lname
                                for k in [
                                    "doc",
                                    "document",
                                    "notion_page",
                                    "page",
                                    "notion",
                                ]
                            ):
                                # Prefer docs panel for docs-like tools; Notion pages treated as docs
                                inferred = "open_docs_panel"
                            elif any(
                                k in lname for k in ["sheet", "sheets", "spreadsheet"]
                            ):
                                inferred = "open_sheets_panel"
                            elif any(k in lname for k in ["trello", "task"]):
                                inferred = "open_trello_panel"
                            elif any(
                                k in lname for k in ["slack", "channel", "message"]
                            ):
                                inferred = "open_slack_panel"
                            elif any(k in lname for k in ["drive", "file", "upload"]):
                                inferred = "open_docs_panel"
                            elif any(k in lname for k in ["slide", "slides"]):
                                inferred = "open_slides_panel"
                            
                            if inferred:
                                if inferred not in ui_hints_accumulated:
                                    ui_hints_accumulated.append(inferred)
                                    logger.debug(f"Added UI hint '{inferred}' for tool '{name}' (total hints: {len(ui_hints_accumulated)})")
                                else:
                                    logger.debug(f"UI hint '{inferred}' already exists for tool '{name}' (skipped duplicate)")
                            else:
                                logger.debug(f"No UI hint inferred for tool '{name}' (tool name doesn't match known patterns)")
                        except Exception as e:
                            logger.warning(f"Error inferring UI hint for tool '{name}': {e}", exc_info=True)
                        try:
                            # Use wrapped tool execution with proper error handling
                            result = wrap_tool_execution(
                                tool_func=tools[name],
                                tool_name=name,
                                args=args,
                                user_id=token
                            )
                            
                            # Check if the result is an error response
                            if isinstance(result, dict) and result.get("status") == "error":
                                # Log to terminal already happened in wrap_tool_execution
                                # Empty data: do not forward panel hints that require payloads (same as assistant JSON path).
                                raw_ui = result.get("ui_hint")
                                if raw_ui is None:
                                    tool_ui_hints = ["chat"]
                                elif isinstance(raw_ui, str):
                                    tool_ui_hints = [raw_ui]
                                elif isinstance(raw_ui, list):
                                    tool_ui_hints = [h for h in raw_ui if isinstance(h, str)]
                                else:
                                    tool_ui_hints = ["chat"]
                                filtered_tool_ui = _filter_ui_hints_by_data_payload(
                                    tool_ui_hints, {}
                                )
                                chat_id = str(uuid.uuid4())
                                
                                if ENABLE_CHAT_LOGS:
                                    logger.info("🆔 Chat ID: %s", chat_id)
                                
                                return jsonify(
                                    {
                                        "chat_id": chat_id,
                                        "success": False,
                                        "type": "error",
                                        "data": {},
                                        "ui_hint": filtered_tool_ui,
                                        "message": tool_status_error_message(result),
                                    }
                                )
                            
                            # print(f"Tool {name} returned: {result}")
                            tool_result_blocks.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.get("id"),
                                    "content": [
                                        {"type": "text", "text": json.dumps(result)}
                                    ],
                                }
                            )
                        except Exception as e:
                            # Catch any unexpected exceptions that weren't handled by wrap_tool_execution
                            log_error_to_terminal(
                                error=e,
                                context=f"Unexpected error in tool call: {name}",
                                tool_name=name,
                                args=args,
                                user_id=token
                            )
                            user_message = get_user_friendly_error_message(e, "tool_execution")
                            chat_id = str(uuid.uuid4())
                            
                            if ENABLE_CHAT_LOGS:
                                logger.info("🆔 Chat ID: %s", chat_id)
                            
                            return jsonify(
                                {
                                    "chat_id": chat_id,
                                    "success": False,
                                    "type": "error",
                                    "data": {},
                                    "ui_hint": "chat",
                                    "message": f"❌ {user_message}",
                                }
                            )

                    messages.append({"role": "assistant", "content": content})                    
                    messages.append({"role": "user", "content": tool_result_blocks})

                    # Save tool interaction to short-term memory — store readable strings and correct role
                    conversation_history.append({
                        "role": "assistant",
                        "content": json.dumps(content) if not isinstance(content, str) else content
                    })

                    conversation_history.append({
                        "role": "user",
                        "content": json.dumps(result) if not isinstance(result, str) else result
                    })



                    body["messages"] = messages
                    step_count += 1
                    continue

                # ------------------------------
                # Final assistant response
                # ------------------------------
                text_blocks = [
                    b.get("text", "").strip()
                    for b in content
                    if b.get("type") == "text" and isinstance(b.get("text"), str)
                ]
                final_text = "\n\n".join([t for t in text_blocks if t])
                
                # Log response: OpenAI streams token-by-token above, Bedrock already printed in invoke_bedrock
                # For OpenAI: Already streamed token by token above, so skip print here
                # For Bedrock: Already printed in invoke_bedrock() function
                # import logging
                # logging.info(final_text)
                import re

                def _extract_and_parse_json(text):
                    # 1) Try direct parse
                    try:
                        return json.loads(text)
                    except Exception:
                        pass

                    # 2) Extract first JSON-like block (object or array) and try parsing
                    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
                    if not m:
                        return None
                    candidate = m.group(1).strip()
                    try:
                        return json.loads(candidate)
                    except Exception:
                        # 3) Try simple cleanup: remove trailing commas before } or ]
                        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
                        try:
                            return json.loads(cleaned)
                        except Exception:
                            return None

                parsed_json = _extract_and_parse_json(final_text)
                if parsed_json is not None:
                    # Check if parsed_json is a dict, not a list
                    if not isinstance(parsed_json, dict):
                        # If it's a list or other type, treat as invalid JSON structure
                        logger.warning(f"Parsed JSON is not a dict (type: {type(parsed_json)}), treating as raw text")
                        parsed_json = None
                    
                    if parsed_json is not None:
                        # Preserve any message the assistant provided. Only auto-add a summary
                        # when the assistant did not include a message and the response type
                        # is a search/result that returns a list in `data`.
                        data = parsed_json.get("data")
                        existing_message = parsed_json.get("message")
                        resp_type = (parsed_json.get("type") or "").lower()
                        search_types = {
                            "emails",
                            "search_results",
                            "sheets",
                            "documents",
                            "events",
                            "calendar_event",
                            "messages",
                            "notion",
                            "docs",
                        }

                        if (
                            not existing_message
                            and isinstance(data, list)
                            and resp_type in search_types
                        ):
                            parsed_json["message"] = (
                                f"I found {len(data)} items matching your query."
                            )

                        # Normalize ui_hint to an array; merge accumulated hints and assistant-provided hints
                        try:
                            provided_ui = parsed_json.get("ui_hint")
                            merged_hints = []
                            if isinstance(provided_ui, list):
                                merged_hints.extend(
                                    [h for h in provided_ui if isinstance(h, str)]
                                )
                                logger.debug(f"Merged {len(merged_hints)} assistant-provided UI hints from list")
                            elif isinstance(provided_ui, str) and provided_ui:
                                merged_hints.append(provided_ui)
                                logger.debug(f"Merged 1 assistant-provided UI hint from string")
                            # Append accumulated hints
                            added_count = 0
                            for h in ui_hints_accumulated:
                                if h not in merged_hints:
                                    merged_hints.append(h)
                                    added_count += 1
                            if added_count > 0:
                                logger.debug(f"Added {added_count} accumulated UI hint(s) to merged list (total: {len(merged_hints)})")
                            # Fallback to chat if none present
                            if not merged_hints:
                                merged_hints = ["chat"]
                                logger.debug("No UI hints found, using fallback 'chat'")

                            if isinstance(data, dict):
                                merged_hints = _filter_ui_hints_by_data_payload(
                                    merged_hints, data
                                )

                            parsed_json["ui_hint"] = merged_hints
                            logger.debug(f"Final filtered UI hints: {merged_hints}")
                            
                            # Check if data node has presentable records; if not, clear ui_hint.
                            if isinstance(data, dict):
                                def _has_presentable_items_for_clear_check(value):
                                    if not isinstance(value, list) or not value:
                                        return False
                                    for item in value:
                                        if isinstance(item, dict):
                                            if "id" in item:
                                                raw_id = item.get("id")
                                                if isinstance(raw_id, str) and raw_id.strip():
                                                    return True
                                                if raw_id is not None and not isinstance(raw_id, str):
                                                    return True
                                            else:
                                                for v in item.values():
                                                    if isinstance(v, str) and v.strip():
                                                        return True
                                                    if isinstance(v, (list, dict)) and len(v) > 0:
                                                        return True
                                                    if v not in (None, "", [], {}):
                                                        return True
                                        elif isinstance(item, str):
                                            if item.strip():
                                                return True
                                        elif item not in (None, "", [], {}):
                                            return True
                                    return False

                                has_any_data = any(
                                    _has_presentable_items_for_clear_check(v)
                                    for v in data.values()
                                    if isinstance(v, list)
                                )
                                if not has_any_data:
                                    parsed_json["ui_hint"] = []
                                    logger.debug("Data node has no presentable IDs/items, cleared ui_hint")
                        except Exception as e:
                            # Ensure ui_hint exists as array even on error
                            logger.warning(f"Error merging UI hints: {e}, using accumulated hints or fallback", exc_info=True)
                            parsed_json["ui_hint"] = ui_hints_accumulated or ["chat"]

                        conversation_history.append(
                            {"role": "user", "content": combined_query}
                        )
                                      
                        conversation_history.append(
                            {"role": "assistant", "content": json.dumps(parsed_json)}
                        )

                        # Use the chat_id generated at the start of the request

                        # Save chat history to MongoDB
                        try:
                            response_text = parsed_json.get("message", "") or json.dumps(parsed_json.get("data", {}))
                            session_id = None
                            try:
                                request_data = request.get_json(force=True) if request.is_json else {}
                                session_id = request_data.get("session_id")
                            except:
                                pass
                            metadata = {
                                "type": parsed_json.get("type", ""),
                                "ui_hint": parsed_json.get("ui_hint", []),
                                "success": parsed_json.get("success", False)
                            }
                            save_chat_history(
                                token=token,
                                query=user_query,
                                response=response_text,
                                raw_response=final_text,  # Raw unfiltered AI response
                                session_id=session_id,
                                metadata=metadata,
                                chat_id=chat_id
                            )
                        except Exception as e:
                            logger.error(f"Failed to save chat history: {e}")

                        # Calculate total response time (kept in code, not stored in MongoDB)
                        total_response_time = time.time() - request_start_time
                        from clients.mongo_token_usage_client import upsert_ai_usage
                        
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
                                purpose="cosilive",
                                model=accumulated_token_usage["model"],
                                input_tokens=accumulated_token_usage["input_tokens"],
                                output_tokens=accumulated_token_usage["output_tokens"],
                                system_prompt_tokens=accumulated_token_usage["system_prompt_tokens"],
                                total_tokens=total_tokens,
                                ip_address=ip_address,
                                total_api_calls=api_call_counter,
                            )
                        
                        # Log final token usage summary if enabled
                        if ENABLE_TOKEN_USAGE_LOGGING and accumulated_token_usage["model"]:
                            total_tokens = (
                                accumulated_token_usage["input_tokens"]
                                + accumulated_token_usage["output_tokens"]
                                + accumulated_token_usage["system_prompt_tokens"]
                            )
                            logger.info(
                                "Token usage | purpose=%s input=%s output=%s system_prompt=%s total=%s model=%s response_time_s=%s api_calls=%s",
                                "cosilive",
                                accumulated_token_usage["input_tokens"],
                                accumulated_token_usage["output_tokens"],
                                accumulated_token_usage["system_prompt_tokens"],
                                total_tokens,
                                accumulated_token_usage["model"],
                                round(total_response_time, 3),
                                api_call_counter,
                            )

                        # Add chat_id as the first field in the response
                        # Contract enforcement: never return attachment objects inside `data.emails[]`.
                        # Attachments are summarized in `message` only.
                        try:
                            data_node = parsed_json.get("data")
                            if isinstance(data_node, dict) and isinstance(data_node.get("emails"), list):
                                for email_obj in data_node["emails"]:
                                    if isinstance(email_obj, dict) and "attachments" in email_obj:
                                        email_obj.pop("attachments", None)
                                    if isinstance(email_obj, dict) and "body_preview" in email_obj:
                                        email_obj["body_preview"] = (
                                            _strip_body_preview_attachment_extras(
                                                email_obj.get("body_preview", "")
                                            )
                                        )
                        except Exception:
                            pass
                        response_with_chat_id = {"chat_id": chat_id}
                        response_with_chat_id.update(parsed_json)
                        if ENABLE_CHAT_LOGS:
                            # Log final response that is being returned to the client
                            logger.info("Final response %s", response_with_chat_id)
                        return jsonify(response_with_chat_id)
                else:
                    logger.warning("Error parsing JSON, returning raw text")
                    # Use the chat_id generated at the start of the request
                    
                    # Save chat history for raw text response too
                    try:
                        session_id = None
                        try:
                            request_data = request.get_json(force=True) if request.is_json else {}
                            session_id = request_data.get("session_id")
                        except:
                            pass
                        save_chat_history(
                            token=token,
                            query=user_query,
                            response=final_text,
                            raw_response=final_text,  # Raw unfiltered AI response (same as response in this case)
                            session_id=session_id,
                            metadata={"type": "message", "ui_hint": ui_hints_accumulated or ["chat"]},
                            chat_id=chat_id
                        )
                    except Exception as e:
                        logger.error(f"Failed to save chat history: {e}")
                    
                    # Calculate total response time (kept in code, not stored in MongoDB)
                    total_response_time = time.time() - request_start_time
                    from clients.mongo_token_usage_client import upsert_ai_usage
                    
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
                            purpose="cosilive",
                            model=accumulated_token_usage["model"],
                            input_tokens=accumulated_token_usage["input_tokens"],
                            output_tokens=accumulated_token_usage["output_tokens"],
                            system_prompt_tokens=accumulated_token_usage["system_prompt_tokens"],
                            total_tokens=total_tokens,
                            ip_address=ip_address,
                            total_api_calls=api_call_counter,
                        )
                    
                    # Log final token usage summary if enabled
                    if ENABLE_TOKEN_USAGE_LOGGING and accumulated_token_usage["model"]:
                        total_tokens = (
                            accumulated_token_usage["input_tokens"] +
                            accumulated_token_usage["output_tokens"] +
                            accumulated_token_usage["system_prompt_tokens"]
                        )
                        logger.info(
                            "Token usage | purpose=%s input=%s output=%s system_prompt=%s total=%s model=%s response_time_s=%s api_calls=%s",
                            "cosilive",
                            accumulated_token_usage["input_tokens"],
                            accumulated_token_usage["output_tokens"],
                            accumulated_token_usage["system_prompt_tokens"],
                            total_tokens,
                            accumulated_token_usage["model"],
                            round(total_response_time, 3),
                            api_call_counter,
                        )

                    # Add chat_id as the first field in the response
                    response_data = {
                        "chat_id": chat_id,
                        "success": True,
                        "type": "message",
                        "data": {"text": final_text},
                        "ui_hint": ui_hints_accumulated or ["chat"],
                        "message": final_text,
                    }
                    if ENABLE_CHAT_LOGS:
                        # Log final response that is being returned to the client
                        logger.info("Final response %s", response_data)
                    return jsonify(response_data)

                # else:
                #     return jsonify({
                #         "success": False,
                #         "type": "error",
                #         "data": {},
                #         "ui_hint": "chat",
                #         "message": "⚠️ No valid response from assistant."
                #     }), 500

            chat_id = str(uuid.uuid4())
            if ENABLE_CHAT_LOGS:
                logger.info("🆔 Chat ID: %s", chat_id)
            return jsonify(
                {
                    "chat_id": chat_id,
                    "success": False,
                    "type": "error",
                    "data": {},
                    "ui_hint": "chat",
                    "message": "⚠️ Too many tool calls in a row.",
                }
            )

        except Exception as e:
            error_str = str(e).lower()
            # Check if it's a quota/rate limit error (429) - for both OpenAI and Bedrock
            is_quota_error = (
                isinstance(e, RateLimitError) or 
                isinstance(e, APIError) and ("429" in error_str or "quota" in error_str or "insufficient_quota" in error_str) or
                "429" in error_str or "quota" in error_str or "insufficient_quota" in error_str or
                "too many requests" in error_str or
                "OPENAI_QUOTA_EXCEEDED" in str(e)
            )
            
            # Check if it's a Bedrock rate limit error
            is_bedrock_rate_limit = (
                "bedrock" in error_str and ("429" in error_str or "too many requests" in error_str)
            )
            
            if is_quota_error or is_bedrock_rate_limit:
                # For OpenAI: Set the fallback flag to fallback mode (1) to use Bedrock
                if not is_bedrock_rate_limit:
                    if switches.USE_BEDROCK_FALLBACK == 0:
                        logger.warning(
                            "⚠️ OpenAI quota exceeded detected in error handler, but OpenAI-only mode is enabled; not switching to Bedrock."
                        )
                    else:
                        # In fallback mode (1), keep Bedrock enabled after quota errors.
                        if switches.USE_BEDROCK_FALLBACK != 2:
                            switches.USE_BEDROCK_FALLBACK = 1
                        logger.warning(
                            "⚠️ OpenAI quota exceeded detected in error handler. Switching to Bedrock fallback mode (1)."
                        )
                else:
                    # For Bedrock: Already using Bedrock, so both APIs are rate limited
                    logger.warning("⚠️ Bedrock rate limit (429) detected. Both OpenAI and Bedrock are rate limited.")
                
                # Return user-friendly error message
                chat_id = str(uuid.uuid4())
                if ENABLE_CHAT_LOGS:
                    logger.info("🆔 Chat ID: %s", chat_id)
                return jsonify({
                    "chat_id": chat_id,
                    "data": {},
                    "message": "❌ We're experiencing high demand right now. Please wait 30-60 seconds and try again.",
                    "success": False,
                    "type": "error",
                    "ui_hint": "chat"
                })
            
            retries += 1
            # Log full error details to terminal
            log_error_to_terminal(
                error=e,
                context=f"OpenAI API invocation attempt {retries}/{max_retries} failed",
                user_id=token
            )
            if retries >= max_retries:
                # Return user-friendly error message
                error_response = handle_api_error(
                    error=e,
                    api_name="OpenAI",
                    context=f"Failed after {max_retries} retries",
                    user_id=token
                )
                # Add chat_id to error response
                chat_id = str(uuid.uuid4())
                error_response["chat_id"] = chat_id
                if ENABLE_CHAT_LOGS:
                    logger.info("🆔 Chat ID: %s", chat_id)
                return jsonify(error_response)
            time.sleep(0.2)
