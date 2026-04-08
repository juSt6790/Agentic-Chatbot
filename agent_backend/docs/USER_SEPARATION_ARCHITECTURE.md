# User Separation Architecture

## How 50 Users Can Use 1 VM Instance Without Data Mixing

### Overview
Your Flask application runs as a **single process** on one VM, but handles **multiple concurrent users** by using **token-based separation** in memory.

---

## 🔑 Key Mechanism: Token-Based Dictionary Keys

### 1. **Memory Structure** (RAM)

```python
# In app/cosi_app.py (lines 103-104)
user_conversations = defaultdict(lambda: deque(maxlen=12))  # Short-term memory
long_term_memory = defaultdict(list)                        # Long-term memory
user_cache = {}                                             # User profile cache
```

**How it works:**
- These are **Python dictionaries** where the **key is the user's token**
- Each user has a **unique token** (from Authorization header)
- Dictionary lookup: `user_conversations[token]` → returns that user's conversation history
- Dictionary lookup: `long_term_memory[token]` → returns that user's summaries

### 2. **Token Extraction** (Per Request)

```python
# In app/cosi_app.py (lines 390-412)
def get_token():
    token = request.headers.get("Authorization")
    # ... parsing logic ...
    return raw, None, None  # Returns the unique token
```

**Flow:**
1. User sends HTTP request with `Authorization: Bearer <unique_token>`
2. Flask extracts token from request headers
3. Token is used as dictionary key to access user-specific data

### 3. **User-Specific Data Access** (In Handlers)

```python
# In app/assistant_handler.py (line 591)
conversation_history = user_conversations[token]  # Gets THIS user's history only

# In app/assistant_handler.py (line 605)
long_term_memory[token].append(summary_json)      # Stores in THIS user's memory
```

**Example with 3 users:**

```
user_conversations = {
    "token_user1": deque([msg1, msg2, msg3]),      # User 1's conversations
    "token_user2": deque([msg4, msg5]),            # User 2's conversations  
    "token_user3": deque([msg6, msg7, msg8, msg9]) # User 3's conversations
}

long_term_memory = {
    "token_user1": [summary1, summary2],           # User 1's summaries
    "token_user2": [summary3],                     # User 2's summaries
    "token_user3": [summary4, summary5, summary6]  # User 3's summaries
}
```

---

## 🔄 How Concurrent Requests Work

### Flask's Request Handling

1. **Single Process, Multiple Threads:**
   - Flask runs in **one Python process**
   - Each HTTP request is handled in a **separate thread** (or async context)
   - Flask's WSGI server (e.g., Werkzeug) manages thread pool

2. **Request Isolation:**
   ```
   Request 1 (User A): token="abc123" → user_conversations["abc123"]
   Request 2 (User B): token="xyz789" → user_conversations["xyz789"]
   Request 3 (User A): token="abc123" → user_conversations["abc123"] (same user, same data)
   ```

3. **No Data Mixing Because:**
   - Each request extracts its own token
   - Dictionary key (token) ensures data isolation
   - Python dictionaries are thread-safe for reads
   - Each thread accesses different dictionary keys

---

## 📊 Memory Structure Visualization

### For 50 Concurrent Users:

```
RAM Memory (Single Process):
┌─────────────────────────────────────────────────────────┐
│ user_conversations (defaultdict)                        │
├─────────────────────────────────────────────────────────┤
│ "token_user1"  → deque([msg1, msg2, ...])              │
│ "token_user2"  → deque([msg3, msg4, ...])              │
│ "token_user3"  → deque([msg5, msg6, ...])              │
│ ...                                                     │
│ "token_user50" → deque([msg99, msg100, ...])            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ long_term_memory (defaultdict)                          │
├─────────────────────────────────────────────────────────┤
│ "token_user1"  → [summary1, summary2, ...]             │
│ "token_user2"  → [summary3, ...]                        │
│ ...                                                     │
│ "token_user50" → [summary98, summary99, ...]           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ user_cache (dict)                                       │
├─────────────────────────────────────────────────────────┤
│ "token_user1"  → {data: {...}, expires_at: 1234567890} │
│ "token_user2"  → {data: {...}, expires_at: 1234567891} │
│ ...                                                     │
│ "token_user50" → {data: {...}, expires_at: 1234567892} │
└─────────────────────────────────────────────────────────┘
```

---

## ⚠️ Important Notes

### 1. **Thread Safety**
- **Reads are safe:** Dictionary lookups are atomic in Python
- **Writes need caution:** If same user sends multiple simultaneous requests, there could be race conditions
- **Current implementation:** Works fine for typical use (users don't usually send 10 requests at exact same millisecond)

### 2. **Memory Limits**
- Each user's conversation: max 12 messages (deque maxlen=12)
- Each user's long-term memory: max 20 summaries (line 607, 758)
- **Total memory:** ~50 users × (12 messages + 20 summaries) = manageable

### 3. **Data Persistence**
- **RAM-only:** Data is lost on server restart
- **Not persisted to disk:** Conversations are in-memory only
- **MongoDB:** User profiles, chat history saved to MongoDB (separate from RAM memory)

### 4. **Token Uniqueness**
- **Critical:** Each user MUST have a unique token
- **If tokens collide:** Users would see each other's data (security issue!)
- **Your responsibility:** Ensure token generation/validation is unique per user

---

## 🔍 Code Flow Example

### When User 1 sends a request:

```python
# 1. Request arrives
POST /chat
Headers: Authorization: Bearer token_user1

# 2. Token extracted (assistant_handler.py line 46)
token = "token_user1"

# 3. User-specific memory accessed (assistant_handler.py line 591)
conversation_history = user_conversations["token_user1"]
# Returns: deque([msg1, msg2, msg3])  ← Only User 1's messages

# 4. Long-term memory accessed (assistant_handler.py line 605)
long_term_memory["token_user1"].append(new_summary)
# Stores in User 1's memory only

# 5. Response sent back to User 1
# User 2, 3, 4... never see User 1's data
```

### When User 2 sends a request (simultaneously):

```python
# 1. Different request, different token
POST /chat
Headers: Authorization: Bearer token_user2

# 2. Different token extracted
token = "token_user2"

# 3. Different memory accessed
conversation_history = user_conversations["token_user2"]
# Returns: deque([msg4, msg5])  ← Only User 2's messages

# 4. Completely isolated from User 1
```

---

## ✅ Summary

**How 50 users work on 1 VM without mixing:**

1. ✅ **Token-based keys:** Each user's token = unique dictionary key
2. ✅ **Dictionary separation:** `user_conversations[token]` isolates each user's data
3. ✅ **Flask threading:** Each request handled in separate thread with its own token
4. ✅ **No shared state:** Each user accesses different dictionary entries
5. ✅ **Memory limits:** Bounded by deque maxlen and summary limits

**The system works because:**
- Python dictionaries use hash tables (O(1) lookup)
- Token uniqueness ensures key separation
- Flask's request context isolates each HTTP request
- Dictionary keys act as "namespaces" for each user

---

## 🚨 Potential Issues & Solutions

### Issue 1: Race Conditions
**Problem:** If same user sends 2 requests simultaneously, both might read/write same memory

**Solution:** Add locks (if needed):
```python
from threading import Lock
memory_locks = defaultdict(Lock)

# In handler:
with memory_locks[token]:
    conversation_history = user_conversations[token]
    # ... modify ...
```

### Issue 2: Memory Leaks
**Problem:** Old users' data stays in memory forever

**Solution:** Add cleanup (already partially done in user_cache):
```python
# Clean up inactive users (not implemented yet)
def cleanup_inactive_users(max_age_seconds=3600):
    # Remove users who haven't accessed in 1 hour
    pass
```

### Issue 3: Token Collision
**Problem:** If 2 users have same token, they see each other's data

**Solution:** Ensure token generation is cryptographically unique (UUID, JWT, etc.)

---

## 📝 Conclusion

Your architecture correctly separates users using **token-based dictionary keys**. Each user's data is isolated in memory through dictionary lookups. The system can handle 50+ concurrent users because:

- ✅ Each request has its own token
- ✅ Dictionary keys ensure data isolation  
- ✅ Flask handles concurrent requests via threading
- ✅ Memory is bounded per user (deque maxlen, summary limits)

**The separation works!** 🎉

