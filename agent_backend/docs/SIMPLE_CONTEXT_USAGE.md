# Email Context Tool - Simple Usage Guide

## 🎯 What It Does (Simplified)

You have **ONE tool**: `get_email_context(email_ids)`

It's super simple:
1. You call `search_emails()` to get emails → You get email IDs back
2. You call `get_email_context(email_ids)` → You get extra correlation data for those IDs
3. Done!

---

## 📋 The Flow

```
User: "What tasks do I have from John's emails?"
    ↓
Step 1: Get emails normally
    search_emails(query="from:john", token=user_token)
    → Returns: {
        "messages": [
            {"message_id": "19aa0c16ce014b61", "subject": "Re: Project", ...},
            {"message_id": "19aa08df4f11d670", "subject": "Meeting", ...}
        ]
    }
    ↓
Step 2: Extract the IDs
    email_ids = ["19aa0c16ce014b61", "19aa08df4f11d670"]
    ↓
Step 3: Get extra context for those IDs
    get_email_context(email_ids=email_ids, token=user_token)
    → Looks up these IDs in context_gmail collection
    → Returns: {
        "matched_contexts": [{
            "email_ids_in_batch": ["19aa0c16ce014b61", "19aa08df4f11d670", ...],
            "correlation_text": 
                "[TASK] ID:19aa0c16ce014b61 Task:Create document Due:None
                 [PRIORITY] ID:19aa0c16ce014b61 Item:Document creation Urgency:medium
                 [COLLABORATOR] ID:19aa08df4f11d670 Name:John Smith Role:Lead"
        }]
    }
    ↓
Step 4: Present to user
    "You have 1 task from John: Create document (Priority: Medium)"
```

---

## 🔧 What the Tool Does

**`get_email_context(email_ids)`:**
- Takes email IDs you got from `search_emails()`
- Looks them up in the `context_gmail` MongoDB collection
- Returns any extra correlation data if found
- That's it!

**What it returns:**
- Tasks extracted from those emails
- Priority levels
- Projects mentioned
- Collaborators involved
- Cross-tool links (Teams, Slack, etc.)
- Events and meetings

---

## 💡 Code Example

```python
# Step 1: User asks about emails
user_query = "Show me John's emails from last week"

# Step 2: AI calls normal email search
emails = search_emails(
    query="from:john",
    start_date="2025-11-13",
    end_date="2025-11-20",
    token=user_token
)

# Step 3: Extract email IDs from results
email_ids = [msg["message_id"] for msg in emails["messages"]]
# email_ids = ["19aa0c16ce014b61", "19aa08df4f11d670", "19aa0cf00e8cb05b"]

# Step 4: Get extra context for those IDs
context = get_email_context(email_ids=email_ids, token=user_token)

# Step 5: Check what extra info we got
if context["total_matches"] > 0:
    for ctx in context["matched_contexts"]:
        print("Extra context found:")
        print(ctx["correlation_text"])
        # Shows: [TASK] ..., [PRIORITY] ..., [COLLABORATOR] ..., etc.
else:
    print("No extra context found for these emails")
```

---

## 📊 What's in context_gmail Collection

The collection stores **batches of 3 emails** with AI-generated analysis:

```json
{
  "email_ids": ["19aa0c16ce014b61", "19aa08df4f11d670", "19aa0cf00e8cb05b"],
  "embedding_text": "
    [TASK] ID:19aa0c16ce014b61 Task:Create doc Due:None
    [PRIORITY] ID:19aa0c16ce014b61 Item:Doc creation Urgency:medium
    [COLLABORATOR] ID:19aa08df4f11d670 Name:John Role:Lead
    [EVENT] Type:meeting Desc:Project sync Date:2025-11-19
  ",
  "min_internalDateNum": 1763630235000,
  "max_internalDateNum": 1763634512000
}
```

When you pass `email_ids=["19aa0c16ce014b61"]`, it finds any batch that contains that ID and returns the correlation text.

---

## ✅ What Was Implemented

**File:** `mcp_gmail/app/cosi_app.py`

**Import:**
```python
from clients.mongo_context_client import get_email_context
```

**Tool Registry:**
```python
"get_email_context": lambda **kwargs: get_email_context(**kwargs),
```

**Tool Definition:**
```python
{
    "name": "get_email_context",
    "description": "Fetch extra AI-generated correlation information for email IDs...",
    "parameters": {
        "type": "object",
        "properties": {
            "email_ids": {
                "type": "array",
                "items": {"type": "string"},
            }
        },
        "required": ["email_ids"],
    },
}
```

---

## 🎯 That's It!

- **One tool**: `get_email_context(email_ids)`
- **Simple flow**: Search emails → Get IDs → Get context → Done
- **No direct searching in context_gmail** - Just ID lookups
- **Automatic enrichment** - AI gets extra task/priority/collaboration info

The AI can now enrich any email results with correlation data! 🚀









