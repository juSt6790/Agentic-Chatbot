import os
import gzip
import zlib
import base64
import json
import re
import numpy as np
from typing import List, Dict, Any, Tuple, Optional, Union
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import requests

from utils.date_utils import DateParser
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_tool_access_token, get_user_id_from_token
from services.docs_mcp import get_gdocs_service

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


# def resolve_user_db_from_token(token: Optional[str], default_db: str = "1100") -> str:
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
    Return the per-tenant Google Docs collection for the provided token.
    Validates that user has access to Gsuite/Docs before returning collection.
    """
    # Validate user has access to Google Docs/Gsuite
    is_valid, error_msg, status_code = validate_user_tool_access(token, "Gsuite")
    if not is_valid:
        raise PermissionError(f"Google Docs access denied: {error_msg}")
    
    # db_name = resolve_user_db_from_token(token, default_db=os.getenv("DEFAULT_MONGO_DB_DOCS", "1100"))
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise PermissionError("Invalid or expired token")
    return mongo_client[db_name]["g_docs"]

# Bedrock / Titan embedding setup
load_dotenv()
REGION = os.getenv("AWS_REGION", "us-east-1")
TITAN_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
# Bearer token for Bedrock authentication (replaces IAM credentials)
AWS_BEARER_TOKEN_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")

# Initialize date parser
date_parser = DateParser()

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def decompress_text(compressed_data) -> str:
    """Decompress the compressed_text field from MongoDB"""
    try:
        if not compressed_data:
            return ""
        # Handle different formats of compressed data
        if isinstance(compressed_data, str):
            # If it's already a string, return as is
            return compressed_data
        elif isinstance(compressed_data, bytes):
            # If it's raw bytes, try different decompression methods
            try:
                # Try zlib first (most common for MongoDB)
                decompressed = zlib.decompress(compressed_data)
                return decompressed.decode('utf-8')
            except:
                try:
                    # Try gzip as fallback
                    decompressed = gzip.decompress(compressed_data)
                    return decompressed.decode('utf-8')
                except:
                    # If both fail, try to decode as plain text
                    return compressed_data.decode('utf-8', errors='ignore')
        elif "$binary" in compressed_data:
            # Extract base64 data
            base64_data = compressed_data["$binary"]["base64"]
            # Decode base64
            binary_data = base64.b64decode(base64_data)
            # Try different decompression methods
            try:
                decompressed = zlib.decompress(binary_data)
                return decompressed.decode('utf-8')
            except:
                try:
                    decompressed = gzip.decompress(binary_data)
                    return decompressed.decode('utf-8')
                except:
                    return binary_data.decode('utf-8', errors='ignore')
        else:
            # If it's a dict but no $binary, try to convert to string
            return str(compressed_data)
    except Exception as e:
        print(f"Error decompressing text: {e}")
        return ""


_IMAGEURL_TAG_RE = re.compile(r"<imageCosi>.*?</imageCosi>", re.DOTALL)


def strip_imageurl_placeholders(text: str) -> Tuple[str, bool, int]:
    """
    Remove <imageurl>...</imageurl> markers from text before sending to the AI,
    while tracking whether images are present and how many placeholders existed.

    - Replaces each image marker with a generic '[IMAGE]' token.
    - Returns (clean_text, has_images, image_count).
    """
    if not text or not isinstance(text, str):
        return text or "", False, 0

    matches = list(_IMAGEURL_TAG_RE.finditer(text))
    if not matches:
        return text, False, 0

    cleaned = _IMAGEURL_TAG_RE.sub("[IMAGE]", text)
    return cleaned, True, len(matches)


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

# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------

def free_text_search(query: str, limit: int = 50, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Perform free text search using MongoDB's text index
    """
    print(f"🔍 Performing free text search with query: '{query}'")
    try:
        collection = get_collection(token)
        results = list(collection.find(
            {"$text": {"$search": query}},
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit))
        print(f"   Found {len(results)} results in free text search")
        return results
    except Exception as e:
        print(f"Error in free text search: {e}")
        return []


def vector_search_on_results(query: str, free_text_results: List[Dict[str, Any]], 
                            min_similarity: float = 0.15,
                            percentile_threshold: float = 0.7,
                            token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Perform vector search ONLY on the results from free text search
    """
    print(f"🧠 Performing vector search with query: '{query}' on {len(free_text_results)} free text results")
    try:
        if not free_text_results:
            print("   No free text results to perform vector search on")
            return []
        # Get embedding for the query
        query_embedding = get_embedding(query)
        print(f"   Calculating similarity for {len(free_text_results)} documents")
        # Check if we have embeddings in the results
        docs_with_embeddings = [doc for doc in free_text_results if "embedding" in doc]
        if not docs_with_embeddings:
            print("   Warning: No embeddings found in results. Fetching embeddings from database...")
            # Get document IDs
            doc_ids = [doc["_id"] for doc in free_text_results]
            # Fetch full documents with embeddings from database
            collection = get_collection(token)
            full_docs = list(collection.find({"_id": {"$in": doc_ids}}))
            # Create a mapping of document IDs to their full versions with embeddings
            doc_map = {str(doc["_id"]): doc for doc in full_docs}
            # Update the results with embeddings
            for i, doc in enumerate(free_text_results):
                doc_id = str(doc["_id"])
                if doc_id in doc_map and "embedding" in doc_map[doc_id]:
                    free_text_results[i]["embedding"] = doc_map[doc_id]["embedding"]
        # Calculate similarity for each document
        for doc in free_text_results:
            if "embedding" in doc:
                # Calculate cosine similarity
                doc["similarity"] = np.dot(query_embedding, doc["embedding"]) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(doc["embedding"]) 
                )
            else:
                print(f"   Warning: No embedding found for document with title: {doc.get('title', 'Unknown')}")
                doc["similarity"] = 0
        # Sort by similarity
        results = sorted(free_text_results, key=lambda x: x.get("similarity", 0), reverse=True)
        # Apply thresholds
        # 1. Absolute threshold - filter out documents with similarity below min_similarity
        filtered_results = [doc for doc in results if doc.get("similarity", 0) >= min_similarity]
        if filtered_results:
            print(f"   After minimum similarity threshold ({min_similarity}): {len(filtered_results)} results")
            # 2. Percentile threshold - keep only top percentile_threshold% of results
            if len(filtered_results) > 1 and percentile_threshold < 1.0:
                # Calculate similarity scores
                similarity_scores = [doc.get("similarity", 0) for doc in filtered_results]
                # Calculate percentile threshold
                if similarity_scores:
                    max_score = max(similarity_scores)
                    percentile_min_score = max_score * percentile_threshold
                    # Apply percentile threshold
                    percentile_results = [doc for doc in filtered_results 
                                         if doc.get("similarity", 0) >= percentile_min_score]
                    print(f"   After percentile threshold ({percentile_threshold*100}%): {len(percentile_results)} results")
                    print(f"   Percentile cutoff score: {percentile_min_score:.4f}")
                    # If percentile filtering removed all results, fall back to absolute threshold
                    if not percentile_results:
                        print("   Warning: Percentile threshold removed all results. Using absolute threshold results.")
                        return filtered_results
                    return percentile_results
            return filtered_results
        else:
            print(f"   Warning: All results filtered out by minimum similarity threshold ({min_similarity})")
            # If all results filtered out, return top 3 from original results
            return results[:3] if results else []
    except Exception as e:
        print(f"Error in vector search: {e}")
        return free_text_results  # Return original results if vector search fails


def date_search(date_query: Dict, exclude_ids: List, limit: int = 20, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Perform date-specific search
    """
    print(f"📅 Performing date search with query: {date_query}")
    try:
        if not date_query:
            return []
        # Find documents matching the date criteria
        # Make sure to include embedding field for vector search
        collection = get_collection(token)
        results = list(collection.find({
            "_id": {"$nin": exclude_ids},
            **date_query
        }).limit(limit))
        print(f"   Found {len(results)} results in date search")
        # Check if we have embeddings in the results
        has_embeddings = any("embedding" in doc for doc in results)
        if not has_embeddings:
            print("   Warning: No embeddings found in date search results. Vector search may not work properly.")
        return results
    except Exception as e:
        print(f"Error in date search: {e}")
        return []


def build_date_query_string(date_parts: Dict) -> str:
    """
    Build a string representation of the date parts for free text search
    """
    if not date_parts:
        return ""
    
    date_strings = []
    
    # Add month abbreviation if present
    if date_parts.get("month"):
        month_num = date_parts["month"]
        # Get month abbreviation (Jan, Feb, etc.)
        import calendar
        month_abbr = calendar.month_abbr[month_num]
        
        # If we also have day, format as "DD Mon"
        if date_parts.get("day"):
            day = date_parts["day"]
            # Format day with leading zero
            day_str = f"{day:02d}"
            date_strings.append(f"{day_str} {month_abbr}")
        else:
            date_strings.append(month_abbr)
    # If we only have day without month
    elif date_parts.get("day"):
        day = date_parts["day"]
        day_str = f"{day:02d}"
        date_strings.append(day_str)
    
    # Add year if present
    if date_parts.get("year"):
        date_strings.append(str(date_parts["year"]))
    
    # Add weekday if present
    if date_parts.get("weekday"):
        date_strings.append(date_parts["weekday"])
    
    # Add quarter if present
    if date_parts.get("quarter"):
        # Find the quarter name from the quarter mapping
        for name, value in date_parser.quarter_mappings.items():
            if value == date_parts["quarter"]:
                date_strings.append(name)
                break
    
    return " ".join(date_strings)


def combined_search(query: str, top_n: int = 5, 
                   min_similarity: float = 0.15, 
                   percentile_threshold: float = 0.7,
                   token: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict]:
    """
    Perform a combined search using all three approaches:
    1. Free text search to get initial results (only date parts if dates are present)
    2. Vector search on those free text results to rerank them (using non-date parts)
    3. Return only the top N most relevant results
    """
    print(f"\n📊 Starting combined docs search for: '{query}'")
    
    # Extract date parts and clean query
    date_parts, clean_query = date_parser.extract_date_parts(query)
    date_query = date_parser.build_date_query(date_parts)
    
    # Track document IDs we've already found
    found_ids = []
    
    # Step 1: Free text search
    print("\n--- Step 1: Free Text Search ---")
    
    # If date parts are present, use them for free text search
    if date_parts:
        # Build a date query string for free text search
        date_query_string = build_date_query_string(date_parts)
        print(f"🗓️ Using date parts for free text search: '{date_query_string}'")
        text_results = free_text_search(date_query_string, token=token)
        
        # If free text search with date returns no results, try date search directly
        if not text_results and date_query:
            print("\n--- Trying Direct Date Search ---")
            text_results = date_search(date_query, [], limit=50, token=token)
            print(f"   Found {len(text_results)} results in direct date search")
    else:
        # No date parts, use the original query
        text_results = free_text_search(query, token=token)
    
    if not text_results:
        print("⚠️ No results found in free text search or date search")
        
        # If still no results, try vector search on everything
        print("\n--- Trying Vector Search on All Documents ---")
        vector_query = clean_query if clean_query else query
        collection = get_collection(token)
        all_docs = list(collection.find({}))
        
        # Get embedding for the query
        query_embedding = get_embedding(vector_query)
        
        # Calculate similarity for each document
        for doc in all_docs:
            if "embedding" in doc:
                doc["similarity"] = np.dot(query_embedding, doc["embedding"]) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(doc["embedding"]) 
                )
            else:
                doc["similarity"] = 0
        
        # Sort by similarity
        vector_results = sorted(all_docs, key=lambda x: x.get("similarity", 0), reverse=True)
        
        # Apply thresholds
        vector_results = [doc for doc in vector_results if doc.get("similarity", 0) >= min_similarity]
        
        # Take top N results
        vector_results = vector_results[:top_n]
        
        print(f"\n✅ Found {len(vector_results)} results from vector search on all documents")
        return vector_results, {"date_parts": date_parts, "clean_query": clean_query}
    
    # Step 2: Vector search on free text results
    print("\n--- Step 2: Vector Search on Free Text Results ---")
    
    # For vector search, use the clean query (without date parts)
    # If clean_query is empty but original query had non-date parts, extract them
    if date_parts and not clean_query.strip() and query != build_date_query_string(date_parts):
        # Extract non-date parts by removing date parts from original query
        date_string = build_date_query_string(date_parts)
        non_date_query = query.lower().replace(date_string.lower(), "").strip()
        vector_query = non_date_query if non_date_query else "relevant"
    else:
        vector_query = clean_query if clean_query and clean_query.strip() else "relevant"
        
    print(f"🔤 Using non-date parts for vector search: '{vector_query}'")
    
    # Check if we need to fetch embeddings for the documents
    # This is necessary if we got results from date_search which might not include embeddings
    docs_with_embeddings = [doc for doc in text_results if "embedding" in doc]
    if not docs_with_embeddings and text_results:
        print("   Fetching embeddings for documents before vector search...")
        # Get document IDs
        doc_ids = [doc["_id"] for doc in text_results]
        
        # Fetch full documents with embeddings from database
        collection = get_collection(token)
        full_docs = list(collection.find({"_id": {"$in": doc_ids}}))
        
        # Create a mapping of document IDs to their full versions with embeddings
        doc_map = {str(doc["_id"]): doc for doc in full_docs}
        
        # Update the results with embeddings
        for i, doc in enumerate(text_results):
            doc_id = str(doc["_id"])
            if doc_id in doc_map and "embedding" in doc_map[doc_id]:
                text_results[i]["embedding"] = doc_map[doc_id]["embedding"]
    
    # Perform vector search on the free text results with thresholds
    vector_results = vector_search_on_results(
        vector_query, 
        text_results,
        min_similarity=min_similarity,
        percentile_threshold=percentile_threshold,
        token=token
    )
    
    # Only return the top N results after vector reranking
    final_results = vector_results[:top_n]
    
    print(f"\n✅ Final result count: {len(final_results)} (top {top_n} most relevant)")
    return final_results, {"date_parts": date_parts, "clean_query": clean_query}


def format_doc_preview(doc: Dict[str, Any]) -> str:
    """Format a document for display"""
    # Format the document for display
    title = doc.get("title", "No title")
    owner = doc.get("owner", "No owner")
    created = doc.get("created", "No creation date")
    modified = doc.get("modified", "No modification date")
    content = doc.get("content", "No content")
    keywords = ", ".join(doc.get("keywords", []))
    
    # Display score for free text search results
    score_info = f"Score: {doc.get('score', 'N/A')}" if "score" in doc else ""
    
    # Display similarity for vector search results
    similarity_info = f"Similarity: {doc.get('similarity', 'N/A'):.4f}" if "similarity" in doc else ""
    
    # Truncate content if it's too long
    if len(content) > 200:
        content = content[:200] + "..."
    
    return (
        f"Title: {title}\n"
        f"Owner: {owner}\n"
        f"Created: {created}\n"
        f"Modified: {modified}\n"
        f"Keywords: {keywords}\n"
        f"Content: {content}\n"
        f"{score_info}\n{similarity_info}".strip()
    )

# ---------------------------------------------------------------------------
# API Functions for MCP Integration
# ---------------------------------------------------------------------------

def mongo_search_docs(
    query: str = None,
    owner: str = None,
    after_date: str = None,
    before_date: str = None,
    max_results: int = 10,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search Google Docs in MongoDB based on various criteria
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Google Docs credentials") if isinstance(result, dict) else "Failed to retrieve Google Docs credentials"
        raise PermissionError(f"Google Docs access denied: {error_msg}")
    
    # Build the search query
    search_parts = []
    
    # Add query parts based on parameters
    if query:
        search_parts.append(query)
    
    if owner:
        search_parts.append(f"owner:{owner}")
    
    # Handle date ranges
    date_query = {}
    if after_date:
        try:
            after_date_obj = datetime.strptime(after_date, "%Y-%m-%d")
            date_query["created"] = {"$gte": after_date_obj}
        except ValueError:
            print(f"Invalid after_date format: {after_date}")
    
    if before_date:
        try:
            before_date_obj = datetime.strptime(before_date, "%Y-%m-%d")
            date_query_part = date_query.get("created", {})
            date_query_part["$lte"] = before_date_obj
            date_query["created"] = date_query_part
        except ValueError:
            print(f"Invalid before_date format: {before_date}")
    
    # Build the combined query string
    search_query = " ".join(search_parts)
    
    # If no specific query parts but we have date filters, use a general query
    if not search_query and date_query:
        search_query = "documents"
    
    # If we still have no query, return empty results
    if not search_query:
        return {"query": "", "total_matches": 0, "documents": []}
    
    # Perform combined search
    results, _ = combined_search(search_query, top_n=max_results, token=token)
    
    # Apply date filters if needed
    if date_query:
        filtered_results = []
        for doc in results:
            if "created" in doc:
                doc_created = doc["created"]
                if isinstance(doc_created, str):
                    try:
                        doc_created = datetime.strptime(doc_created, "%Y-%m-%dT%H:%M:%S.%fZ")
                    except ValueError:
                        try:
                            doc_created = datetime.strptime(doc_created, "%Y-%m-%d")
                        except ValueError:
                            continue
                
                # Check if created date meets the date criteria
                meets_criteria = True
                if "$gte" in date_query.get("created", {}):
                    meets_criteria = meets_criteria and doc_created >= date_query["created"]["$gte"]
                if "$lte" in date_query.get("created", {}):
                    meets_criteria = meets_criteria and doc_created <= date_query["created"]["$lte"]
                
                if meets_criteria:
                    filtered_results.append(doc)
            else:
                # If no created date, skip this document
                continue
        
        results = filtered_results
    
    # Format the response
    response = {
        "query": search_query,
        "total_matches": len(results),
        "documents": []
    }
    
    # Format each document for the response
    for doc in results:
        # Use Google Doc ID (from 'id' or 'document_id' field), not MongoDB's _id
        document_id = doc.get("id") or doc.get("document_id") or str(doc.get("_id", ""))
        
        # Decompress content if needed
        content = doc.get("content", "")
        if not content and doc.get("content_compressed"):
            content = decompress_text(doc.get("content_compressed", {}))
        
        response["documents"].append({
            "id": document_id,
            "title": doc.get("title", "No Title"),
            "owner": doc.get("owner", "Unknown"),
            "created": doc.get("created", "Unknown Date"),
            "modified": doc.get("modified", "Unknown Date"),
            "content": content,
            "content_length": doc.get("content_length", 0),
            "link": doc.get("link", ""),
            "collaborators": doc.get("collaborators", []),
            "keywords": doc.get("keywords", []),
            "topic": doc.get("topic", ""),
        })
    
    return response


def mongo_query_docs(
    query: Optional[str] = None,
    max_results: int = 10,
    token: Optional[str] = None,
    owner: Optional[str] = None,
    start_date: Optional[str] = None,  # YYYY-MM-DD
    end_date: Optional[str] = None,    # YYYY-MM-DD
    limit: Optional[int] = None,
    image_analysis: Optional[bool] = False,  # currently only affects metadata, not bytes
) -> Dict[str, Any]:
    """
    Unified Google Docs search in MongoDB.
    - Accepts a raw text `query` for context search and optional structured filters: `owner`, `start_date`, `end_date`.
    - Applies structured filters first (via Mongo filter). If `query` has text after cleanup, runs $text within the filtered set,
      then vector-re-ranks those results. Otherwise returns the filtered results only. If no filters exist, falls back to
      `combined_search` using the text query.
    - `limit` overrides `max_results` when provided.
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Google Docs credentials") if isinstance(result, dict) else "Failed to retrieve Google Docs credentials"
        raise PermissionError(f"Google Docs access denied: {error_msg}")
    
    effective_limit = int(limit) if isinstance(limit, int) and limit > 0 else int(max_results)
    collection = get_collection(token)
    conditions = []
    # Owner filter
    if owner:
        conditions.append({"owner": {"$regex": owner, "$options": "i"}})
    # Date filters map to `created` ISO timestamps
    date_filter: Dict[str, Any] = {}
    if start_date:
        try:
            after_dt = datetime.strptime(start_date, "%Y-%m-%d")
            date_filter["$gte"] = after_dt.isoformat() + "Z"
        except ValueError:
            print(f"Invalid start_date format: {start_date}")
    if end_date:
        try:
            before_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999000)
            date_filter["$lte"] = before_dt.isoformat() + "Z"
        except ValueError:
            print(f"Invalid end_date format: {end_date}")
    if date_filter:
        conditions.append({"created": date_filter})
    # Build the base filter
    mongo_filter: Dict[str, Any] = {}
    if conditions:
        mongo_filter["$and"] = conditions
    text_query = (query or "").strip()
    results: List[Dict[str, Any]] = []
    if mongo_filter:
        base_cursor = collection.find(mongo_filter).sort("modified", -1)
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
            # Vector rerank on the FTS docs using the text_query
            vector_reranked = vector_search_on_results(
                text_query,
                fts_docs,
                min_similarity=0.15,
                percentile_threshold=0.7,
                token=token,
            )
            results = vector_reranked[:effective_limit]
        else:
            # No text to search; return filtered docs only
            results = base_docs[:effective_limit]
    else:
        # No filters → fallback to combined search on text
        if text_query:
            results, _ = combined_search(text_query, top_n=effective_limit, token=token)
        else:
            # No filters and no text → return latest documents
            results = list(collection.find({}).sort("modified", -1).limit(effective_limit))
    
    # Format the response
    response = {
        "query": query,
        "total_matches": len(results),
        "documents": []
    }
    
    # Format each document for the response
    for doc in results:
        # Use Google Doc ID (from 'id' or 'document_id' field), not MongoDB's _id
        document_id = doc.get("id") or doc.get("document_id") or str(doc.get("_id", ""))
        
        # Decompress content if needed
        content = doc.get("content", "")
        if not content and doc.get("content_compressed"):
            content = decompress_text(doc.get("content_compressed", {}))

        clean_content, has_images, image_count = strip_imageurl_placeholders(content)
        
        response["documents"].append({
            "id": document_id,
            "title": doc.get("title", "No Title"),
            "owner": doc.get("owner", "Unknown"),
            "created": doc.get("created", "Unknown Date"),
            "modified": doc.get("modified", "Unknown Date"),
            "content": clean_content,
            "content_length": doc.get("content_length", 0),
            "link": doc.get("link", ""),
            "collaborators": doc.get("collaborators", []),
            "keywords": doc.get("keywords", []),
            "topic": doc.get("topic", ""),
        })
    
    return response


def mongo_get_docs(
    document_ids: Optional[List[str]] = None,
    token: Optional[str] = None,
    image_analysis: Optional[bool] = False,
    get_formatting: Optional[bool] = False,
    document_id: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
) -> Dict[str, Any]:
    """
    Hybrid Google Docs reader:
    - get_formatting=False → Mongo text
    - get_formatting=True  → Google API structured text
    - image_analysis=True  → attach images (single unified block)

    When document_ids is omitted (None), a single document_id (str or list) from
    tool calls is accepted and normalized to document_ids.
    An explicit empty list [] does not fall back to document_id.
    """
    if document_ids is None:
        document_ids = []
        if document_id is not None:
            raw = document_id
            if isinstance(raw, (list, tuple)):
                document_ids = [
                    str(x).strip() for x in raw if x is not None and str(x).strip()
                ]
            elif str(raw).strip():
                document_ids = [str(raw).strip()]
    else:
        document_ids = [
            str(x).strip() for x in document_ids if x is not None and str(x).strip()
        ]

    response = {
        "status": "success",
        "retrieved_documents_count": 0,
        "documents": [],
        "errors": [],
    }

    # =========================================================
    # 🔹 PHASE 1 — BUILD TEXT CONTENT
    # =========================================================
    if get_formatting:
        # --- Validate Google credentials ---
        result, status = get_user_tool_access_token(token, "Gsuite")
        if status != 200 or not isinstance(result, dict) or "access_token" not in result:
            error_msg = (
                result.get("error", "Failed to retrieve Google Docs credentials")
                if isinstance(result, dict)
                else "Failed to retrieve Google Docs credentials"
            )
            raise PermissionError(f"Google Docs access denied: {error_msg}")
        
        # --- Google Docs API branch ---
        _, docs_service = get_gdocs_service(token)

        for document_id in document_ids:
            try:
                doc = docs_service.documents().get(
                    documentId=document_id
                ).execute()

                content = doc.get("body", {}).get("content", [])
                paragraphs = []
                image_positions = []
                tables = []

                for element in content:
                    # ---------- TABLE SUMMARY DETECTION ----------
                    table = element.get("table")
                    if table:

                        table_start_index = element.get("startIndex")

                        rows = table.get("tableRows", [])
                        rows_count = len(rows)

                        columns_count = 0
                        if rows:
                            columns_count = len(rows[0].get("tableCells", []))

                        tables.append({
                            "table_start_index": table_start_index,
                            "rows": rows_count,
                            "columns": columns_count,
                        })

                        continue
                    # --- Detect inline images ---
                    if "inlineObjectElement" in element:
                        image_positions.append({
                            "imageId": element["inlineObjectElement"].get("inlineObjectId"),
                            "startIndex": element.get("startIndex"),
                            "endIndex": element.get("endIndex"),
                        })
                        continue
                        
                    paragraph = element.get("paragraph")
                    if not paragraph:
                        continue

                    start_index = element.get("startIndex")
                    end_index = element.get("endIndex")

                    paragraph_text = ""
                    paragraph_named_style = paragraph.get("paragraphStyle", {}).get("namedStyleType")
                    paragraph_style = None

                    # ⭐ QUOTE DETECTION
                    ps = paragraph.get("paragraphStyle", {})

                    quote_flag = False

                    border = ps.get("borderLeft")
                    indent = ps.get("indentStart")

                    if border:
                        width = border.get("width", {}).get("magnitude", 0)
                        if width and width > 0:
                            quote_flag = True

                    # optional safety
                    if indent and indent.get("magnitude", 0) >= 30:
                        quote_flag = True
                        
                    

                    for elem in paragraph.get("elements", []):
                        text_run = elem.get("textRun")
                        if "inlineObjectElement" in elem:
                            image_positions.append({
                                "imageId": elem["inlineObjectElement"].get("inlineObjectId"),
                                "startIndex": elem.get("startIndex"),
                                "endIndex": elem.get("endIndex"),
                            })
                            continue
                        if not text_run:
                            continue

                        
                        paragraph_text += text_run.get("content", "")

                        # Extract minimal style from first textRun
                        if paragraph_style is None:
                            style = text_run.get("textStyle", {})
                            

                            style_data = {}

                            if "bold" in style:
                                style_data["bold"] = style["bold"]

                            if "italic" in style:
                                style_data["italic"] = style["italic"]

                            if "underline" in style:
                                style_data["underline"] = style["underline"]

                            if "fontSize" in style:
                                style_data["fontSize"] = style["fontSize"]["magnitude"]

                            if "foregroundColor" in style and "color" in style["foregroundColor"]:
                                style_data["color"] = style["foregroundColor"]["color"].get("rgbColor")

                            if "weightedFontFamily" in style:
                                style_data["fontFamily"] = style["weightedFontFamily"]["fontFamily"]
                            
                            if "backgroundColor" in style and "color" in style["backgroundColor"]:
                                style_data["highlight"] = style["backgroundColor"]["color"].get("rgbColor")

                            if style_data:
                                paragraph_style = style_data
                                break

                    # Decide which style to keep
                    # Decide paragraph formatting (compositional)
                    final_style = None
                    paragraph_fmt = {}
                    
                    bullet_info = paragraph.get("bullet")

                    if quote_flag:
                        paragraph_fmt["quote"] = True

                    if bullet_info:
                        paragraph_fmt["bullet"] = True

                    if paragraph_named_style and paragraph_named_style not in ["NORMAL_TEXT", "PARAGRAPH"]:
                        paragraph_fmt["namedStyleType"] = paragraph_named_style

                    if paragraph_fmt:
                        final_style = {"paragraph": paragraph_fmt}

                    elif paragraph_style:
                        final_style = {"text": paragraph_style}
                    clean_text = paragraph_text.strip()

                    if not clean_text:
                        continue
                    paragraph_payload = {
                        "text": clean_text,
                        "startIndex": start_index,
                        "endIndex": end_index,
                    }

                    if final_style:
                        paragraph_payload["formatting"] = final_style

                    paragraphs.append(paragraph_payload)

                doc_payload = {
                    "id": document_id,
                    "paragraphs": paragraphs,
                }
                if tables:
                    doc_payload["tables"] = tables

                if image_positions:
                    doc_payload["image_positions"] = image_positions

                response["documents"].append(doc_payload)

            except Exception as e:
                response["errors"].append({
                    "document_id": document_id,
                    "error": str(e)
                })

    else:
        # --- Mongo branch ---
        collection = get_collection(token)

        results = list(collection.find({
            "$or": [
                {"id": {"$in": document_ids}},
                {"document_id": {"$in": document_ids}}
            ]
        }))

        found_ids = []

        for doc in results:
            document_id = (
                doc.get("id")
                or doc.get("document_id")
                or str(doc.get("_id", ""))
            )

            found_ids.append(document_id)

            content = doc.get("content", "")

            if not content:
                compressed_field = (
                    doc.get("content_compressed")
                    or doc.get("compressed_content")
                    or doc.get("compressed_text")
                    or doc.get("text_compressed")
                )

                if compressed_field:
                    content = decompress_text(compressed_field)

            clean_content, has_images, image_count = strip_imageurl_placeholders(content)

            doc_payload = {
                "id": document_id,
                "title": doc.get("title", "No Title"),
                "owner": doc.get("owner", "Unknown"),
                "created": doc.get("created", "Unknown Date"),
                "modified": doc.get("modified", "Unknown Date"),
                "content": clean_content,
                "content_length": doc.get("content_length", 0),
                "link": doc.get("link", ""),
                "collaborators": doc.get("collaborators", []),
                "keywords": doc.get("keywords", []),
                "topic": doc.get("topic", ""),
                "has_images": has_images,
                "image_count": image_count,
            }

            response["documents"].append(doc_payload)

        # Add not-found errors
        for doc_id in document_ids:
            if doc_id not in found_ids:
                response["errors"].append({
                    "document_id": doc_id,
                    "error": "Document not found"
                })

    # =========================================================
    # 🔹 PHASE 2 — IMAGE ANALYSIS (Unified Block)
    # =========================================================

    if image_analysis and response["documents"]:
        collection = get_collection(token)

        for doc_payload in response["documents"]:
            document_id = doc_payload["id"]

            mongo_doc = collection.find_one({
                "$or": [
                    {"id": document_id},
                    {"document_id": document_id}
                ]
            })

            if not mongo_doc or not mongo_doc.get("has_images"):
                continue

            try:
                from services.docs_mcp import gdocs_get_document_content_with_images

                img_result = gdocs_get_document_content_with_images(document_id, token)

                if not isinstance(img_result, dict) or img_result.get("status") == "error":
                    raise ValueError(str(img_result.get("message", "unknown error")))

                images_raw = img_result.get("images", []) or []
                images_encoded = []

                for img in images_raw:
                    b = img.get("bytes", b"")
                    if not isinstance(b, (bytes, bytearray)) or not b:
                        continue

                    media_type = img.get("content_type", "image/png")
                    data_b64 = base64.b64encode(b).decode("utf-8")

                    images_encoded.append({
                        "type": "base64",
                        "media_type": media_type,
                        "data": data_b64,
                    })

                if images_encoded:
                    doc_payload["images"] = images_encoded
                    doc_payload["has_images"] = True
                    doc_payload["image_count"] = len(images_encoded)

            except Exception as e:
                doc_payload.setdefault("image_errors", []).append(str(e))

    # =========================================================

    response["retrieved_documents_count"] = len(response["documents"])
    if not response["documents"]:
        response["status"] = "error"
        response["message"] = (
            "❌ We couldn't find that Google Doc in your synced documents. "
            "It may not be indexed yet—sync Docs from the app, or use a document that already appears in your library."
        )
        response["ui_hint"] = "open_docs_panel"

    return response

def search_docs_by_date(
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    on_date: Optional[str] = None,
    max_results: int = 50,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform a strict Mongo date-range search on documents, sorted by newest first.
    Dates use the created field and are rigidly applied.
    """
    collection = get_collection(token)
    date_range: Dict[str, Any] = {}
    try:
        if on_date:
            day = datetime.strptime(on_date, "%Y-%m-%d")
            start_iso = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
            end_iso = (day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1) - timedelta(milliseconds=1)).isoformat() + "Z"
            date_range["$gte"] = start_iso
            date_range["$lte"] = end_iso
        else:
            if after_date:
                after_dt = datetime.strptime(after_date, "%Y-%m-%d")
                date_range["$gte"] = after_dt.isoformat() + "Z"
            if before_date:
                before_dt = datetime.strptime(before_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59, microsecond=999000)
                date_range["$lte"] = before_dt.isoformat() + "Z"
    except ValueError:
        return {"query": "", "total_matches": 0, "documents": []}

    if not date_range:
        return {"query": "", "total_matches": 0, "documents": []}

    cursor = collection.find({"created": date_range}).sort("created", -1).limit(max_results)
    docs = list(cursor)

    response = {"query": "date_search", "total_matches": len(docs), "documents": []}
    for doc in docs:
        # Use Google Doc ID (from 'id' or 'document_id' field), not MongoDB's _id
        document_id = doc.get("id") or doc.get("document_id") or str(doc.get("_id", ""))

        # Decompress content if needed
        content = doc.get("content", "")
        if not content and doc.get("content_compressed"):
            content = decompress_text(doc.get("content_compressed", {}))

        clean_content, has_images, image_count = strip_imageurl_placeholders(content)

        response["documents"].append({
            "id": document_id,
            "title": doc.get("title", "No Title"),
            "owner": doc.get("owner", "Unknown"),
            "created": doc.get("created", "Unknown Date"),
            "modified": doc.get("modified", "Unknown Date"),
            "content": clean_content,
            "content_length": doc.get("content_length", 0),
            "link": doc.get("link", ""),
            "collaborators": doc.get("collaborators", []),
            "keywords": doc.get("keywords", []),
            "topic": doc.get("topic", ""),
            "has_images": has_images,
            "image_count": image_count,
        })
    return response


def list_docs(
    max_results: int = 50,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Simple function to list documents in latest order (by created date descending).
    Takes no query, just returns docs sorted by newest first.
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Google Docs credentials") if isinstance(result, dict) else "Failed to retrieve Google Docs credentials"
        raise PermissionError(f"Google Docs access denied: {error_msg}")
    
    collection = get_collection(token)
    cursor = collection.find({}).sort("created", -1).limit(max_results)
    docs = list(cursor)

    response = {"query": "list_all", "total_matches": len(docs), "documents": []}
    for doc in docs:
        # Use Google Doc ID (from 'id' or 'document_id' field), not MongoDB's _id
        document_id = doc.get("id") or doc.get("document_id") or str(doc.get("_id", ""))

        # Decompress content if needed
        content = doc.get("content", "")
        if not content and doc.get("content_compressed"):
            content = decompress_text(doc.get("content_compressed", {}))

        clean_content, has_images, image_count = strip_imageurl_placeholders(content)

        # Fallback: if we don't see image markers in stored content,
        # do a lightweight live check against Google Docs for this doc
        # to determine whether it currently has images. We do NOT fetch
        # image bytes here, only count them.
        if not has_images:
            try:
                from services.docs_mcp import gdocs_get_document_content_with_images

                live = gdocs_get_document_content_with_images(document_id, token)
                if isinstance(live, dict) and live.get("status") != "error":
                    live_images = live.get("images") or []
                    if live_images:
                        has_images = True
                        image_count = len(live_images)
            except Exception:
                # If live check fails, silently ignore and rely on stored content
                pass

        response["documents"].append({
            "id": document_id,
            "title": doc.get("title", "No Title"),
            "owner": doc.get("owner", "Unknown"),
            "created": doc.get("created", "Unknown Date"),
            "modified": doc.get("modified", "Unknown Date"),
            "content": clean_content,
            "content_length": doc.get("content_length", 0),
            "link": doc.get("link", ""),
            "collaborators": doc.get("collaborators", []),
            "keywords": doc.get("keywords", []),
            "topic": doc.get("topic", ""),
            "has_images": has_images,
            "image_count": image_count,
        })
    return response