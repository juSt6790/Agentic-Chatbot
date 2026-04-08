# Gmail Briefing Tools Implementation

## Summary
Added new Gmail and Calendar briefing fetching tools to provide AI-generated summaries as additional context for the AI assistant.

## Files Created

### 1. `/mcp_gmail/clients/mongo_briefing_client.py`
New module that provides functions to fetch the latest briefings from MongoDB.

**Functions:**
- `get_latest_gmail_briefing(token, include_metadata=True)` - Fetches the latest Gmail briefing
- `get_latest_calendar_briefing(token, include_metadata=True)` - Fetches the latest Calendar briefing  
- `get_all_latest_briefings(token, sources=None)` - Fetches briefings from multiple sources at once

**Features:**
- ✅ Validates user access to GSuite tools
- ✅ Retrieves briefings from MongoDB `briefing` collection
- ✅ Returns latest briefing sorted by timestamp
- ✅ Includes debug logging to terminal (prints when fetching)
- ✅ Handles errors gracefully with detailed error messages

## Files Modified

### 2. `/mcp_gmail/app/cosi_app.py`

**Changes:**

#### a) Added imports (lines 247-251):
```python
from clients.mongo_briefing_client import (
    get_latest_gmail_briefing,
    get_latest_calendar_briefing,
    get_all_latest_briefings,
)
```

#### b) Added tools to registry (lines ~478 and ~501):
```python
# Email Briefing tool - Get latest Gmail briefing
"get_latest_gmail_briefing": lambda **kwargs: get_latest_gmail_briefing(**kwargs),

# Calendar Briefing tool - Get latest Calendar briefing
"get_latest_calendar_briefing": lambda **kwargs: get_latest_calendar_briefing(**kwargs),
```

#### c) Added tool schemas (after line ~948 and ~1201):
- `get_latest_gmail_briefing` - Tool definition with description and parameters
- `get_latest_calendar_briefing` - Tool definition with description and parameters

#### d) Updated system prompt (line ~5502):
Added guidance for AI to use briefing tools when user asks for summaries/overviews

#### e) Updated tool priority (line ~4537):
Made briefing tools highest priority (priority 0) so they don't get truncated

## How It Works

### Data Flow:
1. **Background Process** → Generates briefings periodically (via `generate_gmail_briefing.py`)
2. **MongoDB Storage** → Briefings stored in `{user_id}.briefing` collection
3. **API Tool Call** → AI calls `get_latest_gmail_briefing` when user asks for email summary
4. **Fetch & Return** → Tool fetches latest briefing from MongoDB and returns to AI
5. **AI Response** → AI uses briefing content to answer user's question

### MongoDB Schema:
```javascript
{
  user_id: "1234",
  source: "gmail",  // or "calendar"
  briefing: "AI-generated briefing text...",
  save_timestamp: "2025-12-21T10:30:00Z",
  save_date: "2025-12-21",
  user_prefs: { ... }  // optional
}
```

## Debug Output
When the tool is called, you'll see terminal output like:
```
📧 [DEBUG] Fetching latest Gmail briefing from MongoDB...
   [DEBUG] Resolved user_id: 1234
✅ [DEBUG] Successfully fetched Gmail briefing
   [DEBUG] Briefing timestamp: 2025-12-21T10:30:00Z
   [DEBUG] Briefing date: 2025-12-21
   [DEBUG] Briefing length: 1523 characters
```

## Usage Examples

### For Users:
- "Give me a briefing of my emails"
- "What's happening in my inbox?"
- "Summarize my recent emails"
- "Show me my calendar briefing"
- "What meetings do I have coming up?"

### For AI:
The AI will automatically call:
- `get_latest_gmail_briefing()` for email summaries
- `get_latest_calendar_briefing()` for calendar summaries

## Testing

To test the implementation:

1. **Check if briefing exists in MongoDB:**
   ```javascript
   use 1234  // your user_id
   db.briefing.find({source: "gmail"}).sort({save_timestamp: -1}).limit(1)
   ```

2. **Test via API:**
   - Send a chat request asking for "email briefing"
   - Check terminal logs for debug output
   - Verify AI receives and uses the briefing content

3. **Verify tool is available:**
   - Check that `get_latest_gmail_briefing` appears in tools list
   - Verify it has high priority (priority 0)

## Related Files

### Briefing Generation (Background):
- `/unified_streaming_app/tasks/generate_gmail_briefing.py` - Generates Gmail briefings
- `/unified_streaming_app/tasks/fetch_briefing.py` - Generates Calendar briefings

### Context Tools (Similar Pattern):
- `/mcp_gmail/clients/mongo_context_client.py` - Email/Calendar context tools (existing)

## Notes

- Briefings are generated in the background by Celery tasks
- Briefings are stored in MongoDB and cached in Redis
- The tool fetches from MongoDB (not Redis) for consistency
- User must have GSuite tool access to fetch briefings
- If no briefing exists, returns a message indicating no briefing found


