import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from pymongo import MongoClient
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_id_from_token

# ---------------------------------------------------------------------------
# Initial setup – MongoDB client
# ---------------------------------------------------------------------------
mongo_client = get_mongo_client()


def get_context_collection(token: Optional[str], source: str) -> Any:
    """
    Return the per-tenant context collection for the provided token and source.
    Validates that user has access to the appropriate tool before returning collection.
    
    Args:
        token: User's unified token
        source: Source type (gmail, calendar, docs, slides, notion, trello)
    """
    # Map sources to their tool names for validation
    source_to_tool = {
        "gmail": "Gsuite",
        "calendar": "Gsuite", 
        "docs": "Gsuite",
        "slides": "Gsuite",
        "notion": "Notion",
        "trello": "Trello",
        "slack": "Slack"
    }
    
    tool_name = source_to_tool.get(source, "Gsuite")
    
    # Validate user has access to the tool
    is_valid, error_msg, status_code = validate_user_tool_access(token, tool_name)
    if not is_valid:
        raise PermissionError(f"{tool_name} access denied: {error_msg}")
    
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise PermissionError("Invalid or expired token")
    print(f"[DEBUG] Resolved user_id from token: {db_name}")

    # Return the appropriate context collection based on source
    collection_name = f"context_{source}"
    return mongo_client[db_name][collection_name]


# ---------------------------------------------------------------------------
# Context Search Functions
# ---------------------------------------------------------------------------


def get_email_context(
    email_ids: List[str], 
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Fetch contextual correlation information for given email IDs from the context_gmail collection.
    
    This searches for preprocessed email batches that contain the requested email IDs
    and returns the AI-generated correlation text that provides additional context about:
    - Tasks mentioned in the emails
    - Cross-tool relationships (links to Teams, Slack, etc.)
    - Priority items
    - Projects mentioned
    - Collaborators involved
    - Events and meetings
    
    Args:
        email_ids: List of email IDs to find context for
        token: User's unified token
        include_embeddings: Whether to include the embedding vectors (default: False)
        
    Returns:
        Dictionary containing:
        - matched_contexts: List of context documents found
        - total_matches: Number of context batches found
        - email_ids_queried: The email IDs that were searched for
    """
    print(f"🔍 Fetching email context for {len(email_ids)} email ID(s)")
    
    if not email_ids:
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "email_ids_queried": [],
            "message": "No email IDs provided"
        }
    
    try:
        collection = get_context_collection(token, source="gmail")
        
        # Query for documents where any of the provided email_ids exist in the email_ids array
        query = {"email_ids": {"$in": email_ids}}
        
        # Project fields - only include embedding_vector if requested
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
        
        # Only add embedding_vector to projection if requested
        if include_embeddings:
            projection["embedding_vector"] = 1
        # Note: Don't use {"embedding_vector": 0} - MongoDB doesn't allow mixing inclusion and exclusion
        
        # Execute query
        results = list(collection.find(query, projection))
        
        print(f"   Found {len(results)} context batch(es) containing the requested email IDs")
        
        # Format the results
        formatted_contexts = []
        for doc in results:
            context_item = {
                "context_id": str(doc.get("_id", "")),
                "email_ids_in_batch": doc.get("email_ids", []),
                "correlation_text": doc.get("embedding_text", ""),
                "date_range": {
                    "earliest_email": datetime.fromtimestamp(
                        doc.get("min_internalDateNum", 0) / 1000
                    ).isoformat() if doc.get("min_internalDateNum") else None,
                    "latest_email": datetime.fromtimestamp(
                        doc.get("max_internalDateNum", 0) / 1000
                    ).isoformat() if doc.get("max_internalDateNum") else None,
                },
                "source": doc.get("source", "gmail"),
                "created_at": doc.get("created_at", {}).get("$date") if isinstance(doc.get("created_at"), dict) else str(doc.get("created_at", "")),
                "updated_at": doc.get("updated_at", {}).get("$date") if isinstance(doc.get("updated_at"), dict) else str(doc.get("updated_at", "")),
            }
            
            # Only include embeddings if requested
            if include_embeddings and "embedding_vector" in doc:
                context_item["embedding_vector"] = doc["embedding_vector"]
            
            formatted_contexts.append(context_item)
        
        # Sort by latest_email timestamp (most recent first)
        formatted_contexts.sort(
            key=lambda x: x["date_range"]["latest_email"] or "", 
            reverse=True
        )
        
        return {
            "matched_contexts": formatted_contexts,
            "total_matches": len(formatted_contexts),
            "email_ids_queried": email_ids,
            "message": f"Found {len(formatted_contexts)} context batch(es) with correlation information"
        }
        
    except PermissionError as e:
        print(f"[ERROR] Permission denied: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "email_ids_queried": email_ids,
            "error": str(e)
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch email context: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "email_ids_queried": email_ids,
            "error": f"Failed to fetch context: {str(e)}"
        }


def search_context_by_text(
    query: str,
    token: Optional[str] = None,
    limit: int = 10
) -> Dict[str, Any]:
    """
    Search context collection using text search on the embedding_text field.
    Useful for finding emails related to specific topics, tasks, or collaborators.
    
    Args:
        query: Text query to search for in correlation text
        token: User's unified token
        limit: Maximum number of results to return
        
    Returns:
        Dictionary containing matched context batches
    """
    print(f"🔍 Searching email context with query: '{query}'")
    
    try:
        collection = get_context_collection(token, source="gmail")
        
        # Use text search or regex search on embedding_text
        # First, try using MongoDB text search if index exists
        try:
            results = list(
                collection.find(
                    {"$text": {"$search": query}},
                    {"score": {"$meta": "textScore"}, "embedding_vector": 0}
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit)
            )
        except Exception:
            # Fallback to regex search if text index doesn't exist
            print("   Text index not found, using regex search")
            results = list(
                collection.find(
                    {"embedding_text": {"$regex": query, "$options": "i"}},
                    {"embedding_vector": 0}
                )
                .limit(limit)
            )
        
        print(f"   Found {len(results)} context batch(es) matching the query")
        
        # Format results
        formatted_contexts = []
        for doc in results:
            context_item = {
                "context_id": str(doc.get("_id", "")),
                "email_ids_in_batch": doc.get("email_ids", []),
                "correlation_text": doc.get("embedding_text", ""),
                "date_range": {
                    "earliest_email": datetime.fromtimestamp(
                        doc.get("min_internalDateNum", 0) / 1000
                    ).isoformat() if doc.get("min_internalDateNum") else None,
                    "latest_email": datetime.fromtimestamp(
                        doc.get("max_internalDateNum", 0) / 1000
                    ).isoformat() if doc.get("max_internalDateNum") else None,
                },
                "source": doc.get("source", "gmail"),
                "relevance_score": doc.get("score") if "score" in doc else None
            }
            formatted_contexts.append(context_item)
        
        return {
            "matched_contexts": formatted_contexts,
            "total_matches": len(formatted_contexts),
            "query": query,
            "message": f"Found {len(formatted_contexts)} context batch(es) matching '{query}'"
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to search email context: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "query": query,
            "error": f"Failed to search context: {str(e)}"
        }


def get_context_by_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    token: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Fetch email context batches within a specific date range.
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        token: User's unified token
        limit: Maximum number of results to return
        
    Returns:
        Dictionary containing matched context batches
    """
    print(f"📅 Fetching email context for date range: {start_date} to {end_date}")
    
    try:
        collection = get_context_collection(token, source="gmail")
        
        # Build date query
        date_query = {}
        if start_date:
            try:
                dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_ms = int(dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
                date_query["max_internalDateNum"] = {"$gte": start_ms}
            except ValueError as e:
                print(f"[ERROR] Invalid start_date format: {e}")
        
        if end_date:
            try:
                dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_ms = int(dt.replace(hour=23, minute=59, second=59, microsecond=999000).timestamp() * 1000)
                if "min_internalDateNum" in date_query:
                    date_query["min_internalDateNum"]["$lte"] = end_ms
                else:
                    date_query["min_internalDateNum"] = {"$lte": end_ms}
            except ValueError as e:
                print(f"[ERROR] Invalid end_date format: {e}")
        
        if not date_query:
            print("   No valid date filters provided")
            return {
                "matched_contexts": [],
                "total_matches": 0,
                "error": "No valid date filters provided"
            }
        
        # Execute query
        results = list(
            collection.find(date_query, {"embedding_vector": 0})
            .sort("max_internalDateNum", -1)
            .limit(limit)
        )
        
        print(f"   Found {len(results)} context batch(es) in the date range")
        
        # Format results
        formatted_contexts = []
        for doc in results:
            context_item = {
                "context_id": str(doc.get("_id", "")),
                "email_ids_in_batch": doc.get("email_ids", []),
                "correlation_text": doc.get("embedding_text", ""),
                "date_range": {
                    "earliest_email": datetime.fromtimestamp(
                        doc.get("min_internalDateNum", 0) / 1000
                    ).isoformat() if doc.get("min_internalDateNum") else None,
                    "latest_email": datetime.fromtimestamp(
                        doc.get("max_internalDateNum", 0) / 1000
                    ).isoformat() if doc.get("max_internalDateNum") else None,
                },
                "source": doc.get("source", "gmail")
            }
            formatted_contexts.append(context_item)
        
        return {
            "matched_contexts": formatted_contexts,
            "total_matches": len(formatted_contexts),
            "start_date": start_date,
            "end_date": end_date,
            "message": f"Found {len(formatted_contexts)} context batch(es) in the date range"
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch context by date range: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "error": f"Failed to fetch context: {str(e)}"
        }


# ---------------------------------------------------------------------------
# Generic Context Functions for All Sources
# ---------------------------------------------------------------------------


def get_generic_context(
    ids: List[str],
    source: str,
    id_field: str,
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Generic function to fetch context for any source type.
    
    Args:
        ids: List of IDs to look up
        source: Source type (gmail, calendar, docs, slides, notion, trello)
        id_field: The field name in the collection to search by (e.g., "id", "document_id", "page_id")
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
        
    Returns:
        Dictionary containing matched contexts
    """
    print(f"🔍 Fetching {source} context for {len(ids)} ID(s)")
    
    if not ids:
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "ids_queried": [],
            "message": "No IDs provided"
        }
    
    try:
        collection = get_context_collection(token, source=source)
        
        # Query for documents where the ID matches
        query = {id_field: {"$in": ids}}
        
        # Project fields - only include embedding_vector if requested
        projection = {
            "_id": 1,
            id_field: 1,
            "embedding_text": 1,
            "source": 1,
            "created_at": 1,
            "brief_description": 1,
            "change_summary": 1,
            "title": 1,
        }
        
        # Add source-specific fields
        if source == "calendar":
            projection.update({
                "start_time": 1,
                "end_time": 1,
                "attendees": 1,
                "status": 1,
                "summary": 1,
                "slack_references": 1,
                "referenced_documents": 1
            })
        elif source in ["docs", "slides", "notion", "trello"]:
            projection.update({
                "last_edited_time": 1,
                "comment_count": 1,
                "comments": 1,
            })
            # Add url or link based on source
            if source in ["notion", "trello"]:
                projection["url"] = 1
            else:
                projection["link"] = 1
            
            if source == "trello":
                projection.update({"board_id": 1, "list_id": 1})
        
        # Only add embedding_vector to projection if requested
        if include_embeddings:
            projection["embedding_vector"] = 1
        
        # Execute query
        results = list(collection.find(query, projection))
        
        print(f"   Found {len(results)} context item(s) containing the requested IDs")
        
        # Format the results
        formatted_contexts = []
        for doc in results:
            context_item = {
                "context_id": str(doc.get("_id", "")),
                f"{id_field}": doc.get(id_field, ""),
                "correlation_text": doc.get("embedding_text", ""),
                "brief_description": doc.get("brief_description", ""),
                "change_summary": doc.get("change_summary", ""),
                "title": doc.get("title", ""),
                "source": doc.get("source", source),
            }
            
            # Add source-specific fields to response
            if source == "calendar":
                context_item.update({
                    "start_time": doc.get("start_time", ""),
                    "end_time": doc.get("end_time", ""),
                    "attendees": doc.get("attendees", []),
                    "status": doc.get("status", ""),
                    "summary": doc.get("summary", ""),
                    "slack_references": doc.get("slack_references", []),
                    "referenced_documents": doc.get("referenced_documents", [])
                })
            elif source in ["docs", "slides", "notion", "trello"]:
                context_item.update({
                    "last_edited_time": doc.get("last_edited_time", ""),
                    "comment_count": doc.get("comment_count", 0),
                    "url": doc.get("url") if source in ["notion", "trello"] else doc.get("link", "")
                })
                if source == "trello":
                    context_item.update({
                        "board_id": doc.get("board_id", ""),
                        "list_id": doc.get("list_id", "")
                    })
            
            # Only include embeddings if requested
            if include_embeddings and "embedding_vector" in doc:
                context_item["embedding_vector"] = doc["embedding_vector"]
            
            formatted_contexts.append(context_item)
        
        return {
            "matched_contexts": formatted_contexts,
            "total_matches": len(formatted_contexts),
            "ids_queried": ids,
            "message": f"Found {len(formatted_contexts)} {source} context item(s) with correlation information"
        }
        
    except PermissionError as e:
        print(f"[ERROR] Permission denied: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "ids_queried": ids,
            "error": str(e)
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch {source} context: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "ids_queried": ids,
            "error": f"Failed to fetch context: {str(e)}"
        }


# ---------------------------------------------------------------------------
# Specific Context Functions for Each Source
# ---------------------------------------------------------------------------


def get_calendar_context(
    event_ids: List[str],
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Fetch context for calendar events.
    
    Args:
        event_ids: List of calendar event IDs
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
    """
    return get_generic_context(
        ids=event_ids,
        source="calendar",
        id_field="id",
        token=token,
        include_embeddings=include_embeddings
    )


def get_docs_context(
    document_ids: List[str],
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Fetch context for Google Docs documents.
    
    Args:
        document_ids: List of Google Docs document IDs
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
    """
    return get_generic_context(
        ids=document_ids,
        source="gdocs",
        id_field="document_id",
        token=token,
        include_embeddings=include_embeddings
    )


def get_slides_context(
    presentation_ids: List[str],
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Fetch context for Google Slides presentations.
    
    Args:
        presentation_ids: List of Google Slides presentation IDs
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
    """
    return get_generic_context(
        ids=presentation_ids,
        source="gslides",
        id_field="presentation_id",
        token=token,
        include_embeddings=include_embeddings
    )


def get_notion_context(
    page_ids: List[str],
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Fetch context for Notion pages.
    
    Args:
        page_ids: List of Notion page IDs
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
    """
    return get_generic_context(
        ids=page_ids,
        source="notiondocs",
        id_field="page_id",
        token=token,
        include_embeddings=include_embeddings
    )


def get_trello_context(
    card_ids: List[str],
    token: Optional[str] = None,
    include_embeddings: bool = False
) -> Dict[str, Any]:
    """
    Fetch context for Trello cards (tasks).
    
    Args:
        card_ids: List of Trello card IDs (also called page_id in the schema)
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
    """
    return get_generic_context(
        ids=card_ids,
        source="trello",
        id_field="page_id",
        token=token,
        include_embeddings=include_embeddings
    )


def get_slack_context(
    channel_ids: List[str],
    token: Optional[str] = None,
    include_embeddings: bool = False,
    lookback_days: int = 7
) -> Dict[str, Any]:
    """
    Fetch context for Slack channels with time-based filtering.
    Multiple entries can exist for the same channel, so we filter by time (last 7 days by default).
    
    Args:
        channel_ids: List of Slack channel IDs
        token: User's unified token
        include_embeddings: Whether to include embedding vectors
        lookback_days: Number of days to look back (default: 7)
    """
    print(f"🔍 Fetching slack context for {len(channel_ids)} channel ID(s) (last {lookback_days} days)")
    
    if not channel_ids:
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "ids_queried": [],
            "message": "No channel IDs provided"
        }
    
    try:
        collection = get_context_collection(token, source="slack")
        
        # Calculate time threshold (7 days ago in Unix timestamp)
        from datetime import datetime, timedelta
        cutoff_time = (datetime.now() - timedelta(days=lookback_days)).timestamp()
        
        # Query for documents where channel_id matches and within time threshold
        query = {
            "channel_id": {"$in": channel_ids},
            "max_message_time": {"$gte": cutoff_time}
        }
        
        # Project fields - only include embedding_vector if requested
        projection = {
            "_id": 1,
            "channel_id": 1,
            "channel_name": 1,
            "embedding_text": 1,
            "summary": 1,
            "key_points": 1,
            "action_items": 1,
            "collaborators": 1,
            "topic_tags": 1,
            "message_count": 1,
            "min_message_time": 1,
            "max_message_time": 1,
            "batch_index": 1,
            "related_docs": 1,
            "source": 1,
            "created_at": 1,
        }
        
        # Only add embedding_vector to projection if requested
        if include_embeddings:
            projection["embedding_vector"] = 1
        
        # Execute query - sort by max_message_time descending (most recent first)
        results = list(
            collection.find(query, projection)
            .sort("max_message_time", -1)
        )
        
        print(f"   Found {len(results)} context item(s) for the requested channel IDs (last {lookback_days} days)")
        
        # Format the results
        formatted_contexts = []
        for doc in results:
            context_item = {
                "context_id": str(doc.get("_id", "")),
                "channel_id": doc.get("channel_id", ""),
                "channel_name": doc.get("channel_name", ""),
                "correlation_text": doc.get("embedding_text", ""),
                "summary": doc.get("summary", ""),
                "key_points": doc.get("key_points", []),
                "action_items": doc.get("action_items", []),
                "collaborators": doc.get("collaborators", []),
                "topic_tags": doc.get("topic_tags", []),
                "message_count": doc.get("message_count", 0),
                "batch_index": doc.get("batch_index", 0),
                "related_docs": doc.get("related_docs", []),
                "time_range": {
                    "earliest_message": datetime.fromtimestamp(
                        doc.get("min_message_time", 0)
                    ).isoformat() if doc.get("min_message_time") else None,
                    "latest_message": datetime.fromtimestamp(
                        doc.get("max_message_time", 0)
                    ).isoformat() if doc.get("max_message_time") else None,
                },
                "source": doc.get("source", "slack"),
            }
            
            # Only include embeddings if requested
            if include_embeddings and "embedding_vector" in doc:
                context_item["embedding_vector"] = doc["embedding_vector"]
            
            formatted_contexts.append(context_item)
        
        return {
            "matched_contexts": formatted_contexts,
            "total_matches": len(formatted_contexts),
            "ids_queried": channel_ids,
            "lookback_days": lookback_days,
            "message": f"Found {len(formatted_contexts)} slack context item(s) with correlation information (last {lookback_days} days)"
        }
        
    except PermissionError as e:
        print(f"[ERROR] Permission denied: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "ids_queried": channel_ids,
            "error": str(e)
        }
    except Exception as e:
        print(f"[ERROR] Failed to fetch slack context: {e}")
        return {
            "matched_contexts": [],
            "total_matches": 0,
            "ids_queried": channel_ids,
            "error": f"Failed to fetch context: {str(e)}"
        }

