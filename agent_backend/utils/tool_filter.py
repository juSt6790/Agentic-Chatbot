"""Tool filtering utility to intelligently select relevant service functions."""
import json
import os
import logging
import re
from typing import List, Dict, Optional
from app.structures import function_defs
from app.cosi_app import invoke_ai_with_fallback

logger = logging.getLogger(__name__)

# Configuration
MAX_FILTERED_TOOLS = int(os.getenv("TOOL_FILTER_MAX_TOOLS", "20"))
TOOL_FILTER_ENABLED = os.getenv("TOOL_FILTER_ENABLED", "true").lower() == "true"


def filter_tools(
    user_query: str,
    conversation_context: Optional[List[Dict]] = None,
    max_tools: int = MAX_FILTERED_TOOLS,
    token: Optional[str] = None
) -> List[str]:
    """
    Intelligently filters service function tools using a lightweight AI call.
    
    Args:
        user_query: The user's current query
        conversation_context: Recent conversation history (optional)
        max_tools: Maximum number of tools to return (default: 20)
        token: User token for personalization (optional)
    
    Returns:
        List of tool names (e.g., ["send_email", "search_emails", ...])
        that correspond to service functions.
    """
    if not TOOL_FILTER_ENABLED:
        # Fallback: return all tool names
        all_tool_names = [tool["name"] for tool in function_defs]
        logger.info(
            f"Tool filtering disabled: using all {len(all_tool_names)} tools. "
            f"Tools: {', '.join(all_tool_names[:10])}{'...' if len(all_tool_names) > 10 else ''}"
        )
        return all_tool_names
    
    try:
        # Build lightweight tool registry (name + description only)
        tool_registry = [
            {"name": tool["name"], "description": tool.get("description", "")}
            for tool in function_defs
        ]
        
        # Format tools list
        tools_text = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in tool_registry
        ])
        
        # Build context text
        context_text = ""
        if conversation_context:
            recent = conversation_context[-3:] if len(conversation_context) > 3 else conversation_context
            context_text = "\n\nRecent context:\n" + "\n".join([
                f"{msg.get('role', 'user')}: {str(msg.get('content', ''))[:200]}"
                for msg in recent
            ])
        
        # Create filtering prompt
        filter_prompt = f"""Analyze this user query and select the {max_tools} most relevant service functions.

User Query: {user_query}
{context_text}

Available Service Functions ({len(tool_registry)} total):
{tools_text}

Return ONLY a valid JSON array of function names (tool names), no other text.
Format: ["function_name_1", "function_name_2", ...]"""
        
        # Make lightweight AI call
        messages = [
            {"role": "user", "content": [{"type": "text", "text": filter_prompt}]}
        ]
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "temperature": 0.1,
            "system": "You are a service function selector. Return only JSON arrays of function names.",
            "messages": messages,
            "tools": []  # No tools for filtering stage
        }
        
        response = invoke_ai_with_fallback(body)
        content = response.get("content", [])
        
        if not content:
            raise ValueError("Empty response from filtering AI")
        
        # Extract text response
        text_response = "".join([
            block.get("text", "") 
            for block in content 
            if block.get("type") == "text"
        ]).strip()
        
        # Extract JSON array from response
        # Try to extract JSON array if wrapped in markdown code blocks
        if "```" in text_response:
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])', text_response, re.DOTALL)
            if json_match:
                text_response = json_match.group(1)
        
        # Parse JSON array
        tool_names = json.loads(text_response)
        
        # Validate it's a list of strings
        if not isinstance(tool_names, list):
            raise ValueError("Response is not a list")
        
        # Validate all tool names exist
        valid_tool_names = {tool["name"] for tool in function_defs}
        filtered_names = [name for name in tool_names if name in valid_tool_names]
        
        # Limit to max_tools
        filtered_names = filtered_names[:max_tools]
        
        if not filtered_names:
            # Fallback: return all tools if filtering failed
            all_tool_names = [tool["name"] for tool in function_defs]
            logger.warning(
                f"Tool filtering returned empty list, using all {len(all_tool_names)} tools. "
                f"Tools: {', '.join(all_tool_names[:10])}{'...' if len(all_tool_names) > 10 else ''}"
            )
            return all_tool_names
        
        logger.info(
            f"Tool filtering: selected {len(filtered_names)} tools from {len(function_defs)} total. "
            f"Selected tools: {', '.join(filtered_names)}"
        )
        return filtered_names
        
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        all_tool_names = [tool["name"] for tool in function_defs]
        logger.warning(
            f"Tool filtering JSON parse failed: {e}. Using all {len(all_tool_names)} tools. "
            f"Tools: {', '.join(all_tool_names[:10])}{'...' if len(all_tool_names) > 10 else ''}"
        )
        return all_tool_names
    except Exception as e:
        all_tool_names = [tool["name"] for tool in function_defs]
        logger.error(
            f"Tool filtering failed: {e}. Falling back to all {len(all_tool_names)} tools. "
            f"Tools: {', '.join(all_tool_names[:10])}{'...' if len(all_tool_names) > 10 else ''}"
        )
        # Fallback: return all tool names on error
        return all_tool_names
