# MongoDB Projection Error Fix

## 🐛 The Error

```
Cannot do exclusion on field embedding_vector in inclusion projection
Code: 31254
```

## 🔍 What Went Wrong

In `get_email_context()` function, we were mixing **inclusion** and **exclusion** in the same MongoDB projection:

```python
# ❌ BAD - Mixing inclusion and exclusion
projection = {
    "_id": 1,              # inclusion
    "email_ids": 1,        # inclusion
    "embedding_text": 1,   # inclusion
    ...
    "embedding_vector": 0  # exclusion - MONGODB DOESN'T ALLOW THIS MIX!
}
```

## ✅ The Fix

**Rule:** In MongoDB, you can either:
- Include specific fields: `{"field1": 1, "field2": 1}` (only these fields returned)
- Exclude specific fields: `{"field1": 0, "field2": 0}` (all fields EXCEPT these returned)
- **BUT you can't mix them!** (except for `_id` which is special)

**Fixed code:**
```python
# ✅ GOOD - Only inclusion, conditionally add embedding_vector
projection = {
    "_id": 1,
    "email_ids": 1,
    "embedding_text": 1,
    "min_internalDateNum": 1,
    "max_internalDateNum": 1,
    "source": 1,
    "created_at": 1,
    "updated_at": 1
}

# Only add embedding_vector if needed (don't exclude it explicitly)
if include_embeddings:
    projection["embedding_vector"] = 1
```

## 📊 About Embeddings

**Q: Do we need to read embeddings to understand the content?**

**A: No!** The embeddings are just for vector similarity matching, not for reading. Here's what we have:

1. **`embedding_text`** (string) - This is what we READ
   - Contains human-readable correlation data
   - Example: `"[TASK] Create doc [PRIORITY] Medium [COLLABORATOR] John"`
   - This is what the AI processes and shows to the user

2. **`embedding_vector`** (array of 1024 floats) - This is for MATCHING
   - Contains: `[0.123, -0.456, 0.789, ...]` (1024 numbers)
   - Used ONLY for vector similarity search (cosine similarity)
   - NOT human-readable, NOT processed by AI in our use case
   - We DON'T need this for simple ID lookups!

## 🎯 Our Use Case

When calling `get_email_context(email_ids)`:

1. We look up email IDs in the `context_gmail` collection
2. We return the `embedding_text` field (human-readable correlation data)
3. We **DON'T need** `embedding_vector` because:
   - We're doing direct ID lookup, not similarity search
   - The text already contains all the info (tasks, priorities, etc.)
   - Vector is only useful if we were doing "find similar emails" type queries

## 🔧 What's Fixed

**File:** `mcp_gmail/clients/mongo_context_client.py`

**Line 100-121:** Fixed the projection to not exclude `embedding_vector`, just omit it when not needed.

**Result:** The `get_email_context()` tool now works correctly! ✅

## 🚀 Testing

Try again:
```python
get_email_context(
    email_ids=["19b07b9173b5819e", "19b0792ac9cc3e2d"],
    token="602f56de-70a8-4330-bf2a-bd5c1e716843"
)
```

Should now return successfully with the correlation text data!









