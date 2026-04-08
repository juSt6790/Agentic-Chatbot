# Email Context Tools - Implementation Complete ✅

## 🎯 What Was Implemented

Three new tools that allow the AI to access rich contextual correlation data about emails from the `context_gmail` MongoDB collection.

---

## 📁 Files Created/Modified

### 1. **NEW FILE: `mcp_gmail/clients/mongo_context_client.py`**
- **Purpose**: MongoDB client for `context_gmail` collection
- **Functions**:
  - `get_email_context(email_ids, token, include_embeddings)` - Fetch context for specific email IDs
  - `search_context_by_text(query, token, limit)` - Search correlation text
  - `get_context_by_date_range(start_date, end_date, token, limit)` - Date-based context retrieval
- **Features**:
  - Multi-tenant support with token validation
  - Permission checking via `validate_user_tool_access()`
  - Follows same pattern as `mongo_email_client.py`

### 2. **MODIFIED: `mcp_gmail/app/cosi_app.py`**

#### Added Imports (line ~237):
```python
from clients.mongo_context_client import (
    get_email_context,
    search_context_by_text,
    get_context_by_date_range,
)
```

#### Added to Tools Registry (line ~469):
```python
# Email Context tools (AI-generated correlation data)
"get_email_context": lambda **kwargs: get_email_context(**kwargs),
"search_email_context": lambda **kwargs: search_context_by_text(**kwargs),
"get_email_context_by_date": lambda **kwargs: get_context_by_date_range(**kwargs),
```

#### Added Tool Definitions (line ~910):
```python
{
    "name": "get_email_context",
    "description": "Fetch AI-generated contextual correlation information for specific email IDs...",
    ...
},
{
    "name": "search_email_context",
    "description": "Search for email context using text search on AI-generated correlation data...",
    ...
},
{
    "name": "get_email_context_by_date",
    "description": "Fetch email context batches within a specific date range...",
    ...
}
```

### 3. **NOT MODIFIED: `mcp_gmail/app/server.py`**
- Following the pattern of `mongo_email_client.py`, we imported directly into `cosi_app.py`
- No server.py wrapper functions needed (this is cleaner!)

---

## 🔧 How It Works

### Architecture Flow:

```
User Query: "What tasks do I have from John's emails?"
         ↓
AI in cosi_app.py
         ↓
Step 1: search_emails(query="from:john", token=user_token)
        → Returns: [
            {"message_id": "19aa0c16ce014b61", "subject": "Re: Project Update", ...},
            {"message_id": "19aa08df4f11d670", "subject": "Meeting Notes", ...}
          ]
         ↓
Step 2: get_email_context(email_ids=["19aa0c16ce014b61", "19aa08df4f11d670"], token=user_token)
        → MongoDB Query: db.context_gmail.find({"email_ids": {"$in": ["19aa0c16ce014b61", ...]}})
        → Returns: {
            "matched_contexts": [{
              "correlation_text": 
                "[TASK] ID:19aa0c16ce014b61 Task:Get latest email and make a document Due:None\n
                 [PRIORITY] ID:19aa0c16ce014b61 Item:Creating document Urgency:medium\n
                 [COLLABORATOR] ID:19aa08df4f11d670 Name:John Smith Role:Project Lead\n
                 [EVENT] Type:meeting Desc:Project kickoff Date:2025-11-19"
            }]
          }
         ↓
Step 3: AI parses correlation_text and responds:
        "You have 1 task from John's emails:
         - Create a document from the latest email (Priority: Medium, Due: Not specified)
         
         Also, there's a project kickoff meeting scheduled for November 19, 2025."
```

---

## 🎨 Tool Descriptions for AI

### Tool 1: `get_email_context`

**When AI should use it:**
- After calling `search_emails()` or `get_emails()` to get deeper insights
- User asks about tasks, priorities, or context of specific emails
- Need to understand relationships between emails

**Parameters:**
- `email_ids` (required): List of email message IDs from previous search
- `include_embeddings` (optional): Whether to include vector embeddings (default: false)

**Example AI usage:**
```python
# User: "Tell me about the tasks in my recent emails from Sarah"

# Step 1: Get emails
emails = search_emails(query="from:sarah", limit=10, token=user_token)

# Step 2: Extract IDs
email_ids = [e["message_id"] for e in emails["messages"]]

# Step 3: Get context
context = get_email_context(email_ids=email_ids, token=user_token)

# Step 4: Parse tasks from correlation_text
for ctx in context["matched_contexts"]:
    text = ctx["correlation_text"]
    tasks = [line for line in text.split('\n') if line.startswith('[TASK]')]
    # Present tasks to user
```

---

### Tool 2: `search_email_context`

**When AI should use it:**
- User asks about specific topics without knowing email IDs
- Find all emails related to a project, person, or task
- Broader searches like "find urgent tasks" or "meetings with John"

**Parameters:**
- `query` (required): Search term (e.g., "urgent tasks", "project alpha", "meeting")
- `limit` (optional): Max results (default: 10)

**Example AI usage:**
```python
# User: "What urgent items do I have in my emails?"

context = search_email_context(query="urgent priority", token=user_token)

# Parse all [PRIORITY] and [TASK] entries with urgency:high or urgency:urgent
for ctx in context["matched_contexts"]:
    # Extract urgent items from correlation_text
    ...
```

---

### Tool 3: `get_email_context_by_date`

**When AI should use it:**
- User asks about emails or tasks from a specific time period
- "What was I working on last week?"
- "Show me all meetings from November"

**Parameters:**
- `start_date` (optional): YYYY-MM-DD format
- `end_date` (optional): YYYY-MM-DD format
- `limit` (optional): Max results (default: 50)

**Example AI usage:**
```python
# User: "What tasks did I have last week?"

import datetime
today = datetime.date.today()
last_week_start = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
last_week_end = today.strftime("%Y-%m-%d")

context = get_email_context_by_date(
    start_date=last_week_start,
    end_date=last_week_end,
    token=user_token
)

# Extract all [TASK] entries from correlation_text
...
```

---

## 📊 MongoDB Collection Schema

**Collection Name:** `context_gmail` (per tenant, e.g., `db["1100"]["context_gmail"]`)

**Sample Document:**
```json
{
  "_id": ObjectId("691f5c25c6a6f06e258a98f9"),
  "email_ids": ["19aa0cf00e8cb05b", "19aa0c16ce014b61", "19aa08df4f11d670"],
  "min_internalDateNum": 1763630235000,
  "max_internalDateNum": 1763634512000,
  "embedding_text": "[TASK] ID:19aa0c16ce014b61...\n[PRIORITY]...\n[COLLABORATOR]...",
  "embedding_vector": [0.123, -0.456, ...],  // 1024 dimensions
  "source": "gmail",
  "created_at": {"$date": "2025-11-20T18:21:25.123Z"},
  "updated_at": {"$date": "2025-11-20T18:21:25.123Z"}
}
```

**Key Fields:**
- `email_ids`: Array of 3 email IDs in the batch
- `embedding_text`: AI-generated correlation text with structured tags
- `min/max_internalDateNum`: Date range of emails in milliseconds
- `embedding_vector`: 1024-dim vector for semantic search (optional)

---

## 🏷️ Correlation Text Format

The `embedding_text` contains structured information:

### Tags Used:
- `[TASK]` - Action items from emails
- `[PRIORITY]` - Urgent/important items
- `[CROSS_TOOL]` - Links to Teams, Slack, etc.
- `[PROJECT]` - Project mentions
- `[COLLABORATOR]` - People involved
- `[EVENT]` - Meetings and scheduled activities

### Example:
```
[TASK] ID:19aa0c16ce014b61 Task:Get latest email from Kanishka and make a document Due:None Source:Email Status:open Priority:unknown 

[CROSS_TOOL] ID:19aa08df4f11d670 Desc:Microsoft Teams meeting link provided Tools:Gmail, Microsoft Teams Links:https://teams.microsoft.com/...

[PRIORITY] ID:19aa0c16ce014b61 Item:Creating a document from Kanishka's latest email Urgency:medium Reason:Task is explicitly mentioned as an action point.

[PROJECT] ID:19aa08df4f11d670 Name:Unified Workspace: General discussion Context:Scheduled meeting to discuss queries.

[COLLABORATOR] ID:19aa08df4f11d670 Name:Jheel Choudhury Role:Teammate overall_tone_Sentiment_and_Equation:neutral Interaction_Summary:Jheel forwarded meeting invite.

[EVENT] Type:meeting Desc:Unified Workspace general discussion Date:2025-11-19
```

---

## ✅ Testing Checklist

1. **Import Test:**
   ```bash
   cd /home/popo/work/work/trelloOpen
   python -c "from clients.mongo_context_client import get_email_context; print('✅')"
   ```

2. **Tool Registry Test:**
   ```python
   from app.cosi_app import tools
   assert "get_email_context" in tools
   assert "search_email_context" in tools
   assert "get_email_context_by_date" in tools
   print("✅ All tools registered")
   ```

3. **AI Call Test:**
   Start cosi_app and ask:
   ```
   "Get context for email ID 19aa0c16ce014b61"
   ```
   Expected: AI calls `get_email_context()` and returns correlation data

4. **Search Test:**
   ```
   "Find all emails mentioning urgent tasks"
   ```
   Expected: AI calls `search_email_context(query="urgent tasks")`

5. **Date Range Test:**
   ```
   "What was I working on last week?"
   ```
   Expected: AI calls `get_email_context_by_date()` with appropriate dates

---

## 🚀 Ready to Use!

The implementation is complete and follows the exact same pattern as `mongo_email_client.py`:

✅ Direct import in `cosi_app.py` (not through `server.py`)  
✅ Added to tools registry  
✅ Tool definitions with proper descriptions  
✅ Multi-tenant support  
✅ Token validation  
✅ Permission checking  

The AI can now call these tools to get rich contextual information about emails! 🎉









