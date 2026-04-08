import os
import json
import time
import hmac
import hashlib
import boto3
from datetime import datetime, timedelta
from dateutil import parser
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
# Removed: from botocore.awsrequest import AWSRequest
# Removed: from botocore.auth import SigV4Auth
# Now using bearer token authentication for Bedrock
import base64
from io import BytesIO
from PIL import Image
import fitz
from collections import defaultdict, deque
import csv
import uuid
from dotenv import load_dotenv
import logging
import re
from openai import OpenAI, RateLimitError, APIError

load_dotenv()

# === Logging Setup ===
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)

# Consolidated imports (moved to app/server_parts.py)
from app.server_parts import *  # noqa: F401,F403

from clients.db_method import unified_token_auth_check, resolve_user_id_for_workspace_access

# Static structures (function schemas) moved to app/structures.py
from app.structures import function_defs, tools as structures_tools

# AI usage tracking
from clients.mongo_token_usage_client import upsert_ai_usage
from utils.token_counter import (
    count_tokens_in_messages,
    count_tokens_in_system_prompt,
    count_tokens_openai,
    count_tokens_claude,
    estimate_image_tokens,
)


# === AWS Bedrock Setup (Legacy - not used for Bedrock auth anymore) ===
# Default model ID now lives in app.switches (BEDROCK_MODEL_ID).
# REGION = "us-east-1"
# session = boto3.session.Session()
# credentials = session.get_credentials().get_frozen_credentials()

# === Flask Setup ===
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# === Session Tracking ===
openai_session_id = str(uuid.uuid4())

# Import control switches module (for dynamic modification support)
import app.switches as switches
from app.switches import (
    ENABLE_TOKEN_USAGE_LOGGING,
    ENABLE_CHAT_LOGS,
    ENABLE_IMAGE_ANALYSIS,
    ENABLE_PDF_ANALYSIS,
)
# Import USE_BEDROCK_FALLBACK from module for dynamic modification
USE_BEDROCK_FALLBACK = switches.USE_BEDROCK_FALLBACK

# === AWS Bedrock Setup ===
# Env BEDROCK_MODEL_ID wins; otherwise use switches (Claude Sonnet 4.5 on Bedrock).
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID") or switches.BEDROCK_MODEL_ID
REGION = os.getenv("AWS_REGION", "us-east-1")

# Bearer token for Bedrock authentication (replaces IAM credentials)
AWS_BEARER_TOKEN_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")

# Legacy boto3 session (not used for Bedrock auth anymore, but kept for potential other AWS services)
# session = boto3.session.Session()
# credentials = session.get_credentials().get_frozen_credentials()

# === OpenAI Setup ===
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# if not os.path.exists(SESSION_FILE):
#     with open(SESSION_FILE, mode="w", newline="") as file:
#         writer = csv.writer(file)
#         writer.writerow(["session_id", "timestamp", "query"])

# === Setup user-specific conversation memory ===
user_conversations = defaultdict(lambda: deque(maxlen=12))
long_term_memory = defaultdict(list)

def summarize_conversation(messages, token=None):
    """
    Summarize the deque conversation using the same LLM (Bedrock).
    Returns parsed JSON with preserved 'data' and concise 'message'.
    
    Args:
        messages: Conversation messages to summarize
        token: Optional user token for token tracking (internal use, may be None)
    """
    conversation_text = "\n".join(
        [f"{m['role']}: {m['content']}" for m in messages]
    )

    summary_prompt = f"""
You are an assistant that summarizes past chat context for continuity.

Below is a previous conversation. Summarize it concisely while following these rules:

1. Keep the `data` object EXACTLY as it is since it may contain important IDs and context.
2. Regenerate the `message` field as a short summary (1-3 lines).
3. Keep all other fields and structure (`success`, `type`, `ui_hint`, etc.) unchanged.
4. If multiple previous assistant outputs exist, merge their 'message' parts meaningfully.

Conversation to summarize:
{conversation_text}

Now, generate a concise JSON summary in this exact format:

{{
    "success": true,
    "type": "memory_summary",
    "data": <keep or merge all previous data as-is>,
    "message": "brief natural language summary of the previous discussion",
    "ui_hint": []
}}
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "temperature": 0.2,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": summary_prompt}]}
        ],
    }

    try:
        # Internal function call - token tracking optional
        response = invoke_ai_with_fallback(body, token=token, purpose="cosilive", ip_address=None)
        content = response.get("content", [])
        raw_text = content[0].get("text", "") if content else ""
        raw_text = raw_text.strip()

        # Try to parse JSON
        try:
            return json.loads(raw_text)
        except:
            import re
            m = re.search(r"\{.*\}", raw_text, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            else:
                raise ValueError("No JSON found")

    except Exception as e:
        # Log the error without breaking the request flow
        logger.error("Error during summarization: %s", str(e))
        fallback = "\n".join([f"{m['role']}: {m['content'][:100]}" for m in messages])
        return {
            "success": False,
            "type": "memory_summary",
            "message": f"Summary failed. Raw: {fallback[:300]}...",
            "data": {},
            "ui_hint": []
        }


from app.server_parts import tools
from app.structures import function_defs


# === Helper Functions ===
def add_timestamp_footer(text):
    if switches.OMIT_TOOL_GENERATED_ON_FOOTER:
        return text
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"{text}\n\n---\n> _Generated on {now}_"





def format_tool_result(tool_name, result):
    def bold(text):
        return f"**{text}**"

    def italic(text):
        return f"*{text}*"

    def section(title):
        return f"### {title}\n"

    if isinstance(result, dict) and result.get("status") == "error":
        body = tool_status_error_message(result)
        if body.startswith("❌ "):
            body = body[2:].strip()
        return add_timestamp_footer(f"> ❌ {bold('Error')}: {body}")
    if not result:
        return add_timestamp_footer("> ⚠️ No data found for this request.")

    output = f"# ✅ {tool_name.replace('_', ' ').title()} Completed\n\n"
    if isinstance(result, dict):
        output += section("📋 Summary")
        for key, value in result.items():
            if isinstance(value, list):
                continue
            output += f"- {bold(key.replace('_', ' ').title())}: {value}\n"
        for key, value in result.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                headers = value[0].keys()
                output += "\n" + section("📌 Detailed Results")
                output += "| " + " | ".join(headers) + " |\n"
                output += "| " + " | ".join([":---" for _ in headers]) + " |\n"
                for item in value:
                    row = [str(item.get(h, "")) for h in headers]
                    output += "| " + " | ".join(row) + " |\n"
        return add_timestamp_footer(output)
    if isinstance(result, list):
        if all(isinstance(item, dict) for item in result):
            headers = result[0].keys()
            output += section("📌 Results")
            output += "| " + " | ".join(headers) + " |\n"
            output += "| " + " | ".join([":---" for _ in headers]) + " |\n"
            for item in result:
                row = [str(item.get(h, "")) for h in headers]
                output += "| " + " | ".join(row) + " |\n"
        else:
            output += section("📌 Results")
            for item in result:
                output += f"- {item}\n"
        return add_timestamp_footer(output)
    output += section("ℹ️ Info")
    output += str(result)
    return add_timestamp_footer(output)


def format_email_results(emails):
    if not emails:
        return "No emails found matching your search criteria."
    output = "## 📧 Email Search Results\n\n"
    for i, email in enumerate(emails, 1):
        from_field = email.get("from", {})
        if isinstance(from_field, dict):
            from_name = from_field.get("name", "Unknown")
            from_email = from_field.get("email", "")
        else:
            from_name = str(from_field or "Unknown")
            from_email = ""
        subject = email.get("subject", "No Subject")
        date_str = email.get("date", "")
        snippet = email.get("snippet") or email.get("body") or ""
        try:
            if date_str:
                timestamp = int(str(date_str).split(".")[0]) / 1000
                date_obj = datetime.fromtimestamp(timestamp)
                formatted_date = date_obj.strftime("%B %d, %Y at %I:%M %p")
            else:
                formatted_date = "Unknown date"
        except Exception:
            formatted_date = "Unknown date"
        mid = email.get("id") or email.get("message_id", "")
        if mid:
            output += f"### **{i}.** **id:** `{mid}`\n"
        output += f"**From:** {from_name} ({from_email})\n"
        output += f"**Subject:** {subject}\n"
        output += f"**Date:** {formatted_date}\n"
        output += (
            f"**Summary:** {snippet[:200]}{'...' if len(snippet) > 200 else ''}\n"
        )
        body_txt = (email.get("body") or "").strip()
        if body_txt:
            clip = body_txt[:12000] + ("…" if len(body_txt) > 12000 else "")
            output += f"**Body:**\n```\n{clip}\n```\n"
        attachments = email.get("attachments")
        if attachments:
            output += "\n**Attachments:**\n"
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                aname = att.get("name", "file")
                atype = att.get("type", "")
                prev = att.get("extracted_text_preview")
                if prev:
                    clip = prev[:2500] + ("…" if len(prev) > 2500 else "")
                    output += f"- **{aname}** ({atype}): text preview:\n```\n{clip}\n```\n"
                else:
                    extra = att.get("note") or att.get("url") or ""
                    output += f"- **{aname}** ({atype}){': ' + extra if extra else ''}\n"
        output += "\n"
    return output


def format_calendar_results(events):
    if not events:
        return "No calendar events found matching your search criteria."
    output = "## 📅 Calendar Events\n\n"
    for i, event in enumerate(events, 1):
        summary = event.get("summary", "No Title")
        description = event.get("description", "")
        start_time = event.get("start", {}).get("dateTime", "")
        end_time = event.get("end", {}).get("dateTime", "")
        attendees = event.get("attendees", [])
        location = event.get("location", "")
        organizer = event.get("organizer", {}).get("email", "")
        try:
            if start_time:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                formatted_start = start_dt.strftime("%B %d, %Y at %I:%M %p")
            else:
                formatted_start = "No start time"
            if end_time:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                formatted_end = end_dt.strftime("%B %d, %Y at %I:%M %p")
            else:
                formatted_end = "No end time"
        except:
            formatted_start = "Invalid start time"
            formatted_end = "Invalid end time"
        output += f"### **{i}.** **Event:** {summary}\n"
        if description:
            output += f"**Description:** {description[:200]}{'...' if len(description) > 200 else ''}\n"
        output += f"**Start Time:** {formatted_start}\n"
        output += f"**End Time:** {formatted_end}\n"
        if location:
            output += f"**Location:** {location}\n"
        if organizer:
            output += f"**Organizer:** {organizer}\n"
        if attendees:
            attendee_list = [
                f"{a.get('displayName', 'Unknown')} ({a.get('email', '')})"
                for a in attendees
            ]
            output += f"**Attendees:** {', '.join(attendee_list)}\n"
        output += "\n"
    return output


def format_document_results(docs):
    if not docs:
        return "No documents found matching your search criteria."
    output = "## 📄 Document Search Results\n\n"
    for i, doc in enumerate(docs, 1):
        name = doc.get("name", "Unknown")
        mime_type = doc.get("mimeType", "")
        created_time = doc.get("createdTime", "")
        modified_time = doc.get("modifiedTime", "")
        owners = doc.get("owners", [])
        try:
            if created_time:
                created_dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                formatted_created = created_dt.strftime("%B %d, %Y at %I:%M %p")
            else:
                formatted_created = "Unknown"
            if modified_time:
                modified_dt = datetime.fromisoformat(
                    modified_time.replace("Z", "+00:00")
                )
                formatted_modified = modified_dt.strftime("%B %d, %Y at %I:%M %p")
            else:
                formatted_modified = "Unknown"
        except:
            formatted_created = "Invalid date"
            formatted_modified = "Invalid date"
        output += f"### **{i}.** **Document:** {name}\n"
        output += f"**Type:** {mime_type}\n"
        output += f"**Created:** {formatted_created}\n"
        output += f"**Modified:** {formatted_modified}\n"
        if owners:
            owner_list = [
                f"{o.get('displayName', 'Unknown')} ({o.get('emailAddress', '')})"
                for o in owners
            ]
            output += f"**Owners:** {', '.join(owner_list)}\n"
        output += "\n"
    return output


def format_tool_response(tool_name, result):
    if tool_name in ["search_emails", "query_emails", "get_emails", "search_sent_emails"]:
        if isinstance(result, list):
            return format_email_results(result)
        if isinstance(result, dict) and "emails" in result:
            return format_email_results(result["emails"])
        if isinstance(result, dict) and isinstance(result.get("data"), dict) and "emails" in result["data"]:
            return format_email_results(result["data"]["emails"])
        if isinstance(result, dict) and "messages" in result:
            # mongo_query_emails / mongo_search_emails use "messages"
            return format_email_results(result["messages"])
        return format_tool_result(tool_name, result)
    elif tool_name in ["search_calendar_events", "query_events", "get_events"]:
        if isinstance(result, list):
            return format_calendar_results(result)
        elif isinstance(result, dict) and "events" in result:
            return format_calendar_results(result["events"])
        else:
            return format_tool_result(tool_name, result)
    elif tool_name in [
        "query_docs",
        "search_docs_by_date",
        "list_docs",
    ]:
        if isinstance(result, list):
            return format_document_results(result)
        elif isinstance(result, dict) and "documents" in result:
            return format_document_results(result["documents"])
        else:
            return format_tool_result(tool_name, result)
    else:
        return format_tool_result(tool_name, result)


def get_token():
    token = request.headers.get("Authorization")
    if not token:
        return None, jsonify({"error": "Missing Authorization token"}), 401

    # Support common auth header formats, e.g., "Bearer <token>"
    # Also tolerate extra whitespace
    raw = token.strip()
    parts = raw.split()
    if len(parts) >= 2 and parts[0].lower() in ("bearer", "token", "basic"):
        raw = " ".join(parts[1:]).strip()

    # Avoid returning empty after stripping
    if not raw:
        return None, jsonify({"error": "Invalid Authorization header"}), 400

    auth_err, auth_code = unified_token_auth_check(raw)
    if auth_err is not None:
        return None, auth_err, auth_code

    # Optional: minimal debug without leaking token
    try:
        logger.debug("Parsed Authorization token len=%s", len(raw))
    except Exception:
        pass

    return raw, None, None


def get_autopilot_token():
    """
    Authentication for /autoPilot and /autoPilot/execute.

    If AUTOPILOT_SECRET_KEY is set:
      - Requires X-Signature and X-Timestamp (HMAC-SHA256 over the timestamp string bytes).
      - The credential in MCP_CHAT_API_AUTH_HEADER (default: Authorization) must be a
        workspace user_id or a unified token; the user must exist (live=1).
      - Returns a string workspace key (str(user_id)) suitable for tool + Mongo lookups.

    If AUTOPILOT_SECRET_KEY is unset:
      - Prefer unified Bearer token (same as get_token()).
      - If that fails and AUTOPILOT_ALLOW_USER_ID_AUTH is true (default: true), accept a bare
        workspace user_id (e.g. Authorization: 1100) when that user exists (live=1).
        Set AUTOPILOT_ALLOW_USER_ID_AUTH=false in production if you rely only on unified tokens.
    """
    secret = (os.getenv("AUTOPILOT_SECRET_KEY") or "").strip()
    auth_header_name = (os.getenv("MCP_CHAT_API_AUTH_HEADER") or "Authorization").strip()

    raw_header = request.headers.get(auth_header_name) or request.headers.get("Authorization")
    if not raw_header:
        return None, jsonify({"error": "Missing Authorization token"}), 401

    raw = raw_header.strip()
    parts = raw.split()
    if len(parts) >= 2 and parts[0].lower() in ("bearer", "token", "basic"):
        raw = " ".join(parts[1:]).strip()

    if not raw:
        return None, jsonify({"error": "Invalid Authorization header"}), 400

    if secret:
        ts_header = request.headers.get("X-Timestamp") or request.headers.get("x-timestamp")
        sig_header = request.headers.get("X-Signature") or request.headers.get("x-signature")
        if not ts_header or not sig_header:
            return None, jsonify({"error": "Missing HMAC headers"}), 401
        try:
            ts_int = int(str(ts_header).strip())
        except ValueError:
            return None, jsonify({"error": "Invalid X-Timestamp"}), 400
        try:
            skew = int(os.getenv("AUTOPILOT_HMAC_MAX_SKEW_SEC", "300"))
        except ValueError:
            skew = 300
        now = int(time.time())
        if abs(now - ts_int) > skew:
            return None, jsonify({"error": "Timestamp outside allowed window"}), 401
        ts_bytes = str(ts_header).strip().encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), ts_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.lower(), str(sig_header).strip().lower()):
            return None, jsonify({"error": "Invalid HMAC signature"}), 401

        uid = resolve_user_id_for_workspace_access(raw)
        if uid is None:
            return None, jsonify({"error": "User not found for credential"}), 404
        try:
            logger.debug("Autopilot HMAC auth ok, workspace user_id=%s", uid)
        except Exception:
            pass
        return str(uid), None, None

    auth_err, auth_code = unified_token_auth_check(raw)
    if auth_err is None:
        try:
            logger.debug("Autopilot unified token auth ok, len=%s", len(raw))
        except Exception:
            pass
        return raw, None, None

    allow_bare_uid = (os.getenv("AUTOPILOT_ALLOW_USER_ID_AUTH", "true") or "").lower() in (
        "1",
        "true",
        "yes",
    )
    if allow_bare_uid:
        uid = resolve_user_id_for_workspace_access(raw)
        if uid is not None:
            logger.info(
                "Autopilot auth: bare workspace user_id accepted (AUTOPILOT_ALLOW_USER_ID_AUTH)"
            )
            return str(uid), None, None
        if raw.isdigit():
            return None, jsonify({"error": "User not found for workspace user_id"}), 404

    return None, auth_err, auth_code


def _resolve_bedrock_model_id(model_id=None):
    """Explicit model_id, else env BEDROCK_MODEL_ID, else switches.BEDROCK_MODEL_ID."""
    if model_id:
        return model_id
    env_id = os.getenv("BEDROCK_MODEL_ID")
    if env_id:
        return env_id
    return switches.BEDROCK_MODEL_ID


def invoke_bedrock(
    body,
    max_retries=3,
    initial_backoff=1.0,
    token=None,
    purpose="cosilive",
    ip_address=None,
    start_time=None,
    model_id=None,
):
    """
    Invoke Bedrock API with exponential backoff retry for rate limiting (429 errors).

    Args:
        body: Request body for Bedrock
        max_retries: Maximum number of retry attempts (default: 3)
        initial_backoff: Initial backoff delay in seconds (default: 1.0)
        token: User authentication token (for token usage tracking)
        purpose: Purpose of the API call (briefing/cosilive/autopilot/embedding)
        ip_address: User's IP address (for token usage tracking)
        model_id: Optional Bedrock model ID; defaults to env or switches.BEDROCK_MODEL_ID

    Returns:
        Bedrock API response

    Raises:
        requests.exceptions.HTTPError: If all retries fail or non-429 error occurs
    """
    resolved_model_id = _resolve_bedrock_model_id(model_id)
    # Calculate input tokens (user messages + images, excluding system prompt)
    system_prompt = body.get("system", "")
    br_messages = body.get("messages", [])
    input_tokens = count_tokens_in_messages(br_messages, model_type="claude")
    system_prompt_tokens = count_tokens_in_system_prompt(system_prompt, model_type="claude")
    url = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{resolved_model_id}/invoke"
    
    # Use bearer token authentication instead of SigV4Auth
    if not AWS_BEARER_TOKEN_BEDROCK:
        raise ValueError("AWS_BEARER_TOKEN_BEDROCK environment variable is not set. Please configure the Bedrock bearer token.")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AWS_BEARER_TOKEN_BEDROCK}"
    }
    logger.info(
        "Bedrock request prepared (messages=%d, tools=%d)",
        len(body.get("messages", [])),
        len(body.get("tools", [])),
    )
    
    last_exception = None
    backoff = initial_backoff
    
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            if attempt > 0:
                logger.warning(
                    f"🔄 Bedrock retry attempt {attempt}/{max_retries} after {backoff:.1f}s backoff"
                )
                time.sleep(backoff)
                # Exponential backoff: 1s, 2s, 4s, 8s...
                backoff = min(backoff * 2, 30.0)  # Cap at 30 seconds
            
            logger.info("HTTP Request: POST %s", url)
            response = requests.post(
                url, headers=headers, data=json.dumps(body)
            )
            
            # Check for 429 rate limit error
            if response.status_code == 429:
                if attempt < max_retries:
                    logger.warning(
                        f"⚠️ Bedrock rate limit (429) on attempt {attempt + 1}/{max_retries + 1}. "
                        f"Retrying after {backoff:.1f}s..."
                    )
                    last_exception = requests.exceptions.HTTPError(
                        f"429 Client Error: Too Many Requests for url: {url}"
                    )
                    continue  # Retry
                else:
                    # Final attempt failed
                    logger.error(
                        f"❌ Bedrock rate limit (429) after {max_retries + 1} attempts. Giving up."
                    )
                    response.raise_for_status()
            
            # For non-429 errors, check for authentication issues
            if response.status_code == 403:
                error_msg = response.text
                logger.error(f"❌ Bedrock authentication failed (403). Error: {error_msg}")
                logger.error("💡 Check that AWS_BEARER_TOKEN_BEDROCK environment variable is set and valid.")
                response.raise_for_status()
            
            # For other non-429 errors, raise immediately
            response.raise_for_status()
            
            # Success
            result = response.json()
            logger.info(
                "Bedrock response received (stop_reason=%s)", result.get("stop_reason")
            )
            
            # Print Bedrock response to terminal (similar to OpenAI streaming)
            content = result.get("content", [])
            output_text = ""
            if content:
                logger.debug("Bedrock response stream starting")
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        output_text += text
                        pass  # Stream goes to client via response
            
            # Calculate output tokens from response
            output_tokens = count_tokens_claude(output_text)
            # Add tokens for tool_use blocks if present
            for block in content:
                if block.get("type") == "tool_use":
                    # Estimate tokens for tool use (name + input)
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    output_tokens += count_tokens_claude(tool_name + str(tool_input))
            
            total_tokens = input_tokens + system_prompt_tokens + output_tokens
            
            # Attach token usage info to result instead of storing immediately
            # Token usage will be accumulated and stored once at the end
            model_name = resolved_model_id
            result["_token_usage"] = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "system_prompt_tokens": system_prompt_tokens,
                "total_tokens": total_tokens,
                "model": model_name,
            }
            
            return result
            
        except requests.exceptions.HTTPError as e:
            # Non-429 HTTP errors: raise immediately (don't retry)
            if response.status_code != 429:
                logger.error("Bedrock HTTP error: %s", str(e))
                logger.error("Response text: %s", response.text)
                raise
            # 429 errors are handled above in the if block
            last_exception = e
            if attempt >= max_retries:
                logger.error("Bedrock HTTP error: %s", str(e))
                logger.error("Response text: %s", response.text)
                raise
        except Exception as e:
            # Other exceptions: don't retry
            logger.error("Bedrock invocation failed: %s", str(e))
            raise
    
    # Should never reach here, but just in case
    if last_exception:
        raise last_exception
    raise Exception("Bedrock invocation failed after retries")


def invoke_bedrock_sonnet_45(
    body,
    max_retries=3,
    initial_backoff=1.0,
    token=None,
    purpose="cosilive",
    ip_address=None,
    start_time=None,
):
    """
    Invoke Bedrock using Claude Sonnet 4.5 (anthropic.claude-sonnet-4-5-20250929-v1:0).
    Same as invoke_bedrock but pins switches.BEDROCK_MODEL_ID_SONNET_45 regardless of other defaults.
    """
    return invoke_bedrock(
        body,
        max_retries=max_retries,
        initial_backoff=initial_backoff,
        token=token,
        purpose=purpose,
        ip_address=ip_address,
        start_time=start_time,
        model_id=switches.BEDROCK_MODEL_ID_SONNET_45,
    )


def invoke_ai_with_fallback(body, token=None, purpose="cosilive", ip_address=None, start_time=None):
    """
    Wrapper function that routes between OpenAI and Bedrock based on USE_BEDROCK_FALLBACK mode.
    
    Modes:
        - 0: OpenAI only (no fallback, errors will be raised)
        - 1: Fallback mode (try OpenAI first, automatically fallback to Bedrock on 429/quota errors)
        - 2: Bedrock only (force Bedrock, never use OpenAI)
    
    Args:
        body: Request body
        token: User authentication token (for token usage tracking)
        purpose: Purpose of the API call (briefing/cosilive/autopilot/embedding)
        ip_address: User's IP address (for token usage tracking)
        start_time: Request start time for tracking (optional)
    """
    bedrock_mode = switches.USE_BEDROCK_FALLBACK
    
    # Mode 2: Bedrock only - never use OpenAI
    if bedrock_mode == 2:
        if ENABLE_CHAT_LOGS:
            logger.info("🔄 Using Bedrock only (mode 2)")
        return invoke_bedrock(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
    
    # Mode 0: OpenAI only - no fallback, raise errors
    if bedrock_mode == 0:
        if ENABLE_CHAT_LOGS:
            logger.info("🔄 Using OpenAI only (mode 0, no fallback)")
        return invoke_openai(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
    
    # Mode 1: Fallback mode - try OpenAI first, fallback to Bedrock on errors
    # This is the default behavior
    try:
        return invoke_openai(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
    except (RateLimitError, APIError) as e:
        error_str = str(e).lower()
        if "429" in error_str or "quota" in error_str or "insufficient_quota" in error_str:
            # Set the flag to fallback mode (1) and retry with Bedrock
            switches.USE_BEDROCK_FALLBACK = 1
            logger.warning("⚠️ OpenAI quota exceeded (RateLimitError/APIError). Automatically switching to Bedrock fallback.")
            logger.info("Invoking Bedrock API...")
            return invoke_bedrock(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
        # Re-raise other API errors
        raise
    except Exception as e:
        error_str = str(e)
        if "OPENAI_QUOTA_EXCEEDED" in error_str:
            # Set the flag to fallback mode (1) and retry with Bedrock
            switches.USE_BEDROCK_FALLBACK = 1
            logger.warning("⚠️ OpenAI quota exceeded. Automatically switching to Bedrock fallback.")
            logger.info("Invoking Bedrock API...")
            return invoke_bedrock(body, token=token, purpose=purpose, ip_address=ip_address, start_time=start_time)
        # Re-raise other exceptions
        raise


def invoke_openai_autopilot(
    body,
    max_retries=3,
    initial_backoff=1.0,
    token=None,
    purpose="autopilot",
    ip_address=None,
    start_time=None,
):
    """
    Autopilot-focused OpenAI invoker with Bedrock-like retry behavior.

    This mirrors `invoke_bedrock` orchestration style:
      - same high-level signature (body/retries/token/purpose/ip/start_time)
      - exponential backoff for retryable errors
      - provider-call level logging
      - returns Bedrock-shaped response through `invoke_openai`
    """
    logger.info(
        "OpenAI autopilot request prepared (messages=%d, tools=%d)",
        len(body.get("messages", [])),
        len(body.get("tools", [])),
    )

    backoff = initial_backoff
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(
                    "🔄 OpenAI autopilot retry attempt %d/%d after %.1fs backoff",
                    attempt,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

            return invoke_openai(
                body,
                token=token,
                purpose=purpose,
                ip_address=ip_address,
                start_time=start_time,
            )
        except (RateLimitError, APIError) as e:
            last_exception = e
            error_str = str(e).lower()
            # Retry only for throttle/transient failures.
            retryable = any(
                key in error_str
                for key in (
                    "429",
                    "rate limit",
                    "too many requests",
                    "timeout",
                    "temporarily unavailable",
                    "overloaded",
                    "500",
                    "502",
                    "503",
                    "504",
                )
            )
            if retryable and attempt < max_retries:
                continue
            raise
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()
            retryable = any(
                key in error_str
                for key in ("429", "rate limit", "timeout", "temporarily unavailable")
            )
            if retryable and attempt < max_retries:
                continue
            raise

    if last_exception:
        raise last_exception
    raise Exception("OpenAI autopilot invocation failed after retries")


def invoke_openai(body, token=None, purpose="cosilive", ip_address=None, start_time=None):
    """
    Accepts a Bedrock-style body and calls OpenAI Chat Completions.
    Translates the request and response so upper layers remain unchanged.

    Expected Bedrock-style body keys used here:
      - system: str
      - messages: list of {role, content: [ {type: 'text'|'tool_use'|'tool_result', ...} ]}
      - tools: list of {name, description, input_schema}
      - temperature, max_tokens

    Args:
        body: Request body
        token: User authentication token (for token usage tracking)
        purpose: Purpose of the API call (briefing/cosilive/autopilot/embedding)
        ip_address: User's IP address (for token usage tracking)

    Returns a dict shaped like a Bedrock response:
      { 'content': [ blocks... ], 'stop_reason': 'tool_use'|'end_turn' }
    """
    try:
        system_prompt = body.get("system", "")
        br_messages = body.get("messages", [])
        br_tools = body.get("tools") or []
        temperature = body.get("temperature", 0.3)
        max_tokens = body.get("max_tokens", 1024)
        
        # Calculate input tokens (user messages + images, excluding system prompt)
        input_tokens = count_tokens_in_messages(br_messages, model_type="openai")
        
        # Calculate system prompt tokens separately
        system_prompt_tokens = count_tokens_in_system_prompt(system_prompt, model_type="openai")

        # Build OpenAI messages
        oa_messages = []
        if system_prompt:
            oa_messages.append({"role": "system", "content": system_prompt})

        for m in br_messages:
            role = m.get("role", "user")
            content = m.get("content")
            if isinstance(content, list):
                # Check if there are images in the content
                has_images = any(c.get("type") == "image" for c in content)
                
                if has_images:
                    # Use OpenAI's multimodal format with content array
                    content_array = []
                    for c in content:
                        ctype = c.get("type")
                        if ctype == "text":
                            content_array.append({
                                "type": "text",
                                "text": c.get("text", "")
                            })
                        elif ctype == "image":
                            # Convert Bedrock/Claude image format to OpenAI format
                            source = c.get("source", {})
                            if source.get("type") == "base64":
                                image_url = f"data:{source.get('media_type', 'image/jpeg')};base64,{source.get('data', '')}"
                                content_array.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": image_url
                                    }
                                })
                        elif ctype == "tool_result":
                            # Encode tool results in-text for history fidelity
                            try:
                                tr_text = json.dumps(c.get("content", ""))
                            except Exception:
                                tr_text = str(c.get("content", ""))
                            content_array.append({
                                "type": "text",
                                "text": f"[TOOL_RESULT] {tr_text}"
                            })
                        elif ctype == "tool_use":
                            # Encode prior tool_use as text context
                            name = c.get("name")
                            args = c.get("input", {})
                            content_array.append({
                                "type": "text",
                                "text": f"[TOOL_USE name={name} args={json.dumps(args)}]"
                            })
                    oa_messages.append({"role": role, "content": content_array})
                else:
                    # No images, use simple text format
                    parts = []
                    for c in content:
                        ctype = c.get("type")
                        if ctype == "text":
                            parts.append(c.get("text", ""))
                        elif ctype == "tool_result":
                            # Encode tool results in-text for history fidelity
                            try:
                                tr_text = json.dumps(c.get("content", ""))
                            except Exception:
                                tr_text = str(c.get("content", ""))
                            parts.append(f"[TOOL_RESULT] {tr_text}")
                        elif ctype == "tool_use":
                            # Encode prior tool_use as text context
                            name = c.get("name")
                            args = c.get("input", {})
                            parts.append(f"[TOOL_USE name={name} args={json.dumps(args)}]")
                    oa_messages.append({"role": role, "content": "\n".join([p for p in parts if p])})
            else:
                oa_messages.append({"role": role, "content": str(content)})

        # Sanitize JSON schema to comply with OpenAI (ensure arrays have items, root is object)
        def _sanitize_schema(schema):
            def _fix(node):
                if not isinstance(node, dict):
                    return {"type": "string"}
                n = dict(node)
                t = n.get("type")
                if isinstance(t, list):
                    if "object" in t:
                        t = "object"
                    elif "array" in t:
                        t = "array"
                    elif "string" in t:
                        t = "string"
                    else:
                        t = t[0] if t else "string"
                    n["type"] = t
                if t == "array":
                    items = n.get("items")
                    if not isinstance(items, dict):
                        n["items"] = {"type": "string"}
                    else:
                        n["items"] = _fix(items)
                elif t == "object":
                    props = n.get("properties")
                    if not isinstance(props, dict):
                        props = {}
                    fixed = {}
                    for pk, pv in props.items():
                        fixed[pk] = _fix(pv)
                    n["properties"] = fixed
                    req = n.get("required")
                    if isinstance(req, list):
                        n["required"] = [r for r in req if isinstance(r, str) and r in fixed]
                    else:
                        n["required"] = []
                elif t in ("string", "number", "integer", "boolean", "null"):
                    pass
                else:
                    n["type"] = "string"
                return n

            if not isinstance(schema, dict):
                return {"type": "object", "properties": {}}
            root = dict(schema)
            root["type"] = "object"
            props = root.get("properties")
            if not isinstance(props, dict):
                props = {}
            fixed_root = {}
            for k, v in props.items():
                fixed_root[k] = _fix(v)
            root["properties"] = fixed_root
            req = root.get("required")
            if isinstance(req, list):
                root["required"] = [r for r in req if isinstance(r, str) and r in fixed_root]
            else:
                root["required"] = []
            return root

        def _schema_is_valid(s):
            try:
                if not isinstance(s, dict):
                    return False
                if s.get("type") != "object":
                    return False
                if not isinstance(s.get("properties", {}), dict):
                    return False
                def _walk(n):
                    if not isinstance(n, dict):
                        return True
                    t = n.get("type")
                    if isinstance(t, list):
                        return False
                    if t == "array":
                        items = n.get("items")
                        if not isinstance(items, dict):
                            return False
                        return _walk(items)
                    if t == "object":
                        props = n.get("properties", {})
                        if not isinstance(props, dict):
                            return False
                        for vv in props.values():
                            if not _walk(vv):
                                return False
                    return True
                if not _walk(s):
                    return False
                json.dumps(s)
                return True
            except Exception:
                return False

        # Prioritize key tools so they don't get truncated
        def _tool_priority(t):
            n = (t.get("name") or "").lower()
            if n == "web_search":
                return 0  # Keep public web search if tool list is ever truncated
            if "briefing" in n:
                return 0  # Highest priority for briefing tools
            if any(k in n for k in ["email", "gmail", "mail"]):
                return 1
            if any(k in n for k in ["calendar", "event"]):
                return 2
            if any(k in n for k in ["doc", "document", "sheet", "sheets", "spreadsheet"]):
                return 3
            if any(k in n for k in ["slide", "slides"]):
                return 4
            if "slack" in n:
                return 5
            if any(k in n for k in ["trello", "task_"]):
                return 6
            if "notion" in n:
                return 7
            return 9

        br_tools_sorted = sorted(br_tools, key=_tool_priority)

        # Map tools with sanitization; include all schemas (post-sanitization)
        oa_tools = []
        for t in br_tools_sorted:
            try:
                name = t.get("name")
                if not name:
                    continue
                params = t.get("input_schema") or {"type": "object", "properties": {}}
                params = _sanitize_schema(params)
                if not _schema_is_valid(params):
                    raise ValueError("invalid schema after sanitize")
                oa_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": t.get("description", ""),
                        "parameters": params,
                    },
                })
            except Exception as tool_err:
                logger.warning("Skipping invalid tool schema for %s: %s", t.get("name"), str(tool_err))

        # OpenAI currently limits tools to max 128
        if len(oa_tools) > 128:
            logger.warning("Tools list exceeds 128 (%d). Truncating to 128 for OpenAI.", len(oa_tools))
            oa_tools = oa_tools[:128]

        model_name = os.getenv("OPENAI_MODEL", "gpt-4.1")
        
        # Build the API call parameters
        api_params = {
            "model": model_name,
            "messages": oa_messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "stream": True,
        }
        
        # Only include tools and tool_choice if tools are available
        if oa_tools:
            api_params["tools"] = oa_tools
            api_params["tool_choice"] = "auto"
        
        try:
            stream = client.chat.completions.create(**api_params)
        except RateLimitError as e:
            # OpenAI quota exceeded (429 error).
            # IMPORTANT: Do not mutate USE_BEDROCK_FALLBACK here. Provider switching
            # is handled centrally by `invoke_ai_with_fallback` based on the mode.
            if switches.USE_BEDROCK_FALLBACK == 0:
                logger.warning(
                    "⚠️ OpenAI quota exceeded (429) in OpenAI-only mode; not falling back."
                )
            else:
                logger.warning(
                    "⚠️ OpenAI quota exceeded (429 RateLimitError); fallback may occur depending on mode."
                )
            raise Exception("OPENAI_QUOTA_EXCEEDED")
        except APIError as e:
            # Check if it's a 429 quota error in the APIError
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str or "insufficient_quota" in error_str:
                # Same rule as RateLimitError: do not auto-switch mode here.
                if switches.USE_BEDROCK_FALLBACK == 0:
                    logger.warning(
                        "⚠️ OpenAI quota exceeded (429) in OpenAI-only mode; not falling back."
                    )
                else:
                    logger.warning(
                        "⚠️ OpenAI quota exceeded (429 APIError); fallback may occur depending on mode."
                    )
                raise Exception("OPENAI_QUOTA_EXCEEDED")
            raise

        # Handle streaming response - accumulate chunks
        accumulated_content = ""
        accumulated_tool_calls = []
        finish_reason = None
        usage_info = None  # Will store token usage from final chunk
        
        logger.debug("OpenAI streaming response starting")

        for chunk in stream:
            if not chunk.choices:
                continue
                
            choice = chunk.choices[0]
            delta = choice.delta
            
            # Accumulate text content
            if delta.content:
                accumulated_content += delta.content
            
            # Accumulate tool calls
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    # Initialize or update tool call
                    if tc.index >= len(accumulated_tool_calls):
                        accumulated_tool_calls.append({
                            "id": tc.id,
                            "type": tc.type,
                            "function": {"name": tc.function.name if tc.function else "", "arguments": ""}
                        })
                    
                    # Accumulate function arguments
                    if tc.function and tc.function.arguments:
                        accumulated_tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
                    
                    # Update function name if provided
                    if tc.function and tc.function.name:
                        accumulated_tool_calls[tc.index]["function"]["name"] = tc.function.name
                    
                    # Update id if provided
                    if tc.id:
                        accumulated_tool_calls[tc.index]["id"] = tc.id
            
            # Capture finish reason
            if choice.finish_reason:
                finish_reason = choice.finish_reason
        
        # OpenAI streaming doesn't provide usage in chunks, so estimate from content
        # Estimate output tokens from accumulated content and tool calls
        output_tokens_estimate = count_tokens_openai(accumulated_content)
        # Add tokens for tool calls (rough estimate: ~100 tokens per tool call including function name and args)
        for tc in accumulated_tool_calls:
            tool_name = tc.get("function", {}).get("name", "")
            tool_args = tc.get("function", {}).get("arguments", "")
            output_tokens_estimate += count_tokens_openai(tool_name + tool_args)
        
        usage_info = {
            "prompt_tokens": input_tokens + system_prompt_tokens,
            "completion_tokens": output_tokens_estimate,
            "total_tokens": input_tokens + system_prompt_tokens + output_tokens_estimate,
        }
        
        # Return token usage info instead of storing immediately
        # Token usage will be accumulated and stored once at the end
        output_tokens = usage_info.get("completion_tokens", 0)
        model_name = os.getenv("OPENAI_MODEL", "gpt-4.1")
        
        # Normalize back to Bedrock-like blocks
        content_blocks = []
        stop_reason = "end_turn"

        # Tool calls -> tool_use blocks
        if accumulated_tool_calls:
            stop_reason = "tool_use"
            if ENABLE_CHAT_LOGS:
                logger.info("🔄 Streaming response:")
            for tc in accumulated_tool_calls:
                try:
                    args = json.loads(tc["function"]["arguments"] or "{}")
                except Exception:
                    args = {}
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": args,
                })

        # Assistant text -> text block (append after tool_use if present)
        if accumulated_content:
            content_blocks.append({
                "type": "text",
                "text": accumulated_content,
            })

        # Return response with token usage info attached
        result = {"content": content_blocks, "stop_reason": stop_reason}
        if ENABLE_CHAT_LOGS:
            logger.info("OpenAI response received (stop_reason=%s)", stop_reason)
        result["_token_usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "system_prompt_tokens": system_prompt_tokens,
            "total_tokens": input_tokens + system_prompt_tokens + output_tokens,
            "model": model_name,
        }
        return result
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise


user_cache = {}

CACHE_TTL_SECONDS = 3600  # 1 hour


def get_cached_user(token):
    now = time.time()

    # 🧹 Clean up any expired entries
    expired_keys = [k for k, v in user_cache.items() if v["expires_at"] < now]
    for k in expired_keys:
        del user_cache[k]

    # ✅ Check if valid cached data exists
    cached = user_cache.get(token)
    if cached and now < cached["expires_at"]:
        return cached["data"]

    # 🔄 Fetch fresh user data
    user_data = user_info(token)
    if isinstance(user_data, tuple):  # (error_dict, status_code)
        return user_data

    # 🧠 Store in cache with TTL
    user_cache[token] = {"data": user_data, "expires_at": now + CACHE_TTL_SECONDS}
    return user_data


def get_user_personality_profile(unified_token: str) -> str:
    """
    Get user's email and Slack writing personality profiles from MongoDB using token.
    Returns formatted string for system prompt.
    """
    try:
        profile_data = get_user_personality(unified_token)

        if not profile_data:
            return ""

        personality_profile = profile_data.get("personality_profile", {})

        if not personality_profile:
            return ""

        # Build personality text sections
        personality_sections = []

        # Access email_personality nested structure
        email_personality = personality_profile.get("email_personality", {})
        
        if email_personality:
            email_text = f"""
### USER'S EMAIL WRITING STYLE
When composing, drafting, or sending emails on behalf of this user, ALWAYS match their writing style:

- **Tone**: {email_personality.get('tone', 'professional')}
- **Formality**: {email_personality.get('formality', 'medium')}
- **Greeting Style**: {email_personality.get('greeting_style', 'Standard greeting')}
- **Closing Style**: {email_personality.get('closing_style', 'Best regards')}
- **Communication Style**: {email_personality.get('communication_style', 'direct and clear')}
- **Emotional Tone**: {email_personality.get('emotional_tone', 'neutral')}

**Common Phrases to Use**: {', '.join(email_personality.get('common_phrases', []))}

**Personality Traits to Reflect**: {', '.join(email_personality.get('personality_traits', []))}

**Additional Notes**: {email_personality.get('other_notes', '')}

IMPORTANT: When drafting emails, write naturally in the user's voice. Do not mention that you're following a style guide.
"""
            personality_sections.append(email_text)

        # Access slack_personality nested structure
        slack_personality = personality_profile.get("slack_personality", {})
        
        if slack_personality:
            slack_text = f"""
### USER'S SLACK MESSAGING STYLE
When sending Slack messages on behalf of this user, ALWAYS match their messaging style:

- **Tone**: {slack_personality.get('tone', 'casual')}
- **Formality**: {slack_personality.get('formality', 'low')}
- **Greeting Style**: {slack_personality.get('greeting_style', 'Casual greeting')}
- **Response Style**: {slack_personality.get('response_style', 'Quick and concise')}
- **Communication Style**: {slack_personality.get('communication_style', 'direct and friendly')}
- **Emoji Usage**: {slack_personality.get('emoji_usage', 'moderate')}

**Common Phrases to Use**: {', '.join(slack_personality.get('common_phrases', []))}

**Personality Traits to Reflect**: {', '.join(slack_personality.get('personality_traits', []))}

**Additional Notes**: {slack_personality.get('other_notes', '')}

IMPORTANT: When sending Slack messages, write naturally in the user's voice. Match their emoji usage and casual tone.
"""
            personality_sections.append(slack_text)

        # Return combined personality text or empty string
        if personality_sections:
            return "\n".join(personality_sections)
        else:
            return ""

    except Exception as e:
        logger.error(f"Error fetching personality profile: {e}")
        return ""




# Import modular route handlers so they register their routes on import
# Placed at the end to ensure all referenced symbols are defined
from app import assistant_handler  # noqa: F401
from app import autopilot_handler  # noqa: F401

