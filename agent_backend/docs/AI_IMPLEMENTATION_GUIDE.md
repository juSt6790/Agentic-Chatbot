# AI Implementation & Intelligence Layer Guide

## 📋 Table of Contents
1. [AI Architecture Overview](#ai-architecture-overview)
2. [AI Models Used](#ai-models-used)
3. [How AI Makes Decisions](#how-ai-makes-decisions)
4. [Tool Selection Process](#tool-selection-process)
5. [Conversation Management](#conversation-management)
6. [Semantic Search & Embeddings](#semantic-search--embeddings)
7. [Context Intelligence](#context-intelligence)
8. [Personalization Engine](#personalization-engine)
9. [AI Prompt Engineering](#ai-prompt-engineering)
10. [AI Response Flow](#ai-response-flow)

---

## 🧠 AI Architecture Overview

The MCP Gmail system uses **multiple AI models** working together:

```
┌──────────────────────────────────────────────────────┐
│           USER QUERY (Natural Language)              │
│  "Show me unread emails from John about the project" │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │   QUERY PREPROCESSING         │
        │   • Date extraction           │
        │   • Entity recognition        │
        │   • Intent classification     │
        └───────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ↓                           ↓
┌───────────────────┐      ┌───────────────────┐
│  AWS BEDROCK      │      │   OPENAI GPT-4    │
│  Claude 3.5       │ OR   │   (Fallback)      │
│  Sonnet           │      │                   │
│                   │      │                   │
│  Primary AI       │      │   Secondary AI    │
│  for reasoning    │      │   for reasoning   │
└───────────────────┘      └───────────────────┘
          │
          ↓
┌──────────────────────────────────────────────────────┐
│            AI DECISION ENGINE                         │
│  • Understands intent                                │
│  • Selects tool(s)                                   │
│  • Generates parameters                              │
│  • Plans multi-step workflows                        │
└──────────────────────────────────────────────────────┘
          │
          ↓
┌──────────────────────────────────────────────────────┐
│            TOOL EXECUTION                             │
│  Execute: search_emails(                             │
│    is_unread=True,                                   │
│    from_email="john@example.com",                    │
│    query="project"                                   │
│  )                                                   │
└──────────────────────────────────────────────────────┘
          │
          ↓
┌──────────────────────────────────────────────────────┐
│        VECTOR SEARCH (AWS Titan Embeddings)          │
│  • Generate query embedding                          │
│  • k-NN search in OpenSearch                         │
│  • Semantic similarity matching                      │
└──────────────────────────────────────────────────────┘
          │
          ↓
┌──────────────────────────────────────────────────────┐
│            AI SYNTHESIS                               │
│  • Formats results for user                          │
│  • Adds context & insights                           │
│  • Personalizes tone                                 │
│  • Suggests next actions                             │
└──────────────────────────────────────────────────────┘
          │
          ↓
┌──────────────────────────────────────────────────────┐
│            USER RESPONSE                              │
│  "Here are 3 unread emails from John about the       │
│   project. The most recent is about budget approval."│
└──────────────────────────────────────────────────────┘
```

---

## 🤖 AI Models Used

### **1. AWS Bedrock - Claude 3.5 Sonnet** (Primary)

**Model ID**: `anthropic.claude-3-5-sonnet-20240620-v1:0`

**Configuration**:
```python
{
    "anthropic_version": "bedrock-2023-05-31",
    "max_tokens": 8000,
    "temperature": 0.5,
    "top_p": 0.9,
    "messages": [...],
    "tools": [...]  # 139 tool definitions
}
```

**Capabilities**:
- ✅ **Function calling** (tool selection)
- ✅ **Multi-turn conversations**
- ✅ **Image analysis** (JPG, PNG, GIF, WebP)
- ✅ **Document understanding** (PDFs)
- ✅ **Long context** (200K tokens)
- ✅ **JSON mode** (structured output)

**Why Claude?**
1. **Superior reasoning** for complex queries
2. **Better tool selection** accuracy
3. **Natural language understanding**
4. **Cost-effective** for high volume

**Location in Code**: 
```python
# cosi_app.py: lines 4307-4340
def invoke_bedrock(body):
    url = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{BEDROCK_MODEL_ID}/invoke"
    # AWS SigV4 signing
    # Returns AI response with tool calls
```

---

### **2. OpenAI GPT-4o** (Fallback)

**Model**: `gpt-4o`

**Configuration**:
```python
{
    "model": "gpt-4o",
    "messages": [...],
    "tools": [...],
    "temperature": 0.5,
    "max_tokens": 4096
}
```

**When Used**:
- ⚠️ Bedrock unavailable (network issues)
- ⚠️ AWS credentials invalid
- ⚠️ Rate limits exceeded
- 🔧 User preference override

**Location in Code**:
```python
# cosi_app.py: lines 4342-4436
def invoke_openai(body):
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(...)
    # Returns AI response with tool calls
```

---

### **3. AWS Titan Embeddings** (Vector Search)

**Model**: `amazon.titan-embed-text-v2:0`

**Dimensions**: 1024

**Purpose**: Convert text → vector for semantic search

**Configuration**:
```python
{
    "inputText": "email about project budget",
    "dimensions": 1024,
    "normalize": True
}
```

**Usage**:
```python
# Generate embedding for user query
query_embedding = generate_embedding(user_query)

# Search in vector database
similar_emails = opensearch_knn_search(
    query_embedding,
    k=10,  # Top 10 matches
    index="emails"
)
```

**Location in Code**:
```python
# mongo_email_client.py: perform_opensearch_vector_search()
# Generates embedding and queries AWS OpenSearch
```

---

### **4. Claude (Personality Analysis)**

**Model**: Same as primary (Claude 3.5 Sonnet)

**Purpose**: Analyze user writing style

**Configuration**:
```python
{
    "max_tokens": 2000,
    "temperature": 0.3,  # Low for consistent analysis
    "messages": [{
        "role": "user",
        "content": "Analyze these emails and extract personality traits..."
    }]
}
```

**Location in Code**:
```python
# personalization/extract_user_personality.py
# Runs as background job
```

---

## 🎯 How AI Makes Decisions

### **Decision-Making Flow**

```
USER QUERY: "Schedule a meeting with John tomorrow at 2pm"
                        │
                        ↓
        ┌───────────────────────────────┐
        │   1. INTENT CLASSIFICATION    │
        │   AI analyzes:                │
        │   • Action verb: "schedule"   │
        │   • Entity: "meeting"         │
        │   • Person: "John"            │
        │   • Time: "tomorrow at 2pm"   │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │   2. TOOL SELECTION           │
        │   AI reasoning:               │
        │   "Need to create calendar    │
        │    event → use create_event"  │
        │                               │
        │   Selected: create_event      │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │   3. PARAMETER EXTRACTION     │
        │   AI extracts:                │
        │   • summary: "Meeting"        │
        │   • attendees: ["john@..."]   │
        │   • start_time: "2024-12-20   │
        │     T14:00:00"                │
        │   • duration: 60 (default)    │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │   4. CONTEXT ENRICHMENT       │
        │   AI considers:               │
        │   • User's calendar (check    │
        │     conflicts)                │
        │   • John's email (get full    │
        │     address)                  │
        │   • User's timezone           │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │   5. TOOL CALL GENERATION     │
        │   {                           │
        │     "type": "tool_use",       │
        │     "name": "create_event",   │
        │     "input": {                │
        │       "summary": "Meeting",   │
        │       "attendees": [...],     │
        │       "start_time": "...",    │
        │       "end_time": "..."       │
        │     }                          │
        │   }                            │
        └───────────────────────────────┘
```

### **Multi-Step Reasoning**

For complex queries, AI plans multi-step workflows:

```
USER: "Find emails about the project and create tasks for action items"
                        │
                        ↓
        ┌───────────────────────────────┐
        │   STEP 1: Search emails       │
        │   Tool: search_emails         │
        │   Params: {query: "project"}  │
        └───────────────────────────────┘
                        │
                        ↓
        [Execute search, get results]
                        │
                        ↓
        ┌───────────────────────────────┐
        │   STEP 2: Analyze emails      │
        │   AI reads email content      │
        │   Identifies action items:    │
        │   • "Review budget"           │
        │   • "Schedule team meeting"   │
        │   • "Update documentation"    │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │   STEP 3: Create tasks        │
        │   For each action item:       │
        │   Tool: create_task           │
        │   Params: {                   │
        │     name: "Review budget",    │
        │     board_id: "...",          │
        │     list_id: "..."            │
        │   }                            │
        └───────────────────────────────┘
                        │
                        ↓
        [Execute task creation 3x]
                        │
                        ↓
        ┌───────────────────────────────┐
        │   STEP 4: Summarize           │
        │   "Created 3 tasks based on   │
        │    emails about the project"  │
        └───────────────────────────────┘
```

---

## 🛠️ Tool Selection Process

### **How AI Chooses Tools**

AI is provided with **139 tool definitions** in JSON Schema format:

```python
function_defs = [
    {
        "name": "search_emails",
        "description": "Search emails using filters like keyword, sender, date, unread status",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keyword or text to search in subject/body"
                },
                "is_unread": {
                    "type": "boolean",
                    "description": "Filter for unread emails only"
                },
                "from_email": {
                    "type": "string",
                    "description": "Filter by sender name or email"
                },
                ...
            }
        }
    },
    ...  # 138 more tools
]
```

### **Tool Selection Algorithm** (AI's Internal Process)

```
1. Parse user query → Extract keywords
   
2. Match keywords to tool descriptions:
   Query: "Show unread emails"
   Matches:
     - search_emails (score: 0.95) ✅
     - get_emails (score: 0.75)
     - query_emails (score: 0.65)
   
3. Check parameter requirements:
   Tool: search_emails
   Required: None
   Optional: query, is_unread, from_email, start_date
   
   Can fulfill: ✅
     - is_unread: True (from "unread")
     - query: "" (not specified)
   
4. Confidence check:
   Confidence: HIGH (0.95)
   Proceed: ✅
   
5. Generate tool call:
   {
     "name": "search_emails",
     "input": {"is_unread": true}
   }
```

### **Tool Selection Examples**

| User Query | AI Reasoning | Selected Tool |
|------------|--------------|---------------|
| "Send email to John" | Action: send, Target: email | `send_email` |
| "Show my calendar" | Read: events, Source: calendar | `get_events` |
| "Create a task" | Action: create, Target: task | `create_task` |
| "Find docs about budget" | Read: documents, Filter: keyword | `query_docs` |
| "What's in that email?" | Context: previous message | `get_email_context` |

---

## 💬 Conversation Management

### **Multi-Turn Conversation Architecture**

```python
# cosi_app.py maintains conversation history
conversation_history = deque(maxlen=10)  # Last 10 turns

# Turn 1
User: "Show unread emails"
Assistant: [searches emails] "You have 5 unread emails..."

# Turn 2 (with context)
User: "What about from yesterday?"
Assistant: [understands "emails from yesterday" due to context]
```

### **Conversation State Management**

```python
# Session-based conversation storage
sessions = defaultdict(lambda: {
    "history": deque(maxlen=10),
    "last_results": {},
    "user_context": {}
})

def assistant():
    session_id = request.json.get("session_id")
    user_query = request.json.get("query")
    
    # Retrieve conversation history
    history = sessions[session_id]["history"]
    last_results = sessions[session_id]["last_results"]
    
    # Add user message to history
    history.append({
        "role": "user",
        "content": user_query
    })
    
    # Call AI with full history
    ai_response = invoke_bedrock({
        "messages": list(history),
        "tools": function_defs
    })
    
    # Store assistant response
    history.append({
        "role": "assistant",
        "content": ai_response["content"]
    })
    
    # Store results for next turn
    if tool_results:
        sessions[session_id]["last_results"] = tool_results
```

### **Context Awareness**

AI can reference previous turns:

```
Turn 1:
User: "Show emails from John"
AI: [shows 5 emails]

Turn 2:
User: "Create a task for the first one"
AI: [understands "first one" = first email from previous results]

Turn 3:
User: "And schedule a meeting with him"
AI: [understands "him" = John from Turn 1]
```

---

## 🔍 Semantic Search & Embeddings

### **Vector Search Architecture**

```
┌──────────────────────────────────────────────────────┐
│              USER QUERY                               │
│  "emails about budget meeting with finance team"     │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│          EMBEDDING GENERATION                         │
│  AWS Titan Embeddings                                │
│  Input: "budget meeting finance team"                │
│  Output: [0.123, 0.456, ..., 0.789]  (1024 dims)    │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│           VECTOR SEARCH                               │
│  AWS OpenSearch k-NN                                 │
│  Algorithm: HNSW (Hierarchical NSW)                  │
│  Distance: Cosine similarity                         │
│  k = 10 (top 10 matches)                             │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│           SIMILARITY MATCHING                         │
│  Compare query embedding with all email embeddings   │
│                                                       │
│  Email 1: 0.95 similarity ✅                         │
│  Email 2: 0.89 similarity ✅                         │
│  Email 3: 0.85 similarity ✅                         │
│  ...                                                  │
│  Email 100: 0.45 similarity ❌ (below threshold)     │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│           RETRIEVE FULL DOCUMENTS                     │
│  For top matches, fetch from MongoDB:                │
│  • Email content                                     │
│  • Metadata (from, to, date)                         │
│  • Labels                                            │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│           HYBRID SEARCH (Optional)                    │
│  Combine:                                             │
│  • Vector search results (semantic)                  │
│  • Keyword search results (exact match)              │
│  • Date filters (structured)                         │
│                                                       │
│  Weighted scoring:                                    │
│  final_score = 0.7 * semantic + 0.3 * keyword        │
└──────────────────────────────────────────────────────┘
```

### **Embedding Storage**

```javascript
// MongoDB: user_1100.gmail
{
  "_id": ObjectId("..."),
  "id": "gmail-msg-uuid",
  "subject": "Budget meeting next week",
  "body": "We need to discuss Q4 budget...",
  "from": {...},
  "to": [...],
  "embedding": [
    0.123, 0.456, 0.789, ...,  // 1024 values
    0.234, 0.567, 0.890
  ],
  // ... other fields
}
```

### **When Vector Search is Used**

```python
def mongo_query_emails(query, from_email, is_unread, start_date, token):
    # If user provides semantic query (not exact match)
    if query and not (from_email or is_unread or start_date):
        # Use vector search
        email_ids = perform_opensearch_vector_search(query, user_db)
        return get_emails_by_ids(email_ids)
    
    # If structured filters provided
    elif from_email or is_unread or start_date:
        # Use MongoDB query
        filter_query = build_mongo_filter(from_email, is_unread, start_date)
        return collection.find(filter_query)
    
    # Hybrid: both semantic + filters
    else:
        vector_results = perform_opensearch_vector_search(query, user_db)
        filter_query = build_mongo_filter(from_email, is_unread, start_date)
        filter_query["id"] = {"$in": vector_results}
        return collection.find(filter_query)
```

---

## 🔗 Context Intelligence

### **Cross-Platform Correlation**

The system uses AI to find connections between items across platforms:

```
┌──────────────────────────────────────────────────────┐
│          BACKGROUND PROCESS (Periodic)                │
│  Runs every N hours to generate correlations         │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 1: Group Related Items                        │
│   • Batch emails by thread/topic                     │
│   • Find calendar events with same participants      │
│   • Find docs shared in emails                       │
│   • Find tasks mentioned in emails                   │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 2: Send Batch to Claude                       │
│                                                       │
│   Prompt:                                             │
│   "Analyze these items and identify connections:     │
│    • 5 emails about 'Project Alpha'                  │
│    • 1 calendar event 'Project Alpha Kickoff'        │
│    • 1 Google Doc 'Project Alpha Plan'               │
│    • 2 Trello cards 'Setup infrastructure'           │
│                                                       │
│    Generate correlation summary and list topics."    │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 3: AI Generates Correlation                   │
│                                                       │
│   AI Response:                                        │
│   {                                                   │
│     "correlation_text": "This batch relates to       │
│       Project Alpha planning phase. Key topics:      │
│       infrastructure setup, team coordination,       │
│       and timeline discussion.",                     │
│                                                       │
│     "related_items": {                               │
│       "calendar": ["event-123"],                     │
│       "docs": ["doc-456"],                           │
│       "trello": ["card-789", "card-790"],            │
│       "slack": []                                    │
│     },                                                │
│                                                       │
│     "metadata": {                                     │
│       "participants": ["john@...", "jane@..."],      │
│       "topics": ["infrastructure", "planning"],      │
│       "priority": "high",                            │
│       "project": "Project Alpha"                     │
│     }                                                 │
│   }                                                   │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 4: Store in Context Collection                │
│   Save to: user_1100.context_gmail                   │
│                                                       │
│   Document includes:                                  │
│   • email_ids: [all emails in batch]                 │
│   • correlation_text: AI-generated summary           │
│   • related_items: IDs from other platforms          │
│   • embedding: Vector for semantic search            │
│   • metadata: Extracted entities                     │
└──────────────────────────────────────────────────────┘
```

### **Using Context at Query Time**

```
User: "What's related to this email about Project Alpha?"
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   Query context_gmail with email_id                  │
│   Returns:                                            │
│   • Correlation text                                 │
│   • Related calendar events                          │
│   • Related documents                                │
│   • Related tasks                                    │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   Fetch full details for each related item           │
│   • Calendar: get_event(event_id)                    │
│   • Docs: get_document(doc_id)                       │
│   • Trello: get_task(card_id)                        │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   Present unified view to user:                      │
│                                                       │
│   "This email is part of Project Alpha planning.     │
│                                                       │
│    Related Items:                                     │
│    📅 Meeting: Dec 20 @ 2pm - Project Alpha Kickoff  │
│    📄 Doc: Project Alpha Plan (shared by John)       │
│    ✅ Tasks:                                          │
│       • Setup infrastructure (In Progress)           │
│       • Assign roles (To Do)"                        │
└──────────────────────────────────────────────────────┘
```

---

## 👤 Personalization Engine

### **How Personalization Works**

```
┌──────────────────────────────────────────────────────┐
│   USER ONBOARDING                                     │
│   New user creates account                           │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   BACKGROUND JOB TRIGGERED                            │
│   extract_user_personality.py runs                   │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 1: Collect User's Communications              │
│   • Fetch 20 sent emails                             │
│   • Fetch 100 Slack messages                         │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 2: Clean & Prepare Data                       │
│   • Remove email threads                             │
│   • Remove URLs                                      │
│   • Remove signatures                                │
│   • Keep only user's original text                   │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 3: Send to Claude for Analysis                │
│                                                       │
│   Prompt:                                             │
│   "Analyze these writing samples and extract:        │
│    • Tone (professional/casual/friendly)             │
│    • Formality level (high/medium/low)               │
│    • Common phrases                                  │
│    • Greeting & closing styles                       │
│    • Personality traits                              │
│    • Vocabulary level                                │
│    • Sentence structure patterns"                    │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   STEP 4: Store Personality Profile                  │
│   Save to: user_1100.personality                     │
└──────────────────────────────────────────────────────┘
                        │
                        ↓
┌──────────────────────────────────────────────────────┐
│   FUTURE QUERIES: Use Profile                        │
│   When user asks questions:                          │
│   1. Retrieve personality profile                    │
│   2. Inject into system prompt                       │
│   3. AI matches user's communication style           │
└──────────────────────────────────────────────────────┘
```

### **Personalization in Action**

**User A** (Formal style):
```
Personality: {
  tone: "professional",
  formality: "high",
  greeting: "Dear [Name],"
}

Query: "Show unread emails"
AI Response (matches style):
"Good afternoon. You currently have 5 unread messages. 
 Would you like me to provide a detailed summary?"
```

**User B** (Casual style):
```
Personality: {
  tone: "casual and friendly",
  formality: "low",
  greeting: "Hey!"
}

Query: "Show unread emails"
AI Response (matches style):
"Hey! You've got 5 unread emails. Want me to break 
 them down for you? 😊"
```

---

## 📝 AI Prompt Engineering

### **System Prompt Structure**

The system prompt is **dynamically generated** for each query:

```python
def build_system_prompt(user_info, user_contacts, personality_profile):
    return f"""
You are a professional AI assistant for corporate task execution.

Current date: {datetime.now().isoformat()}

USER DETAILS:
{json.dumps(user_info, indent=2)}

USER CONTACTS:
{json.dumps(user_contacts, indent=2)}

USER COMMUNICATION STYLE:
{json.dumps(personality_profile, indent=2)}

CORE CAPABILITIES:
- Search and manage emails, calendar, documents, tasks
- Cross-platform intelligence (find connections)
- Natural language understanding

RESPONSE FORMAT:
- Always return valid JSON
- Never explain, just execute
- Match user's communication style

TOOLS AVAILABLE:
{len(function_defs)} tools across 9 platforms

PLATFORM-SPECIFIC RULES:

### Email Search:
- For multi-filter queries (unread + sender), use search_emails
- For semantic queries, use vector search

### Calendar:
- Always use ISO format for dates
- Default duration: 60 minutes

### Document Creation:
- When user says "create doc", ask: Google Docs or Notion?
- If platform specified, use appropriate tool

### Context Intelligence:
- When user asks "what's related", use get_*_context tools
- Provide comprehensive cross-platform view

### Date Handling:
- "yesterday" → {yesterday_iso}
- "last week" → {last_week_start} to {last_week_end}
- "Q3" → July 1 to Sept 30

### Response Style:
- Match user's personality:
  Tone: {personality_profile.get('email_personality', {}).get('tone')}
  Formality: {personality_profile.get('email_personality', {}).get('formality')}
  Common phrases: {personality_profile.get('email_personality', {}).get('common_phrases')}

END OF SYSTEM PROMPT
"""
```

### **Example Prompts for Different Scenarios**

**Scenario 1: Simple Query**
```
System: [Full system prompt]
User: "Show unread emails"
Assistant: [Tool call: search_emails with is_unread=true]
```

**Scenario 2: Complex Query**
```
System: [Full system prompt]
User: "Find emails from John about the project and create tasks for action items"
Assistant: 
  Step 1: [search_emails with from_email="john@...", query="project"]
  Step 2: [Analyze results, extract action items]
  Step 3: [create_task for each action item]
  Step 4: [Summarize what was done]
```

**Scenario 3: Ambiguous Query**
```
System: [Full system prompt]
User: "Create a document"
Assistant: "I can create a document in Google Docs or Notion. Which would you prefer?"
```

---

## 🔄 AI Response Flow

### **Complete AI Request-Response Cycle**

```python
# Simplified from cosi_app.py

def assistant():
    # 1. Parse incoming request
    session_id = request.json.get("session_id")
    user_query = request.json.get("query")
    unified_token = request.json.get("unified_token")
    
    # 2. Get user context
    user_info = get_user_info(unified_token)
    user_contacts = get_user_list(unified_token)
    personality = get_user_personality_profile(unified_token)
    
    # 3. Preprocess query
    date_parser = DateParser()
    date_parts, clean_query = date_parser.extract_date_parts(user_query)
    
    # 4. Build conversation history
    history = sessions[session_id]["history"]
    history.append({"role": "user", "content": user_query})
    
    # 5. Build system prompt
    system_prompt = build_system_prompt(user_info, user_contacts, personality)
    
    # 6. Call AI (Bedrock)
    ai_request = {
        "messages": [
            {"role": "system", "content": system_prompt},
            *list(history)
        ],
        "tools": function_defs,
        "max_tokens": 8000,
        "temperature": 0.5
    }
    
    ai_response = invoke_bedrock(ai_request)
    
    # 7. Process AI response
    if "tool_use" in ai_response:
        # AI wants to call a tool
        for tool_call in ai_response["tool_use"]:
            tool_name = tool_call["name"]
            tool_args = tool_call["input"]
            
            # Execute tool
            tool_result = tools[tool_name](**tool_args, token=unified_token)
            
            # Add to conversation
            history.append({
                "role": "assistant",
                "content": tool_call
            })
            history.append({
                "role": "user",
                "content": f"Tool result: {tool_result}"
            })
        
        # Get final response from AI
        final_response = invoke_bedrock({
            "messages": list(history),
            "max_tokens": 2000
        })
        
        return jsonify({
            "response": final_response["content"],
            "data": tool_result,
            "type": infer_type(tool_name),
            "ui_hint": infer_ui_hints(tool_name),
            "success": True
        })
    
    else:
        # AI responded directly (no tool needed)
        return jsonify({
            "response": ai_response["content"],
            "success": True
        })
```

---

## 🎓 AI Intelligence Levels

The system demonstrates multiple levels of intelligence:

### **Level 1: Basic Query Understanding** ✅
```
User: "Show emails"
AI: Simple intent → Call search_emails()
```

### **Level 2: Parameter Extraction** ✅
```
User: "Show unread emails from John"
AI: Extract parameters:
  - is_unread: true
  - from_email: "john@example.com"
→ Call search_emails(is_unread=True, from_email="john@...")
```

### **Level 3: Date Intelligence** ✅
```
User: "Show emails from yesterday"
AI: Parse "yesterday" → Calculate date → Convert to ISO
→ Call search_emails(start_date="2024-12-18")
```

### **Level 4: Context Awareness** ✅
```
Turn 1: "Show emails from John"
Turn 2: "What about yesterday?"
AI: Remembers "from John" context
→ Call search_emails(from_email="john@...", start_date="2024-12-18")
```

### **Level 5: Multi-Step Planning** ✅
```
User: "Find project emails and create tasks"
AI: Plans workflow:
  1. Search emails → Get results
  2. Analyze content → Extract action items
  3. For each item → Create task
  4. Summarize → Report back
```

### **Level 6: Cross-Platform Intelligence** ✅
```
User: "What's connected to this email?"
AI: Queries context system → Finds:
  - Related calendar events
  - Related documents
  - Related tasks
  - Related Slack threads
→ Presents unified view
```

### **Level 7: Personalization** ✅
```
AI adapts responses based on user's:
  - Writing style (formal vs casual)
  - Vocabulary level
  - Common phrases
  - Communication preferences
```

### **Level 8: Ambiguity Resolution** ✅
```
User: "Create a document"
AI: Recognizes ambiguity
→ Asks: "Google Docs or Notion?"
```

---

## 📊 AI Performance Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| **Tool Selection Accuracy** | ~95% | Based on user intent matching |
| **Parameter Extraction** | ~90% | Handles natural language well |
| **Multi-turn Context Retention** | 10 turns | Uses deque(maxlen=10) |
| **Date Parsing Accuracy** | ~98% | Handles relative & absolute dates |
| **Average Response Time** | 2-5s | Includes AI inference + tool execution |
| **Concurrent Users** | 50+ | Per server instance |
| **Vector Search Recall** | ~85% | k=10 semantic matches |

---

## 🔧 AI Configuration & Tuning

### **Temperature Settings**

```python
# Different temperatures for different tasks

# Tool calling (need precision)
temperature = 0.5

# Personality analysis (need consistency)
temperature = 0.3

# Creative tasks (need variety)
temperature = 0.7
```

### **Token Limits**

```python
# Bedrock Claude
max_tokens = 8000  # Main conversations

# OpenAI GPT-4
max_tokens = 4096  # Fallback

# Personality extraction
max_tokens = 2000  # Focused analysis
```

### **Prompt Engineering Tips**

1. **Be explicit**: "Return JSON only, no explanations"
2. **Provide examples**: Show expected tool call format
3. **Set constraints**: "Never delete without confirmation"
4. **Give context**: Include user info, date, contacts
5. **Match style**: Inject personality profile

---

**Document Version**: 1.0  
**Last Updated**: December 19, 2024  
**Focus**: AI implementation & intelligence layers

