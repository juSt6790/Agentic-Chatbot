"""
MongoDB History Client - Saves chat query and response history
"""

from typing import Optional, Dict, Any
from datetime import datetime
from pymongo import MongoClient
from db.mongo_client import get_mongo_client
from clients.db_method import get_user_id_from_token

# Get MongoDB client from centralized configuration
mongo_client = get_mongo_client()


def get_history_collection(token: Optional[str]) -> Any:
    """
    Return the per-tenant chat_history collection for the provided token.
    
    Args:
        token: User's unified token
        
    Returns:
        MongoDB collection for chat_history
    """
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise ValueError("Invalid or expired token")
    return mongo_client[db_name]["chat_history"]


def save_chat_history(
    token: Optional[str],
    query: str,
    response: str,
    raw_response: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    chat_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Save chat query and response to MongoDB chat_history collection.
    
    Args:
        token: User's unified token
        query: User's query text
        response: AI's response text (filtered/formatted)
        raw_response: Raw unfiltered text from AI (no processing)
        session_id: Optional session identifier
        metadata: Optional additional metadata (type, ui_hint, etc.)
        chat_id: Optional unique chat identifier (UUID)
        
    Returns:
        Dictionary with success status and inserted document ID
    """
    try:
        collection = get_history_collection(token)
        
        # Create document to save
        document = {
            "query": query,
            "response": response,
            "raw_response": raw_response or "",  # Raw unfiltered AI response
            "session_id": session_id,
            "timestamp": datetime.utcnow(),
            "metadata": metadata or {}
        }
        
        # Add chat_id if provided
        if chat_id:
            document["chat_id"] = chat_id
        
        # Insert into collection
        result = collection.insert_one(document)
        
        return {
            "success": True,
            "inserted_id": str(result.inserted_id),
            "message": "Chat history saved successfully"
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to save chat history: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to save chat history"
        }


def get_chat_history(
    token: Optional[str],
    limit: int = 50,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve chat history for a user.
    
    Args:
        token: User's unified token
        limit: Maximum number of records to return
        session_id: Optional filter by session_id
        
    Returns:
        Dictionary with chat history records
    """
    try:
        collection = get_history_collection(token)
        
        # Build query
        query = {}
        if session_id:
            query["session_id"] = session_id
        
        # Fetch records, sorted by timestamp (newest first)
        records = list(
            collection.find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )
        
        # Convert ObjectId to string for JSON serialization
        for record in records:
            record["_id"] = str(record["_id"])
            if "timestamp" in record:
                record["timestamp"] = record["timestamp"].isoformat()
        
        return {
            "success": True,
            "count": len(records),
            "history": records
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to retrieve chat history: {e}")
        return {
            "success": False,
            "error": str(e),
            "history": []
        }

