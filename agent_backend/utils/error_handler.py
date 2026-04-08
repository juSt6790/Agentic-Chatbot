"""
Centralized error handling utility for the application.
Separates internal error logging from user-facing error messages.
"""

import logging
import traceback
from typing import Dict, Any, Optional

# Try to import HttpError for Google API client errors
try:
    from googleapiclient.errors import HttpError
except ImportError:
    HttpError = None

logger = logging.getLogger(__name__)

# User-friendly error messages with actionable guidance
GENERIC_ERROR_MESSAGES = {
    # Authentication & Credentials
    "authentication": "Your connection has expired. Please log in again to continue.",
    "credential_missing": "This feature requires you to connect your account first. Please set up the integration in your settings.",
    "permission": "I don't have permission to access that. Please check your sharing settings or ask the owner to grant access.",
    "token_invalid": "Your session has expired. Please refresh the page and log in again.",
    "tool_not_connected": "This tool isn't connected yet. Please add it in your integrations settings to use this feature.",
    
    # Service Connection Issues
    "service_unavailable": "I'm having trouble connecting to that service right now. Please try again in a moment.",
    "service_init_failed": "I couldn't initialize the connection. Please check your integration settings and try again.",
    "api_error": "The service is temporarily unavailable. Please wait a moment and try again.",
    
    # Data Not Found
    "email_not_found": "I couldn't find that email. It may have been deleted or moved. Try searching with different criteria.",
    "document_not_found": "That document doesn't exist or you don't have access to it. Please check the document name or link.",
    "event_not_found": "I couldn't find that calendar event. It may have been deleted or you might not have access to it.",
    "user_not_found": "I couldn't find that user. Please check the name or email address and try again.",
    "channel_not_found": "That channel doesn't exist or you're not a member. Please check the channel name.",
    "item_not_found": "I couldn't find what you're looking for. Please check the details and try again.",
    "workflow_not_found": "That workflow doesn't exist. Use a different workflow name or create a new one.",
    
    # Invalid Input/Validation
    "invalid_date": "The date format isn't recognized. Please use a format like 'YYYY-MM-DD' or '2024-01-15'.",
    "invalid_parameter": "Some information provided isn't valid. Please check your input and try again.",
    "missing_required": "Some required information is missing. Please provide all necessary details and try again.",
    "invalid_id": "The ID or identifier provided isn't valid. Please double-check and try again.",
    "out_of_range": "The value provided is out of range. Please check the valid range and try again.",
    "invalid_format": "The format of the data isn't correct. Please check the example format and try again.",
    "invalid_email": "One or more email addresses are invalid. Please check the email addresses and try again.",
    
    # Rate Limiting & Performance
    "rate_limit": "We're experiencing high demand right now. Please wait 30 seconds and try again.",
    "timeout": "That's taking longer than expected. Try breaking it into smaller requests or try again later.",
    "quota_exceeded": "You've reached the usage limit for this feature. Please try again later or upgrade your plan.",
    
    # Creation/Update Failures
    "create_failed": "I couldn't create that item. Please check your input and try again.",
    "update_failed": "I couldn't update that item. Please make sure it still exists and try again.",
    "delete_failed": "I couldn't delete that item. Please check if you have permission and try again.",
    "export_failed": "I couldn't export that file. Please try again or use a different format.",
    "upload_failed": "I couldn't upload that file. Please check the file size and format, then try again.",
    
    # Communication Failures
    "dm_failed": "I couldn't send that direct message. Please make sure the user exists and try again.",
    "channel_action_failed": "I couldn't perform that action in the channel. Please check your permissions and try again.",
    "send_failed": "I couldn't send that message. Please check the recipient and try again.",
    
    # Database/Collection Issues
    "database_error": "I'm having trouble accessing your data right now. Please try again in a moment.",
    "collection_error": "I couldn't access that information. Please try again or contact support if this persists.",
    
    # Tool Execution
    "tool_execution": "I encountered an issue while performing that action. Please try again or rephrase your request.",
    
    # File/Media Issues
    "file_too_large": "That file is too large to process. Please try a smaller file or compress it first.",
    "unsupported_format": "That file format isn't supported. Please try a different format.",
    "file_corrupted": "The file appears to be corrupted or unreadable. Please try a different file.",
    
    # General Fallback
    "general": "Something unexpected happened. Please try again, and if it persists, contact support.",
}


def log_error_to_terminal(
    error: Exception,
    context: str = "",
    tool_name: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> None:
    """
    Log the full error details to terminal/log file for debugging.
    
    Args:
        error: The exception that occurred
        context: Additional context about where/when the error occurred
        tool_name: Name of the tool that failed (if applicable)
        args: Arguments passed to the tool (if applicable)
        user_id: User identifier for tracking (if applicable)
    """
    error_type = type(error).__name__
    error_message = str(error)
    
    # Build concise error log message
    log_parts = [f"{error_type}: {error_message}"]
    
    if context:
        log_parts.append(f"Context: {context}")
    
    if tool_name:
        log_parts.append(f"Tool: {tool_name}")
    
    if user_id:
        log_parts.append(f"User: {user_id}")
    
    # For expected errors (like PermissionError), just log the message without traceback
    expected_errors = (PermissionError, ValueError, KeyError, FileNotFoundError)
    
    if isinstance(error, expected_errors):
        # Just log the error message cleanly without traceback
        logger.error(" | ".join(log_parts))
    else:
        # For unexpected errors, include a minimal traceback (just the last few frames)
        tb_lines = traceback.format_tb(error.__traceback__)
        # Only show last 3 frames to keep it clean
        relevant_tb = ''.join(tb_lines[-3:]) if len(tb_lines) > 3 else ''.join(tb_lines)
        logger.error(" | ".join(log_parts))
        if relevant_tb.strip():
            logger.error(f"Traceback (last frames):\n{relevant_tb.strip()}")


def get_user_friendly_error_message(
    error: Exception,
    error_category: str = "general"
) -> str:
    """
    Get a user-friendly error message without exposing internal details.
    Analyzes the error message to provide specific, actionable guidance.
    
    Args:
        error: The exception that occurred
        error_category: Category of error (optional, will be auto-detected)
    
    Returns:
        A user-friendly error message with actionable guidance
    """
    error_type = type(error).__name__
    error_msg = str(error).lower()
    
    # Authentication & Credentials
    if isinstance(error, PermissionError) or "permission" in error_type.lower():
        if "access denied" in error_msg:
            return GENERIC_ERROR_MESSAGES["permission"]
        return GENERIC_ERROR_MESSAGES["authentication"]
    
    if any(keyword in error_msg for keyword in ["credential", "auth", "token", "login", "session"]):
        if "missing" in error_msg or "not found" in error_msg:
            return GENERIC_ERROR_MESSAGES["credential_missing"]
        elif "invalid" in error_msg or "expired" in error_msg:
            return GENERIC_ERROR_MESSAGES["token_invalid"]
        elif "failed to retrieve" in error_msg:
            return GENERIC_ERROR_MESSAGES["tool_not_connected"]
        return GENERIC_ERROR_MESSAGES["authentication"]
    
    # Service Connection Issues
    if any(keyword in error_msg for keyword in ["service not available", "failed to initialize", "could not initialize"]):
        return GENERIC_ERROR_MESSAGES["service_init_failed"]
    
    if any(keyword in error_msg for keyword in ["connection", "network", "unreachable"]):
        return GENERIC_ERROR_MESSAGES["service_unavailable"]
    
    # Data Not Found (specific types)
    if "not found" in error_msg or "404" in str(error) or "does not exist" in error_msg:
        if "email" in error_msg or "message" in error_msg:
            return GENERIC_ERROR_MESSAGES["email_not_found"]
        elif "document" in error_msg or "doc" in error_msg or "file" in error_msg:
            return GENERIC_ERROR_MESSAGES["document_not_found"]
        elif "event" in error_msg or "calendar" in error_msg:
            return GENERIC_ERROR_MESSAGES["event_not_found"]
        elif "user" in error_msg:
            return GENERIC_ERROR_MESSAGES["user_not_found"]
        elif "channel" in error_msg:
            return GENERIC_ERROR_MESSAGES["channel_not_found"]
        elif "workflow" in error_msg:
            return GENERIC_ERROR_MESSAGES["workflow_not_found"]
        return GENERIC_ERROR_MESSAGES["item_not_found"]
    
    # Invalid Input/Validation
    if isinstance(error, ValueError) or "invalid" in error_type.lower():
        if "date" in error_msg or "time" in error_msg:
            return GENERIC_ERROR_MESSAGES["invalid_date"]
        elif "id" in error_msg:
            return GENERIC_ERROR_MESSAGES["invalid_id"]
        elif "format" in error_msg:
            return GENERIC_ERROR_MESSAGES["invalid_format"]
        elif "range" in error_msg or "out of" in error_msg:
            return GENERIC_ERROR_MESSAGES["out_of_range"]
        return GENERIC_ERROR_MESSAGES["invalid_parameter"]
    
    # HTTP 400 errors with invalid email messages (especially for calendar events)
    # Check for HttpError from Google API client
    is_http_400 = False
    if HttpError and isinstance(error, HttpError):
        if hasattr(error, 'resp') and hasattr(error.resp, 'status'):
            is_http_400 = error.resp.status == 400
    elif "400" in str(error) or (hasattr(error, 'resp') and hasattr(error.resp, 'status') and error.resp.status == 400):
        is_http_400 = True
    
    if is_http_400:
        if "invalid attendee email" in error_msg or "invalid email" in error_msg:
            return GENERIC_ERROR_MESSAGES["invalid_email"]
    
    if "missing" in error_msg or "required" in error_msg:
        return GENERIC_ERROR_MESSAGES["missing_required"]
    
    # Rate Limiting & Performance
    if "rate limit" in error_msg or "429" in str(error) or "too many" in error_msg:
        return GENERIC_ERROR_MESSAGES["rate_limit"]
    
    if isinstance(error, TimeoutError) or "timeout" in error_type.lower() or "timed out" in error_msg:
        return GENERIC_ERROR_MESSAGES["timeout"]
    
    if "quota" in error_msg or "limit exceeded" in error_msg:
        return GENERIC_ERROR_MESSAGES["quota_exceeded"]
    
    # Creation/Update/Delete Failures
    if "failed to create" in error_msg or "could not create" in error_msg or "unable to create" in error_msg:
        return GENERIC_ERROR_MESSAGES["create_failed"]
    
    if "failed to update" in error_msg or "could not update" in error_msg:
        return GENERIC_ERROR_MESSAGES["update_failed"]
    
    if "failed to delete" in error_msg or "could not delete" in error_msg:
        return GENERIC_ERROR_MESSAGES["delete_failed"]
    
    if "export" in error_msg and ("failed" in error_msg or "error" in error_msg):
        return GENERIC_ERROR_MESSAGES["export_failed"]
    
    if "upload" in error_msg and ("failed" in error_msg or "error" in error_msg):
        return GENERIC_ERROR_MESSAGES["upload_failed"]
    
    # Communication Failures
    if "unable to open dm" in error_msg or "could not determine current user" in error_msg:
        return GENERIC_ERROR_MESSAGES["dm_failed"]
    
    if "could not send" in error_msg or "failed to send" in error_msg:
        return GENERIC_ERROR_MESSAGES["send_failed"]
    
    # File/Media Issues
    if "too large" in error_msg or "size" in error_msg:
        return GENERIC_ERROR_MESSAGES["file_too_large"]
    
    if "unsupported" in error_msg or "not supported" in error_msg:
        return GENERIC_ERROR_MESSAGES["unsupported_format"]
    
    if "corrupt" in error_msg or "invalid file" in error_msg:
        return GENERIC_ERROR_MESSAGES["file_corrupted"]
    
    # Database/Collection Issues
    if "collection" in error_msg and ("none" in error_msg or "null" in error_msg):
        return GENERIC_ERROR_MESSAGES["collection_error"]
    
    if "database" in error_msg or "mongodb" in error_msg:
        return GENERIC_ERROR_MESSAGES["database_error"]
    
    # HTTP Error Codes
    if any(code in str(error) for code in ["500", "502", "503", "504"]):
        return GENERIC_ERROR_MESSAGES["api_error"]
    
    # Use provided category if nothing specific matched
    return GENERIC_ERROR_MESSAGES.get(error_category, GENERIC_ERROR_MESSAGES["general"])


def handle_tool_error(
    error: Exception,
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Handle tool execution errors with proper logging and user-friendly response.
    
    Args:
        error: The exception that occurred
        tool_name: Name of the tool that failed
        args: Arguments passed to the tool
        user_id: User identifier for tracking
    
    Returns:
        A standardized error response dictionary
    """
    # Log the full error to terminal/logs
    log_error_to_terminal(
        error=error,
        context=f"Tool execution failed: {tool_name}",
        tool_name=tool_name,
        args=args,
        user_id=user_id,
    )
    
    # Check if this is a connection/authentication error
    error_type = type(error).__name__
    error_msg = str(error).lower()
    
    # Check for various connection/auth error patterns
    is_connection_error = (
        # Exception types - PermissionError from clients, ValueError/Exception from services
        isinstance(error, PermissionError) or
        (isinstance(error, ValueError) and ("credential" in error_msg or "access token" in error_msg or "failed to retrieve" in error_msg)) or
        (error_type == "KeyError" and ("access_token" in error_msg or "access_token" in str(error))) or
        
        # Common auth/credential messages from services and clients
        "access denied" in error_msg or
        "not have access" in error_msg or
        "credentials" in error_msg or
        "credential" in error_msg or
        "not_authed" in error_msg or
        "failed to retrieve" in error_msg or
        "please connect" in error_msg or
        "please re-authenticate" in error_msg or
        "connect" in error_msg and ("gmail" in error_msg or "calendar" in error_msg or "slack" in error_msg or "notion" in error_msg or "trello" in error_msg or "docs" in error_msg or "sheets" in error_msg) or
        
        # Token/access related
        "no access data found" in error_msg or
        "no access token found" in error_msg or
        "token is invalid" in error_msg or
        "api token" in error_msg or
        "access token" in error_msg or
        "invalid access token" in error_msg or
        "authentication" in error_msg or
        "failed to get access token" in error_msg or
        "invalid access token data" in error_msg or
        
        # Service unavailable/not initialized
        "service not available" in error_msg or
        "failed to initialize" in error_msg or
        "check authentication" in error_msg or
        
        # Slack specific
        "slackapierror" in error_type.lower() or
        
        # Notion specific  
        "apiresponseerror" in error_type.lower()
    )
    
    if is_connection_error:
        # Get the tool/service name for user-friendly message
        service_name = _get_service_name_from_tool(tool_name, error)
        
        return {
            "status": "error",
            "message": f"🔗 {service_name} is not connected. Please connect {service_name} in your integrations to use this feature.",
            "success": False,
            "ui_hint": "open_connection_page",
        }
    
    # Get context-aware user-friendly error message for other errors
    user_message = get_user_friendly_error_message(error, "tool_execution")
    
    # Add tool-specific context if relevant
    user_message = _add_tool_specific_context(user_message, tool_name, error)
    
    return {
        "status": "error",
        "message": f"❌ {user_message}",
        "success": False,
    }


def _get_service_name_from_tool(tool_name: str, error: Exception) -> str:
    """
    Extract a user-friendly service name from tool name or error message.
    
    Args:
        tool_name: Name of the tool that failed
        error: The exception that occurred
    
    Returns:
        User-friendly service name
    """
    tool_lower = tool_name.lower()
    error_msg = str(error).lower()
    
    # Map tool names to user-friendly service names
    if any(keyword in tool_lower for keyword in ["email", "gmail", "mail"]):
        return "Gmail"
    elif any(keyword in tool_lower for keyword in ["calendar", "event", "meeting", "transcript"]):
        return "Google Calendar"
    elif "slack" in tool_lower or "channel" in tool_lower or "user" in tool_lower and "slack" in error_msg:
        return "Slack"
    elif "notion" in tool_lower or "page" in tool_lower or "database" in tool_lower and "notion" in error_msg:
        return "Notion"
    elif any(keyword in tool_lower for keyword in ["trello", "task", "board", "card"]):
        return "Trello"
    elif any(keyword in tool_lower for keyword in ["doc", "document"]) and "sheet" not in tool_lower:
        return "Google Docs"
    elif any(keyword in tool_lower for keyword in ["sheet", "spreadsheet", "cell", "row", "column"]):
        return "Google Sheets"
    elif any(keyword in tool_lower for keyword in ["slide", "presentation", "deck"]):
        return "Google Slides"
    elif "drive" in tool_lower or "file" in tool_lower:
        return "Google Drive"
    elif "salesforce" in tool_lower:
        return "Salesforce"
    elif "jira" in tool_lower or "jeera" in tool_lower or "jira" in error_msg:
        return "Jira"
    
    # Try to detect from error message
    if "gsuite" in error_msg or "google workspace" in error_msg:
        return "Google Workspace"
    elif "gmail" in error_msg:
        return "Gmail"
    elif "calendar" in error_msg:
        return "Google Calendar"
    elif "slack" in error_msg:
        return "Slack"
    elif "notion" in error_msg:
        return "Notion"
    elif "trello" in error_msg:
        return "Trello"
    elif "sheets" in error_msg or "spreadsheet" in error_msg:
        return "Google Sheets"
    elif "slides" in error_msg or "presentation" in error_msg:
        return "Google Slides"
    elif "docs" in error_msg or "document" in error_msg:
        return "Google Docs"
    
    # Default fallback
    return "this service"


def _add_tool_specific_context(base_message: str, tool_name: str, error: Exception) -> str:
    """
    Add tool-specific context to error messages to make them more helpful.
    
    Args:
        base_message: The base user-friendly message
        tool_name: Name of the tool that failed
        error: The original error
    
    Returns:
        Enhanced message with tool-specific context
    """
    tool_lower = tool_name.lower()
    error_msg = str(error).lower()
    
    # Gmail/Email specific
    if any(keyword in tool_lower for keyword in ["email", "gmail", "mail"]):
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Gmail connection needs to be refreshed. Please reconnect Gmail in your settings."
        elif "not found" in error_msg:
            return "That email couldn't be found. It may have been moved to trash or another folder."
    
    # Calendar specific
    elif any(keyword in tool_lower for keyword in ["calendar", "event", "meeting", "transcript"]):
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Calendar connection needs to be refreshed. Please reconnect Google Calendar in your settings."
        elif "not found" in error_msg:
            return "That calendar event couldn't be found. It may have been deleted or you might not have access."
        elif "invalid attendee email" in error_msg or ("400" in str(error) and "invalid" in error_msg and "email" in error_msg):
            return "One or more attendee email addresses are invalid. Please check the email addresses and try again."
    
    # Slack specific
    elif "slack" in tool_lower:
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Slack connection needs to be refreshed. Please reconnect Slack in your settings."
        elif "channel" in error_msg and "not found" in error_msg:
            return "That Slack channel doesn't exist or you're not a member. Please check the channel name."
        elif "user" in error_msg and "not found" in error_msg:
            return "That Slack user couldn't be found. Please check the username or email."
    
    # Notion specific
    elif "notion" in tool_lower:
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Notion connection needs to be refreshed. Please reconnect Notion in your settings."
        elif "not found" in error_msg or "invalid id" in error_msg:
            return "That Notion page or database couldn't be found. Please check the page link or ID."
    
    # Trello specific
    elif "trello" in tool_lower or "task" in tool_lower:
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Trello connection needs to be refreshed. Please reconnect Trello in your settings."
        elif "not found" in error_msg:
            return "That Trello board or card couldn't be found. Please check the name or ID."
    
    # Google Docs specific
    elif any(keyword in tool_lower for keyword in ["doc", "document"]):
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Google Docs connection needs to be refreshed. Please reconnect Google Docs in your settings."
        elif "not found" in error_msg:
            return "That document couldn't be found. Please check the document link or name."
    
    # Google Sheets specific
    elif "sheet" in tool_lower:
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Google Sheets connection needs to be refreshed. Please reconnect Google Sheets in your settings."
        elif "not found" in error_msg:
            return "That spreadsheet couldn't be found. Please check the sheet link or name."
        elif "range" in error_msg or "invalid" in error_msg:
            return "The cell range specified isn't valid. Please use a format like 'Sheet1!A1:D10'."
    
    # Google Slides specific
    elif "slide" in tool_lower:
        if "credential" in error_msg or "auth" in error_msg:
            return "Your Google Slides connection needs to be refreshed. Please reconnect Google Slides in your settings."
        elif "not found" in error_msg:
            return "That presentation couldn't be found. Please check the presentation link or name."
    
    # Gamma specific
    elif "gamma" in tool_lower:
        if "api key" in error_msg or "credential" in error_msg:
            return "Slides API credentials are not configured. Please contact your administrator."
        elif "generation failed" in error_msg:
            return "The presentation generation failed. Please try again with different content."
    
    # If no specific context, return base message
    return base_message


def handle_api_error(
    error: Exception,
    api_name: str,
    context: str = "",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Handle API invocation errors (OpenAI, Bedrock, etc.).
    
    Args:
        error: The exception that occurred
        api_name: Name of the API (OpenAI, Bedrock, etc.)
        context: Additional context
        user_id: User identifier for tracking
    
    Returns:
        A standardized error response dictionary
    """
    # Log the full error to terminal/logs
    log_error_to_terminal(
        error=error,
        context=f"{api_name} API invocation failed: {context}",
        user_id=user_id,
    )
    
    # Return user-friendly error
    user_message = get_user_friendly_error_message(error, "api_error")
    
    return {
        "success": False,
        "type": "error",
        "data": {},
        "ui_hint": "chat",
        "message": f"❌ {user_message}",
    }


def _sanitize_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove or mask sensitive data from arguments before logging.
    
    Args:
        data: Dictionary that may contain sensitive information
    
    Returns:
        Sanitized dictionary
    """
    sensitive_keys = {
        "password", "token", "api_key", "secret", "credential",
        "auth", "authorization", "access_token", "refresh_token",
        "client_secret", "private_key", "session_id"
    }
    
    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_sensitive_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                _sanitize_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized


def tool_status_error_message(result: Dict[str, Any]) -> str:
    """
    User-visible text when a tool returns {"status": "error", ...}.
    Prefer explicit message; otherwise summarize per-item errors (e.g. Mongo not-found).
    """
    if not isinstance(result, dict):
        return "❌ Something went wrong. Please try again."
    msg = result.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        parts: list[str] = []
        for e in errors[:12]:
            if not isinstance(e, dict):
                continue
            ident = (
                e.get("document_id")
                or e.get("message_id")
                or e.get("event_id")
            )
            err = e.get("error") or "not found"
            if ident is not None and str(ident).strip():
                parts.append(f"{ident}: {err}")
            elif err:
                parts.append(str(err))
        if parts:
            return "❌ " + "; ".join(parts)
    return "❌ Something went wrong. Please try again."


def wrap_tool_execution(tool_func, tool_name: str, args: Dict[str, Any], user_id: Optional[str] = None):
    """
    Wrapper function to execute a tool with proper error handling.
    
    Args:
        tool_func: The tool function to execute
        tool_name: Name of the tool
        args: Arguments to pass to the tool
        user_id: User identifier for tracking
    
    Returns:
        Tool result or error response
    """
    try:
        result = tool_func(**args)
        return result
    except Exception as e:
        return handle_tool_error(
            error=e,
            tool_name=tool_name,
            args=args,
            user_id=user_id,
        )

