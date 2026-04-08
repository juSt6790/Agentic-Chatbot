# MCP Gmail System - Complete Architecture Documentation

## 📋 Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [File Structure & Purpose](#file-structure--purpose)
4. [Data Flow](#data-flow)
5. [AI Integration](#ai-integration)
6. [Authentication & Security](#authentication--security)
7. [Database Schema](#database-schema)
8. [API Endpoints](#api-endpoints)
9. [Tool System](#tool-system)
10. [Architecture Diagrams](#architecture-diagrams)

---

## 🎯 System Overview

**MCP Gmail** (Multi-Channel Platform) is an **AI-powered unified workspace assistant** that integrates multiple productivity platforms:
- **Gmail** (Email management)
- **Google Calendar** (Event scheduling)
- **Google Docs, Sheets, Slides** (Document management)
- **Slack** (Team messaging)
- **Notion** (Note-taking & databases)
- **Trello** (Task management)
- **Gamma** (AI presentations)

### Core Capabilities
- **Cross-platform search** with natural language
- **AI-powered context correlation** between platforms
- **Personalized responses** based on user writing style
- **Multi-modal** input (text, images, PDFs)
- **Smart date parsing** and query normalization

---

## 🏗️ Architecture Layers

The system follows a **4-tier architecture**:

```
┌─────────────────────────────────────────┐
│   Presentation Layer (Flask REST API)   │
│     - /chat, /autoPilot endpoints        │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│    Application Layer (cosi_app.py)      │
│  - AI orchestration (Bedrock/OpenAI)    │
│  - Tool routing & execution              │
│  - Multi-turn conversation management    │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│     Service Layer (services/*.py)        │
│  - Platform-specific API integration     │
│  - Gmail, Slack, Trello, Notion, etc.    │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      Data Layer (clients/*.py)           │
│  - MongoDB query builders                │
│  - Vector search (AWS OpenSearch)        │
│  - Context correlation                   │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│    Infrastructure Layer                  │
│  - MongoDB (per-tenant databases)        │
│  - AWS Bedrock (Claude AI)               │
│  - AWS OpenSearch (embeddings)           │
└─────────────────────────────────────────┘
```

---

## 📁 File Structure & Purpose

### **1. `/app` - Application Entry Points**

| File | Purpose | Key Functions |
|------|---------|---------------|
| `cosi_app.py` | **Main Flask application** | `/chat`, `/autoPilot` endpoints, AI orchestration |
| `server.py` | **Tool registry & imports** | Aggregates all platform tools, exports unified interface |
| `mcp_flask_api.py` | Alternative API interface | Lightweight API wrapper |
| `mcp_gmail_agent.py` | Agent-based interface | Autonomous task execution |

**cosi_app.py** is the **brain** of the system:
- Handles HTTP requests
- Manages conversation history
- Routes queries to appropriate AI model (Bedrock Claude or OpenAI)
- Executes tools based on AI decisions
- Formats and returns responses

### **2. `/services` - Platform Integration Layer**

Each service file handles integration with a specific platform:

| File | Platform | Key Functions |
|------|----------|---------------|
| `gmail.py` | Gmail API | Authentication, send/search emails, manage labels |
| `calendar_mcp.py` | Google Calendar | Create/update/delete events, search calendar |
| `docs_mcp.py` | Google Docs | Create/edit/share documents, search docs |
| `sheets_mcp.py` | Google Sheets | CRUD operations, charts, pivot tables |
| `slides_mcp.py` | Google Slides | Create/edit presentations, add elements |
| `slack_mcp.py` | Slack API | Send messages, manage channels, DMs |
| `notion_mcp.py` | Notion API | Pages, databases, blocks, comments |
| `trello_mcp.py` | Trello API | Boards, cards, checklists, labels |

**Common Pattern**:
1. Get access token via `get_user_tool_access_token(unified_token, tool_name)`
2. Build platform-specific client
3. Execute API calls
4. Return normalized response

### **3. `/clients` - Data Access Layer**

Database clients that abstract MongoDB operations:

| File | Purpose | Key Responsibilities |
|------|---------|---------------------|
| `mongo_email_client.py` | Gmail data queries | Vector search, date filtering, email CRUD |
| `mongo_calendar_client.py` | Calendar data queries | Event search, date range queries |
| `mongo_docs_client.py` | Docs/Sheets/Slides data | Document search and retrieval |
| `mongo_notion_client.py` | Notion data queries | Page/database search |
| `mongo_context_client.py` | **Cross-platform correlation** | Find related items across platforms |
| `mongo_personalization_client.py` | User personality data | Retrieve writing style profiles |
| `db_method.py` | **Authentication & authorization** | Validate user access, manage tokens |
| `drive_client.py` | Google Drive integration | File metadata and sharing |

**Key Innovation**: `mongo_context_client.py` provides **cross-platform intelligence**:
- Given email IDs → Find related calendar events, docs, tasks
- Given calendar event → Find related emails, documents
- Uses **vector embeddings** to find semantic relationships

### **4. `/config` - Configuration Management**

| File | Purpose |
|------|---------|
| `config.py` | Main configuration (scopes, paths) |
| `config_calender.py` | Calendar-specific config |
| `config_salesforce.py` | Salesforce integration config |
| `credentials_calender.json` | OAuth credentials |
| `token.json`, `token_calendar.json` | OAuth tokens |

### **5. `/db` - Database Connection**

| File | Purpose |
|------|---------|
| `mongo_client.py` | MongoDB connection factory, returns client instances |

**Multi-tenancy**: Each user gets their own database named by `user_id`.

### **6. `/utils` - Utility Functions**

| File | Purpose | Key Features |
|------|---------|--------------|
| `utils.py` | Token management | `get_tool_token()` - retrieves OAuth tokens |
| `date_utils.py` | **Smart date parsing** | Natural language → ISO dates ("yesterday" → "2024-12-18") |
| `error_handler.py` | Error handling & logging | Centralized error management |

**date_utils.py** is particularly sophisticated:
- Parses "last week", "Q3", "June 7th 2025"
- Extracts year, month, day, weekday, quarter
- Builds MongoDB date queries
- Handles relative time expressions

### **7. `/personalization` - AI Personalization**

| File | Purpose |
|------|---------|
| `extract_user_personality.py` | Analyzes user emails/Slack to extract writing style |
| `slack.py` | Slack-specific personality extraction |

**Workflow**:
1. Fetch user's sent emails & Slack messages
2. Send to AWS Bedrock (Claude) for analysis
3. Extract tone, formality, vocabulary, common phrases
4. Store in `{user_id}.personality` collection
5. Use profile to personalize AI responses

### **8. `/tests` - Test Suite**

| File | Purpose |
|------|---------|
| `test_gmail_setup.py` | Gmail OAuth flow testing |
| `test_openai_key.py` | OpenAI API validation |
| `test.py` | General integration tests |

### **9. Root Level Files**

| File | Purpose |
|------|---------|
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container configuration |
| `start_cosi_app.sh` | Startup script |
| `compare.py` | Large comparison/analysis utility |
| `search_apis_*.py` | API search/discovery scripts |
| `token_counter.py` | Token usage tracking |
| `test_bedrock_embeddings.py` | Vector embedding tests |

---

## 🔄 Data Flow

### **User Query Flow**

```
1. User sends query to /chat endpoint
   ↓
2. cosi_app.py receives request
   - Extracts unified_token
   - Validates user authentication
   - Gets user personality profile
   ↓
3. Query preprocessing
   - Extract dates using date_utils.py
   - Normalize natural language
   - Handle image/PDF uploads
   ↓
4. AI Model Selection
   - Default: AWS Bedrock (Claude Sonnet 3.5)
   - Fallback: OpenAI GPT-4
   ↓
5. System prompt construction
   - Current date/time
   - User contacts
   - Tool definitions
   - Platform-specific rules
   ↓
6. AI reasoning & tool selection
   - AI analyzes query intent
   - Selects appropriate tool(s)
   - Generates parameters
   ↓
7. Tool execution
   - cosi_app.py calls selected tool
   - Tool routes to service layer
   - Service layer calls data layer
   - Data layer queries MongoDB/API
   ↓
8. Response formatting
   - Structure results for UI
   - Add ui_hints (open panels, etc.)
   - Format for readability
   ↓
9. Return to user
   - JSON response with data, message, ui_hints
```

### **Tool Execution Flow**

```
User Query: "Show unread emails from yesterday"
   ↓
AI Decision: Use tool "search_emails"
Parameters: {
  "is_unread": true,
  "start_date": "2024-12-18",
  "end_date": "2024-12-18"
}
   ↓
cosi_app.py: tools["search_emails"](**params)
   ↓
server.py: mongo_query_emails(**kwargs)
   ↓
mongo_email_client.py: mongo_query_emails()
   - Validates user access to Gmail
   - Gets user_id from token
   - Connects to {user_id}.gmail collection
   - Builds MongoDB query
   - Executes vector search if needed
   ↓
Returns: List of email documents
   ↓
cosi_app.py: Formats results
   ↓
Returns to user with ui_hint: ["open_email_panel"]
```

### **Context Correlation Flow**

```
User: "What's related to this email?"
   ↓
1. Get email IDs from previous response
   ↓
2. Call get_email_context(email_ids)
   ↓
3. mongo_context_client.py
   - Queries context_gmail collection
   - Finds AI-generated correlation data
   - Returns related:
     * Calendar events
     * Documents
     * Trello tasks
     * Slack threads
     * Notion pages
   ↓
4. Present unified view of connections
```

---

## 🤖 AI Integration

### **AI Models Used**

1. **AWS Bedrock - Claude 3.5 Sonnet** (Primary)
   - Model ID: `anthropic.claude-3-5-sonnet-20240620-v1:0`
   - Max tokens: 8000
   - Temperature: 0.5 (balanced creativity)
   - Use case: General queries, tool orchestration

2. **OpenAI GPT-4o** (Fallback)
   - Model: `gpt-4o`
   - Max tokens: 4096
   - Use case: When Bedrock unavailable

3. **AWS Bedrock - Titan Embeddings** (Vector Search)
   - Model: `amazon.titan-embed-text-v2:0`
   - Dimensions: 1024
   - Use case: Semantic email/doc search

### **AI Orchestration in cosi_app.py**

**Key Functions**:

```python
def invoke_bedrock(body):
    """Send request to AWS Bedrock Claude model"""
    # Signs request with AWS credentials
    # Handles streaming/non-streaming responses
    # Parses tool calls from AI response

def invoke_openai(body):
    """Fallback to OpenAI API"""
    # OpenAI function calling
    # Schema validation for tools

def assistant():
    """Main /chat endpoint - handles conversation"""
    # Multi-turn conversation management
    # Tool execution loop
    # Response formatting
```

**AI Decision Process**:

1. **System Prompt** defines:
   - Available tools (139 functions)
   - Current date/time context
   - User contacts and info
   - Platform-specific rules
   - Example responses

2. **AI analyzes query** to determine:
   - Primary intent (search, create, update, delete)
   - Target platform(s)
   - Required parameters
   - Need for context/correlation

3. **Tool calls** are executed:
   - AI returns JSON with tool name + args
   - System validates parameters
   - Executes function
   - Returns result to AI

4. **AI synthesizes response**:
   - Formats results for user
   - Adds clarifications
   - Suggests next actions

### **Tool Definition Schema**

Each tool is defined with:
```python
{
    "name": "search_emails",
    "description": "Search emails using filters",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "..."},
            "is_unread": {"type": "boolean"},
            "from_email": {"type": "string"},
            ...
        },
        "required": ["query"]
    }
}
```

**Total: 139 tool definitions** across all platforms.

---

## 🔐 Authentication & Security

### **Authentication Flow**

```
User logs in → Gets unified_token
   ↓
For each platform:
  1. User grants OAuth permission
  2. Access token stored in MongoDB
  3. Linked to user_id + tool_name
   ↓
On API call:
  1. Client sends unified_token
  2. System resolves to user_id
  3. Retrieves platform-specific token
  4. Validates tool access
  5. Executes request
```

### **Key Security Components**

**1. Token Management** (`db_method.py`):
```python
def validate_user_tool_access(token, tool_name):
    """
    Validates user has access to specific tool
    Returns: (is_valid, error_msg, status_code)
    """

def get_user_tool_access_token(token, tool_name):
    """
    Retrieves OAuth token for specific tool
    Returns: (token_data, status_code)
    """
```

**2. Multi-Tenancy**:
- Each user gets own MongoDB database: `{user_id}`
- Collections: `gmail`, `calendar`, `docs`, `slack`, etc.
- No cross-user data leakage

**3. OAuth Token Storage**:
```javascript
// unified_workspace.user_authenticate_token
{
    "user_id": "1100",
    "tool_name": "Gsuite",
    "tool_token": "uuid-token",
    "created_at": ISODate,
    "expires_at": ISODate
}

// unified_workspace.user_tools
{
    "user_id": "1100",
    "tool_id": "gsuite",
    "access_token": {
        "token": "ya29.xxx",
        "refresh_token": "1//xxx",
        "client_id": "xxx",
        "client_secret": "xxx",
        "scopes": [...]
    }
}
```

**4. Token Refresh**:
- Google tokens expire after 1 hour
- Auto-refresh using `refresh_token`
- Updated in MongoDB after refresh

---

## 🗄️ Database Schema

### **Database Structure**

```
MongoDB Instance
│
├── unified_workspace (Global database)
│   ├── users (User accounts)
│   ├── tools (Available platforms)
│   ├── user_tools (User-tool access mappings)
│   ├── user_authenticate_token (Unified tokens)
│   ├── counters (Auto-increment IDs)
│   └── workflow (User workflows)
│
├── {user_id_1} (Per-user database)
│   ├── gmail (Email documents)
│   ├── calendar (Calendar events)
│   ├── docs (Google Docs)
│   ├── sheets (Google Sheets)
│   ├── slides (Google Slides)
│   ├── slack_channel_messages (Slack data)
│   ├── notion (Notion pages)
│   ├── trello (Trello boards)
│   ├── context_gmail (Email correlations)
│   ├── context_calendar (Event correlations)
│   ├── context_docs (Doc correlations)
│   ├── context_slides (Slide correlations)
│   ├── context_notion (Notion correlations)
│   ├── context_trello (Trello correlations)
│   ├── context_slack (Slack correlations)
│   └── personality (Writing style profile)
│
└── {user_id_2} (Another user's database)
    └── ... (same structure)
```

### **Key Collections**

#### **1. Gmail Collection**
```javascript
{
    "_id": ObjectId("..."),
    "id": "gmail-msg-uuid",
    "from": {"name": "John Doe", "email": "john@example.com"},
    "to": [{"name": "Jane", "email": "jane@example.com"}],
    "subject": "Meeting follow-up",
    "body": "Email body text...",
    "snippet": "Preview text...",
    "internalDate": "2024-12-19",
    "internalDateNum": 1734566400000,
    "labels": ["INBOX", "UNREAD"],
    "year": 2024,
    "month": 12,
    "day": 19,
    "weekday": "thursday",
    "embedding": [0.123, 0.456, ...],  // 1024-dim vector
    "attachments": [...]
}
```

#### **2. Context Collections** (e.g., `context_gmail`)
```javascript
{
    "_id": ObjectId("..."),
    "batch_id": "batch-uuid",
    "source": "gmail",
    "email_ids": ["gmail-msg-1", "gmail-msg-2", ...],
    "correlation_text": "AI-generated insights about this batch...",
    "related_items": {
        "calendar_events": ["event-1", "event-2"],
        "documents": ["doc-1"],
        "trello_cards": ["card-1"],
        "slack_threads": ["thread-1"],
        "notion_pages": ["page-1"]
    },
    "embedding": [0.789, ...],
    "created_at": ISODate("..."),
    "metadata": {
        "participants": ["john@example.com"],
        "topics": ["meeting", "project"],
        "priority": "high"
    }
}
```

#### **3. Personality Collection**
```javascript
{
    "_id": ObjectId("..."),
    "user_email": "john@example.com",
    "personality_profile": {
        "email_personality": {
            "tone": "professional yet friendly",
            "formality": "medium",
            "greeting_style": "Hi [Name],",
            "closing_style": "Best regards,",
            "common_phrases": ["Just wanted to follow up", "Let me know"],
            "personality_traits": ["collaborative", "detail-oriented"]
        },
        "slack_personality": {
            "tone": "casual and friendly",
            "emoji_usage": "frequent",
            "response_style": "quick, concise",
            ...
        }
    },
    "created_at": ISODate("..."),
    "num_emails_analyzed": 20,
    "num_slack_messages_analyzed": 100
}
```

### **Vector Search with AWS OpenSearch**

For semantic search, embeddings are generated and stored:

1. **Email/Doc indexed** → Generate embedding via Titan
2. **Store in MongoDB** with embedding field
3. **User searches** → Generate query embedding
4. **Vector similarity** → Find closest matches
5. **Return results** sorted by relevance

---

## 🔌 API Endpoints

### **Main Endpoints**

#### **1. POST /chat**
**Primary conversational interface**

Request:
```json
{
    "session_id": "user-session-123",
    "query": "Show me unread emails from yesterday",
    "unified_token": "abc-def-123",
    "model": "bedrock",  // or "openai"
    "image": "base64-encoded-image",  // optional
    "file": "base64-encoded-pdf"  // optional
}
```

Response:
```json
{
    "response": "Here are your unread emails from yesterday...",
    "type": "emails",
    "data": {
        "emails": [...]
    },
    "ui_hint": ["open_email_panel"],
    "success": true
}
```

**Features**:
- Multi-turn conversation
- Image & PDF analysis
- Tool orchestration
- Personalized responses

#### **2. POST /autoPilot**
**Autonomous task execution mode**

Similar to `/chat` but optimized for:
- Batch operations
- Complex workflows
- Less user interaction

#### **3. GET /health**
```json
{
    "status": "healthy",
    "timestamp": "2024-12-19T10:30:00Z"
}
```

---

## 🛠️ Tool System

### **Tool Registry Architecture**

**server.py** acts as the tool aggregator:

```python
# Import all platform tools
from services.gmail import send_email, ...
from services.slack_mcp import send_slack_messages, ...
from clients.mongo_email_client import mongo_query_emails, ...

# Export unified interface
__all__ = [
    "send_email",
    "mongo_query_emails",
    "send_slack_messages",
    ...  # 139 tools total
]
```

**cosi_app.py** builds the tool dictionary:

```python
tools = {
    # Gmail tools (13)
    "send_email": lambda **kwargs: send_email(**kwargs),
    "search_emails": lambda **kwargs: mongo_query_emails(**kwargs),
    "update_email": lambda **kwargs: update_email(**kwargs),
    ...

    # Calendar tools (8)
    "create_event": lambda **kwargs: create_event(**kwargs),
    ...

    # Slack tools (13)
    "send_slack_messages": lambda **kwargs: send_slack_messages(**kwargs),
    ...

    # Context tools (7)
    "get_email_context": lambda **kwargs: get_email_context(**kwargs),
    ...

    # Total: 139 tools
}

function_defs = [
    # Tool schema definitions for AI
    {
        "name": "send_email",
        "description": "Send an email via Gmail",
        "parameters": {...}
    },
    ...
]
```

### **Tool Categories**

| Category | Count | Examples |
|----------|-------|----------|
| Gmail | 13 | send_email, search_emails, update_email |
| Calendar | 8 | create_event, search_events, delete_events |
| Slack | 13 | send_slack_messages, get_channels, send_dm |
| Google Docs | 12 | create_document, update_document, query_docs |
| Google Sheets | 15 | create_sheet, read_sheet_data, create_chart |
| Google Slides | 12 | create_gamma_presentation, add_slide |
| Notion | 18 | create_page, query_database, add_todo |
| Trello | 32 | create_task, update_task, add_checklist |
| Context | 7 | get_email_context, get_calendar_context |

### **Tool Execution Pattern**

All tools follow this pattern:

```python
def tool_function(
    param1: str,
    param2: Optional[int] = None,
    token: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Args:
        param1: Required parameter
        param2: Optional parameter
        token: User's unified token
    
    Returns:
        Standardized response dict
    """
    try:
        # 1. Validate user access
        validate_user_tool_access(token, "Platform")
        
        # 2. Get platform-specific token
        access_token = get_user_tool_access_token(token, "Platform")
        
        # 3. Build platform client
        client = build_platform_client(access_token)
        
        # 4. Execute operation
        result = client.do_operation(param1, param2)
        
        # 5. Return standardized response
        return {
            "success": True,
            "data": result,
            "message": "Operation completed"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "Operation failed"
        }
```

---

## 📊 Architecture Diagrams

### **1. High-Level System Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                         USER CLIENT                         │
│  (Web App / Mobile App / API Consumer)                     │
└─────────────────────────────────────────────────────────────┘
                            │ HTTPS
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    FLASK REST API                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  /chat   │  │/autoPilot│  │ /health  │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│               APPLICATION ORCHESTRATION                      │
│  ┌─────────────────────────────────────────────────────┐  │
│  │         cosi_app.py (Main Controller)                │  │
│  │  • Conversation Management                           │  │
│  │  • AI Model Selection (Bedrock/OpenAI)              │  │
│  │  • Tool Routing & Execution                          │  │
│  │  • Response Formatting                               │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
            │                │                 │
            ↓                ↓                 ↓
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  AWS Bedrock │  │    OpenAI    │  │ Personalize  │
    │   (Claude)   │  │   (GPT-4)    │  │    Module    │
    └──────────────┘  └──────────────┘  └──────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                   SERVICE LAYER                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │  Gmail  │ │ Calendar│ │  Slack  │ │ Notion  │   ...    │
│  │   MCP   │ │   MCP   │ │   MCP   │ │   MCP   │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
│                  Platform-Specific API Clients               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  MongoDB Clients  │  │  Context Clients │               │
│  │  • Email Query    │  │  • Cross-platform│               │
│  │  • Calendar Query │  │    Correlation   │               │
│  │  • Docs Query     │  │  • Vector Search │               │
│  └──────────────────┘  └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
            │                            │
            ↓                            ↓
┌────────────────────────┐  ┌─────────────────────────┐
│      MongoDB            │  │  AWS OpenSearch         │
│  (Per-User Databases)   │  │  (Vector Embeddings)    │
│  • user_1100.gmail      │  │  • Semantic Search      │
│  • user_1100.calendar   │  │  • Similarity Matching  │
│  • user_1100.context_*  │  │                         │
└────────────────────────┘  └─────────────────────────┘
```

### **2. Request-Response Flow**

```
┌──────────┐
│   User   │
└──────────┘
     │
     │ 1. POST /chat
     │    { query: "Show unread emails", token: "xxx" }
     ↓
┌─────────────────────────────────────────────────────────┐
│                    Flask Endpoint                        │
│  • Validate request                                     │
│  • Extract session_id, token, query                     │
└─────────────────────────────────────────────────────────┘
     │
     │ 2. Pass to assistant()
     ↓
┌─────────────────────────────────────────────────────────┐
│                  Query Preprocessing                     │
│  • Extract dates ("yesterday" → "2024-12-18")          │
│  • Get user personality profile                         │
│  • Handle image/PDF uploads                             │
└─────────────────────────────────────────────────────────┘
     │
     │ 3. Build AI request
     ↓
┌─────────────────────────────────────────────────────────┐
│                  AI Model (Bedrock)                      │
│  • Analyze intent                                       │
│  • Select tool: "search_emails"                         │
│  • Generate params: {is_unread: true, date: "..."}     │
└─────────────────────────────────────────────────────────┘
     │
     │ 4. Execute tool
     ↓
┌─────────────────────────────────────────────────────────┐
│              Tool: search_emails                         │
│  ↓                                                       │
│  mongo_query_emails()                                   │
│  ↓                                                       │
│  mongo_email_client.py                                  │
│    • Validate user access                               │
│    • Get user_id from token                             │
│    • Query user_1100.gmail collection                   │
│    • Filter: { labels: "UNREAD", date: "2024-12-18" }  │
│    • Return: [email1, email2, ...]                      │
└─────────────────────────────────────────────────────────┘
     │
     │ 5. Return results to AI
     ↓
┌─────────────────────────────────────────────────────────┐
│                  AI Model (Bedrock)                      │
│  • Synthesize response                                  │
│  • Format for user                                      │
│  • Add ui_hints                                         │
└─────────────────────────────────────────────────────────┘
     │
     │ 6. Format response
     ↓
┌─────────────────────────────────────────────────────────┐
│               Response Formatting                        │
│  {                                                       │
│    "response": "You have 5 unread emails...",           │
│    "type": "emails",                                    │
│    "data": { "emails": [...] },                         │
│    "ui_hint": ["open_email_panel"]                      │
│  }                                                       │
└─────────────────────────────────────────────────────────┘
     │
     │ 7. Return to user
     ↓
┌──────────┐
│   User   │
│  Sees    │
│  Results │
└──────────┘
```

### **3. Tool Execution Architecture**

```
┌────────────────────────────────────────────────────┐
│           cosi_app.py - Tool Registry               │
│                                                     │
│  tools = {                                          │
│    "send_email": λ **kw: send_email(**kw),        │
│    "search_emails": λ **kw: mongo_query_emails(),  │
│    "create_event": λ **kw: create_event(**kw),    │
│    ...                                              │
│    (139 tools total)                                │
│  }                                                  │
└────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ↓               ↓               ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│Gmail Service │ │Slack Service │ │Trello Service│
│  (Gmail API) │ │ (Slack API)  │ │(Trello API)  │
└──────────────┘ └──────────────┘ └──────────────┘
        │               │               │
        ↓               ↓               ↓
┌──────────────────────────────────────────────────┐
│              Data Layer Clients                   │
│  ┌────────────────┐  ┌────────────────┐          │
│  │ API Execution  │  │ MongoDB Query  │          │
│  │ (Create/Update)│  │ (Search/Read)  │          │
│  └────────────────┘  └────────────────┘          │
└──────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   Gmail API  │ │   MongoDB    │ │ AWS OpenSearch│
│ (Google SDK) │ │(Per-User DB) │ │(Vector Search)│
└──────────────┘ └──────────────┘ └──────────────┘
```

### **4. Multi-Tenant Data Isolation**

```
                    ┌─────────────────────┐
                    │  unified_workspace  │
                    │  (Global Database)  │
                    │                     │
                    │  • users            │
                    │  • tools            │
                    │  • user_tools       │
                    │  • auth_tokens      │
                    └─────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ↓              ↓              ↓
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │   user_1100  │ │   user_1101  │ │   user_1102  │
    │   (Alice's)  │ │   (Bob's)    │ │  (Carol's)   │
    ├──────────────┤ ├──────────────┤ ├──────────────┤
    │ gmail        │ │ gmail        │ │ gmail        │
    │ calendar     │ │ calendar     │ │ calendar     │
    │ slack        │ │ slack        │ │ slack        │
    │ context_*    │ │ context_*    │ │ context_*    │
    │ personality  │ │ personality  │ │ personality  │
    └──────────────┘ └──────────────┘ └──────────────┘
    
    ✅ Complete data isolation per user
    ✅ No cross-user queries possible
    ✅ Independent scaling
```

### **5. Context Correlation System**

```
                    User Query:
        "What's related to these emails?"
                        │
                        ↓
        ┌───────────────────────────────┐
        │   get_email_context()         │
        │   Input: [email_id_1, ...]    │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │  Query context_gmail          │
        │  Find batches containing      │
        │  these email IDs              │
        └───────────────────────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │  Return correlation data:     │
        │  {                            │
        │    related_items: {           │
        │      calendar: [event_ids],   │
        │      docs: [doc_ids],         │
        │      trello: [card_ids],      │
        │      slack: [thread_ids],     │
        │      notion: [page_ids]       │
        │    },                          │
        │    correlation_text: "..."    │
        │  }                             │
        └───────────────────────────────┘
                        │
        ┌───────────────┼────────────────┐
        ↓               ↓                ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Fetch Events │ │ Fetch Docs   │ │ Fetch Tasks  │
│ from calendar│ │ from docs    │ │ from trello  │
└──────────────┘ └──────────────┘ └──────────────┘
                        │
                        ↓
        ┌───────────────────────────────┐
        │  Present unified view:        │
        │                               │
        │  Email Thread:                │
        │  "Re: Project Update"         │
        │                               │
        │  Related Items:               │
        │  📅 Meeting: Dec 20 @ 2pm     │
        │  📄 Doc: Project Plan v2      │
        │  ✅ Task: Review requirements │
        │  💬 Slack: #project-alpha     │
        └───────────────────────────────┘
```

### **6. Personalization Flow**

```
New User Onboarded
        │
        ↓
┌────────────────────────────────────┐
│ extract_user_personality.py        │
│ (Background job)                   │
└────────────────────────────────────┘
        │
        ├─→ 1. Fetch sent emails
        │      GET user_id.gmail
        │      WHERE from = user_email
        │      LIMIT 20
        │
        ├─→ 2. Fetch Slack messages
        │      GET user_id.slack_channel_messages
        │      WHERE sender = user_id
        │      LIMIT 100
        │
        ↓
┌────────────────────────────────────┐
│ Send to AWS Bedrock (Claude)       │
│                                    │
│ Prompt: "Analyze writing style     │
│          and extract personality   │
│          traits..."                │
└────────────────────────────────────┘
        │
        ↓
┌────────────────────────────────────┐
│ AI Response:                       │
│ {                                  │
│   tone: "professional yet casual", │
│   formality: "medium",             │
│   greeting_style: "Hi [Name]",     │
│   common_phrases: [...],           │
│   personality_traits: [...]        │
│ }                                  │
└────────────────────────────────────┘
        │
        ↓
┌────────────────────────────────────┐
│ Store in user_id.personality       │
└────────────────────────────────────┘
        │
        ↓
┌────────────────────────────────────┐
│ On subsequent queries:             │
│ • Retrieve personality profile     │
│ • Inject into system prompt        │
│ • AI tailors responses to          │
│   match user's style               │
└────────────────────────────────────┘
```

---

## 🎓 Key Architectural Patterns

### **1. Service Layer Pattern**
- Each platform has dedicated service module
- Encapsulates API-specific logic
- Provides uniform interface to application layer

### **2. Repository Pattern**
- MongoDB clients abstract database operations
- Tools don't know about database structure
- Easy to swap database implementations

### **3. Strategy Pattern**
- AI model selection (Bedrock vs OpenAI)
- Tool selection based on query intent
- Response formatting based on data type

### **4. Facade Pattern**
- `server.py` provides unified tool interface
- Hides complexity of 9 different platforms
- Single import point for all tools

### **5. Multi-Tenancy Pattern**
- Database-per-tenant isolation
- Token-based access control
- Per-user resource limits

---

## 🚀 Deployment Considerations

### **Environment Variables Required**
```bash
# MongoDB
MONGO_URI=mongodb://...

# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0

# OpenAI (fallback)
OPENAI_API_KEY=sk-...

# User Service
USER_SERVICE_BASE_URL=http://...

# OAuth Credentials
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SLACK_CLIENT_ID=...
NOTION_CLIENT_SECRET=...
```

### **Scaling Strategies**
1. **Horizontal Scaling**: Deploy multiple Flask instances behind load balancer
2. **Database Sharding**: MongoDB sharded cluster for user databases
3. **Caching**: Redis for frequent queries and token caching
4. **Async Processing**: Celery for background tasks (personality extraction)

---

## 📈 Performance Optimizations

1. **Token Caching**: 5-minute TTL cache for OAuth tokens
2. **Vector Search Indexing**: Pre-computed embeddings in MongoDB
3. **Query Batching**: Batch related queries to reduce DB calls
4. **Streaming Responses**: Real-time AI response streaming
5. **Connection Pooling**: MongoDB connection pool management

---

## 🔧 Development Guidelines

### **Adding a New Platform**

1. Create service file: `/services/{platform}_mcp.py`
2. Implement OAuth flow
3. Create MongoDB client: `/clients/mongo_{platform}_client.py`
4. Add tool definitions to `server.py`
5. Register tools in `cosi_app.py`
6. Create context collection schema
7. Add to system prompt
8. Write tests

### **Adding a New Tool**

1. Define function in appropriate service file
2. Add to `__all__` in `server.py`
3. Add lambda wrapper in `tools` dict
4. Define JSON schema in `function_defs`
5. Update system prompt with usage rules
6. Test with AI model

---

## 📚 Further Reading

- **MCP Protocol**: Model Context Protocol specification
- **AWS Bedrock**: Claude API documentation
- **MongoDB**: Multi-tenancy best practices
- **Vector Search**: OpenSearch vector engine guide

---

**Document Version**: 1.0  
**Last Updated**: December 19, 2024  
**Author**: System Architecture Team

