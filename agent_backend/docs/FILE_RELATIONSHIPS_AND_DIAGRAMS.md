# MCP Gmail - File Relationships & Visual Diagrams

## 📋 Table of Contents
1. [Directory Structure Tree](#directory-structure-tree)
2. [File Dependency Graph](#file-dependency-graph)
3. [Import Relationships](#import-relationships)
4. [Data Flow Diagrams](#data-flow-diagrams)
5. [Component Interaction Maps](#component-interaction-maps)
6. [Detailed File-by-File Breakdown](#detailed-file-by-file-breakdown)

---

## 🌲 Directory Structure Tree

```
mcp_gmail/
│
├── 📁 app/                          [Application Entry Points]
│   ├── cosi_app.py                 ⭐ Main Flask app (7166 lines)
│   ├── server.py                   🔧 Tool registry & aggregator
│   ├── mcp_flask_api.py            🌐 Alternative API interface
│   ├── mcp_gmail_agent.py          🤖 Agent-based interface
│   ├── mockapi_call.py             🧪 API testing utility
│   └── cosi_app.log                📝 Application logs
│
├── 📁 services/                     [Platform Integration Layer]
│   ├── gmail.py                    📧 Gmail API integration
│   ├── calendar_mcp.py             📅 Google Calendar API
│   ├── docs_mcp.py                 📄 Google Docs API
│   ├── sheets_mcp.py               📊 Google Sheets API
│   ├── slides_mcp.py               🎨 Google Slides API
│   ├── slack_mcp.py                💬 Slack API integration
│   ├── notion_mcp.py               📝 Notion API integration
│   ├── trello_mcp.py               ✅ Trello API integration
│   ├── salesforce_mcp.py           💼 Salesforce (optional)
│   └── jeera_mcp.py                🎯 Jira (optional)
│
├── 📁 clients/                      [Data Access Layer]
│   ├── mongo_email_client.py       🗄️ Gmail MongoDB queries (1185 lines)
│   ├── mongo_calendar_client.py    🗄️ Calendar MongoDB queries
│   ├── mongo_docs_client.py        🗄️ Docs/Sheets/Slides queries (906 lines)
│   ├── mongo_notion_client.py      🗄️ Notion MongoDB queries
│   ├── mongo_context_client.py     🔗 Cross-platform correlation (774 lines)
│   ├── mongo_personalization_client.py 👤 User personality queries
│   ├── db_method.py                🔐 Auth & token management (837 lines)
│   └── drive_client.py             📁 Google Drive operations
│
├── 📁 config/                       [Configuration Files]
│   ├── config.py                   ⚙️ Main config settings
│   ├── config_calender.py          ⚙️ Calendar-specific config
│   ├── config_salesforce.py        ⚙️ Salesforce config
│   ├── credentials_calender.json   🔑 OAuth credentials
│   ├── token.json                  🎫 OAuth tokens
│   └── token_calendar.json         🎫 Calendar OAuth tokens
│
├── 📁 db/                           [Database Layer]
│   └── mongo_client.py             🔌 MongoDB connection factory
│
├── 📁 utils/                        [Utility Functions]
│   ├── utils.py                    🛠️ Token fetching utilities
│   ├── date_utils.py               📆 Date parsing engine (259 lines)
│   ├── error_handler.py            ⚠️ Error handling
│   └── session_queries.csv         📊 Query logging
│
├── 📁 personalization/              [AI Personalization]
│   ├── extract_user_personality.py 🧠 Personality extraction (681 lines)
│   └── slack.py                    💬 Slack personality analysis
│
├── 📁 tests/                        [Test Suite]
│   ├── test_gmail_setup.py         ✅ Gmail OAuth tests
│   ├── test_openai_key.py          ✅ OpenAI validation
│   └── test.py                     ✅ General tests
│
├── 📁 backups/                      [Legacy/Backup Files]
│   └── [8 backup files]
│
├── 📁 docs/                         [Documentation]
│   ├── architecture_diagram.md
│   ├── MCP_Gmail_Architecture_Overview.md
│   └── README.md
│
├── 📁 google_calender/              [Legacy Calendar Module]
│   └── [5 files]
│
├── 📁 notebooks/                    [Jupyter Notebooks]
│   └── ab.ipynb
│
├── 📄 requirements.txt              📦 Python dependencies
├── 📄 Dockerfile                    🐳 Container config
├── 📄 start_cosi_app.sh             🚀 Startup script
├── 📄 compare.py                    🔍 Comparison utility (5620 lines)
├── 📄 search_apis_*.py              🔎 API discovery scripts
├── 📄 token_counter.py              📊 Token tracking
└── 📄 test_bedrock_embeddings.py    🧪 Vector embedding tests

Total: ~22,000+ lines of Python code
```

---

## 🕸️ File Dependency Graph

### **Import Hierarchy (Top-Down)**

```
┌─────────────────────────────────────────────────────────────┐
│                    ENTRY POINT                              │
│                   cosi_app.py                               │
│                   (7166 lines)                              │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ↓                 ↓                 ↓
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  server.py  │  │date_utils.py│  │ db_method.py│
│  (imports   │  │             │  │             │
│  all tools) │  │             │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
        │                                   │
        ↓                                   ↓
┌───────────────────────────────────────────────────┐
│            SERVICE LAYER IMPORTS                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  │gmail.py │ │slack_mcp│ │trello   │    ...     │
│  └─────────┘ └─────────┘ └─────────┘            │
└───────────────────────────────────────────────────┘
        │
        ↓
┌───────────────────────────────────────────────────┐
│            CLIENT LAYER IMPORTS                    │
│  ┌──────────────────┐ ┌──────────────────┐       │
│  │mongo_email_client│ │mongo_context_    │  ...  │
│  │                  │ │client            │       │
│  └──────────────────┘ └──────────────────┘       │
└───────────────────────────────────────────────────┘
        │
        ↓
┌───────────────────────────────────────────────────┐
│               BASE IMPORTS                         │
│  ┌──────────────┐  ┌──────────────┐              │
│  │mongo_client  │  │  db_method   │              │
│  │    .py       │  │    .py       │              │
│  └──────────────┘  └──────────────┘              │
└───────────────────────────────────────────────────┘
```

---

## 📊 Import Relationships

### **cosi_app.py Dependencies**

```python
cosi_app.py
├── Standard Library
│   ├── os, json, time, csv
│   ├── datetime (dateutil.parser)
│   ├── base64, io (for file handling)
│   └── logging, re, uuid
│
├── Third-Party
│   ├── Flask (Flask, request, jsonify, CORS)
│   ├── boto3 (AWS Bedrock)
│   ├── openai (OpenAI)
│   ├── PIL (Image processing)
│   ├── fitz (PyMuPDF for PDF)
│   └── requests
│
├── Internal - Tools (from server.py)
│   ├── Gmail: send_email, draft_email, update_email
│   ├── Calendar: create_event, search_events, delete_events
│   ├── Slack: send_slack_messages, get_channels
│   ├── Docs: create_document, update_document
│   ├── Notion: create_page, query_database
│   ├── Trello: task_create, task_update
│   └── [Total: 139 tool imports]
│
├── Internal - MongoDB Clients
│   ├── mongo_email_client: mongo_query_emails, mongo_get_emails
│   ├── mongo_calendar_client: mongo_query_events, mongo_get_events
│   ├── mongo_docs_client: mongo_query_docs, mongo_get_docs
│   └── mongo_context_client: get_*_context functions
│
├── Internal - Utilities
│   ├── date_utils.DateParser
│   ├── db_method: get_user_list, get_user_info
│   └── personalization: get_user_personality_profile
│
└── Internal - Config
    └── mongo_client: get_mongo_client
```

### **server.py Dependencies**

```python
server.py (Tool Aggregator)
├── Gmail Service
│   └── services.gmail
│       ├── send_email
│       ├── draft_email
│       ├── update_email
│       ├── download_attachments
│       ├── list_available_labels
│       └── create_gmail_label
│
├── Calendar Service
│   └── services.calendar_mcp
│       ├── create_event
│       ├── get_event
│       ├── search_events
│       ├── update_calendar_event
│       └── delete_events_by_filter
│
├── Slack Service
│   └── services.slack_mcp
│       ├── get_channels
│       ├── send_slack_messages
│       ├── get_channel_messages
│       ├── send_dm
│       └── [13 Slack functions]
│
├── [Similar for Docs, Sheets, Slides, Notion, Trello]
│
└── MongoDB Clients
    ├── clients.mongo_email_client
    ├── clients.mongo_calendar_client
    ├── clients.mongo_docs_client
    ├── clients.mongo_notion_client
    └── clients.mongo_context_client
```

### **Service Layer Dependencies**

Each service file follows this pattern:

```python
services/gmail.py
├── Google Libraries
│   ├── google.auth.transport.requests
│   ├── google.oauth2.credentials
│   ├── google_auth_oauthlib.flow
│   └── googleapiclient.discovery
│
├── Internal
│   ├── clients.db_method
│   │   └── get_user_tool_access_token
│   └── Standard libraries (base64, email, etc.)
│
└── Exports
    ├── get_gmail_service
    ├── send_email
    ├── draft_email
    └── [other Gmail functions]
```

```python
services/slack_mcp.py
├── slack_sdk.WebClient
├── clients.db_method
│   └── get_user_tool_access_token
├── db.mongo_client
│   └── get_mongo_client
└── Exports: [13 Slack functions]
```

### **Client Layer Dependencies**

```python
clients/mongo_email_client.py
├── pymongo.MongoClient
├── boto3 (for AWS OpenSearch)
├── botocore (for SigV4 auth)
├── requests
├── numpy (for vector operations)
├── db.mongo_client
│   └── get_mongo_client
├── clients.db_method
│   └── validate_user_tool_access
└── utils.date_utils
    └── DateParser
```

```python
clients/mongo_context_client.py
├── pymongo.MongoClient
├── db.mongo_client
├── clients.db_method
│   └── validate_user_tool_access
└── Exports context functions for all platforms
```

---

## 🔄 Data Flow Diagrams

### **1. Email Search Flow**

```
USER REQUEST
    │
    │ query: "Show unread emails from yesterday"
    │ token: "abc-123"
    ↓
┌─────────────────────────────────────┐
│ cosi_app.py: /chat endpoint         │
│ • Parse query                       │
│ • Extract date with DateParser      │
│ • Call AI model                     │
└─────────────────────────────────────┘
    │
    │ AI decides: Use "search_emails"
    │ params: {is_unread: true, date: "2024-12-18"}
    ↓
┌─────────────────────────────────────┐
│ cosi_app.py: tools["search_emails"] │
│ ↓                                   │
│ server.py: mongo_query_emails()     │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ mongo_email_client.py               │
│ • validate_user_tool_access(token)  │
│ • get_user_id_from_token(token)     │
│ • get_collection(token) → db.gmail  │
│ • Build MongoDB query               │
│ • Execute query with filters        │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ MongoDB: user_1100.gmail            │
│ Find: {                             │
│   labels: "UNREAD",                 │
│   internalDate: "2024-12-18"        │
│ }                                   │
│ Sort: -internalDateNum              │
│ Limit: 10                           │
└─────────────────────────────────────┘
    │
    │ Returns: [email1, email2, ...]
    ↓
┌─────────────────────────────────────┐
│ mongo_email_client.py               │
│ • Format results                    │
│ • Add metadata                      │
│ • Return dict                       │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ cosi_app.py                         │
│ • Pass results to AI                │
│ • AI formats for user               │
│ • Add ui_hints                      │
│ • Return JSON response              │
└─────────────────────────────────────┘
    │
    ↓
USER RESPONSE
```

### **2. Context Correlation Flow**

```
USER: "What's related to this email?"
    │
    ↓
┌─────────────────────────────────────┐
│ cosi_app.py                         │
│ • Extract email_id from context     │
│ • AI selects: get_email_context     │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ server.py → mongo_context_client    │
│ get_email_context([email_id])       │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ mongo_context_client.py             │
│ • validate_user_tool_access         │
│ • get_context_collection(token)     │
│ • Query context_gmail collection    │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ MongoDB: user_1100.context_gmail    │
│ Find: {                             │
│   email_ids: {$in: [email_id]}      │
│ }                                   │
│ Returns: {                          │
│   correlation_text: "...",          │
│   related_items: {...}              │
│ }                                   │
└─────────────────────────────────────┘
    │
    │ For each related item type:
    ├→ Calendar: get_calendar_events()
    ├→ Docs: get_documents()
    ├→ Trello: get_tasks()
    ├→ Slack: get_messages()
    └→ Notion: get_pages()
    │
    ↓
┌─────────────────────────────────────┐
│ Aggregate all related data          │
│ Format unified response             │
└─────────────────────────────────────┘
    │
    ↓
USER SEES CONNECTED ITEMS
```

### **3. Tool Execution Pattern**

```
┌─────────────────────────────────────┐
│         ANY TOOL REQUEST            │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ 1. AUTHORIZATION LAYER              │
│    (db_method.py)                   │
│                                     │
│ validate_user_tool_access(token,    │
│                          tool_name) │
│ ↓                                   │
│ • Check unified_workspace.user_tools│
│ • Verify user has access            │
│ • Return (is_valid, error, code)    │
└─────────────────────────────────────┘
    │
    │ ✅ Authorized
    ↓
┌─────────────────────────────────────┐
│ 2. TOKEN RETRIEVAL                  │
│    (db_method.py)                   │
│                                     │
│ get_user_tool_access_token(token,   │
│                           tool_name)│
│ ↓                                   │
│ • Get platform-specific OAuth token │
│ • Check expiration                  │
│ • Refresh if needed                 │
│ • Return access_token               │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ 3. USER ID RESOLUTION               │
│    (mongo_*_client.py)              │
│                                     │
│ get_user_id_from_token(token)       │
│ ↓                                   │
│ • Query user_authenticate_token     │
│ • Resolve unified token to user_id  │
│ • Return user_id (e.g., "1100")     │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ 4. PLATFORM CLIENT BUILDING         │
│    (services/*_mcp.py)              │
│                                     │
│ • Use access_token to build client  │
│ • Gmail: build('gmail', 'v1', ...)  │
│ • Slack: WebClient(token=...)       │
│ • Trello: TrelloClient(token=...)   │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ 5. API CALL / DB QUERY              │
│                                     │
│ • If CREATE/UPDATE: Call API        │
│ • If READ/SEARCH: Query MongoDB     │
│   → Connect to user_id database     │
│   → Query specific collection       │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ 6. RESPONSE FORMATTING              │
│                                     │
│ • Standardize response structure    │
│ • {success, data, message}          │
│ • Add metadata                      │
└─────────────────────────────────────┘
    │
    ↓
┌─────────────────────────────────────┐
│ 7. RETURN TO APPLICATION            │
└─────────────────────────────────────┘
```

---

## 🗺️ Component Interaction Maps

### **1. File Interaction: Email Operations**

```
┌──────────────────────────────────────────────────────────┐
│                    cosi_app.py                           │
│  • Main orchestrator                                     │
│  • Handles /chat endpoint                                │
└──────────────────────────────────────────────────────────┘
           │                          │
           │ Import                   │ Import
           ↓                          ↓
┌────────────────────┐    ┌─────────────────────────┐
│    server.py       │    │  date_utils.py          │
│  • send_email      │    │  • DateParser           │
│  • mongo_query_*   │    │  • extract_date_parts   │
└────────────────────┘    └─────────────────────────┘
           │
           │ Routes to
           ↓
┌────────────────────────────────────────────────────────┐
│              services/gmail.py                          │
│  • get_gmail_service(token)                            │
│  • send_email(to, subject, body, token)                │
│  • draft_email(...)                                  │
│                                                         │
│  Imports:                                               │
│  ├→ google.auth (OAuth)                                │
│  └→ db_method.get_user_tool_access_token               │
└────────────────────────────────────────────────────────┘
           │                          │
           │ For SEARCH               │ For SEND
           ↓                          ↓
┌───────────────────────┐  ┌──────────────────────┐
│mongo_email_client.py  │  │   Gmail API          │
│• mongo_query_emails   │  │ (Google SDK)         │
│• vector search        │  │ • messages().send()  │
└───────────────────────┘  └──────────────────────┘
           │
           │ Uses
           ↓
┌────────────────────────────────────────────────────────┐
│               db_method.py                              │
│  • validate_user_tool_access(token, "Gsuite")          │
│  • get_user_tool_access_token(token, "Gsuite")         │
│  • get_user_id_from_token(token)                       │
│                                                         │
│  Accesses:                                              │
│  └→ unified_workspace.user_authenticate_token           │
│  └→ unified_workspace.user_tools                        │
└────────────────────────────────────────────────────────┘
           │
           │ Uses
           ↓
┌────────────────────────────────────────────────────────┐
│              mongo_client.py                            │
│  • get_mongo_client()                                  │
│  • Returns MongoClient instance                         │
└────────────────────────────────────────────────────────┘
           │
           ↓
┌────────────────────────────────────────────────────────┐
│                   MongoDB                               │
│  • unified_workspace (global)                          │
│  • user_1100.gmail (per-user data)                     │
└────────────────────────────────────────────────────────┘
```

### **2. File Interaction: Context Correlation**

```
┌──────────────────────────────────────────────────────────┐
│                    cosi_app.py                           │
│  • Tool: get_email_context                              │
└──────────────────────────────────────────────────────────┘
                         │
                         │ Routes to
                         ↓
┌──────────────────────────────────────────────────────────┐
│           mongo_context_client.py                        │
│  (774 lines - THE CORRELATION ENGINE)                   │
│                                                          │
│  Functions:                                              │
│  ├→ get_email_context(email_ids, token)                 │
│  ├→ get_calendar_context(event_ids, token)              │
│  ├→ get_docs_context(doc_ids, token)                    │
│  ├→ get_slides_context(slide_ids, token)                │
│  ├→ get_notion_context(page_ids, token)                 │
│  ├→ get_trello_context(card_ids, token)                 │
│  └→ get_slack_context(message_ids, token)               │
└──────────────────────────────────────────────────────────┘
         │                    │                    │
         │ Queries            │ Validates          │ Uses
         ↓                    ↓                    ↓
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   MongoDB    │  │   db_method.py   │  │mongo_client  │
│ context_*    │  │ • validate_      │  │    .py       │
│ collections  │  │   user_access    │  │              │
└──────────────┘  └──────────────────┘  └──────────────┘
         │
         │ Returns related IDs
         ↓
┌──────────────────────────────────────────────────────────┐
│          Related Item Fetching                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │mongo_calendar│  │ mongo_docs   │  │mongo_notion  │  │
│  │_client.py    │  │_client.py    │  │_client.py    │  │
│  │• get_events  │  │• get_docs    │  │• get_pages   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### **3. File Interaction: Personalization**

```
┌──────────────────────────────────────────────────────────┐
│         personalization/extract_user_personality.py      │
│  (681 lines - PERSONALITY EXTRACTION SCRIPT)            │
│                                                          │
│  Workflow:                                               │
│  1. get_all_users()                                      │
│  2. For each user:                                       │
│     • get_sent_emails(user_id, email)                   │
│     • get_slack_messages(user_id)                       │
│     • extract_personality_with_bedrock(emails)          │
│     • extract_slack_personality_with_bedrock(msgs)      │
│     • store_personality_in_mongo(user_id, profile)      │
└──────────────────────────────────────────────────────────┘
         │                    │                    │
         │ Fetches from       │ Analyzes with      │ Stores in
         ↓                    ↓                    ↓
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│   MongoDB    │  │   AWS Bedrock    │  │   MongoDB    │
│ • user.gmail │  │   (Claude API)   │  │ • user.      │
│ • user.slack │  │   • Analyze      │  │   personality│
│              │  │     writing      │  │              │
└──────────────┘  └──────────────────┘  └──────────────┘
         │
         │ Used by
         ↓
┌──────────────────────────────────────────────────────────┐
│         mongo_personalization_client.py                  │
│  • get_user_personality_profile(token)                  │
│  • Returns personality dict for AI prompting            │
└──────────────────────────────────────────────────────────┘
         │
         │ Consumed by
         ↓
┌──────────────────────────────────────────────────────────┐
│                    cosi_app.py                           │
│  • Retrieves personality profile                        │
│  • Injects into system prompt                           │
│  • AI tailors responses to user's style                 │
└──────────────────────────────────────────────────────────┘
```

### **4. File Interaction: Authentication & Authorization**

```
┌──────────────────────────────────────────────────────────┐
│                    db_method.py                          │
│  (837 lines - AUTHENTICATION HUB)                       │
│                                                          │
│  Key Functions:                                          │
│  ├→ validate_user_tool_access(token, tool_name)         │
│  │   • Checks if user has access to platform            │
│  │                                                       │
│  ├→ get_user_tool_access_token(token, tool_name)        │
│  │   • Retrieves OAuth token for platform               │
│  │                                                       │
│  ├→ add_or_update_user_tool(token, tool, cred)          │
│  │   • Stores/updates OAuth credentials                 │
│  │                                                       │
│  └→ get_user_id_from_token(token)                       │
│      • Maps unified token → user_id                      │
└──────────────────────────────────────────────────────────┘
         │                                    │
         │ Uses                               │ Queries
         ↓                                    ↓
┌──────────────────┐          ┌──────────────────────────┐
│ mongo_client.py  │          │      MongoDB             │
│ • get_mongo_     │          │ unified_workspace:       │
│   client()       │          │ • users                  │
└──────────────────┘          │ • user_tools             │
                              │ • user_authenticate_token│
                              └──────────────────────────┘
         │
         │ Called by ALL clients
         ↓
┌──────────────────────────────────────────────────────────┐
│              ALL CLIENT FILES                            │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │mongo_email_client│  │mongo_calendar_   │   ...      │
│  │                  │  │client            │            │
│  │ def get_         │  │ def get_         │            │
│  │ collection():    │  │ collection():    │            │
│  │   validate_user_ │  │   validate_user_ │            │
│  │   tool_access()  │  │   tool_access()  │            │
│  └──────────────────┘  └──────────────────┘            │
└──────────────────────────────────────────────────────────┘
         │
         │ Called by ALL services
         ↓
┌──────────────────────────────────────────────────────────┐
│              ALL SERVICE FILES                           │
│  ┌──────────────────┐  ┌──────────────────┐            │
│  │  gmail.py        │  │  slack_mcp.py    │   ...      │
│  │                  │  │                  │            │
│  │ def get_gmail_   │  │ def get_slack_   │            │
│  │ service():       │  │ client():        │            │
│  │   get_user_tool_ │  │   get_user_tool_ │            │
│  │   access_token() │  │   access_token() │            │
│  └──────────────────┘  └──────────────────┘            │
└──────────────────────────────────────────────────────────┘
```

---

## 📖 Detailed File-by-File Breakdown

### **Tier 1: Entry Points (app/)**

#### **cosi_app.py** (7166 lines) ⭐ **MOST CRITICAL FILE**

**Purpose**: Main Flask application & AI orchestration engine

**Key Sections**:
```python
Lines 1-200:   Imports & Configuration
Lines 201-400: Tool imports from server.py
Lines 401-460: Helper functions (create_document_with_platform_choice)
Lines 461-686: Tool registry (139 tools)
Lines 687-4000: Tool definitions (function_defs array)
Lines 4001-5195: Utility functions
  - summarize_conversation()
  - format_tool_result()
  - log_to_csv()
  - invoke_bedrock()
  - invoke_openai()
Lines 5196-6180: /chat endpoint (main conversation handler)
Lines 6182-7166: /autoPilot endpoint (autonomous mode)
```

**Critical Functions**:
- `assistant()` (line 5197): Main `/chat` handler
  - Manages conversation history
  - Calls AI models
  - Executes tools
  - Formats responses

- `invoke_bedrock(body)` (line 4307): AWS Bedrock integration
  - Signs requests with AWS credentials
  - Handles streaming
  - Parses tool calls

- `invoke_openai(body)` (line 4342): OpenAI fallback
  - Function calling
  - Schema validation

**Imports From**:
- `server.py` → All 139 tools
- `mongo_*_client.py` → MongoDB query functions
- `db_method.py` → User management
- `date_utils.py` → Date parsing

**Used By**: Direct HTTP clients (web apps, mobile apps)

---

#### **server.py** ⭐ **TOOL AGGREGATOR**

**Purpose**: Centralized tool registry & imports

**Structure**:
```python
Lines 1-500:   Import all Gmail tools
Lines 501-1000: Import all Calendar tools
Lines 1001-1500: Import all Slack tools
Lines 1501-2000: Import all Docs tools
Lines 2001-2500: Import all Notion tools
Lines 2501-3000: Import all Trello tools
Lines 3001-3485: Export all tools via __all__
```

**Pattern**:
```python
# Import from services
from services.gmail import (
    send_email,
    draft_email,
    update_email,
    ...
)

# Import from clients
from clients.mongo_email_client import (
    mongo_query_emails,
    mongo_get_emails,
    ...
)

# Export everything
__all__ = [
    "send_email",
    "mongo_query_emails",
    ...  # 139 exports
]
```

**Why It Exists**: 
- Single import point for cosi_app.py
- Avoids circular dependencies
- Provides clean abstraction

---

### **Tier 2: Service Layer (services/)**

#### **services/gmail.py** (689 lines)

**Purpose**: Gmail API integration

**Key Functions**:
```python
get_gmail_service(token)
  - Retrieves OAuth token via db_method
  - Builds Google API client
  - Returns gmail service object

send_email(to, subject, body, token)
  - Builds MIME message
  - Calls Gmail API messages().send()
  
draft_email(to, subject, body, token)
  - Creates draft email
  
update_email(email_id, action, token)
  - Mark read/unread
  - Star/unstar
  - Add/remove labels
  - Delete
```

**Dependencies**:
- `google.oauth2.credentials`
- `googleapiclient.discovery`
- `db_method.get_user_tool_access_token`

**Used By**: cosi_app.py via server.py

---

#### **services/slack_mcp.py** (895 lines)

**Purpose**: Slack API integration

**Key Functions**:
```python
get_slack_client(token)
  - Gets Slack OAuth token
  - Returns WebClient instance

send_slack_messages(channel, message, token)
  - Posts message to channel
  
get_channel_messages(channel, limit, token)
  - Fetches channel history
  - Caches channels for 5 minutes
  
send_dm(user, message, token)
  - Opens DM conversation
  - Sends private message
```

**Special Features**:
- Channel caching (5-min TTL)
- User caching
- Message ID generation (UUID format)
- MongoDB integration for channel data

**Dependencies**:
- `slack_sdk.WebClient`
- `db_method.get_user_tool_access_token`
- `mongo_client.get_mongo_client`

---

#### **services/trello_mcp.py**

**Purpose**: Trello API integration (32 functions)

**Key Functions**:
```python
task_list_boards(token)
task_create(board_id, list_id, name, desc, token)
task_update(card_id, updates, token)
task_move(card_id, list_id, token)
task_checklist_create(card_id, name, token)
task_label_add(card_id, label_id, token)
```

**Pattern**: All functions follow `task_*` naming

---

### **Tier 3: Data Layer (clients/)**

#### **clients/mongo_email_client.py** (1185 lines) ⭐ **DATA WORKHORSE**

**Purpose**: Gmail data queries with vector search

**Key Functions**:

```python
get_collection(token)
  - Validates user access to Gmail
  - Returns user_id.gmail collection
  
mongo_query_emails(query, is_unread, from_email, start_date, token)
  - Builds MongoDB query
  - Handles vector search for semantic queries
  - Returns matched emails
  
perform_opensearch_vector_search(query_text, user_db_name)
  - Generates embedding via AWS Titan
  - Performs k-NN search
  - Returns similar emails
```

**Vector Search Flow**:
1. User query → Generate embedding
2. Query AWS OpenSearch with k-NN
3. Get email IDs
4. Fetch full emails from MongoDB
5. Return ranked results

**Dependencies**:
- `boto3` (AWS OpenSearch)
- `numpy` (vector operations)
- `date_utils.DateParser`
- `db_method.validate_user_tool_access`

---

#### **clients/mongo_context_client.py** (774 lines) ⭐ **CORRELATION ENGINE**

**Purpose**: Cross-platform relationship discovery

**Key Insight**: This is the "magic" of the system – finding connections between emails, events, docs, tasks, etc.

**Architecture**:
```python
get_email_context(email_ids, token)
  1. Query context_gmail collection
  2. Find batches containing email_ids
  3. Extract related_items: {
       calendar: [event_ids],
       docs: [doc_ids],
       trello: [card_ids],
       slack: [thread_ids],
       notion: [page_ids]
     }
  4. Return AI-generated correlation_text + IDs

get_calendar_context(event_ids, token)
  - Similar pattern for calendar events
  
get_docs_context(doc_ids, token)
  - Similar pattern for documents
  
... (7 context functions total)
```

**Data Structure**:
```javascript
// context_gmail collection
{
  batch_id: "batch-uuid",
  email_ids: ["email-1", "email-2"],
  correlation_text: "AI analysis about these emails...",
  related_items: {
    calendar: ["event-1"],
    docs: ["doc-1"],
    trello: ["card-1"],
    slack: ["thread-1"]
  },
  embedding: [0.123, ...],  // For vector search
  metadata: {
    participants: ["john@example.com"],
    topics: ["meeting", "budget"],
    priority: "high"
  }
}
```

**How Context is Generated** (Background Process):
1. Periodic batch processing
2. Group related items (emails, events, docs)
3. Send to AWS Bedrock Claude
4. AI generates correlation_text
5. Store in context_* collections

---

#### **clients/db_method.py** (837 lines) ⭐ **AUTH CENTRAL**

**Purpose**: Authentication, authorization, token management

**Critical Functions**:

```python
validate_user_tool_access(token, tool_name)
  → Checks if user has permission
  → Returns: (is_valid: bool, error_msg: str, status_code: int)
  
get_user_tool_access_token(token, tool_name)
  → Retrieves OAuth token for platform
  → Returns: (token_data: dict, status_code: int)
  
get_user_id_from_token(token)
  → Maps unified_token → user_id
  → Queries unified_workspace.user_authenticate_token
  
add_or_update_user_tool(token, tool_name, cred, access_token)
  → Stores OAuth credentials
  → Upserts to user_tools collection
```

**Token Flow**:
```
unified_token (from client)
    ↓
get_user_id_from_token()
    ↓
user_id (e.g., "1100")
    ↓
validate_user_tool_access(user_id, "Gmail")
    ↓
✅ Authorized
    ↓
get_user_tool_access_token(user_id, "Gmail")
    ↓
gmail_oauth_token
    ↓
Build Gmail API client
```

**Database Schema**:
```javascript
// unified_workspace.user_authenticate_token
{
  user_id: "1100",
  tool_name: "unified",
  tool_token: "abc-123",
  created_at: ISODate,
  expires_at: ISODate
}

// unified_workspace.user_tools
{
  user_id: "1100",
  tool_id: "gsuite",
  access_token: {
    token: "ya29...",
    refresh_token: "1//...",
    client_id: "...",
    client_secret: "...",
    scopes: [...]
  }
}
```

---

#### **clients/mongo_personalization_client.py**

**Purpose**: Retrieve user personality profiles

**Key Function**:
```python
get_user_personality_profile(unified_token)
  - Gets user_id from token
  - Queries user_id.personality collection
  - Returns personality_profile dict
```

**Used By**: cosi_app.py to inject into system prompt

---

### **Tier 4: Utilities & Config**

#### **utils/date_utils.py** (259 lines) ⭐ **DATE INTELLIGENCE**

**Purpose**: Natural language → ISO date conversion

**Class**: `DateParser`

**Capabilities**:
- Relative: "yesterday", "last week", "next month"
- Specific: "June 7th 2025", "15th of July"
- Weekdays: "Monday", "Friday"
- Quarters: "Q3", "first quarter"
- Ranges: "from Jan 1 to Jan 31"

**Key Methods**:
```python
extract_date_parts(query)
  → Returns: (date_parts: dict, clean_query: str)
  → Example: "emails from June 7th" 
            → {month: 6, day: 7}, "emails from"
  
build_date_query(date_parts)
  → Converts to MongoDB query
  → Example: {month: 6, day: 7} 
            → {"$and": [{"month": 6}, {"day": 7}]}
```

**Usage in cosi_app.py**:
```python
parser = DateParser()
date_parts, clean_query = parser.extract_date_parts(user_query)
# Use clean_query for AI
# Use date_parts for MongoDB filters
```

---

#### **utils/utils.py**

**Purpose**: Token fetching from external service

```python
get_tool_token(unified_token, tool_name)
  - Calls external user service API
  - Returns OAuth token for tool
```

---

#### **db/mongo_client.py** (17 lines)

**Purpose**: MongoDB connection factory

```python
def get_mongo_client():
    client = MongoClient(MONGO_URI)
    return client

def get_mongo_client_by_db(db_name: str):
    client = MongoClient(MONGO_URI)
    return client[db_name]
```

**Why Separate File**: 
- Centralized connection management
- Easy to add connection pooling
- Single source of truth for MONGO_URI

---

### **Tier 5: Personalization**

#### **personalization/extract_user_personality.py** (681 lines)

**Purpose**: AI-powered personality extraction (batch script)

**Workflow**:
```python
main()
  ↓
get_all_users()  # From unified_workspace.users
  ↓
for each user:
  ↓
  process_user(user)
    ↓
    get_sent_emails(user_id, email, limit=20)
      - Query user_id.gmail WHERE from=user_email
    ↓
    extract_personality_with_bedrock(emails)
      - Clean email bodies
      - Send to Claude with analysis prompt
      - Parse JSON response
    ↓
    get_slack_messages(user_id, limit=100)
      - Query user_id.slack_channel_messages
    ↓
    extract_slack_personality_with_bedrock(messages)
      - Analyze Slack writing style
    ↓
    store_personality_in_mongo(user_id, profile)
      - Upsert to user_id.personality
```

**Personality Profile Structure**:
```javascript
{
  user_email: "john@example.com",
  personality_profile: {
    email_personality: {
      tone: "professional yet friendly",
      formality: "medium",
      greeting_style: "Hi [Name],",
      closing_style: "Best regards,",
      common_phrases: ["Just wanted to...", "Let me know"],
      personality_traits: ["collaborative", "detail-oriented"]
    },
    slack_personality: {
      tone: "casual",
      emoji_usage: "frequent",
      response_style: "quick, concise"
    }
  },
  num_emails_analyzed: 20,
  num_slack_messages_analyzed: 100,
  created_at: ISODate,
  updated_at: ISODate
}
```

**Run As**: Background job or manual script

---

## 🎯 File Criticality Matrix

| File | Lines | Criticality | Role | Can System Run Without It? |
|------|-------|-------------|------|---------------------------|
| cosi_app.py | 7166 | 🔴 CRITICAL | Main orchestrator | ❌ No |
| server.py | 3485 | 🔴 CRITICAL | Tool registry | ❌ No |
| db_method.py | 837 | 🔴 CRITICAL | Auth/tokens | ❌ No |
| mongo_email_client.py | 1185 | 🟠 HIGH | Gmail queries | ⚠️ Gmail only |
| mongo_context_client.py | 774 | 🟠 HIGH | Correlations | ⚠️ Context only |
| date_utils.py | 259 | 🟡 MEDIUM | Date parsing | ⚠️ Dates only |
| gmail.py | 689 | 🟡 MEDIUM | Gmail API | ⚠️ Gmail only |
| slack_mcp.py | 895 | 🟡 MEDIUM | Slack API | ⚠️ Slack only |
| mongo_client.py | 17 | 🔴 CRITICAL | DB connection | ❌ No |
| extract_personality.py | 681 | 🟢 LOW | Personalization | ✅ Yes |

---

## 🔗 Circular Dependency Prevention

The system **carefully avoids circular imports** through:

1. **One-way import flow**: 
   ```
   cosi_app.py → server.py → services → clients → db/utils
   ```

2. **db_method.py as leaf node**: 
   - No imports from other internal modules
   - Only imports from stdlib and pymongo

3. **mongo_client.py as foundation**: 
   - Imported by all clients
   - No internal dependencies

4. **server.py as facade**: 
   - Aggregates without logic
   - Pure re-export pattern

---

## 📊 Code Statistics

| Category | Files | Total Lines | % of Codebase |
|----------|-------|-------------|---------------|
| Application Layer | 4 | ~10,000 | 45% |
| Service Layer | 10 | ~6,000 | 27% |
| Data Layer | 8 | ~5,000 | 23% |
| Utilities | 5 | ~1,000 | 5% |
| **Total** | **27** | **~22,000** | **100%** |

**Largest Files**:
1. cosi_app.py - 7,166 lines
2. compare.py - 5,620 lines
3. server.py - 3,485 lines
4. mongo_email_client.py - 1,185 lines
5. mongo_docs_client.py - 906 lines

---

**Document Version**: 1.0  
**Last Updated**: December 19, 2024  
**Purpose**: File relationships & visual architecture

