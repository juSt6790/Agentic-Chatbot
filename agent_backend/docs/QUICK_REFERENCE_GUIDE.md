# MCP Gmail - Quick Reference Guide

## 📚 Documentation Index

### **Complete Documentation Set**

1. **[MCP_GMAIL_ARCHITECTURE_DOCUMENTATION.md](MCP_GMAIL_ARCHITECTURE_DOCUMENTATION.md)** (Main Architecture)
   - System overview
   - 4-tier architecture
   - File structure & purpose
   - Database schema
   - API endpoints
   - Tool system (139 tools)

2. **[FILE_RELATIONSHIPS_AND_DIAGRAMS.md](FILE_RELATIONSHIPS_AND_DIAGRAMS.md)** (File Dependencies)
   - Directory structure tree
   - Import relationships
   - Data flow diagrams
   - Component interaction maps
   - File-by-file breakdown

3. **[AI_IMPLEMENTATION_GUIDE.md](AI_IMPLEMENTATION_GUIDE.md)** (AI Intelligence)
   - AI models used (Claude, GPT-4, Titan)
   - Decision-making process
   - Tool selection algorithm
   - Semantic search & embeddings
   - Context intelligence
   - Personalization engine

4. **This File** (Quick Reference)

---

## 🎯 System Overview (30-Second Version)

**What**: AI-powered unified workspace assistant

**Platforms**: Gmail, Calendar, Docs, Sheets, Slides, Slack, Notion, Trello, Gamma (9 platforms)

**Features**: 139 tools across platforms, cross-platform intelligence, AI-powered search, personalization

**Tech Stack**: 
- Backend: Python/Flask
- AI: AWS Bedrock (Claude 3.5), OpenAI GPT-4
- Database: MongoDB (multi-tenant)
- Vector Search: AWS OpenSearch + Titan Embeddings
- Auth: OAuth 2.0

---

## 🏗️ Architecture (1-Minute Version)

```
┌──────────────────────────────────────────────────┐
│  PRESENTATION LAYER: Flask REST API              │
│  /chat, /autoPilot endpoints                     │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│  APPLICATION LAYER: cosi_app.py (7166 lines)     │
│  • AI orchestration (Bedrock/OpenAI)             │
│  • Tool routing (139 tools)                      │
│  • Conversation management                       │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│  SERVICE LAYER: Platform APIs                    │
│  gmail.py, slack_mcp.py, trello_mcp.py, etc.    │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│  DATA LAYER: MongoDB Clients                     │
│  mongo_email_client.py, mongo_context_client.py  │
└──────────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────────┐
│  INFRASTRUCTURE: MongoDB + AWS Services          │
└──────────────────────────────────────────────────┘
```

---

## 📁 Critical Files (Top 10)

| File | Lines | Role | Importance |
|------|-------|------|------------|
| `app/cosi_app.py` | 7166 | Main orchestrator | 🔴 CRITICAL |
| `app/server.py` | 3485 | Tool registry | 🔴 CRITICAL |
| `clients/db_method.py` | 837 | Auth & tokens | 🔴 CRITICAL |
| `clients/mongo_email_client.py` | 1185 | Gmail data | 🟠 HIGH |
| `clients/mongo_context_client.py` | 774 | Correlations | 🟠 HIGH |
| `services/slack_mcp.py` | 895 | Slack API | 🟡 MEDIUM |
| `services/gmail.py` | 689 | Gmail API | 🟡 MEDIUM |
| `utils/date_utils.py` | 259 | Date parsing | 🟡 MEDIUM |
| `personalization/extract_user_personality.py` | 681 | Personality | 🟢 LOW |
| `db/mongo_client.py` | 17 | DB connection | 🔴 CRITICAL |

**Total: ~22,000 lines of Python**

---

## 🔄 Request Flow (Visual)

```
USER → Flask API → cosi_app.py → AI Model → Tool Selection
                                                  ↓
        ← JSON Response ← Format ← Execute ← Service Layer
                                                  ↓
                                             Data Layer
                                                  ↓
                                          MongoDB/AWS
```

**Example**:
```
Query: "Show unread emails from yesterday"
  ↓
AI selects: search_emails(is_unread=True, date="2024-12-18")
  ↓
mongo_email_client.py queries MongoDB
  ↓
Returns 5 emails
  ↓
AI formats response
  ↓
User sees: "You have 5 unread emails..."
```

---

## 🛠️ Tool System

### **Tool Categories**

| Platform | Tools | Examples |
|----------|-------|----------|
| Gmail | 13 | send_email, search_emails, update_email |
| Calendar | 8 | create_event, search_events, delete_events |
| Slack | 13 | send_slack_messages, get_channels, send_dm |
| Docs | 12 | create_document, update_document, query_docs |
| Sheets | 15 | create_sheet, read_sheet_data, create_chart |
| Slides | 12 | list_slides, add_slide, format_text |
| Notion | 18 | create_page, query_database, add_todo |
| Trello | 32 | create_task, update_task, add_checklist |
| Gamma | 2 | create_gamma_presentation, list_gamma_themes |
| Context | 7 | get_email_context, get_calendar_context |
| **TOTAL** | **139** | |

### **Tool Definition Example**

```python
{
    "name": "search_emails",
    "description": "Search emails with filters",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "is_unread": {"type": "boolean"},
            "from_email": {"type": "string"},
            "start_date": {"type": "string"}
        }
    }
}
```

---

## 🤖 AI Models

### **Primary: AWS Bedrock - Claude 3.5 Sonnet**
- **Purpose**: Main reasoning engine
- **Model ID**: `anthropic.claude-3-5-sonnet-20240620-v1:0`
- **Max Tokens**: 8000
- **Temperature**: 0.5
- **Use Cases**: Tool selection, conversation, multi-step planning

### **Fallback: OpenAI GPT-4o**
- **Purpose**: Backup when Bedrock unavailable
- **Model**: `gpt-4o`
- **Max Tokens**: 4096

### **Vector Search: AWS Titan Embeddings**
- **Purpose**: Semantic search
- **Model**: `amazon.titan-embed-text-v2:0`
- **Dimensions**: 1024
- **Use Cases**: Email/doc similarity search

---

## 🗄️ Database Structure

```
MongoDB
│
├── unified_workspace (Global)
│   ├── users
│   ├── tools
│   ├── user_tools
│   └── user_authenticate_token
│
└── {user_id} (Per-user, e.g., "1100")
    ├── gmail
    ├── calendar
    ├── docs
    ├── slack_channel_messages
    ├── notion
    ├── trello
    ├── context_gmail
    ├── context_calendar
    ├── context_docs
    ├── context_slack
    ├── context_notion
    ├── context_trello
    └── personality
```

**Key Concept**: Each user gets their own database for complete data isolation.

---

## 🔐 Authentication Flow

```
1. User logs in → Gets unified_token
2. User connects platform (e.g., Gmail) → OAuth flow
3. Access token stored in unified_workspace.user_tools
4. On API call:
   - Send unified_token
   - System resolves to user_id
   - Retrieves platform OAuth token
   - Validates access
   - Executes request
```

**Key Files**:
- `clients/db_method.py` - Token management
- Functions: `validate_user_tool_access()`, `get_user_tool_access_token()`

---

## 🔍 Key Features

### **1. Cross-Platform Intelligence**
Find connections between emails, events, docs, tasks automatically.

```python
get_email_context(["email-id-123"])
# Returns:
{
  "related_items": {
    "calendar": ["event-456"],
    "docs": ["doc-789"],
    "trello": ["card-012"]
  },
  "correlation_text": "AI-generated insights..."
}
```

### **2. Semantic Search**
Vector-based similarity matching (not just keyword).

```python
# Query: "budget discussion"
# Matches emails about: "financial planning", "Q4 spending", "cost analysis"
```

### **3. Personalization**
AI adapts responses to match user's writing style.

```python
# Formal user: "Good afternoon. You have 5 unread messages."
# Casual user: "Hey! You've got 5 unread emails 😊"
```

### **4. Natural Language Dates**
Understands relative and natural dates.

```python
# "yesterday" → "2024-12-18"
# "last week" → "2024-12-11 to 2024-12-17"
# "Q3" → "2024-07-01 to 2024-09-30"
```

---

## 📡 API Endpoints

### **POST /chat**
Main conversational interface

**Request**:
```json
{
  "session_id": "user-123",
  "query": "Show unread emails",
  "unified_token": "abc-def-123",
  "model": "bedrock"
}
```

**Response**:
```json
{
  "response": "You have 5 unread emails...",
  "type": "emails",
  "data": {
    "emails": [...]
  },
  "ui_hint": ["open_email_panel"],
  "success": true
}
```

### **POST /autoPilot**
Autonomous task execution mode (similar to /chat but optimized for batch operations)

---

## 🚀 Getting Started

### **1. Environment Setup**

```bash
# Clone repo
git clone <repo-url>
cd mcp_gmail

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MONGO_URI="mongodb://..."
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export OPENAI_API_KEY="sk-..."
```

### **2. Start Server**

```bash
# Using shell script
./start_cosi_app.sh

# Or directly
python -m app.cosi_app
```

### **3. Test with cURL**

```bash
curl -X POST http://localhost:5000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-123",
    "query": "Show unread emails",
    "unified_token": "your-token"
  }'
```

---

## 🧪 Common Use Cases

### **1. Search Emails**
```
Query: "Show unread emails from John about the project"
AI: search_emails(is_unread=true, from_email="john@...", query="project")
```

### **2. Create Calendar Event**
```
Query: "Schedule meeting with Jane tomorrow at 2pm"
AI: create_event(summary="Meeting", attendees=["jane@..."], start_time="2024-12-20T14:00:00")
```

### **3. Send Slack Message**
```
Query: "Send message to #engineering: Code review ready"
AI: send_slack_messages(channel="engineering", message="Code review ready")
```

### **4. Create Task**
```
Query: "Create task 'Review PR' in Project Alpha board"
AI: create_task(board_id="...", list_id="...", name="Review PR")
```

### **5. Find Related Items**
```
Query: "What's related to this email?"
AI: get_email_context(["email-id"])
Returns: Related calendar events, docs, tasks, Slack threads
```

---

## 🔧 Configuration

### **Key Environment Variables**

```bash
# MongoDB
MONGO_URI=mongodb://localhost:27017

# AWS Bedrock
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0

# OpenAI (fallback)
OPENAI_API_KEY=sk-...

# User Service (for OAuth)
USER_SERVICE_BASE_URL=http://3.6.95.164:5000/users

# Flask
FLASK_ENV=development
FLASK_PORT=5000
```

### **OAuth Credentials**

Store in `config/`:
- `credentials_calender.json` - Google OAuth
- `token.json` - Google tokens
- Platform-specific tokens stored in MongoDB

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Average Response Time | 2-5 seconds |
| Concurrent Users | 50+ per instance |
| Tool Selection Accuracy | ~95% |
| Vector Search Recall | ~85% |
| Multi-turn Context | 10 turns |
| Total Tools | 139 |
| Supported Platforms | 9 |

---

## 🛡️ Security

### **Multi-Tenancy**
- Each user gets own database
- No cross-user data access
- Complete isolation

### **Authentication**
- OAuth 2.0 for all platforms
- Unified token system
- Token validation on every request
- Automatic token refresh

### **Data Protection**
- Encrypted connections (MongoDB, AWS)
- No plaintext credentials
- Scoped API permissions

---

## 📝 Development Workflow

### **Adding a New Tool**

1. **Define function** in service file:
```python
# services/gmail.py
def new_gmail_function(param1, param2, token=None):
    # Implementation
    return result
```

2. **Export in server.py**:
```python
from services.gmail import new_gmail_function

__all__ = [
    "new_gmail_function",
    # ... other exports
]
```

3. **Register in cosi_app.py**:
```python
tools = {
    "new_gmail_function": lambda **kwargs: new_gmail_function(**kwargs),
    # ... other tools
}

function_defs = [
    {
        "name": "new_gmail_function",
        "description": "...",
        "parameters": {...}
    },
    # ... other defs
]
```

4. **Test**:
```python
# Query AI: "Use the new Gmail function"
# AI should select and execute it
```

---

## 🐛 Debugging

### **Enable Debug Logging**

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### **Common Issues**

| Issue | Solution |
|-------|----------|
| "Unauthorized" | Check unified_token validity |
| "Tool not found" | Verify tool registered in cosi_app.py |
| "MongoDB connection failed" | Check MONGO_URI |
| "Bedrock error" | Verify AWS credentials |
| "Token expired" | Refresh OAuth tokens |

### **Log Files**

- `app/cosi_app.log` - Application logs
- `logs/flask_output.log` - Flask server logs

---

## 📚 Code Examples

### **Example 1: Call Tool Directly**

```python
from services.gmail import send_email

result = send_email(
    to="john@example.com",
    subject="Test",
    body="Hello!",
    token="unified-token-123"
)
```

### **Example 2: MongoDB Query**

```python
from clients.mongo_email_client import mongo_query_emails

emails = mongo_query_emails(
    query="project",
    is_unread=True,
    start_date="2024-12-01",
    token="unified-token-123"
)
```

### **Example 3: Get Context**

```python
from clients.mongo_context_client import get_email_context

context = get_email_context(
    email_ids=["email-123"],
    token="unified-token-123"
)
```

---

## 🔗 Import Cheat Sheet

```python
# Main app
from app.cosi_app import app

# Services
from services.gmail import send_email
from services.slack_mcp import send_slack_messages
from services.trello_mcp import task_create

# Clients
from clients.mongo_email_client import mongo_query_emails
from clients.mongo_context_client import get_email_context
from clients.db_method import validate_user_tool_access

# Utils
from utils.date_utils import DateParser
from db.mongo_client import get_mongo_client
```

---

## 📖 Further Reading

For detailed information, see:

1. **Architecture**: [MCP_GMAIL_ARCHITECTURE_DOCUMENTATION.md](MCP_GMAIL_ARCHITECTURE_DOCUMENTATION.md)
2. **File Relationships**: [FILE_RELATIONSHIPS_AND_DIAGRAMS.md](FILE_RELATIONSHIPS_AND_DIAGRAMS.md)
3. **AI Implementation**: [AI_IMPLEMENTATION_GUIDE.md](AI_IMPLEMENTATION_GUIDE.md)

---

## 🎯 Quick Decision Tree

**"Where do I put this code?"**

```
Is it an API call?
├─ Yes → services/
│  └─ Which platform? → {platform}_mcp.py
│
└─ No → Is it a database query?
    ├─ Yes → clients/
    │  └─ Which collection? → mongo_{platform}_client.py
    │
    └─ No → Is it a utility?
        ├─ Yes → utils/
        │  └─ What type? → {type}_utils.py
        │
        └─ No → Is it configuration?
            ├─ Yes → config/
            └─ No → app/ (orchestration logic)
```

---

## 💡 Pro Tips

1. **Always use unified_token** - Don't hardcode user_ids
2. **Let AI handle dates** - Don't parse dates manually
3. **Use context tools** - Leverage cross-platform intelligence
4. **Follow the pattern** - Look at existing tools as templates
5. **Test with AI** - Ask Claude to use your new tool
6. **Check db_method first** - Auth errors often come from token issues
7. **Use vector search** - For semantic queries, not exact match
8. **Cache when possible** - Slack channels, user data, etc.
9. **Return standardized format** - {success, data, message}
10. **Log everything** - Debug mode is your friend

---

## 🆘 Getting Help

1. **Check logs**: `tail -f app/cosi_app.log`
2. **Test tool directly**: Import and call function
3. **Verify token**: Use `validate_user_tool_access()`
4. **Check MongoDB**: Verify data exists
5. **Test AI prompt**: Use Claude Playground
6. **Review docs**: See detailed architecture docs

---

## 📊 Statistics

- **Total Files**: ~50
- **Total Lines**: ~22,000
- **Total Tools**: 139
- **Platforms**: 9
- **Languages**: Python 3.8+
- **Dependencies**: ~30 packages
- **AI Models**: 3 (Claude, GPT-4, Titan)
- **Databases**: MongoDB + OpenSearch

---

## 🎓 Architecture Principles

1. **Separation of Concerns**: App → Service → Data → Infrastructure
2. **Multi-Tenancy**: Database per user
3. **Unified Interface**: server.py as single import point
4. **AI-First**: Let AI make decisions, not hardcoded rules
5. **Extensible**: Easy to add new platforms/tools
6. **Secure**: OAuth, token validation, data isolation
7. **Intelligent**: Cross-platform context, semantic search
8. **Personalized**: User-specific response styling

---

**Last Updated**: December 19, 2024  
**Version**: 1.0  
**Purpose**: Quick reference for developers

