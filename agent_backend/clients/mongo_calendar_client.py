import os
import json
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import calendar
import requests

from utils.date_utils import DateParser
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_tool_access_token, get_user_id_from_token

# ---------------------------------------------------------------------------
# Initial setup – env & clients
# ---------------------------------------------------------------------------
load_dotenv()
mongo_client = get_mongo_client()

# External user/token service
BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://3.6.95.164:5000/users")


# def get_tool_token(unified_token: str, tool_name: str = "MongoDB") -> Dict[str, Any]:
#     try:
#         url = f"{BASE_URL}/get_tool_token"
#         payload = {"unified_token": unified_token, "tool_name": tool_name}
#         headers = {"Authorization": unified_token}
#         response = requests.post(url, json=payload, headers=headers, timeout=10)
#         response.raise_for_status()
#         return response.json()
#     except Exception as e:
#         print(f"[WARN] get_tool_token failed: {e}")
#         return {}

# def resolve_user_db_from_token(token: Optional[str], default_db: str = "300") -> str:
#     if not token:
#         return default_db
#     data = get_tool_token(token, tool_name="MongoDB") or {}
#     for key in ("user_id", "db_id", "tenant_id", "mongo_db", "org_id"):
#         val = data.get(key)
#         if isinstance(val, (str, int)) and str(val).strip():
#             return str(val)
#     access = data.get("access_token", {}) if isinstance(data, dict) else {}
#     for key in ("user_id", "db_id", "tenant_id", "mongo_db", "org_id"):
#         val = access.get(key)
#         if isinstance(val, (str, int)) and str(val).strip():
#             return str(val)
#     return default_db


def get_collection(token: Optional[str]):
    """
    Return the per-tenant Calendar collection for the provided token.
    Validates that user has access to Gsuite/Calendar before returning collection.
    """
    # Validate user has access to Calendar/Gsuite
    is_valid, error_msg, status_code = validate_user_tool_access(token, "Gsuite")
    if not is_valid:
        raise PermissionError(f"Calendar access denied: {error_msg}")
    
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise PermissionError("Invalid or expired token")
    print(f"[DEBUG] Using user database: {db_name}")
    return mongo_client[db_name]["calendar"]

# Bedrock / Titan embedding setup
load_dotenv()
REGION = os.getenv("AWS_REGION", "us-east-1")
TITAN_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
# Bearer token for Bedrock authentication (replaces IAM credentials)
AWS_BEARER_TOKEN_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")

# Initialize date parser
date_parser = DateParser()

# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def _norm_meet_url(url: str) -> str:
    if not url:
        return ""
    return str(url).strip().split("?")[0].rstrip("/")


def meeting_url_from_calendar_doc(doc: Dict[str, Any]) -> str:
    """Google Meet URL if present on the stored calendar row (for scheduling / transcript lookup)."""
    for key in ("hangout_link", "hangoutLink", "meeting_url"):
        v = doc.get(key)
        if v:
            return _norm_meet_url(str(v))
    ed = doc.get("event_data")
    if isinstance(ed, dict):
        v = ed.get("hangoutLink") or ed.get("hangout_link")
        if v:
            return _norm_meet_url(str(v))
    loc = (doc.get("location") or "").strip()
    if "meet.google.com" in loc:
        for part in loc.split():
            if "meet.google.com" in part:
                return _norm_meet_url(part)
    return ""


def generate_titan_embedding(text: str) -> List[float]:
    try:
        body = {"inputText": text.replace("\n", " ")}
        url = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{TITAN_EMBEDDING_MODEL_ID}/invoke"
        
        # Use bearer token authentication instead of SigV4Auth
        if not AWS_BEARER_TOKEN_BEDROCK:
            print("[ERROR] AWS_BEARER_TOKEN_BEDROCK environment variable is not set")
            return []
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {AWS_BEARER_TOKEN_BEDROCK}"
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(body))
        response.raise_for_status()
        result = response.json()
        embedding = result.get("embedding", [])
        if not embedding:
            print("[ERROR] Titan response missing embedding")
            return []
        if len(embedding) != 1024:
            print(f"[WARNING] Expected 1024 dimensions, got {len(embedding)}")
        return embedding
    except Exception as e:
        print(f"[ERROR] Titan embedding failed: {e}")
        return []


def get_embedding(text: str) -> List[float]:
    return generate_titan_embedding(text)


def free_text_search(query: str, limit: int = 50, token: Optional[str] = None) -> List[Dict[str, Any]]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Calendar credentials") if isinstance(result, dict) else "Failed to retrieve Calendar credentials"
        raise PermissionError(f"Calendar access denied: {error_msg}")
    
    print(f"🔍 Performing free text search with query: '{query}'")
    collection = get_collection(token)
    results = list(collection.find(
        {"$text": {"$search": query}},
        {"score": {"$meta": "textScore"}}
    ).sort([("score", {"$meta": "textScore"})]).limit(limit))
    print(f"   Found {len(results)} results in free text search")
    return results


def vector_search_on_results(query: str, free_text_results: List[Dict[str, Any]], 
                            min_similarity: float = 0.15,
                            percentile_threshold: float = 0.7,
                            token: Optional[str] = None) -> List[Dict[str, Any]]:
    print(f"🧠 Performing vector search with query: '{query}' on {len(free_text_results)} free text results")
    try:
        if not free_text_results:
            print("   No free text results to perform vector search on")
            return []
        query_embedding = get_embedding(query)
        print(f"   Calculating similarity for {len(free_text_results)} documents")
        docs_with_embeddings = [doc for doc in free_text_results if "embedding" in doc]
        if not docs_with_embeddings:
            print("   Warning: No embeddings found in results. Fetching embeddings from database...")
            doc_ids = [doc["_id"] for doc in free_text_results]
            collection = get_collection(token)
            full_docs = list(collection.find({"_id": {"$in": doc_ids}}))
            doc_map = {str(doc["_id"]): doc for doc in full_docs}
            for i, doc in enumerate(free_text_results):
                doc_id = str(doc["_id"])
                if doc_id in doc_map and "embedding" in doc_map[doc_id]:
                    free_text_results[i]["embedding"] = doc_map[doc_id]["embedding"]
        for doc in free_text_results:
            if "embedding" in doc:
                doc["similarity"] = np.dot(query_embedding, doc["embedding"]) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(doc["embedding"])
                )
            else:
                doc["similarity"] = 0
        results = sorted(free_text_results, key=lambda x: x.get("similarity", 0), reverse=True)
        filtered_results = [doc for doc in results if doc.get("similarity", 0) >= min_similarity]
        if filtered_results:
            if len(filtered_results) > 1 and percentile_threshold < 1.0:
                similarity_scores = [doc.get("similarity", 0) for doc in filtered_results]
                if similarity_scores:
                    max_score = max(similarity_scores)
                    percentile_min_score = max_score * percentile_threshold
                    percentile_results = [doc for doc in filtered_results 
                                         if doc.get("similarity", 0) >= percentile_min_score]
                    if not percentile_results:
                        return filtered_results
                    return percentile_results
            return filtered_results
        else:
            return results[:3] if results else []
    except PermissionError:
        # Re-raise permission errors so they get handled properly
        raise
    except Exception as e:
        # For other errors (embedding failures, etc.), log and return fallback
        print(f"Error in vector search: {e}")
        return free_text_results


def date_range_search(start: Optional[str], end: Optional[str], limit: int = 50, token: Optional[str] = None) -> List[Dict[str, Any]]:
    print(f"📅 Performing date range search: start={start}, end={end}")
    query = {}
    # If start and end are just dates (YYYY-MM-DD), expand to full day
    def expand_date(date_str, is_start):
        if len(date_str) == 10:  # YYYY-MM-DD
            return date_str + ("T00:00:00" if is_start else "T23:59:59")
        return date_str
    if start and end:
        start_exp = expand_date(start, True)
        end_exp = expand_date(end, False)
        query["start_time"] = {"$gte": start_exp, "$lte": end_exp}
    elif start:
        start_exp = expand_date(start, True)
        query["start_time"] = {"$gte": start_exp}
    elif end:
        end_exp = expand_date(end, False)
        query["start_time"] = {"$lte": end_exp}
    collection = get_collection(token)
    # Sort ascending by start_time so the next upcoming meeting is first
    results = list(collection.find(query).sort("start_time", 1).limit(limit))
    print(f"   Found {len(results)} results in date range search")
    return results


def combined_search(query: str = None, start: str = None, end: str = None, top_n: int = 5, 
                   min_similarity: float = 0.15, percentile_threshold: float = 0.7,
                   token: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict]:
    print(f"\n📊 Starting combined calendar search for: '{query}', start={start}, end={end}")
    
    # Always validate calendar access first, even if returning empty results
    # This will raise PermissionError if user doesn't have access
    get_collection(token)
    
    found_ids = []
    
    # Step 1: Date range search if dates provided
    date_results = []
    if start or end:
        print(f"   📅 Searching date range: {start} to {end}")
        date_results = date_range_search(start, end, limit=50, token=token)
        found_ids = [doc["_id"] for doc in date_results]
        print(f"   📅 Found {len(date_results)} events in date range")
    
    # Step 2: Free text search (exclude already found)
    text_results = []
    if query and query.strip():
        print(f"   🔍 Searching text query: '{query}'")
        text_results = free_text_search(query, limit=50, token=token)
        if found_ids:
            text_results = [doc for doc in text_results if doc["_id"] not in found_ids]
        print(f"   🔍 Found {len(text_results)} events from text search (excluding date matches)")
    
    # Step 3: Vector search on free text results
    vector_results = []
    if text_results:
        vector_results = vector_search_on_results(query, text_results, min_similarity, percentile_threshold, token)
        print(f"   🧠 Vector search returned {len(vector_results)} events")
    
    # Combine results
    all_results = date_results + vector_results
    # Ensure deterministic ordering: next meeting first (ascending by start_time)
    try:
        all_results.sort(key=lambda d: d.get("start_time", ""))
    except Exception:
        pass
    all_results = all_results[:top_n]
    print(f"\n✅ Final result count: {len(all_results)} (top {top_n} most relevant)")
    print(f"   📅 Date range events: {len(date_results)}")
    print(f"   🧠 Vector search events: {len(vector_results)}")
    
    return all_results, {"query": query, "start": start, "end": end}


def mongo_search_events(query: str = None,
                        start: str = None,
                        end: str = None,
                        date: str = None,
                        email: str = None,
                        max_results: int = 10,
                        token: Optional[str] = None,
                        limit: Optional[int] = None) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Calendar credentials") if isinstance(result, dict) else "Failed to retrieve Calendar credentials"
        raise PermissionError(f"Calendar access denied: {error_msg}")
    
    # Handle date parameter like the original search_events function
    if date and not (start or end):
        try:
            if len(date) == 7:  # YYYY-MM
                year, month = map(int, date.split('-'))
                start = f"{year:04d}-{month:02d}-01"
                last_day = calendar.monthrange(year, month)[1]
                end = f"{year:04d}-{month:02d}-{last_day:02d}"
            elif len(date) == 10:  # YYYY-MM-DD
                start = end = date
        except Exception:
            pass
    
    effective_top = int(limit) if isinstance(limit, int) and limit > 0 else int(max_results)
    results, _ = combined_search(query=query, start=start, end=end, top_n=effective_top, token=token)
    # Final safety: sort ascending by start_time
    try:
        results.sort(key=lambda d: d.get("start_time", ""))
    except Exception:
        pass
    
    # Filter by email if provided
    if email:
        filtered_results = []
        for doc in results:
            # Check if email appears in attendees, organizer, or creator
            attendees = doc.get("attendees", [])
            organizer_email = doc.get("organizer", {}).get("email", "")
            creator_email = doc.get("event_data", {}).get("creator", {}).get("email", "")

            # Check attendees list
            attendee_emails = [att.get("email", "") for att in attendees if isinstance(att, dict)]

            if (
                email in attendee_emails
                or email == organizer_email
                or email == creator_email
            ):
                filtered_results.append(doc)
        results = filtered_results

    # Final safety sort before formatting
    try:
        results.sort(key=lambda d: d.get("start_time", ""))
    except Exception:
        pass

    response = {
        "query": query,
        "start": start,
        "end": end,
        "date": date,
        "email": email,
        "total_matches": len(results),
        "events": []
    }
    for doc in results:
        # Use Google Calendar event ID (from 'id' or 'event_id' field), not MongoDB's _id
        event_id = doc.get("id") or doc.get("event_id") or str(doc.get("_id", ""))
        response["events"].append({
            "event_id": event_id,
            "summary": doc.get("summary", "No Title"),
            "description": doc.get("description", ""),
            "start_time": doc.get("start_time", ""),
            "end_time": doc.get("end_time", ""),
            "attendees": doc.get("attendees", []),
            "location": doc.get("location", ""),
            "organizer": doc.get("organizer", ""),
            "status": doc.get("status", ""),
            "html_link": doc.get("html_link", ""),
            "meeting_url": meeting_url_from_calendar_doc(doc),
            "keywords": doc.get("keywords", []),
        })
    return response


def mongo_query_events(
    query: Optional[str] = None,
    max_results: int = 10,
    token: Optional[str] = None,
    start: Optional[str] = None,  # YYYY-MM-DD or RFC3339
    end: Optional[str] = None,    # YYYY-MM-DD or RFC3339
    email: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Unified calendar events search in MongoDB.
    - Accepts a raw text `query` for context search and optional structured filters: `start`, `end`, `email`.
    - Applies structured filters first (via Mongo filter). If `query` has text, runs $text within the filtered set,
      then vector-re-ranks those results. Otherwise returns the filtered results only. If no filters exist, falls back to
      `combined_search` using the text query.
    - `limit` overrides `max_results` when provided.
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Calendar credentials") if isinstance(result, dict) else "Failed to retrieve Calendar credentials"
        raise PermissionError(f"Calendar access denied: {error_msg}")
    
    effective_limit = int(limit) if isinstance(limit, int) and limit > 0 else int(max_results)
    collection = get_collection(token)
    conditions: List[Dict[str, Any]] = []
    # Date range on start_time
    date_filter: Dict[str, Any] = {}
    if start:
        # expand date-only to full start of day
        start_exp = start + ("T00:00:00" if len(start) == 10 else "")
        date_filter["$gte"] = start_exp
    if end:
        end_exp = end + ("T23:59:59" if len(end) == 10 else "")
        date_filter["$lte"] = end_exp
    if date_filter:
        conditions.append({"start_time": date_filter})
    # Email filter across attendees/organizer/creator
    if email:
        conditions.append({
            "$or": [
                {"attendees.email": {"$regex": email, "$options": "i"}},
                {"organizer.email": {"$regex": email, "$options": "i"}},
                {"event_data.creator.email": {"$regex": email, "$options": "i"}},
            ]
        })
    mongo_filter: Dict[str, Any] = {}
    if conditions:
        mongo_filter["$and"] = conditions
    text_query = (query or "").strip()
    results: List[Dict[str, Any]] = []
    if mongo_filter:
        # Sort ascending so upcoming meetings appear first
        base_cursor = collection.find(mongo_filter).sort("start_time", 1)
        base_docs = list(base_cursor)
        if text_query:
            # Run $text within the filtered set
            query_with_text = {**mongo_filter, "$text": {"$search": text_query}}
            fts_cursor = (
                collection.find(query_with_text, {"score": {"$meta": "textScore"}})
                .sort([("score", {"$meta": "textScore"})])
                .limit(effective_limit * 3)
            )
            fts_docs = list(fts_cursor)
            vector_reranked = vector_search_on_results(
                text_query, fts_docs, min_similarity=0.15, percentile_threshold=0.7, token=token
            )
            results = vector_reranked[:effective_limit]
        else:
            # Ensure ascending order
            base_docs.sort(key=lambda d: d.get("start_time", ""))
            results = base_docs[:effective_limit]
    else:
        # No filters → fallback to combined search on text or default latest
        if text_query:
            results, _ = combined_search(query=text_query, top_n=effective_limit, token=token)
        else:
            # Upcoming-first ordering
            results = list(collection.find({}).sort("start_time", 1).limit(effective_limit))

    response = {
        "query": query,
        "start": start,
        "end": end,
        "email": email,
        "total_matches": len(results),
        "events": []
    }
    for doc in results:
        # Use Google Calendar event ID (from 'id' or 'event_id' field), not MongoDB's _id
        event_id = doc.get("id") or doc.get("event_id") or str(doc.get("_id", ""))
        response["events"].append({
            "event_id": event_id,
            "summary": doc.get("summary", "No Title"),
            "description": doc.get("description", ""),
            "start_time": doc.get("start_time", ""),
            "end_time": doc.get("end_time", ""),
            "attendees": doc.get("attendees", []),
            "location": doc.get("location", ""),
            "organizer": doc.get("organizer", ""),
            "status": doc.get("status", ""),
            "html_link": doc.get("html_link", ""),
            "meeting_url": meeting_url_from_calendar_doc(doc),
            "keywords": doc.get("keywords", []),
        })
    return response


def mongo_get_events(event_ids: List[str], token: Optional[str] = None) -> Dict[str, Any]:
    """
    Get calendar events from MongoDB by their IDs (Google Calendar event IDs, not MongoDB _id)
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Calendar credentials") if isinstance(result, dict) else "Failed to retrieve Calendar credentials"
        raise PermissionError(f"Calendar access denied: {error_msg}")
    
    # Query MongoDB for the events using Google Calendar event IDs
    # The LLM provides Google Calendar event IDs (like recurring event IDs or unique identifiers)
    # These are stored in the 'id' or 'event_id' field, NOT MongoDB's '_id' field
    collection = get_collection(token)
    
    # Try multiple possible field names for the Google Calendar event ID
    # Use $or to check both 'id' and 'event_id' fields
    results = list(collection.find({
        "$or": [
            {"id": {"$in": event_ids}},
            {"event_id": {"$in": event_ids}}
        ]
    }))
    
    # Format the response
    response = {
        "status": "success" if results else "error",
        "retrieved_events_count": len(results),
        "events": [],
        "errors": []
    }
    
    # Format each event for the response
    for doc in results:
        # Use Google Calendar event ID (from 'id' or 'event_id' field), not MongoDB's _id
        event_id = doc.get("id") or doc.get("event_id") or str(doc.get("_id", ""))
        response["events"].append({
            "event_id": event_id,
            "summary": doc.get("summary", "No Title"),
            "description": doc.get("description", ""),
            "start_time": doc.get("start_time", ""),
            "end_time": doc.get("end_time", ""),
            "attendees": doc.get("attendees", []),
            "location": doc.get("location", ""),
            "organizer": doc.get("organizer", ""),
            "status": doc.get("status", ""),
            "html_link": doc.get("html_link", ""),
            "meeting_url": meeting_url_from_calendar_doc(doc),
            "keywords": doc.get("keywords", []),
        })
    
    # Add errors for any IDs that weren't found
    # Track by Google Calendar event ID (from 'id' or 'event_id' field)
    found_ids = [doc.get("id") or doc.get("event_id") or str(doc.get("_id", "")) for doc in results]
    for event_id in event_ids:
        if event_id not in found_ids:
            response["errors"].append({
                "event_id": event_id,
                "error": "Event not found"
            })

    if not results:
        response["message"] = (
            "❌ None of the requested calendar events were found in your synced calendar. "
            "They may not be indexed yet—open Meetings in the app to refresh sync."
        )
        response["ui_hint"] = "open_meetings_panel"

    return response