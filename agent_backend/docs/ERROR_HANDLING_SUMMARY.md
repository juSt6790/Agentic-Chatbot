# Error Handling Implementation Summary

## Overview

We've implemented a comprehensive error handling system that:
1. **Logs full error details** to terminal/logs for debugging
2. **Shows user-friendly messages** to users without exposing internal details

## What Was Changed

### 1. Created Centralized Error Handler (`mcp_gmail/utils/error_handler.py`)

A new utility module that provides:

- **`log_error_to_terminal()`**: Logs full error details with stack traces to terminal/logs
  - Includes error type, message, context, tool name, arguments, user ID
  - Sanitizes sensitive data (tokens, passwords, API keys) before logging
  - Includes full stack trace for debugging

- **`get_user_friendly_error_message()`**: Returns generic, user-friendly messages
  - Maps specific error types to appropriate generic messages
  - Never exposes: API endpoints, tool names, model names, credentials, internal paths
  - Examples:
    - Instead of: "Error: MongoDB connection failed at mongodb://internal-server:27017"
    - Shows: "I encountered an issue while performing that action. Please try again."

- **`handle_tool_error()`**: Handles tool execution errors
  - Logs full error to terminal
  - Returns standardized error response with user-friendly message

- **`handle_api_error()`**: Handles API invocation errors (OpenAI, Bedrock)
  - Logs full error to terminal
  - Returns standardized error response without exposing API details

- **`wrap_tool_execution()`**: Wraps tool execution with automatic error handling
  - Catches all exceptions during tool execution
  - Automatically logs to terminal and returns user-friendly response

### 2. Updated `mcp_gmail/app/cosi_app.py`

#### Tool Invocation (Both `/chat` and `/autoPilot` endpoints)

**Before:**
```python
try:
    result = tools[name](**args)
    # ...
except Exception as e:
    return jsonify({
        "message": f"❌ Error during tool call {name}: {str(e)}"
    })
```

**After:**
```python
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
        # Log already happened in wrap_tool_execution
        # Return user-friendly error to client
        return jsonify({
            "message": result.get("message", "❌ Something went wrong. Please try again.")
        })
    # ...
except Exception as e:
    # Catch any unexpected exceptions
    log_error_to_terminal(error=e, context=f"Unexpected error in tool call: {name}", ...)
    user_message = get_user_friendly_error_message(e, "tool_execution")
    return jsonify({"message": f"❌ {user_message}"})
```

#### OpenAI API Error Handling

**Before:**
```python
except Exception as e:
    logger.error("OpenAI invocation attempt %d failed: %s", retries, str(e))
    return jsonify({
        "message": f"❌ Error invoking OpenAI: {str(e)}"
    })
```

**After:**
```python
except Exception as e:
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
        return jsonify(error_response)
```

#### Bedrock API Error Handling

Same pattern as OpenAI - full errors logged, generic messages shown.

#### Image & PDF Analysis Error Handling

**Before:**
```python
except Exception as e:
    logger.error("Image analysis error: %s", str(e))
    file_analyses.append(f"❌ Error analyzing image {filename}: {str(e)}")
```

**After:**
```python
except Exception as e:
    # Log full error to terminal
    log_error_to_terminal(
        error=e,
        context=f"Image analysis failed for file: {filename}",
        user_id=token
    )
    # Show user-friendly message
    file_analyses.append(f"❌ Unable to analyze image {filename}. Please try again.")
```

## Generic Error Messages Used

The system uses these categories of user-friendly messages:

- **tool_execution**: "I encountered an issue while performing that action. Please try again or rephrase your request."
- **api_error**: "I'm having trouble connecting to the service right now. Please try again in a moment."
- **authentication**: "There seems to be an authentication issue. Please check your connection and try again."
- **permission**: "I don't have the necessary permissions to complete that action."
- **not_found**: "I couldn't find what you're looking for. Could you provide more details?"
- **validation**: "The information provided doesn't seem quite right. Could you check and try again?"
- **timeout**: "That's taking longer than expected. Please try again."
- **rate_limit**: "We're experiencing high demand right now. Please wait a moment and try again."
- **general**: "Something went wrong while processing your request. Please try again."

## What Gets Logged vs What Users See

### Example 1: Tool Error

**Logged to Terminal:**
```
[ERROR] {
  'error_type': 'ValueError',
  'error_message': 'Database connection failed: mongodb://internal-server:27017/db_name',
  'context': 'Tool execution failed: search_emails',
  'tool_name': 'search_emails',
  'tool_args': {'query': 'test', 'token': '***REDACTED***'},
  'user_id': 'user123'
}
Traceback:
  File "cosi_app.py", line 5656, in assistant
    result = wrap_tool_execution(...)
  ...
```

**Shown to User:**
```
❌ I encountered an issue while performing that action. Please try again or rephrase your request.
```

### Example 2: API Error

**Logged to Terminal:**
```
[ERROR] {
  'error_type': 'RateLimitError',
  'error_message': 'Rate limit exceeded for model gpt-4 in organization org-abc123',
  'context': 'OpenAI API invocation attempt 3/3 failed',
  'user_id': 'user123'
}
Traceback:
  ...
```

**Shown to User:**
```
❌ We're experiencing high demand right now. Please wait a moment and try again.
```

## Benefits

1. **Security**: No internal implementation details exposed to users
2. **User Experience**: Clear, friendly messages instead of technical errors
3. **Debugging**: Full error details with stack traces in logs for developers
4. **Privacy**: Sensitive data (tokens, credentials) automatically redacted from logs
5. **Consistency**: All errors handled uniformly across the application

## Do You Need to Change Individual Tool Files?

**No, you don't need to modify individual tool files** (in `services/` folder) because:

1. Tool errors are now caught and handled at the top level in `cosi_app.py`
2. The `wrap_tool_execution()` function catches all exceptions from any tool
3. Errors are automatically logged and converted to user-friendly messages

However, if you want tools to return more specific error information for internal logging, you can make them raise exceptions with detailed messages. These will be logged but not shown to users.

## Testing

To verify the implementation:

1. Trigger a tool error (e.g., invalid parameters)
2. Check terminal/logs - should see full error details with stack trace
3. Check user response - should see generic friendly message
4. Verify no API endpoints, tool names, or credentials are exposed to user

## Files Modified

- ✅ `mcp_gmail/utils/error_handler.py` (NEW)
- ✅ `mcp_gmail/app/cosi_app.py` (UPDATED)
  - Added error handler imports
  - Updated tool invocation in `/chat` endpoint
  - Updated tool invocation in `/autoPilot` endpoint
  - Updated OpenAI API error handling
  - Updated Bedrock API error handling
  - Updated image/PDF analysis error handling

## Next Steps (Optional)

If you want even more control, you could:

1. Add custom error messages for specific tools
2. Implement error recovery mechanisms (retry logic, fallbacks)
3. Add error analytics/monitoring
4. Create user-facing error codes for support tickets
5. Add localization for error messages in different languages

But the current implementation provides solid, production-ready error handling that:
- Protects sensitive information
- Helps debugging with detailed logs
- Provides good user experience with friendly messages










