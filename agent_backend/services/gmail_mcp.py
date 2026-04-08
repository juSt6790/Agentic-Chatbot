"""
This module provides utilities for authenticating with and using the Gmail API.
"""

import base64
import json
import os
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build
import requests
from clients.db_method import get_user_tool_access_token

# Default settings
DEFAULT_USER_ID = "me"

# Type alias for the Gmail service
GmailService = Resource




# BASE_URL = "http://3.6.95.164:5000/users"

# # Example: Call get_tool_token endpoint
# def get_tool_token(unified_token, tool_name):
#     url = f"{BASE_URL}/get_tool_token"
#     payload = {
#         "unified_token": unified_token,
#         "tool_name": tool_name
#     }

#     response = requests.post(url, json=payload)
#     print("abc")
#     if response.status_code == 200:
#         print("Access Token:", response.json())
#         return response.json()
#     else:
#         print("Error:", response.status_code, response.text)









def get_gmail_service(unified_token):
    tool_name="Gsuite"
    # Step 1: Get access token details
    # result = get_tool_token(unified_token, tool_name)
    result, status = get_user_tool_access_token(unified_token, tool_name)
    
    # Check if credentials exist before accessing
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise Exception(f"Failed to retrieve Gmail credentials. Please connect Gmail. {error_msg}")

    access_data = result["access_token"]

    # Note: Don't specify scopes - use whatever was originally granted
    # to avoid "invalid_scope" errors during token refresh
    creds = Credentials(
        token=access_data.get("token"),
        refresh_token=access_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=access_data.get("client_id"),
        client_secret=access_data.get("client_secret"),
    )

    # Step 2: Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # Step 3: Update MongoDB with new token
        # update_user_tool_access_token(unified_token, tool_name, {
        #     "token": creds.token,
        #     "refresh_token": creds.refresh_token,
        #     "client_id": creds.client_id,
        #     "client_secret": creds.client_secret,
        #     "expiry": creds.expiry.isoformat() if creds.expiry else None
        # })

    # Step 4: Build and return service
    return build('gmail', 'v1', credentials=creds)




def create_message(
    sender: str,
    to: str,
    subject: str,
    message_text: str,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a message for the Gmail API.

    Args:
        sender: Email sender
        to: Email recipient
        subject: Email subject
        message_text: Email body text
        cc: Carbon copy recipients (optional)
        bcc: Blind carbon copy recipients (optional)

    Returns:
        A dictionary containing a base64url encoded email object
    """
    message = MIMEText(message_text)
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject

    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    # Encode the message
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    return {"raw": encoded_message}


def create_multipart_message(
    sender: str,
    to: str,
    subject: str,
    text_part: str,
    html_part: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a multipart MIME message (text and HTML).

    Args:
        sender: Email sender
        to: Email recipient
        subject: Email subject
        text_part: Plain text email body
        html_part: HTML email body (optional)
        cc: Carbon copy recipients (optional)
        bcc: Blind carbon copy recipients (optional)

    Returns:
        A dictionary containing a base64url encoded email object
    """
    message = MIMEMultipart("alternative")
    message["to"] = to
    message["from"] = sender
    message["subject"] = subject

    if cc:
        message["cc"] = cc
    if bcc:
        message["bcc"] = bcc

    # Attach text part
    text_mime = MIMEText(text_part, "plain")
    message.attach(text_mime)

    # Attach HTML part if provided
    if html_part:
        html_mime = MIMEText(html_part, "html")
        message.attach(html_mime)

    # Encode the message
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    return {"raw": encoded_message}


def parse_message_body(message: Dict[str, Any]) -> str:
    """
    Parse the body of a Gmail message.

    Prefers text/plain when available, but will fall back to text/html
    (raw HTML) if no plain text part exists. This is important for some
    drafts that are created as HTML-only.
    """

    def get_text_part(parts) -> str:
        text_plain = ""
        text_html = ""
        for part in parts:
            mime_type = part.get("mimeType", "")
            body = part.get("body", {}) or {}
            data = body.get("data")

            if mime_type == "text/plain" and data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode()
                    text_plain += decoded
                except Exception:
                    pass
            elif mime_type == "text/html" and data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode()
                    text_html += decoded
                except Exception:
                    pass
            elif "parts" in part:
                child_text = get_text_part(part["parts"])
                if child_text:
                    # Treat child as plain if we don't have anything yet
                    text_plain += child_text

        # Prefer plain text; fall back to html if needed
        return text_plain or text_html

    payload = message.get("payload", {}) or {}

    # Multipart
    if "parts" in payload:
        return get_text_part(payload["parts"]) or ""

    # Single-part: decode whatever is there
    body = payload.get("body", {}) or {}
    data = body.get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data).decode()
        except Exception:
            return ""
    return ""


def parse_raw_message_body(raw_base64: str) -> str:
    """
    Parse body from a format=raw MIME message (message['raw']).
    Prefer text/plain, fall back to text/html, then any payload.
    """
    if not raw_base64:
        return ""
    try:
        raw_bytes = base64.urlsafe_b64decode(raw_base64)
        msg = email.message_from_bytes(raw_bytes)

        # Prefer text/plain, then text/html
        plain = ""
        html = ""
        for part in msg.walk():
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            text = payload.decode("utf-8", errors="ignore")
            if ctype == "text/plain" and not plain:
                plain = text
            elif ctype == "text/html" and not html:
                html = text

        if plain:
            return plain
        if html:
            return html

        # Fallback to top-level payload
        payload = msg.get_payload(decode=True)
        return payload.decode("utf-8", errors="ignore") if payload else ""
    except Exception as e:
        print(f"[DEBUG] parse_raw_message_body failed: {e}")
        return ""


def get_headers_dict(message: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract headers from a Gmail message into a dictionary.

    Args:
        message: The Gmail message object

    Returns:
        Dictionary of message headers
    """
    headers = {}
    for header in message["payload"]["headers"]:
        headers[header["name"]] = header["value"]
    return headers


def send_email(
    service: GmailService,
    sender: str,
    to: str,
    subject: str,
    body: Optional[str] = None,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compose and send an email. Supports both plain text and HTML formats.

    Args:
        service: Gmail API service instance
        sender: Email sender
        to: Email recipient
        subject: Email subject
        body: Email body text (legacy parameter, used if body_text not provided)
        body_text: Plain text email body (optional, falls back to body if not provided)
        body_html: HTML email body (optional)
        user_id: Gmail user ID (default: 'me')
        cc: Carbon copy recipients (optional)
        bcc: Blind carbon copy recipients (optional)

    Returns:
        Sent message object
    """
    # Support legacy 'body' parameter for backward compatibility
    text_content = body_text or body or ""
    
    # Use multipart if HTML is provided, otherwise use simple text message
    if body_html:
        message = create_multipart_message(
            sender, to, subject, text_content, body_html, cc, bcc
        )
    else:
        message = create_message(sender, to, subject, text_content, cc, bcc)
    
    return service.users().messages().send(userId=user_id, body=message).execute()


def get_labels(service: GmailService, user_id: str = DEFAULT_USER_ID) -> List[Dict[str, Any]]:
    """
    Get all labels for the specified user.

    Args:
        service: Gmail API service instance
        user_id: Gmail user ID (default: 'me')

    Returns:
        List of label objects
    """
    response = service.users().labels().list(userId=user_id).execute()
    return response.get("labels", [])


def list_messages(
    service: GmailService,
    user_id: str = DEFAULT_USER_ID,
    max_results: int = 10,
    query: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List messages in the user's mailbox.

    Args:
        service: Gmail API service instance
        user_id: Gmail user ID (default: 'me')
        max_results: Maximum number of messages to return (default: 10)
        query: Search query (default: None)

    Returns:
        List of message objects
    """
    response = (
        service.users().messages().list(userId=user_id, maxResults=max_results, q=query or "").execute()
    )
    messages = response.get("messages", [])
    return messages


def search_messages(
    service: GmailService,
    user_id: str = DEFAULT_USER_ID,
    max_results: int = 10,
    is_unread: Optional[bool] = None,
    labels: Optional[List[str]] = None,
    from_email: Optional[str] = None,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    after: Optional[str] = None,
    before: Optional[str] = None,
    has_attachment: Optional[bool] = None,
    is_starred: Optional[bool] = None,
    is_important: Optional[bool] = None,
    in_trash: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    Search for messages in the user's mailbox using various criteria.

    Args:
        service: Gmail API service instance
        user_id: Gmail user ID (default: 'me')
        max_results: Maximum number of messages to return (default: 10)
        is_unread: If True, only return unread messages (optional)
        labels: List of label names to search for (optional)
        from_email: Sender email address (optional)
        to_email: Recipient email address (optional)
        subject: Subject text to search for (optional)
        after: Only return messages after this date (format: YYYY/MM/DD) (optional)
        before: Only return messages before this date (format: YYYY/MM/DD) (optional)
        has_attachment: If True, only return messages with attachments (optional)
        is_starred: If True, only return starred messages (optional)
        is_important: If True, only return important messages (optional)
        in_trash: If True, only search in trash (optional)

    Returns:
        List of message objects matching the search criteria
    """
    query_parts = []

    # Handle read/unread status
    if is_unread is not None:
        query_parts.append("is:unread" if is_unread else "")

    # Handle labels
    if labels:
        for label in labels:
            query_parts.append(f"label:{label}")

    # Handle from and to
    if from_email:
        query_parts.append(f"from:{from_email}")
    if to_email:
        query_parts.append(f"to:{to_email}")

    # Handle subject
    if subject:
        query_parts.append(f"subject:{subject}")

    # Handle date filters
    if after:
        query_parts.append(f"after:{after}")
    if before:
        query_parts.append(f"before:{before}")

    # Handle attachment filter
    if has_attachment is not None and has_attachment:
        query_parts.append("has:attachment")

    # Handle starred and important flags
    if is_starred is not None and is_starred:
        query_parts.append("is:starred")
    if is_important is not None and is_important:
        query_parts.append("is:important")

    # Handle trash
    if in_trash is not None and in_trash:
        query_parts.append("in:trash")

    # Join all query parts with spaces
    query = " ".join(query_parts)

    # Use the existing list_messages function to perform the search
    return list_messages(service, user_id, max_results, query)


def get_message(
    service: GmailService,
    message_id: str,
    user_id: str = DEFAULT_USER_ID,
    format: str = "full",
) -> Dict[str, Any]:
    """
    Get a specific message by ID.

    Args:
        service: Gmail API service instance
        message_id: Gmail message ID
        user_id: Gmail user ID (default: 'me')

    Returns:
        Message object
    """
    message = (
        service.users()
        .messages()
        .get(userId=user_id, id=message_id, format=format)
        .execute()
    )
    return message


def get_thread(service: GmailService, thread_id: str, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    """
    Get a specific thread by ID.

    Args:
        service: Gmail API service instance
        thread_id: Gmail thread ID
        user_id: Gmail user ID (default: 'me')

    Returns:
        Thread object
    """
    thread = service.users().threads().get(userId=user_id, id=thread_id).execute()
    return thread


def create_draft(
    service: GmailService,
    sender: str,
    to: str,
    subject: str,
    body: Optional[str] = None,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a draft email. Supports both plain text and HTML formats.

    Args:
        service: Gmail API service instance
        sender: Email sender
        to: Email recipient
        subject: Email subject
        body: Email body text (legacy parameter, used if body_text not provided)
        body_text: Plain text email body (optional, falls back to body if not provided)
        body_html: HTML email body (optional)
        user_id: Gmail user ID (default: 'me')
        cc: Carbon copy recipients (optional)
        bcc: Blind carbon copy recipients (optional)
        thread_id: Gmail thread ID for reply drafts (optional)

    Returns:
        Draft object
    """
    # Support legacy 'body' parameter for backward compatibility
    text_content = body_text or body or ""
    
    # Use multipart if HTML is provided, otherwise use simple text message
    if body_html:
        message = create_multipart_message(
            sender, to, subject, text_content, body_html, cc, bcc
        )
    else:
        message = create_message(sender, to, subject, text_content, cc, bcc)
    
    if thread_id:
        message["threadId"] = str(thread_id)

    draft_body = {"message": message}
    return service.users().drafts().create(userId=user_id, body=draft_body).execute()


def list_drafts(
    service: GmailService, user_id: str = DEFAULT_USER_ID, max_results: int = 10
) -> List[Dict[str, Any]]:
    """
    List draft emails in the user's mailbox.

    Args:
        service: Gmail API service instance
        user_id: Gmail user ID (default: 'me')
        max_results: Maximum number of drafts to return (default: 10)

    Returns:
        List of draft objects
    """
    response = service.users().drafts().list(userId=user_id, maxResults=max_results).execute()
    drafts = response.get("drafts", [])
    return drafts


def get_draft(
    service: GmailService,
    draft_id: str,
    user_id: str = DEFAULT_USER_ID,
    format: str = "raw",
) -> Dict[str, Any]:
    """
    Get a specific draft by ID.

    Args:
        service: Gmail API service instance
        draft_id: Gmail draft ID
        user_id: Gmail user ID (default: 'me')

    Returns:
        Draft object
    """
    draft = (
        service.users()
        .drafts()
        .get(userId=user_id, id=draft_id, format=format)
        .execute()
    )
    return draft


def send_draft(service: GmailService, draft_id: str, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    """
    Send an existing draft email.

    Args:
        service: Gmail API service instance
        draft_id: Gmail draft ID
        user_id: Gmail user ID (default: 'me')

    Returns:
        Sent message object
    """
    draft = {"id": draft_id}
    return service.users().drafts().send(userId=user_id, body=draft).execute()


def create_label(
    service: GmailService, name: str, user_id: str = DEFAULT_USER_ID, label_type: str = "user"
) -> Dict[str, Any]:
    """
    Create a new label.

    Args:
        service: Gmail API service instance
        name: Label name
        user_id: Gmail user ID (default: 'me')
        label_type: Label type (default: 'user')

    Returns:
        Created label object
    """
    label_body = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
        "type": label_type,
    }
    return service.users().labels().create(userId=user_id, body=label_body).execute()


def update_label(
    service: GmailService,
    label_id: str,
    name: Optional[str] = None,
    label_list_visibility: Optional[str] = None,
    message_list_visibility: Optional[str] = None,
    user_id: str = DEFAULT_USER_ID,
) -> Dict[str, Any]:
    """
    Update an existing label.

    Args:
        service: Gmail API service instance
        label_id: Label ID to update
        name: New label name (optional)
        label_list_visibility: Label visibility in label list (optional)
        message_list_visibility: Label visibility in message list (optional)
        user_id: Gmail user ID (default: 'me')

    Returns:
        Updated label object
    """
    # Get the current label to update
    label = service.users().labels().get(userId=user_id, id=label_id).execute()

    # Update fields if provided
    if name:
        label["name"] = name
    if label_list_visibility:
        label["labelListVisibility"] = label_list_visibility
    if message_list_visibility:
        label["messageListVisibility"] = message_list_visibility

    return service.users().labels().update(userId=user_id, id=label_id, body=label).execute()


def delete_label(service: GmailService, label_id: str, user_id: str = DEFAULT_USER_ID) -> None:
    """
    Delete a label.

    Args:
        service: Gmail API service instance
        label_id: Label ID to delete
        user_id: Gmail user ID (default: 'me')

    Returns:
        None
    """
    service.users().labels().delete(userId=user_id, id=label_id).execute()


def modify_message_labels(
    service: GmailService,
    message_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    user_id: str = DEFAULT_USER_ID,
) -> Dict[str, Any]:
    """
    Modify the labels on a message.

    Args:
        service: Gmail API service instance
        message_id: Message ID
        add_labels: List of label IDs to add (optional)
        remove_labels: List of label IDs to remove (optional)
        user_id: Gmail user ID (default: 'me')

    Returns:
        Updated message object
    """
    body = {"addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []}
    return service.users().messages().modify(userId=user_id, id=message_id, body=body).execute()


def batch_modify_messages_labels(
    service: GmailService,
    message_ids: List[str],
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
    user_id: str = DEFAULT_USER_ID,
) -> None:
    """
    Batch modify the labels on multiple messages.

    Args:
        service: Gmail API service instance
        message_ids: List of message IDs
        add_labels: List of label IDs to add (optional)
        remove_labels: List of label IDs to remove (optional)
        user_id: Gmail user ID (default: 'me')

    Returns:
        None
    """
    body = {"ids": message_ids, "addLabelIds": add_labels or [], "removeLabelIds": remove_labels or []}
    service.users().messages().batchModify(userId=user_id, body=body).execute()


def trash_message(service: GmailService, message_id: str, user_id: str = DEFAULT_USER_ID) -> Dict[str, Any]:
    """
    Move a message to trash.

    Args:
        service: Gmail API service instance
        message_id: Message ID
        user_id: Gmail user ID (default: 'me')

    Returns:
        Updated message object
    """
    return service.users().messages().trash(userId=user_id, id=message_id).execute()


def untrash_message(
    service: GmailService, message_id: str, user_id: str = DEFAULT_USER_ID
) -> Dict[str, Any]:
    """
    Remove a message from trash.

    Args:
        service: Gmail API service instance
        message_id: Message ID
        user_id: Gmail user ID (default: 'me')

    Returns:
        Updated message object
    """
    return service.users().messages().untrash(userId=user_id, id=message_id).execute()


def safe_message_headers(message: Dict[str, Any]) -> Dict[str, str]:
    """Headers from a Gmail API message payload (tolerates missing payload)."""
    payload = message.get("payload") or {}
    headers_list = payload.get("headers") or []
    out: Dict[str, str] = {}
    for h in headers_list:
        if isinstance(h, dict) and h.get("name") and "value" in h:
            out[h["name"]] = h["value"]
    return out


def message_to_ai_email_dict(message: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a full-format Gmail message for tool / AI consumption (includes body text)."""
    hdrs = safe_message_headers(message)
    body = parse_message_body(message)
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "snippet": message.get("snippet") or "",
        "subject": hdrs.get("Subject", ""),
        "from": hdrs.get("From", ""),
        "to": hdrs.get("To", ""),
        "cc": hdrs.get("Cc", ""),
        "date": message.get("internalDate"),
        "body": body,
    }


def list_message_refs_paginated(
    service: GmailService,
    user_id: str,
    q: str,
    max_results: int,
) -> List[Dict[str, str]]:
    """
    List message id/thread refs using Gmail users.messages.list with pagination.
    """
    refs: List[Dict[str, str]] = []
    page_token: Optional[str] = None
    while len(refs) < max_results:
        batch_size = min(500, max_results - len(refs))
        kwargs: Dict[str, Any] = {
            "userId": user_id,
            "maxResults": batch_size,
            "q": q or "",
        }
        if page_token:
            kwargs["pageToken"] = page_token
        resp = service.users().messages().list(**kwargs).execute()
        batch = resp.get("messages") or []
        for m in batch:
            if isinstance(m, dict) and m.get("id"):
                refs.append({"id": m["id"], "threadId": m.get("threadId", "")})
        page_token = resp.get("nextPageToken")
        if not page_token or not batch:
            break
    return refs[:max_results]


def search_or_fetch_gmail_messages(
    service: GmailService,
    *,
    user_id: str = DEFAULT_USER_ID,
    message_ids: Optional[List[str]] = None,
    gmail_query: Optional[str] = None,
    max_results: int = 10,
    scope: str = "sent",
) -> Dict[str, Any]:
    """
    Either fetch specific messages by id or search with a Gmail `q` string, returning
    each message with a decoded plain-text (or HTML fallback) body.

    - If ``message_ids`` is non-empty, those ids are fetched (up to ``max_results``);
      ``gmail_query`` and ``scope`` are ignored.
    - Otherwise Gmail ``users.messages.list`` is used, then each hit is loaded with
      ``format=full`` so bodies can be parsed.

    ``scope``:
      - ``sent`` (default): query is ``in:sent`` plus optional ``gmail_query`` tokens.
      - ``all``: query is ``gmail_query`` alone, or ``in:inbox`` if ``gmail_query`` is empty.
    """
    emails: List[Dict[str, Any]] = []
    mode = "search"
    q_used = ""
    sc = (scope or "sent").strip().lower()
    if sc not in ("sent", "all"):
        sc = "sent"

    if message_ids:
        mode = "by_id"
        ids = [str(x).strip() for x in message_ids if x][:max_results]
        for mid in ids:
            try:
                msg = get_message(service, mid, user_id, format="full")
                emails.append(message_to_ai_email_dict(msg))
            except Exception:
                continue
    else:
        mq = (gmail_query or "").strip()
        if sc == "sent":
            q_used = f"in:sent {mq}".strip()
        else:
            q_used = mq if mq else "in:inbox"
        refs = list_message_refs_paginated(service, user_id, q_used, max_results)
        for ref in refs:
            try:
                msg = get_message(service, ref["id"], user_id, format="full")
                emails.append(message_to_ai_email_dict(msg))
            except Exception:
                continue

    return {
        "emails": emails,
        "mode": mode,
        "gmail_query_used": q_used if mode == "search" else None,
        "count": len(emails),
    }


def get_message_history(
    service: GmailService, history_id: str, user_id: str = DEFAULT_USER_ID, max_results: int = 100
) -> Dict[str, Any]:
    """
    Get history of changes to the mailbox.

    Args:
        service: Gmail API service instance
        history_id: Starting history ID
        user_id: Gmail user ID (default: 'me')
        max_results: Maximum number of history records to return

    Returns:
        History object
    """
    return (
        service.users()
        .history()
        .list(userId=user_id, startHistoryId=history_id, maxResults=max_results)
        .execute()
    )


# Note: Duplicate create_label and delete_label functions removed.
# The proper definitions with type hints are above (lines 510-582).