# Intelligent Tool Filtering

## Overview

This document outlines the design for an **Intelligent Tool Filtering Layer** to address performance issues caused by passing all 127 tools to the AI model on every request. This layer intelligently selects a relevant subset of tools before the main AI execution.

---

## Problem

**Current State:**
- All 127 tools are passed to the AI model (Claude 3.5 / GPT-4) on every request
- Tools include full schemas (name, description, input_schema), adding significant token overhead
- AI must process all 127 tool definitions to select appropriate ones
- This causes performance bottlenecks: larger context size, slower response times, higher API costs

**Where it happens:**
- `app/assistant_handler.py` (line 676-683) - passes all tools
- `app/autopilot_handler.py` (line 695-702) - passes all tools

---

## Solution: Two-Stage Filtering

### Architecture

```
User Query
    ↓
┌─────────────────────────────────────┐
│ Stage 1: Tool Filtering AI (NEW)   │
│ • Analyzes user query               │
│ • Selects 10-30 most relevant tools │
│ • Returns filtered tool names       │
│ • Uses lightweight/fast AI model    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ Stage 2: Main Execution AI          │
│ • Receives filtered tool subset     │
│ • Selects and executes tools        │
│ • Same as current implementation    │
└─────────────────────────────────────┘
```

### How It Works

1. **Filtering Stage** (NEW):
   - Lightweight AI call analyzes the user query
   - Reviews all 127 tools (name + description only, no full schemas)
   - Returns a filtered list of 10-30 most relevant tool names
   - Fast and low-cost operation

2. **Execution Stage** (EXISTING):
   - Receives the filtered tool list
   - Builds full tool definitions (with schemas) only for selected tools
   - Passes filtered tools to main AI for execution
   - Same behavior as before, but with fewer tools

---

## Implementation

### New Component: `utils/tool_filter.py`

**Key Function:**
```python
def filter_tools(
    user_query: str,
    conversation_context: Optional[List[Dict]] = None,
    max_tools: int = 20,
    token: Optional[str] = None
) -> List[str]:
    """
    Intelligently filters tools from the full pool.
    
    Returns list of tool names that are most relevant to the query.
    """
    # Implementation: Use lightweight AI to select relevant tools
    pass
```

### Integration Points

**File: `app/assistant_handler.py`** (around line 676)

**Before:**
```python
claude_tools = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["parameters"],
    }
    for tool in function_defs  # ALL 127 tools
]
```

**After:**
```python
from utils.tool_filter import filter_tools

# Stage 1: Filter tools
filtered_tool_names = filter_tools(
    user_query=combined_query,
    conversation_context=history_messages[-5:],
    max_tools=20,
    token=token
)

# Stage 2: Build filtered tool list with full schemas
tools_dict = {tool["name"]: tool for tool in function_defs}
claude_tools = [
    {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["parameters"],
    }
    for tool in function_defs
    if tool["name"] in filtered_tool_names  # Only filtered tools
]
```

**Same changes apply to `app/autopilot_handler.py`** (around line 695)

### Configuration

Add to `config/config.py`:
```python
TOOL_FILTER_MAX_TOOLS = 20  # Default number of tools to select
TOOL_FILTER_ENABLED = True  # Toggle feature
```

---

## Filtering Logic

### AI Prompt Strategy

The filtering AI should:
- Use a **fast, lightweight model** (e.g., Claude Haiku, GPT-3.5-turbo)
- Analyze user query intent and required functionality
- Score tool relevance based on query
- Return JSON array of tool names (top N most relevant)

### Example

**User Query:** "Show unread emails from John"

**Filtering Result:** 
- Selected tools: `["search_emails", "get_email_context", "send_email", ...]` (12 tools)
- Instead of all 127 tools

**Execution:**
- Main AI receives only 12 tools
- Selects `search_emails` and executes it

---

## Benefits

1. **Performance**: Smaller context = faster AI processing
2. **Cost**: Fewer tokens per request = lower API costs
3. **Scalability**: System can handle more tools without degradation
4. **Accuracy**: Focused tool set may improve selection quality

---

## Rollout Plan

1. **Phase 1**: Implement `utils/tool_filter.py` module
2. **Phase 2**: Integrate into `assistant_handler.py` and `autopilot_handler.py`
3. **Phase 3**: Add feature flag for gradual rollout
4. **Phase 4**: Monitor and optimize

**Rollback**: Feature flag can disable filtering (fallback to all tools)

---

## Edge Cases

- **Filtering fails**: Fallback to all tools (current behavior)
- **No relevant tools**: Return default set (most commonly used tools)
- **Very broad query**: Cap at max_tools limit, prioritize common tools
- **Context-dependent queries**: Include conversation history in filtering

---

**Document Version:** 1.0  
**Last Updated:** 2024-12-19
