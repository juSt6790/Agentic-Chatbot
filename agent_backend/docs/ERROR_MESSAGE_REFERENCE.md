# Error Message Quick Reference

This document shows how internal errors map to user-friendly messages.

## Authentication & Credentials

| Detected Keywords | User Message |
|------------------|--------------|
| "credential", "auth", "token" + "missing" | "This feature requires you to connect your account first. Please set up the integration in your settings." |
| "credential", "auth", "token" + "invalid" / "expired" | "Your session has expired. Please refresh the page and log in again." |
| "failed to retrieve" + "credentials" | "This tool isn't connected yet. Please add it in your integrations settings to use this feature." |
| PermissionError / "access denied" | "I don't have permission to access that. Please check your sharing settings or ask the owner to grant access." |

### Tool-Specific Auth Messages

| Tool | User Message |
|------|--------------|
| Gmail/Email | "Your Gmail connection needs to be refreshed. Please reconnect Gmail in your settings." |
| Calendar | "Your Calendar connection needs to be refreshed. Please reconnect Google Calendar in your settings." |
| Slack | "Your Slack connection needs to be refreshed. Please reconnect Slack in your settings." |
| Notion | "Your Notion connection needs to be refreshed. Please reconnect Notion in your settings." |
| Trello | "Your Trello connection needs to be refreshed. Please reconnect Trello in your settings." |
| Docs | "Your Google Docs connection needs to be refreshed. Please reconnect Google Docs in your settings." |
| Sheets | "Your Google Sheets connection needs to be refreshed. Please reconnect Google Sheets in your settings." |
| Slides | "Your Google Slides connection needs to be refreshed. Please reconnect Google Slides in your settings." |
| Gamma | "Gamma API credentials are not configured. Please contact your administrator." |

## Data Not Found

| Detected Keywords | User Message |
|------------------|--------------|
| "not found" + "email" / "message" | "That email couldn't be found. It may have been moved to trash or another folder." |
| "not found" + "document" / "doc" / "file" | "That document doesn't exist or you don't have access to it. Please check the document name or link." |
| "not found" + "event" / "calendar" | "That calendar event couldn't be found. It may have been deleted or you might not have access." |
| "not found" + "user" | "That user couldn't be found. Please check the username or email." |
| "not found" + "channel" | "That channel doesn't exist or you're not a member. Please check the channel name." |
| "not found" + "workflow" | "That workflow doesn't exist. Use a different workflow name or create a new one." |
| "not found" (generic) | "I couldn't find what you're looking for. Please check the details and try again." |

### Tool-Specific Not Found Messages

| Tool | User Message |
|------|--------------|
| Gmail | "That email couldn't be found. It may have been moved to trash or another folder." |
| Calendar | "That calendar event couldn't be found. It may have been deleted or you might not have access." |
| Slack (channel) | "That Slack channel doesn't exist or you're not a member. Please check the channel name." |
| Slack (user) | "That Slack user couldn't be found. Please check the username or email." |
| Notion | "That Notion page or database couldn't be found. Please check the page link or ID." |
| Trello | "That Trello board or card couldn't be found. Please check the name or ID." |
| Docs | "That document couldn't be found. Please check the document link or name." |
| Sheets | "That spreadsheet couldn't be found. Please check the sheet link or name." |
| Slides | "That presentation couldn't be found. Please check the presentation link or name." |

## Invalid Input

| Detected Keywords | User Message |
|------------------|--------------|
| ValueError + "date" / "time" | "The date format isn't recognized. Please use a format like 'YYYY-MM-DD' or '2024-01-15'." |
| ValueError + "id" | "The ID or identifier provided isn't valid. Please double-check and try again." |
| ValueError + "format" | "The format of the data isn't correct. Please check the example format and try again." |
| ValueError + "range" / "out of" | "The value provided is out of range. Please check the valid range and try again." |
| ValueError (generic) | "Some information provided isn't valid. Please check your input and try again." |
| "missing" / "required" | "Some required information is missing. Please provide all necessary details and try again." |

### Tool-Specific Invalid Input

| Tool | Error Type | User Message |
|------|------------|--------------|
| Sheets | Invalid range | "The cell range specified isn't valid. Please use a format like 'Sheet1!A1:D10'." |
| Slides | Slide number out of range | "The value provided is out of range. Please check the valid range and try again." |
| Any | Invalid date | "The date format isn't recognized. Please use a format like 'YYYY-MM-DD' or '2024-01-15'." |

## Rate Limiting & Performance

| Detected Keywords | User Message |
|------------------|--------------|
| "rate limit" / "429" / "too many" | "We're experiencing high demand right now. Please wait 30 seconds and try again." |
| TimeoutError / "timeout" / "timed out" | "That's taking longer than expected. Try breaking it into smaller requests or try again later." |
| "quota" / "limit exceeded" | "You've reached the usage limit for this feature. Please try again later or upgrade your plan." |

## Service & API Errors

| Detected Keywords | User Message |
|------------------|--------------|
| "service not available" / "failed to initialize" | "I couldn't initialize the connection. Please check your integration settings and try again." |
| "connection" / "network" / "unreachable" | "I'm having trouble connecting to that service right now. Please try again in a moment." |
| "500" / "502" / "503" / "504" | "The service is temporarily unavailable. Please wait a moment and try again." |

## CRUD Operations

| Detected Keywords | User Message |
|------------------|--------------|
| "failed to create" / "could not create" | "I couldn't create that item. Please check your input and try again." |
| "failed to update" / "could not update" | "I couldn't update that item. Please make sure it still exists and try again." |
| "failed to delete" / "could not delete" | "I couldn't delete that item. Please check if you have permission and try again." |
| "export" + "failed" / "error" | "I couldn't export that file. Please try again or use a different format." |
| "upload" + "failed" / "error" | "I couldn't upload that file. Please check the file size and format, then try again." |

## Communication Errors

| Detected Keywords | User Message |
|------------------|--------------|
| "unable to open dm" / "could not determine current user" | "I couldn't send that direct message. Please make sure the user exists and try again." |
| "could not send" / "failed to send" | "I couldn't send that message. Please check the recipient and try again." |

## File & Media Errors

| Detected Keywords | User Message |
|------------------|--------------|
| "too large" / "size" | "That file is too large to process. Please try a smaller file or compress it first." |
| "unsupported" / "not supported" | "That file format isn't supported. Please try a different format." |
| "corrupt" / "invalid file" | "The file appears to be corrupted or unreadable. Please try a different file." |

## Database Errors

| Detected Keywords | User Message |
|------------------|--------------|
| "collection" + ("none" / "null") | "I couldn't access that information. Please try again or contact support if this persists." |
| "database" / "mongodb" | "I'm having trouble accessing your data right now. Please try again in a moment." |

## Error Detection Priority

The system checks errors in this order:

1. **Permission/Auth errors** (PermissionError, "auth", "credential")
2. **Not Found errors** ("not found", "404", "does not exist")
3. **Validation errors** (ValueError, "invalid", "missing")
4. **Rate Limiting** ("rate limit", "429", TimeoutError)
5. **Service errors** ("service", "connection", HTTP 5xx)
6. **CRUD operations** ("failed to create/update/delete")
7. **Communication** ("dm", "send")
8. **File/Media** ("file", "size", "format")
9. **Database** ("database", "collection")
10. **Tool-specific context** (adds based on tool name)

## How Tool-Specific Context Works

After determining the base error message, the system checks the tool name:

```python
if "gmail" in tool_name.lower():
    # Add Gmail-specific context
elif "calendar" in tool_name.lower():
    # Add Calendar-specific context
elif "slack" in tool_name.lower():
    # Add Slack-specific context
# ... etc
```

This ensures users get the most relevant, actionable guidance for each tool.

## Examples in Practice

### Example 1: Gmail Auth Error
```
Internal: "PermissionError: Gmail access denied: No credentials found for tool Gsuite"
→ Detected: PermissionError + "gmail" in tool name
→ User sees: "Your Gmail connection needs to be refreshed. Please reconnect Gmail in your settings."
```

### Example 2: Invalid Date
```
Internal: "ValueError: Invalid after_date format: 2024-13-45"
→ Detected: ValueError + "date" keyword
→ User sees: "The date format isn't recognized. Please use a format like 'YYYY-MM-DD' or '2024-01-15'."
```

### Example 3: Rate Limit
```
Internal: "RateLimitError: Rate limit exceeded for model gpt-4"
→ Detected: "rate limit" keyword
→ User sees: "We're experiencing high demand right now. Please wait 30 seconds and try again."
```

### Example 4: Notion Page Not Found
```
Internal: "ValueError: Invalid ID abc123. Not a valid database or page ID"
→ Detected: ValueError + "id" + "notion" in tool name
→ User sees: "That Notion page or database couldn't be found. Please check the page link or ID."
```

### Example 5: Slack Channel Not Found
```
Internal: "Exception: Channel #marketing not found"
→ Detected: "not found" + "channel" + "slack" in tool name
→ User sees: "That Slack channel doesn't exist or you're not a member. Please check the channel name."
```

## Testing Your Error Messages

Use this checklist to verify error handling:

- [ ] Disconnect a tool → See reconnection message
- [ ] Search non-existent item → See helpful "not found" message
- [ ] Use wrong date format → See date format example
- [ ] Try invalid parameter → See validation message
- [ ] Trigger rate limit → See wait time guidance
- [ ] Check terminal logs → See full error with stack trace
- [ ] Verify redaction → Tokens shown as `***REDACTED***`
- [ ] Check user message → No internal details exposed

## Quick Debugging Guide

When debugging errors:

1. **Check terminal logs** for full error details
2. **User message** shows what the user saw
3. **Tool name** tells you which integration failed
4. **Arguments** show what was passed (sensitive data redacted)
5. **Stack trace** shows exact line of failure
6. **User ID** helps track specific user issues

All this information is logged but never shown to users!










