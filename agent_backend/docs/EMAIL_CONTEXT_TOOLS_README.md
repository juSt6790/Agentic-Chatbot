# Email Context Tools Documentation

## Overview

These new tools provide AI-generated contextual correlation information about emails. They work with the `context_gmail` MongoDB collection which contains preprocessed email batches analyzed for:

- **Tasks** - Action items mentioned in emails
- **Cross-tool relationships** - Links to Teams, Slack, etc.
- **Priority items** - Important or urgent matters
- **Projects** - Project mentions and context
- **Collaborators** - People involved and their roles
- **Events** - Meetings and scheduled activities

## MongoDB Schema

The `context_gmail` collection stores batches of 3 emails with their correlation analysis:

```json
{
  "_id": ObjectId,
  "email_ids": ["19aa0cf00e8cb05b", "19aa0c16ce014b61", "19aa08df4f11d670"],
  "min_internalDateNum": 1763630235000,
  "max_internalDateNum": 1763634512000,
  "embedding_text": "[TASK] ID:19aa0c16ce014b61 Task:Get latest email...",
  "embedding_vector": [0.123, -0.456, ...],
  "source": "gmail",
  "created_at": "2025-11-20T18:21:25.123Z",
  "updated_at": "2025-11-20T18:21:25.123Z"
}
```

## Available Tools

### 1. `get_email_context_info`

**Purpose**: Fetch correlation information for specific email IDs

**Use Case**: After querying emails, use this to get rich context about tasks, priorities, and relationships

**Parameters**:
- `email_ids` (List[str]): List of email message IDs
- `token` (str): User authentication token
- `include_embeddings` (bool): Whether to include embedding vectors (default: False)

**Example Usage**:
```python
# Step 1: Query emails
emails = query_emails(query="project alpha meeting", token=user_token)

# Step 2: Extract email IDs
email_ids = [msg["message_id"] for msg in emails["messages"]]

# Step 3: Get context for those emails
context = get_email_context_info(email_ids=email_ids, token=user_token)

# Step 4: Review correlation information
for ctx in context["matched_contexts"]:
    print(ctx["correlation_text"])
    # Shows: Tasks, priorities, collaborators, events, etc.
```

**Response Format**:
```json
{
  "success": true,
  "matched_contexts": [
    {
      "context_id": "691f5c25c6a6f06e258a98f9",
      "email_ids_in_batch": ["19aa0cf00e8cb05b", "19aa0c16ce014b61", "19aa08df4f11d670"],
      "correlation_text": "[TASK] ID:19aa0c16ce014b61 Task:Get latest email from Kanishka...\n[PRIORITY] Item:Creating a document...",
      "date_range": {
        "earliest_email": "2025-11-19T10:30:35.000Z",
        "latest_email": "2025-11-19T11:41:52.000Z"
      },
      "source": "gmail"
    }
  ],
  "total_matches": 1,
  "email_ids_queried": ["19aa0c16ce014b61"]
}
```

---

### 2. `search_email_context`

**Purpose**: Search for emails by topics, tasks, or collaborators mentioned in correlation text

**Use Case**: Find all emails related to specific tasks, projects, or people without knowing exact email IDs

**Parameters**:
- `query` (str): Text to search for
- `token` (str): User authentication token
- `limit` (int): Maximum results (default: 10)

**Example Usage**:
```python
# Find all email batches mentioning "urgent tasks"
context = search_email_context(
    query="urgent tasks",
    token=user_token,
    limit=20
)

# Find emails related to a project
context = search_email_context(
    query="Unified Workspace project",
    token=user_token
)

# Find emails involving a specific person
context = search_email_context(
    query="Jheel Choudhury",
    token=user_token
)
```

**Response Format**:
```json
{
  "success": true,
  "matched_contexts": [
    {
      "context_id": "691f5c25c6a6f06e258a98f9",
      "email_ids_in_batch": ["19aa0cf00e8cb05b", "19aa0c16ce014b61"],
      "correlation_text": "[TASK] ...\n[COLLABORATOR] Name:Jheel Choudhury...",
      "date_range": { ... },
      "relevance_score": 5.2
    }
  ],
  "total_matches": 5,
  "query": "Jheel Choudhury"
}
```

---

### 3. `get_email_context_by_date`

**Purpose**: Get context for emails within a specific date range

**Use Case**: Understand tasks, projects, and collaborations during a time period

**Parameters**:
- `start_date` (str): Start date (YYYY-MM-DD format)
- `end_date` (str): End date (YYYY-MM-DD format)
- `token` (str): User authentication token
- `limit` (int): Maximum results (default: 50)

**Example Usage**:
```python
# Get November 2025 email context
context = get_email_context_by_date(
    start_date="2025-11-01",
    end_date="2025-11-30",
    token=user_token
)

# Get last week's context
context = get_email_context_by_date(
    start_date="2025-11-13",
    end_date="2025-11-20",
    token=user_token
)
```

---

## AI Workflow Example

Here's how an AI agent would use these tools:

### Scenario: "What tasks do I have from Kanishka's emails?"

```python
# Step 1: Search for emails from Kanishka
emails = query_emails(
    query="from:kanishka",
    max_results=10,
    token=user_token
)

# Step 2: Extract email IDs
email_ids = [msg["message_id"] for msg in emails["messages"]]

# Step 3: Get rich context about those emails
context = get_email_context_info(
    email_ids=email_ids,
    token=user_token
)

# Step 4: Parse and present tasks
for ctx in context["matched_contexts"]:
    correlation_text = ctx["correlation_text"]
    
    # Extract [TASK] entries
    tasks = [line for line in correlation_text.split('\n') 
             if line.startswith('[TASK]')]
    
    # Present to user
    print("Tasks from Kanishka's emails:")
    for task in tasks:
        print(f"  - {task}")
```

### Output:
```
Tasks from Kanishka's emails:
  - [TASK] ID:19aa0c16ce014b61 Task:Get latest email from Kanishka and make a document Due:None Source:Email Status:open Priority:unknown
```

---

## Correlation Text Format

The `embedding_text` field contains structured information:

### [TASK] Format
```
[TASK] ID:<email_id> Task:<description> Due:<date> Source:<source> Status:<status> Priority:<priority>
```

### [CROSS_TOOL] Format
```
[CROSS_TOOL] ID:<email_id> Desc:<description> Tools:<tool1, tool2> Links:<url>
```

### [PRIORITY] Format
```
[PRIORITY] ID:<email_id> Item:<description> Urgency:<level> Reason:<explanation>
```

### [PROJECT] Format
```
[PROJECT] ID:<email_id> Name:<project_name> Context:<description>
```

### [COLLABORATOR] Format
```
[COLLABORATOR] ID:<email_id> Name:<person_name> Role:<role> overall_tone_Sentiment_and_Equation:<tone> Interaction_Summary:<summary>
```

### [EVENT] Format
```
[EVENT] Type:<meeting/call/etc> Desc:<description> Date:<date>
```

---

## Implementation Files

1. **`mcp_gmail/clients/mongo_context_client.py`**
   - Core functions: `get_email_context()`, `search_context_by_text()`, `get_context_by_date_range()`
   - Handles MongoDB queries to `context_gmail` collection
   - Token validation and multi-tenant support

2. **`mcp_gmail/app/server.py`**
   - Tool wrappers: `get_email_context_info()`, `search_email_context()`, `get_email_context_by_date()`
   - Registered with MCP Gmail server via `@tool()` decorator
   - Automatically available in `cosi_app.py`

---

## Integration Flow

```
User Query
    ↓
AI in cosi_app.py
    ↓
Calls query_emails() → Gets email IDs
    ↓
Calls get_email_context_info(email_ids) → Gets correlation data
    ↓
Parses [TASK], [PRIORITY], [COLLABORATOR] entries
    ↓
Returns enriched response to user
```

---

## Benefits

1. **Richer Context**: AI can understand relationships between emails
2. **Task Extraction**: Automatically identifies action items
3. **Priority Awareness**: Knows what's urgent vs. informational
4. **Cross-tool Integration**: Discovers links to Teams, Slack, etc.
5. **Collaboration Insights**: Understands who's involved and their roles
6. **Event Detection**: Identifies meetings and scheduled activities

---

## Testing

To test the new tools:

```bash
# Start the server
cd /home/popo/work/work/trelloOpen
python -m app.cosi_app

# In another terminal or via API:
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Get context for email ID 19aa0c16ce014b61",
    "unified_token": "your_token_here"
  }'
```

The AI should now be able to call `get_email_context_info` and provide rich context about the email!









