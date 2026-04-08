import os
import gzip
import zlib
import base64
import json
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import requests

from utils.date_utils import DateParser
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_tool_access_token, get_user_id_from_token

# ---------------------------------------------------------------------------
# Initial setup – env & clients
# ---------------------------------------------------------------------------
load_dotenv()
mongo_client = get_mongo_client()

# External user/token service (same as other *_mcp modules)
BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://3.6.95.164:5000/users")


# Collections helpers

def get_docs_collection(token: Optional[str]):
    """
    Return the per-tenant Notion Docs collection for the provided token.
    Validates that user has access to Notion before returning collection.
    """
    # Validate user has access to Notion
    is_valid, error_msg, status_code = validate_user_tool_access(token, "Notion")
    if not is_valid:
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise PermissionError("Invalid or expired token")
    return mongo_client[db_name]["notion_doc"]


def get_tasks_collection(token: Optional[str]):
    """
    Return the Notion Tasks collection. Tries common names for compatibility.
    Validates that user has access to Notion before returning collection.
    """
    # Validate user has access to Notion
    is_valid, error_msg, status_code = validate_user_tool_access(token, "Notion")
    if not is_valid:
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise PermissionError("Invalid or expired token")
    db = mongo_client[db_name]
    return db["notion_task"]


# Bedrock / Titan embedding setup (optional reranking if embeddings exist)
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
    """Decompress the compressed_text field as found in Notion docs collection."""
    try:
        if not compressed_data:
            return ""
        if isinstance(compressed_data, str):
            return compressed_data
        elif isinstance(compressed_data, bytes):
            try:
                return zlib.decompress(compressed_data).decode("utf-8")
            except Exception:
                try:
                    return gzip.decompress(compressed_data).decode("utf-8")
                except Exception:
                    return compressed_data.decode("utf-8", errors="ignore")
        elif isinstance(compressed_data, dict) and "$binary" in compressed_data:
            base64_data = compressed_data["$binary"].get("base64", "")
            binary_data = base64.b64decode(base64_data)
            try:
                return zlib.decompress(binary_data).decode("utf-8")
            except Exception:
                try:
                    return gzip.decompress(binary_data).decode("utf-8")
                except Exception:
                    return binary_data.decode("utf-8", errors="ignore")
        return str(compressed_data)
    except Exception as e:
        print(f"[WARN] decompress_text failed: {e}")
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
        return embedding or []
    except Exception as e:
        print(f"[ERROR] Titan embedding failed: {e}")
        return []


def get_embedding(text: str) -> List[float]:
    return generate_titan_embedding(text)

# ---------------------------------------------------------------------------
# Notion Docs (collection: notion_doc)
# ---------------------------------------------------------------------------

def free_text_search_docs(query: str, limit: int = 50, token: Optional[str] = None) -> List[Dict[str, Any]]:
    print(f"🔍 Notion Docs FTS: '{query}'")
    try:
        col = get_docs_collection(token)
        return list(
            col.find({"$text": {"$search": query}}, {"score": {"$meta": "textScore"}})
              .sort([("score", {"$meta": "textScore"})])
              .limit(limit)
        )
    except Exception as e:
        print(f"Error in docs FTS: {e}")
        return []


def vector_rerank(query: str, docs: List[Dict[str, Any]], token: Optional[str] = None,
                  min_similarity: float = 0.15, percentile_threshold: float = 0.7) -> List[Dict[str, Any]]:
    try:
        if not docs:
            return []
        q_emb = get_embedding(query)
        if not q_emb:
            return docs
        # Ensure we have embeddings on docs
        col = None
        if token:
            col = get_docs_collection(token)
        missing = [d for d in docs if "embedding" not in d]
        if missing and col is not None:
            ids = [d["_id"] for d in docs]
            full = list(col.find({"_id": {"$in": ids}}))
            fmap = {str(d["_id"]): d for d in full}
            for i, d in enumerate(docs):
                fid = str(d["_id"])            
                if fid in fmap and "embedding" in fmap[fid]:
                    docs[i]["embedding"] = fmap[fid]["embedding"]
        # Score
        import numpy as np
        for d in docs:
            if "embedding" in d:
                de = d["embedding"]
                try:
                    d["similarity"] = float(np.dot(q_emb, de) / (np.linalg.norm(q_emb) * np.linalg.norm(de)))
                except Exception:
                    d["similarity"] = 0.0
            else:
                d["similarity"] = 0.0
        ranked = sorted(docs, key=lambda x: x.get("similarity", 0), reverse=True)
        filtered = [d for d in ranked if d.get("similarity", 0) >= min_similarity]
        if filtered:
            if len(filtered) > 1 and percentile_threshold < 1.0:
                mx = max(d.get("similarity", 0) for d in filtered)
                cutoff = mx * percentile_threshold
                top = [d for d in filtered if d.get("similarity", 0) >= cutoff]
                return top or filtered
            return filtered
        return ranked[:3]
    except Exception as e:
        print(f"Error in vector_rerank: {e}")
        return docs


def mongo_query_notion_docs(query: str, max_results: int = 10, token: Optional[str] = None,
                             after_date: str = None, before_date: str = None) -> Dict[str, Any]:
    """Search Notion documents stored in Mongo (collection: notion_doc)."""
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Notion")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Notion credentials") if isinstance(result, dict) else "Failed to retrieve Notion credentials"
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    # Optional date filter on last_edited_time (ISO string)
    date_filter: Dict[str, Any] = {}
    if after_date:
        try:
            dt = datetime.strptime(after_date, "%Y-%m-%d")
            date_filter["$gte"] = dt.isoformat() + "Z"
        except ValueError:
            pass
    if before_date:
        try:
            dt = datetime.strptime(before_date, "%Y-%m-%d") + timedelta(days=1)
            date_filter["$lt"] = dt.isoformat() + "Z"
        except ValueError:
            pass

    col = get_docs_collection(token)

    base_docs: List[Dict[str, Any]] = []
    if date_filter:
        base_docs = list(col.find({"last_edited_time": date_filter}).limit(max_results * 2))
    if query and query.strip():
        if date_filter:
            docs = list(col.find({"$and": [{"last_edited_time": date_filter}, {"$text": {"$search": query}}]},
                                  {"score": {"$meta": "textScore"}})
                           .sort([("score", {"$meta": "textScore"})]).limit(max_results * 3))
        else:
            docs = free_text_search_docs(query, limit=max_results * 3, token=token)
        results = vector_rerank(query, docs, token=token)
    else:
        # No text query → return latest edited
        if not base_docs:
            base_docs = list(col.find({}).sort("last_edited_time", -1).limit(max_results))
        results = base_docs[:max_results]

    def doc_entry(d: Dict[str, Any]) -> Dict[str, Any]:
        content = ""
        if not content and d.get("compressed_text"):
            content = decompress_text(d.get("compressed_text"))
        return {
            "document_id": str(d.get("_id", "")),
            "page_id": d.get("page_id", ""),
            "title": d.get("title", "No Title"),
            "url": d.get("url", ""),
            "last_edited_time": d.get("last_edited_time", ""),
            "last_edited_by_name": d.get("last_edited_by_name", ""),
            "last_edited_by_email": d.get("last_edited_by_email", ""),
            "content": content,
        }

    return {
        "query": query or "",
        "total_matches": len(results),
        "documents": [doc_entry(d) for d in results[:max_results]],
    }


def mongo_get_notion_docs(document_ids: List[str], token: Optional[str] = None) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Notion")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Notion credentials") if isinstance(result, dict) else "Failed to retrieve Notion credentials"
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    object_ids = []
    for did in document_ids:
        try:
            object_ids.append(ObjectId(did))
        except Exception:
            pass
    col = get_docs_collection(token)
    results = list(col.find({"_id": {"$in": object_ids}}))

    items = []
    for d in results:
        content = ""
        if d.get("compressed_text"):
            content = decompress_text(d.get("compressed_text"))
        items.append({
            "document_id": str(d.get("_id", "")),
            "page_id": d.get("page_id", ""),
            "title": d.get("title", "No Title"),
            "url": d.get("url", ""),
            "last_edited_time": d.get("last_edited_time", ""),
            "content": content,
        })

    if not items:
        return {
            "status": "error",
            "documents": items,
            "message": (
                "❌ None of the requested Notion pages were found in your synced workspace. "
                "They may not be indexed yet—open Docs in the app to refresh Notion sync."
            ),
            "ui_hint": "open_docs_panel",
        }
    return {"status": "success", "documents": items}


# Convenience: list latest notion docs

def mongo_list_notion_docs(max_results: int = 20, token: Optional[str] = None) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Notion")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Notion credentials") if isinstance(result, dict) else "Failed to retrieve Notion credentials"
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    col = get_docs_collection(token)
    docs = list(col.find({}).sort("last_edited_time", -1).limit(max_results))
    return {
        "total": len(docs),
        "documents": [
            {
                "document_id": str(d.get("_id", "")),
                "page_id": d.get("page_id", ""),
                "title": d.get("title", "No Title"),
                "url": d.get("url", ""),
                "last_edited_time": d.get("last_edited_time", ""),
            }
            for d in docs
        ],
    }


# ---------------------------------------------------------------------------
# Notion Tasks (collection: notion_tasks / notion_task)
# ---------------------------------------------------------------------------

def free_text_search_tasks(query: str, limit: int = 50, token: Optional[str] = None, 
                         additional_filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
    """
    Perform free text search on Notion tasks with optional additional filters.
    """
    print(f"🔍 Notion Tasks FTS: '{query}'")
    try:
        col = get_tasks_collection(token)
        
        # Build the base query
        query_parts = [{"$text": {"$search": query}}]
        if additional_filters:
            query_parts.append(additional_filters)
            
        # Combine all conditions with $and
        query_filter = {"$and": query_parts} if len(query_parts) > 1 else query_parts[0]
        
        return list(
            col.find(query_filter, {"score": {"$meta": "textScore"}})
              .sort([("score", {"$meta": "textScore"})])
              .limit(limit)
        )
    except Exception as e:
        print(f"Error in tasks FTS: {e}")
        return []


def vector_rerank_tasks(query: str, tasks: List[Dict[str, Any]], token: Optional[str] = None,
                      min_similarity: float = 0.15, percentile_threshold: float = 0.7) -> List[Dict[str, Any]]:
    """
    Rerank tasks using vector similarity with the query.
    """
    if not tasks or not query.strip():
        return tasks
        
    try:
        # Generate query embedding
        q_emb = get_embedding(query.lower())
        if not q_emb:
            return tasks
            
        # Calculate similarity for each task
        import numpy as np
        for task in tasks:
            # Use task's embedding if available, otherwise generate from title + description
            if "embedding" in task:
                task_emb = task["embedding"]
            else:
                task_text = f"{task.get('title', '')} {task.get('description', '')}"
                task_emb = get_embedding(task_text.lower())
                if not task_emb:
                    task["similarity"] = 0.0
                    continue
                    
            try:
                # Calculate cosine similarity
                task["similarity"] = float(np.dot(q_emb, task_emb) / 
                                         (np.linalg.norm(q_emb) * np.linalg.norm(task_emb)))
            except Exception:
                task["similarity"] = 0.0
                
        # Filter and sort by similarity
        tasks = [t for t in tasks if t.get("similarity", 0) >= min_similarity]
        tasks.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        
        # Apply percentile threshold if we have enough results
        if len(tasks) > 1 and percentile_threshold < 1.0:
            max_sim = max(t.get("similarity", 0) for t in tasks)
            min_sim = max_sim * percentile_threshold
            tasks = [t for t in tasks if t.get("similarity", 0) >= min_sim]
            
        return tasks
        
    except Exception as e:
        print(f"Error in vector reranking: {e}")
        return tasks

def mongo_query_notion_tasks(
    query: str = None,
    max_results: int = 10,
    token: Optional[str] = None,
    status: str = None,
    priority: str = None,
    assignee_email: str = None,
    due_after: str = None,
    due_before: str = None,
) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Notion")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Notion credentials") if isinstance(result, dict) else "Failed to retrieve Notion credentials"
        raise PermissionError(f"Notion access denied: {error_msg}")
    """
    Search Notion tasks with a unified search pipeline:
    1. Apply exact filters (status, priority, assignee, date range)
    2. Perform free text search on remaining tasks
    3. Rerank results using vector similarity
    """
    col = get_tasks_collection(token)
    
    # Build base filters
    filters: Dict[str, Any] = {}
    if status:
        filters["status_lower"] = status.lower()
    if priority:
        filters["priority_lower"] = priority.lower()
    if assignee_email:
        filters["assignee.person.email"] = assignee_email.lower()
        
    # Handle date range
    date_filter = {}
    if due_after:
        try:
            date_filter["$gte"] = due_after  # Already in YYYY-MM-DD format
        except ValueError:
            pass
    if due_before:
        try:
            date_filter["$lte"] = due_before  # Already in YYYY-MM-DD format
        except ValueError:
            pass
    if date_filter:
        filters["due_date"] = date_filter
    
    # If no query, just return filtered results
    if not query or not query.strip():
        results = list(col.find(filters)
                      .sort("last_modified", -1)
                      .limit(max_results))
    else:
        # 1. First do free text search with filters
        fts_results = free_text_search_tasks(
            query, 
            limit=max_results * 5,  # Get more results for reranking
            token=token,
            additional_filters=filters if filters else None
        )
        
        # 2. Rerank using vector similarity
        results = vector_rerank_tasks(
            query,
            fts_results,
            token=token,
            min_similarity=0.15,
            percentile_threshold=0.7
        )[:max_results]  # Take top N after reranking
    
    def format_task(t: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task_id": str(t.get("_id", "")) or t.get("id", ""),
            "id": t.get("id", ""),
            "title": t.get("title", "No Title"),
            "url": t.get("url", ""),
            "stage": t.get("stage", ""),
            "type": t.get("type", []),
            "priority": t.get("priority", ""),
            "due_date": t.get("due_date", ""),
            "status": t.get("status", ""),
            "assignee": t.get("assignee", []),
            "related_to": t.get("related_to", ""),
            "database_id": t.get("database_id", ""),
            "last_modified": t.get("last_modified", ""),
            "author": t.get("author", ""),
            "comment_count": t.get("comment_count", 0),
            "latest_comment_time": t.get("latest_comment_time"),
            "similarity": t.get("similarity", 0.0)  # Include similarity score
        }

    return {
        "query": query or "",
        "filters": {
            "status": status,
            "priority": priority,
            "assignee_email": assignee_email,
            "due_after": due_after,
            "due_before": due_before
        },
        "total_matches": len(results),
        "tasks": [format_task(t) for t in results],
    }


def mongo_get_notion_tasks(task_ids: List[str], token: Optional[str] = None) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Notion")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Notion credentials") if isinstance(result, dict) else "Failed to retrieve Notion credentials"
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    object_ids = []
    for tid in task_ids:
        try:
            object_ids.append(ObjectId(tid))
        except Exception:
            pass
    col = get_tasks_collection(token)
    results = list(col.find({"_id": {"$in": object_ids}}))

    items = []
    for t in results:
        items.append({
            "task_id": str(t.get("_id", "")) or t.get("id", ""),
            "id": t.get("id", ""),
            "title": t.get("title", "No Title"),
            "url": t.get("url", ""),
            "stage": t.get("stage", ""),
            "type": t.get("type", []),
            "priority": t.get("priority", ""),
            "due_date": t.get("due_date", ""),
            "status": t.get("status", ""),
            "assignee": t.get("assignee", []),
            "related_to": t.get("related_to", ""),
            "database_id": t.get("database_id", ""),
            "last_modified": t.get("last_modified", ""),
            "author": t.get("author", ""),
        })

    if not items:
        return {
            "status": "error",
            "tasks": items,
            "message": (
                "❌ None of the requested Notion tasks were found in your synced tasks. "
                "They may not be indexed yet—open Tasks in the app to refresh sync."
            ),
            "ui_hint": "open_trello_panel",
        }
    return {"status": "success", "tasks": items}


# Convenience: list latest tasks

def mongo_list_notion_tasks(max_results: int = 20, token: Optional[str] = None) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Notion")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Notion credentials") if isinstance(result, dict) else "Failed to retrieve Notion credentials"
        raise PermissionError(f"Notion access denied: {error_msg}")
    
    col = get_tasks_collection(token)
    tasks = list(col.find({}).sort("last_modified", -1).limit(max_results))
    return {
        "total": len(tasks),
        "tasks": [
            {
                "task_id": str(t.get("_id", "")) or t.get("id", ""),
                "id": t.get("id", ""),
                "title": t.get("title", "No Title"),
                "url": t.get("url", ""),
                "status": t.get("status", ""),
                "priority": t.get("priority", ""),
                "due_date": t.get("due_date", ""),
                "last_modified": t.get("last_modified", ""),
            }
            for t in tasks
        ],
    }
