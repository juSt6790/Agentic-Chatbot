import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from pymongo import MongoClient
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_id_from_token

# ---------------------------------------------------------------------------
# Initial setup – MongoDB client
# ---------------------------------------------------------------------------
mongo_client = get_mongo_client()


# ---------------------------------------------------------------------------
# Briefing Fetch Functions
# ---------------------------------------------------------------------------

# Tool name to validation mapping
TOOL_VALIDATION_MAP = {
    "gmail": "Gsuite",
    "calendar": "Gsuite",
    "docs": "Gsuite",
    "sheets": "Gsuite",
    "slides": "Gsuite",
    "trello": "Trello",
    "slack": "Slack"
}

# Tool name to emoji mapping for logging
TOOL_EMOJI_MAP = {
    "gmail": "📧",
    "calendar": "📅",
    "docs": "📝",
    "sheets": "📊",
    "slides": "📽️",
    "trello": "✅",
    "slack": "💬"
}


def get_latest_briefing(
    token: Optional[str] = None,
    tool_name: str = "gmail",
    include_metadata: bool = True
) -> Dict[str, Any]:
    """
    Fetch the latest briefing for a specific tool from MongoDB.
    
    This retrieves the most recent AI-generated briefing that summarizes the user's
    data from the specified tool. Supports: gmail, calendar, docs, sheets, slides, trello, slack.
    
    Args:
        token: User's unified token
        tool_name: Name of the tool to fetch briefing for. Options: "gmail", "calendar", 
                  "docs", "sheets", "slides", "trello", "slack" (default: "gmail")
        include_metadata: Whether to include timestamp and metadata (default: True)
        
    Returns:
        Dictionary containing:
        - briefing: The AI-generated briefing text
        - save_timestamp: When the briefing was generated
        - save_date: Date of the briefing
        - user_id: User ID
        - source: Source type (tool_name)
        - message: Success message
    """
    # Normalize tool name to lowercase
    tool_name = tool_name.lower()
    
    # Validate tool name
    valid_tools = ["gmail", "calendar", "docs", "sheets", "slides", "trello", "slack"]
    if tool_name not in valid_tools:
        return {
            "briefing": None,
            "error": f"Invalid tool name: {tool_name}. Valid options: {', '.join(valid_tools)}",
            "source": tool_name
        }
    
    emoji = TOOL_EMOJI_MAP.get(tool_name, "📋")
    print(f"{emoji} [DEBUG] Fetching latest {tool_name} briefing from MongoDB...")
    
    try:
        # Validate user has access to the required service (if applicable)
        validation_service = TOOL_VALIDATION_MAP.get(tool_name)
        if validation_service:
            is_valid, error_msg, status_code = validate_user_tool_access(token, validation_service)
            if not is_valid:
                print(f"[ERROR] {validation_service} access denied: {error_msg}")
                return {
                    "briefing": None,
                    "error": f"{validation_service} access denied: {error_msg}",
                    "status_code": status_code,
                    "source": tool_name
                }
        
        # Get user ID from token
        user_id, status = get_user_id_from_token(token)
        if status != 200 or not user_id:
            return {
                "briefing": None,
                "error": "Invalid or expired token",
                "status_code": 401,
                "source": tool_name,
            }
        print(f"   [DEBUG] Resolved user_id: {user_id}")

        # Get the briefing collection for this user
        db = mongo_client[user_id]
        briefing_collection = db["briefing"]

        # Query for the latest briefing for this tool
        query = {
            "user_id": user_id,
            "source": tool_name
        }
        
        # Find the most recent briefing
        result = briefing_collection.find_one(
            query,
            sort=[("save_timestamp", -1)]  # Sort by timestamp descending
        )

        # Backward-compatibility fallback:
        # - Some existing briefing documents may have an older `user_id` value baked into
        #   the document body (e.g. numeric "100") while the current system resolves a
        #   UUID for the user. Since each user has their own Mongo DB, `source` is
        #   sufficient to find the latest briefing within this DB.
        if not result:
            fallback_query = {"source": tool_name}
            result = briefing_collection.find_one(
                fallback_query,
                sort=[("save_timestamp", -1)]
            )
            if result:
                print(
                    f"   [DEBUG] Found {tool_name} briefing by `source` only "
                    f"(user_id mismatch: expected={user_id}, found={result.get('user_id')})"
                )
        
        if not result:
            print(f"   [DEBUG] No {tool_name} briefing found for user {user_id}")
            return {
                "briefing": None,
                "message": f"No {tool_name} briefing found for this user",
                "user_id": user_id,
                "source": tool_name
            }
        
        print(f"✅ [DEBUG] Successfully fetched {tool_name} briefing")
        print(f"   [DEBUG] Briefing timestamp: {result.get('save_timestamp')}")
        print(f"   [DEBUG] Briefing date: {result.get('save_date')}")
        print(f"   [DEBUG] Briefing length: {len(str(result.get('briefing', '')))} characters")
        
        # Format the response
        response = {
            "briefing": result.get("briefing", ""),
            "save_timestamp": result.get("save_timestamp", ""),
            "save_date": result.get("save_date", ""),
            "user_id": result.get("user_id", user_id),
            "source": result.get("source", tool_name),
            "message": f"Successfully retrieved latest {tool_name} briefing"
        }
        
        # Optionally include metadata
        if include_metadata and "user_prefs" in result:
            response["user_prefs"] = result.get("user_prefs")
        
        return response
        
    except Exception as e:
        print(f"❌ [ERROR] Failed to fetch {tool_name} briefing: {e}")
        import traceback
        traceback.print_exc()
        return {
            "briefing": None,
            "error": f"Failed to fetch briefing: {str(e)}",
            "user_id": user_id if 'user_id' in locals() else None,
            "source": tool_name
        }


# Legacy functions for backward compatibility (deprecated - use get_latest_briefing instead)
def get_latest_gmail_briefing(
    token: Optional[str] = None,
    include_metadata: bool = True
) -> Dict[str, Any]:
    """Deprecated: Use get_latest_briefing(tool_name="gmail") instead."""
    return get_latest_briefing(token=token, tool_name="gmail", include_metadata=include_metadata)


def get_latest_calendar_briefing(
    token: Optional[str] = None,
    include_metadata: bool = True
) -> Dict[str, Any]:
    """Deprecated: Use get_latest_briefing(tool_name="calendar") instead."""
    return get_latest_briefing(token=token, tool_name="calendar", include_metadata=include_metadata)


def get_all_latest_briefings(
    token: Optional[str] = None,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Fetch latest briefings from multiple sources at once.
    
    Args:
        token: User's unified token
        sources: List of sources to fetch (default: all available sources)
                 Options: ["gmail", "calendar", "trello", "slack", "docs", "slides", "sheets"]
        
    Returns:
        Dictionary containing briefings from all requested sources
    """
    if sources is None:
        sources = ["gmail", "calendar", "docs", "sheets", "slides", "trello", "slack"]  # All available sources
    
    print(f"📦 [DEBUG] Fetching briefings from sources: {sources}")
    
    try:
        # Get user ID from token
        user_id, status = get_user_id_from_token(token)
        if status != 200 or not user_id:
            return {
                "error": "Invalid or expired token",
                "status_code": 401,
                "briefings": {},
            }
        print(f"   [DEBUG] Resolved user_id: {user_id}")

        # Get the briefing collection for this user
        db = mongo_client[user_id]
        briefing_collection = db["briefing"]

        # Query for all requested source briefings
        query = {
            "user_id": user_id,
            "source": {"$in": sources}
        }
        
        # Find all matching briefings
        results = list(briefing_collection.find(query))

        # Backward-compatibility fallback (see get_latest_briefing):
        # if the user's resolved id changed but the briefing documents weren't updated,
        # still fetch by `source` within this user's DB.
        if not results:
            fallback_query = {"source": {"$in": sources}}
            results = list(briefing_collection.find(fallback_query))
        
        print(f"   [DEBUG] Found {len(results)} briefings across {len(sources)} sources")
        
        # Organize by source
        briefings_by_source = {}
        for result in results:
            source = result.get("source", "unknown")
            briefings_by_source[source] = {
                "briefing": result.get("briefing", ""),
                "save_timestamp": result.get("save_timestamp", ""),
                "save_date": result.get("save_date", ""),
            }
            print(f"   [DEBUG] Added {source} briefing (date: {result.get('save_date')})")
        
        # Check for missing sources
        missing_sources = [s for s in sources if s not in briefings_by_source]
        if missing_sources:
            print(f"   [DEBUG] No briefings found for sources: {missing_sources}")
        
        print(f"✅ [DEBUG] Successfully fetched briefings from {len(briefings_by_source)} source(s)")
        
        return {
            "briefings": briefings_by_source,
            "user_id": user_id,
            "sources_requested": sources,
            "sources_found": list(briefings_by_source.keys()),
            "missing_sources": missing_sources,
            "message": f"Retrieved {len(briefings_by_source)} briefing(s)"
        }
        
    except Exception as e:
        print(f"❌ [ERROR] Failed to fetch briefings: {e}")
        import traceback
        traceback.print_exc()
        return {
            "briefings": {},
            "error": f"Failed to fetch briefings: {str(e)}",
            "user_id": user_id if 'user_id' in locals() else None,
            "sources_requested": sources
        }


