import os
import re
import json
import zlib
import gzip
import base64
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv
from pandas import date_range
from pymongo import MongoClient
from bson import ObjectId
import calendar
from datetime import datetime, timedelta, timezone
import requests
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_tool_access_token, get_user_id_from_token
from app.switches import USE_USER_TIMEZONE_FOR_EMAIL_DATE_FILTER
from zoneinfo import ZoneInfo

from utils.date_utils import DateParser

# ---------------------------------------------------------------------------
# Initial setup – env & clients
# ---------------------------------------------------------------------------
# load_dotenv()
# Prefer env var, fallback to previous direct connection string

# mongo_client =MongoClient("mongo_uri")

# External user/token service (same as other *_mcp modules)
# BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://3.6.95.164:5000/users")

mongo_client = get_mongo_client()


def _get_user_timezone_from_mongo(unified_token: Optional[str]) -> str:
    """
    Resolve the user's timezone (IANA string) from unified_workspace.users.timezone.
    Falls back to UTC when unavailable.
    """
    try:
        if not unified_token:
            return "UTC"
        user_id, status = get_user_id_from_token(unified_token)
        if status != 200 or not user_id:
            return "UTC"
        user_doc = mongo_client["unified_workspace"]["users"].find_one(
            {"user_id": user_id},
            {"timezone": 1},
        )
        tz = (user_doc or {}).get("timezone")
        return tz or "UTC"
    except Exception:
        return "UTC"


# def get_tool_token(unified_token: str, tool_name: str = "MongoDB") -> Dict[str, Any]:
#     """Retrieve tool-scoped token/details to resolve user/tenant from a unified token."""
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
#     """
#     Map the unified token to a MongoDB database name (tenant id). Falls back to default_db.
#     Tries common keys from the token service response.
#     """
#     if not token:
#         return default_db
#     data = get_tool_token(token, tool_name="MongoDB") or {}
#     # Try direct keys first
#     for key in ("user_id", "db_id", "tenant_id", "mongo_db", "org_id"):
#         val = data.get(key)
#         if isinstance(val, (str, int)) and str(val).strip():
#             return str(val)
#     # Sometimes details are nested under access_token
#     access = data.get("access_token", {}) if isinstance(data, dict) else {}
#     for key in ("user_id", "db_id", "tenant_id", "mongo_db", "org_id"):
#         val = access.get(key)
#         if isinstance(val, (str, int)) and str(val).strip():
#             return str(val)
#     return default_db


def get_collection(token: Optional[str]) -> Any:
    """
    Return the per-tenant Gmail collection for the provided token.
    Validates that user has access to Gsuite/Gmail before returning collection.
    """
    # Validate user has access to Gmail/Gsuite
    is_valid, error_msg, status_code = validate_user_tool_access(token, "Gsuite")
    if not is_valid:
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    db_name, status = get_user_id_from_token(token)
    if status != 200 or not db_name:
        raise PermissionError("Invalid or expired token")
    print(f"[DEBUG] Resolved user_id from token: {db_name}")
    return mongo_client[db_name]["gmail"]


# Bedrock / Titan embedding setup
load_dotenv()
REGION = os.getenv("AWS_REGION", "us-east-1")
TITAN_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
# Bearer token for Bedrock authentication (replaces IAM credentials)
AWS_BEARER_TOKEN_BEDROCK = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")

# Initialize date parser
date_parser = DateParser()

# ---------------------------------------------------------------------------
# Attachment shaping for tool / LLM responses (Mongo stores binary previews)
# ---------------------------------------------------------------------------

_MAX_PDF_TEXT_FOR_TOOLS = 4000


def _mongo_binary_to_bytes(raw: Any) -> Optional[bytes]:
    """Decode BSON Binary, raw bytes, or extended JSON {$binary:{base64}}."""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray, memoryview)):
        return bytes(raw)
    try:
        from bson.binary import Binary

        if isinstance(raw, Binary):
            return bytes(raw)
    except ImportError:
        pass
    if isinstance(raw, dict):
        inner = raw.get("$binary")
        if isinstance(inner, dict) and inner.get("base64"):
            try:
                return base64.b64decode(inner["base64"])
            except Exception:
                return None
        if raw.get("base64"):
            try:
                return base64.b64decode(raw["base64"])
            except Exception:
                return None
    return None


def _resolve_pdf_bytes(raw: bytes) -> bytes:
    """
    Stored preview may be:
    - raw PDF bytes
    - zlib-compressed PDF bytes
    - gzip-compressed PDF bytes

    In some DB payloads, `%PDF` may not be the first 4 bytes; we also scan for it.
    """
    if not raw:
        return b""

    # Raw might already contain a PDF but with a leading header/marker.
    idx = raw.find(b"%PDF")
    if idx != -1:
        return raw[idx:]

    candidates: List[bytes] = []
    try:
        z = zlib.decompress(raw)
        candidates.append(z)
    except zlib.error:
        pass

    try:
        g = gzip.decompress(raw)
        candidates.append(g)
    except OSError:
        pass

    for cand in candidates:
        idx2 = cand.find(b"%PDF")
        if idx2 != -1:
            return cand[idx2:]

    return b""


def _looks_like_text(raw: bytes, min_len: int = 200) -> bool:
    """
    Heuristic to detect whether bytes are actually text (not binary PDF).
    """
    if not raw or len(raw) < min_len:
        return False
    # Decode permissively; then judge by printable ratio.
    text = raw.decode("utf-8", errors="ignore")
    if len(text) < min_len:
        return False
    printable = sum(1 for c in text if c.isprintable() or c in ("\n", "\r", "\t"))
    return (printable / max(1, len(text))) >= 0.85


def _bytes_to_text_preview(raw: bytes, max_chars: int = _MAX_PDF_TEXT_FOR_TOOLS) -> Optional[str]:
    if not raw:
        return None
    if not _looks_like_text(raw):
        return None
    text = raw.decode("utf-8", errors="ignore").strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[:max_chars] + "\n…"
    return text


def _pdf_bytes_to_text(pdf_bytes: bytes, max_chars: int = _MAX_PDF_TEXT_FOR_TOOLS) -> str:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        text = (text or "").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…"
        return text
    except Exception as e:
        return f"[pdf text extraction failed: {e}]"


def normalize_email_attachments(
    raw_attachments: Optional[List[Any]],
    message_id: str,
    max_pdf_text: int = _MAX_PDF_TEXT_FOR_TOOLS,
) -> List[Dict[str, Any]]:
    """
    Build JSON-safe attachment rows for search/get tools: drop raw binary, add
    extracted PDF text from compressed_preview, and hints for images.
    """
    if not raw_attachments:
        return []
    out: List[Dict[str, Any]] = []
    for att in raw_attachments:
        if not isinstance(att, dict):
            continue
        name = att.get("name") or att.get("filename") or "attachment"
        mime = (att.get("type") or att.get("mimeType") or "") or ""
        aid = att.get("attachmentId") or att.get("attachment_id")
        row: Dict[str, Any] = {
            "name": name,
            "type": mime,
            "size": att.get("size"),
            "attachment_id": aid,
        }
        url = att.get("url")
        if url:
            row["url"] = url

        name_l = name.lower()
        is_pdf = mime == "application/pdf" or name_l.endswith(".pdf")
        is_image = (
            (mime.startswith("image/") if mime else False)
            or name_l.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"))
        )

        cp = att.get("compressed_preview")
        if is_pdf:
            extracted_text: Optional[str] = None

            raw_b = _mongo_binary_to_bytes(cp) if cp is not None else None
            if raw_b:
                # 1) Try to resolve to valid PDF bytes (scan for %PDF).
                pdf_bytes = _resolve_pdf_bytes(raw_b)
                if pdf_bytes:
                    extracted_text = _pdf_bytes_to_text(pdf_bytes, max_pdf_text) or None

                # 2) If not valid PDF bytes, sometimes the DB payload is
                #    compressed text rather than PDF bytes.
                if not extracted_text:
                    extracted_text = (
                        _bytes_to_text_preview(raw_b, max_chars=max_pdf_text) or None
                    )

                    # Also try decompression variants for text.
                    if not extracted_text:
                        try:
                            z = zlib.decompress(raw_b)
                            extracted_text = _bytes_to_text_preview(
                                z, max_chars=max_pdf_text
                            )
                        except zlib.error:
                            pass

                    if not extracted_text:
                        try:
                            g = gzip.decompress(raw_b)
                            extracted_text = _bytes_to_text_preview(
                                g, max_chars=max_pdf_text
                            )
                        except OSError:
                            pass

            if extracted_text:
                row["extracted_text_preview"] = extracted_text
            elif cp is not None:
                row["extracted_text_preview"] = (
                    "[PDF preview present in DB but could not be decoded to text "
                    "(blob did not resolve to valid PDF bytes or text after decompress)]"
                )
        elif is_image:
            row["kind"] = "image"
            row["note"] = (
                "Image attachment: use `download_attachments` with this email "
                f"`message_id` ({message_id!r}) to fetch bytes via Gmail, or open `url` in the app when logged in."
            )

        out.append(row)
    return out


def _query_looks_like_attachment_filename(q: str) -> bool:
    """Heuristic: user searching for e.g. report.pdf or photo.jpg."""
    q = (q or "").strip().lower()
    if "." not in q:
        return False
    return bool(re.search(r"\.(pdf|jpe?g|png|gif|webp|bmp|docx?|xlsx?)$", q, re.I))


def _doc_matches_attachment_name(doc: Dict[str, Any], q: str) -> bool:
    q = (q or "").strip().lower()
    if not q:
        return False
    for att in doc.get("attachments") or []:
        if not isinstance(att, dict):
            continue
        name = (att.get("name") or "").lower()
        if not name:
            continue
        if q == name or q in name or name.endswith(q):
            return True
    return False


# ---------------------------------------------------------------------------
# Search functions
# ---------------------------------------------------------------------------


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


def free_text_search(
    query: str, limit: int = 50, token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform free text search using MongoDB's text index for the tenant resolved by token
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    print(f"🔍 Performing free text search with query: '{query}'")
    try:
        collection = get_collection(token)
        results = list(
            collection.find(
                {"$text": {"$search": query}}, {"score": {"$meta": "textScore"}}
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(limit)
        )
        print(f"   Found {len(results)} results in free text search")
        return results
    except PermissionError:
        # Re-raise PermissionError so it can be caught by error handler
        raise
    except Exception as e:
        print(f"Error in free text search: {e}")
        return []


def vector_search_on_results(
    query: str,
    free_text_results: List[Dict[str, Any]],
    min_similarity: float = 0.15,
    percentile_threshold: float = 0.7,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Perform vector search ONLY on the results from free text search
    """
    print(
        f"🧠 Performing vector search with query: '{query}' on {len(free_text_results)} free text results"
    )
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
            print(
                "   Warning: No embeddings found in results. Fetching embeddings from database..."
            )
            # Get document IDs
            doc_ids = [doc["id"] for doc in free_text_results]
            # Fetch full documents with embeddings from database (tenant-specific)
            collection = get_collection(token)
            full_docs = list(collection.find({"id": {"$in": doc_ids}}))
            # Create a mapping of document IDs to their full versions with embeddings
            doc_map = {str(doc["id"]): doc for doc in full_docs}
            # Update the results with embeddings
            for i, doc in enumerate(free_text_results):
                doc_id = str(doc["id"])
                if doc_id in doc_map and "embedding" in doc_map[doc_id]:
                    free_text_results[i]["embedding"] = doc_map[doc_id]["embedding"]
        # Calculate similarity for each document
        for doc in free_text_results:
            if "embedding" in doc:
                doc_embedding = doc["embedding"]
                # Check if dimensions match
                if len(query_embedding) != len(doc_embedding):
                    print(
                        f"   Warning: Dimension mismatch - query: {len(query_embedding)}, doc: {len(doc_embedding)} for subject: {doc.get('subject', 'Unknown')}"
                    )
                    doc["similarity"] = 0
                else:
                    # Calculate cosine similarity
                    doc["similarity"] = np.dot(query_embedding, doc_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
                    )
            else:
                print(
                    f"   Warning: No embedding found for document with subject: {doc.get('subject', 'Unknown')}"
                )
                doc["similarity"] = 0
        # Sort by similarity
        results = sorted(
            free_text_results, key=lambda x: x.get("similarity", 0), reverse=True
        )
        # Apply thresholds
        # 1. Absolute threshold - filter out documents with similarity below min_similarity
        filtered_results = [
            doc for doc in results if doc.get("similarity", 0) >= min_similarity
        ]
        if filtered_results:
            print(
                f"   After minimum similarity threshold ({min_similarity}): {len(filtered_results)} results"
            )
            # 2. Percentile threshold - keep only top percentile_threshold% of results
            if len(filtered_results) > 1 and percentile_threshold < 1.0:
                # Calculate similarity scores
                similarity_scores = [
                    doc.get("similarity", 0) for doc in filtered_results
                ]
                # Calculate percentile threshold
                if similarity_scores:
                    max_score = max(similarity_scores)
                    percentile_min_score = max_score * percentile_threshold
                    # Apply percentile threshold
                    percentile_results = [
                        doc
                        for doc in filtered_results
                        if doc.get("similarity", 0) >= percentile_min_score
                    ]
                    print(
                        f"   After percentile threshold ({percentile_threshold*100}%): {len(percentile_results)} results"
                    )
                    print(f"   Percentile cutoff score: {percentile_min_score:.4f}")
                    # If percentile filtering removed all results, fall back to absolute threshold
                    if not percentile_results:
                        print(
                            "   Warning: Percentile threshold removed all results. Using absolute threshold results."
                        )
                        return filtered_results
                    return percentile_results
            return filtered_results
        else:
            print(
                f"   Warning: All results filtered out by minimum similarity threshold ({min_similarity})"
            )
            # If all results filtered out, return top 3 from original results
            return results[:3] if results else []
        print(f"   Reranked {len(results)} results based on vector similarity")
        return results
    except Exception as e:
        print(f"Error in vector search: {e}")
        return free_text_results  # Return original results if vector search fails


def date_search(
    date_query: Dict, exclude_ids: List, limit: int = 20, token: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform date-specific search
    """
    print(f"📅 Performing date search with query: {date_query}")
    try:
        if not date_query:
            return []
        collection = get_collection(token)
        # Find documents matching the date criteria
        # Make sure to include embedding field for vector search
        results = list(
            collection.find({"id": {"$nin": exclude_ids}, **date_query}).limit(limit)
        )
        print(f"   Found {len(results)} results in date search")
        # Check if we have embeddings in the results
        has_embeddings = any("embedding" in doc for doc in results)
        if not has_embeddings:
            print(
                "   Warning: No embeddings found in date search results. Vector search may not work properly."
            )
        return results
    except Exception as e:
        print(f"Error in date search: {e}")
        return []


def build_date_query_string(date_parts: Dict) -> str:
    """
    Build a string representation of the date parts for free text search
    Format dates in "07 Jun" format to match database format
    """
    if not date_parts:
        return ""
    date_strings = []
    # Add month abbreviation if present
    if date_parts.get("month"):
        month_num = date_parts["month"]
        # Get month abbreviation (Jan, Feb, etc.)
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


def combined_search(
    query: str,
    top_n: int = 5,
    min_similarity: float = 0.15,
    percentile_threshold: float = 0.7,
    token: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict]:
    """
    Perform a combined search using all three approaches:
    1. Free text search to get initial results (TEXT PARTS ONLY, no dates)
    2. Vector search on those free text results to rerank them (TEXT PARTS ONLY)
    3. Return only the top N most relevant results
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    print(f"\n📊 Starting combined search for: '{query}'")
    # Extract date parts and clean query
    date_parts, clean_query = date_parser.extract_date_parts(query)
    date_query = date_parser.build_date_query(date_parts)
    # Track document IDs we've already found
    found_ids = []
    # Step 1: Free text search (TEXT PARTS ONLY, no dates)
    print("\n--- Step 1: Free Text Search (Text Parts Only) ---")
    # Use ONLY the clean query (text parts) for free text search
    if clean_query and clean_query.strip():
        print(f"🔤 Using text parts for free text search: '{clean_query}'")
        text_results = free_text_search(clean_query, token=token)
    else:
        # If no text parts, use a general search term
        print(f"🔤 No text parts found, using general search")
        text_results = free_text_search("email", token=token)
    if not text_results:
        print("⚠️ No results found in free text search")
        # If still no results, try vector search on everything
        print("\n--- Trying Vector Search on All Documents ---")
        vector_query = clean_query if clean_query and clean_query.strip() else "email"
        collection = get_collection(token)
        all_docs = list(collection.find({}))
        # Get embedding for the query
        query_embedding = get_embedding(vector_query)
        # Calculate similarity for each document
        for doc in all_docs:
            if "embedding" in doc:
                doc_embedding = doc["embedding"]
                # Check if dimensions match
                if len(query_embedding) != len(doc_embedding):
                    print(
                        f"   Warning: Dimension mismatch - query: {len(query_embedding)}, doc: {len(doc_embedding)} for subject: {doc.get('subject', 'Unknown')}"
                    )
                    doc["similarity"] = 0
                else:
                    # Calculate cosine similarity
                    doc["similarity"] = np.dot(query_embedding, doc_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
                    )
            else:
                doc["similarity"] = 0
        # Sort by similarity
        vector_results = sorted(
            all_docs, key=lambda x: x.get("similarity", 0), reverse=True
        )
        # Apply thresholds
        vector_results = [
            doc for doc in vector_results if doc.get("similarity", 0) >= min_similarity
        ]
        # Take top N results
        vector_results = vector_results[:top_n]
        print(
            f"\n✅ Found {len(vector_results)} results from vector search on all documents"
        )
        return vector_results, {"date_parts": date_parts, "clean_query": clean_query}
    # Step 2: Vector search on free text results (TEXT PARTS ONLY)
    print("\n--- Step 2: Vector Search on Free Text Results (Text Parts Only) ---")
    # For vector search, use ONLY the clean query (text parts, no dates)
    vector_query = clean_query if clean_query and clean_query.strip() else "relevant"
    print(f"🔤 Using text parts for vector search: '{vector_query}'")
    # Check if we need to fetch embeddings for the documents
    docs_with_embeddings = [doc for doc in text_results if "embedding" in doc]
    if not docs_with_embeddings and text_results:
        print("   Fetching embeddings for documents before vector search...")
        # Get document IDs
        doc_ids = [doc["id"] for doc in text_results]
        # Fetch full documents with embeddings from database
        collection = get_collection(token)
        full_docs = list(collection.find({"id": {"$in": doc_ids}}))
        # Create a mapping of document IDs to their full versions with embeddings
        doc_map = {str(doc["id"]): doc for doc in full_docs}
        # Update the results with embeddings
        for i, doc in enumerate(text_results):
            doc_id = str(doc["id"])
            if doc_id in doc_map and "embedding" in doc_map[doc_id]:
                text_results[i]["embedding"] = doc_map[doc_id]["embedding"]
    # Perform vector search on the free text results with thresholds
    vector_results = vector_search_on_results(
        vector_query,
        text_results,
        min_similarity=min_similarity,
        percentile_threshold=percentile_threshold,
        token=token,
    )
    # Only return the top N results after vector reranking
    final_results = vector_results[:top_n]
    print(f"\n✅ Final result count: {len(final_results)} (top {top_n} most relevant)")
    return final_results, {"date_parts": date_parts, "clean_query": clean_query}


def format_email_preview(email: Dict[str, Any]) -> str:
    """Format an email for display"""
    # Format the email for display
    subject = email.get("subject", "No subject")
    from_addr = email.get("from", "No sender")
    date = email.get("date", "No date")
    body = email.get("body", "No body")
    keywords = ", ".join(email.get("keywords", []))
    # Display score for free text search results
    score_info = f"Score: {email.get('score', 'N/A')}" if "score" in email else ""
    # Display similarity for vector search results
    similarity_info = (
        f"Similarity: {email.get('similarity', 'N/A'):.4f}"
        if "similarity" in email
        else ""
    )
    # Truncate body if it's too long
    if len(body) > 100:
        body = body[:100] + "..."
    return (
        f"Subject: {subject}\n"
        f"From: {from_addr}\n"
        f"Date: {date}\n"
        f"Keywords: {keywords}\n"
        f"Body: {body}\n"
        f"{score_info}\n{similarity_info}".strip()
    )


# ---------------------------------------------------------------------------
# API Functions for MCP Integration
# ---------------------------------------------------------------------------


def mongo_search_emails(
    from_email: Optional[str] = None,
    to_email: Optional[str] = None,
    subject: Optional[str] = None,
    has_attachment: bool = False,
    is_unread: bool = False,
    after_date: Optional[str] = None,
    before_date: Optional[str] = None,
    label: Optional[str] = None,
    max_results: int = 10,
    token: Optional[str] = None,
    get_thread: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Search emails in MongoDB based on various criteria
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    # Build the search query
    search_parts = []
    # Add query parts based on parameters
    if from_email:
        search_parts.append(f"from:{from_email}")
    if to_email:
        search_parts.append(f"to:{to_email}")
    if subject:
        search_parts.append(f"{subject}")
    if has_attachment:
        search_parts.append("has:attachment")
    if is_unread:
        search_parts.append("is:unread")
    if label:
        search_parts.append(f"label:{label}")
    # Handle date ranges
    date_query = {}
    if after_date:
        try:
            after_date_obj = datetime.strptime(after_date, "%Y-%m-%d")
            date_query["timestamp"] = {"$gte": after_date_obj}
        except ValueError:
            print(f"Invalid after_date format: {after_date}")
    if before_date:
        try:
            before_date_obj = datetime.strptime(before_date, "%Y-%m-%d")
            date_query_part = date_query.get("timestamp", {})
            date_query_part["$lte"] = before_date_obj
            date_query["timestamp"] = date_query_part
        except ValueError:
            print(f"Invalid before_date format: {before_date}")
    # Build the combined query string
    query = " ".join(search_parts)
    # If no specific query parts but we have date filters, use a general query
    if not query and date_query:
        query = "emails"
    # If we still have no query, return empty results
    if not query:
        return {"query": "", "total_matches": 0, "messages": []}
    # Perform combined search
    results, _ = combined_search(query, top_n=max_results, token=token)
    # Apply date filters if needed
    if date_query:
        filtered_results = []
        for doc in results:
            if "timestamp" in doc:
                doc_timestamp = doc["timestamp"]
                if isinstance(doc_timestamp, str):
                    try:
                        doc_timestamp = datetime.strptime(doc_timestamp, "%Y-%m-%d")
                    except ValueError:
                        continue
                # Check if timestamp meets the date criteria
                meets_criteria = True
                if "$gte" in date_query.get("timestamp", {}):
                    meets_criteria = (
                        meets_criteria
                        and doc_timestamp >= date_query["timestamp"]["$gte"]
                    )
                if "$lte" in date_query.get("timestamp", {}):
                    meets_criteria = (
                        meets_criteria
                        and doc_timestamp <= date_query["timestamp"]["$lte"]
                    )
                if meets_criteria:
                    filtered_results.append(doc)
            else:
                # If no timestamp, skip this document
                continue
        results = filtered_results
    # Apply unread filter if requested
    if is_unread:
        results = [doc for doc in results if not doc.get("is_read", False)]
    # Format the response
    response: Dict[str, Any] = {
        "query": query,
        "total_matches": len(results),
        "messages": [],
    }

    thread_ids = set()
    search_message_ids = set()

    # Format each email for the response
    for doc in results:
        message_id = str(doc.get("id", ""))
        search_message_ids.add(message_id)

        # Extract time information from various fields
        time_info: Dict[str, Any] = {}

        # Get timestamp (Unix timestamp in milliseconds)
        if "internalDateNum" in doc:
            timestamp_ms = doc["internalDateNum"]
            if isinstance(timestamp_ms, (int, float)):
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                time_info["timestamp"] = timestamp_dt.isoformat()
                time_info["timestamp_ms"] = timestamp_ms

        # Get date string
        if "date" in doc:
            time_info["date_string"] = doc["date"]

        # Get received time if available
        if "receivedTime" in doc:
            time_info["received_time"] = doc["receivedTime"]

        # Get sent time if available
        if "sentTime" in doc:
            time_info["sent_time"] = doc["sentTime"]

        thread_id = doc.get("thread") or ""
        if thread_id:
            thread_ids.add(thread_id)

        response["messages"].append(
            {
                "message_id": message_id,
                "from": doc.get("from", "Unknown"),
                "subject": doc.get("subject", "No Subject"),
                "date": doc.get("date", "Unknown Date"),
                "body": doc.get("body", ""),
                "time_info": time_info,
                "thread_id": thread_id,
                "attachments": normalize_email_attachments(
                    doc.get("attachments"), message_id
                ),
            }
        )

    # Optionally expand each result to include its full thread context
    if get_thread and thread_ids:
        try:
            collection = get_collection(token)
            thread_docs = list(
                collection.find({"thread": {"$in": list(thread_ids)}}).sort(
                    "internalDateNum", 1
                )
            )

            threads: Dict[str, List[Dict[str, Any]]] = {}

            for doc in thread_docs:
                t_id = doc.get("thread") or str(doc.get("id", ""))
                if not t_id:
                    continue

                msg_id = str(doc.get("id", ""))

                # Extract time information from various fields
                time_info: Dict[str, Any] = {}
                if "internalDateNum" in doc:
                    timestamp_ms = doc["internalDateNum"]
                    if isinstance(timestamp_ms, (int, float)):
                        timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                        time_info["timestamp"] = timestamp_dt.isoformat()
                        time_info["timestamp_ms"] = timestamp_ms
                if "date" in doc:
                    time_info["date_string"] = doc["date"]
                if "receivedTime" in doc:
                    time_info["received_time"] = doc["receivedTime"]
                if "sentTime" in doc:
                    time_info["sent_time"] = doc["sentTime"]

                thread_message = {
                    "message_id": msg_id,
                    "from": doc.get("from", "Unknown"),
                    "subject": doc.get("subject", "No Subject"),
                    "date": doc.get("date", "Unknown Date"),
                    "body": doc.get("body", ""),
                    "time_info": time_info,
                    "thread_id": t_id,
                    "labels": doc.get("labels", []),
                    "is_search_match": msg_id in search_message_ids,
                    "attachments": normalize_email_attachments(
                        doc.get("attachments"), msg_id
                    ),
                }

                if t_id not in threads:
                    threads[t_id] = []
                threads[t_id].append(thread_message)

            response["threads"] = threads
        except Exception as e:
            print(f"[DEBUG] Failed to expand thread context in mongo_search_emails: {e}")

    return response


def mongo_query_emails(
    max_results: int = 10,
    query: Optional[str] = None,
    token: Optional[str] = None,
    is_unread: Optional[bool] = None,
    from_email: Optional[str] = None,
    to_email: Optional[str] = None,
    start_date: Optional[str] = None,  # YYYY-MM-DD
    end_date: Optional[str] = None,  # YYYY-MM-DD
    limit: Optional[int] = None,
    get_thread: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Search emails in MongoDB using Gmail-style query syntax with proper separation of date and text.
    Behavior:
    - If a date filter is present (standalone YYYY-MM-DD or after:/before:), apply Mongo date filtering FIRST.
    - Strip date tokens from the text so only text terms are used for FTS/vector (no artifacts like '- -').
    - If text remains, run $text search restricted by the date/label filters, then vector rerank over those results.
    - If no text remains after stripping, SKIP FTS/vector and return date-filtered results only.
    - If no date/label filters exist, fall back to combined_search on the cleaned text.
    - 'unread' is treated as normal text; no special is_read handling.
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    print(f"[DEBUG] Original query: {query}")
    # Determine effective limit (prefer explicit limit over max_results for backward compatibility)
    effective_limit = int(limit) if isinstance(limit, int) and limit > 0 else int(max_results)

    # --- Structured filters from MCP arguments ---
    conditions = []

    # Unread filter
    if is_unread is True:
        conditions.append({"is_read": False})

    # From filter
    if from_email:
        conditions.append(
            {
                "$or": [
                    {"from.email": {"$regex": from_email, "$options": "i"}},
                    {"from.name": {"$regex": from_email, "$options": "i"}},
                ]
            }
        )

    # To filter
    if to_email:
        conditions.append(
            {
                "$or": [
                    {"to.email": {"$regex": to_email, "$options": "i"}},
                    {"to.name": {"$regex": to_email, "$options": "i"}},
                ]
            }
        )
    date_range = {}

    # debug print to confirm incoming args
    print(f"[DEBUG] start_date arg: {start_date}, end_date arg: {end_date}")

    if start_date:
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d")

            if USE_USER_TIMEZONE_FOR_EMAIL_DATE_FILTER:
                tz_str = _get_user_timezone_from_mongo(token)
                tz = ZoneInfo(tz_str)
            else:
                tz = timezone.utc

            start_dt = datetime(
                dt.year,
                dt.month,
                dt.day,
                0,
                0,
                0,
                0,
                tzinfo=tz,
            )
            # Convert to epoch milliseconds (Mongo stores internalDateNum in ms).
            start_ms = int(start_dt.timestamp() * 1000)
            date_range["$gte"] = start_ms
        except Exception as ex:
            print(f"[DEBUG] start_date parse error: {ex}")

    if end_date:
        try:
            dt = datetime.strptime(end_date, "%Y-%m-%d")

            if USE_USER_TIMEZONE_FOR_EMAIL_DATE_FILTER:
                tz_str = _get_user_timezone_from_mongo(token)
                tz = ZoneInfo(tz_str)
            else:
                tz = timezone.utc

            end_dt = datetime(
                dt.year,
                dt.month,
                dt.day,
                23,
                59,
                59,
                999000,
                tzinfo=tz,
            )
            end_ms = int(end_dt.timestamp() * 1000)
            date_range["$lte"] = end_ms
        except Exception as ex:
            print(f"[DEBUG] end_date parse error: {ex}")

    print(f"[DEBUG] Applied structured filters: {conditions}")

    print(f"[DEBUG] Extracted date range filter: {date_range}")
    # add date range condition
    if date_range:
        conditions.append({"internalDateNum": date_range})
        print(f"[DEBUG] Applied date filter: {date_range}")

    # ... after all filters are collected:
    mongo_filter = {}
    if conditions:
        mongo_filter["$and"] = conditions
        print(f"[DEBUG] Combined mongo_filter: {mongo_filter}")

    # 1) Parse parts
    # mongo_filter = {}
    print(f"query: {query}")
    text_query = query or ""
    # Label:LABEL_NAME
    label_match = re.search(r"\blabel:([A-Z_]+)\b", text_query, re.IGNORECASE)
    if label_match:
        label = label_match.group(1).upper()
        mongo_filter["labels"] = label
        text_query = re.sub(r"\blabel:[A-Z_]+\b", " ", text_query, flags=re.IGNORECASE)
        print(f"[DEBUG] Added label filter: {label}")
    # Support explicit date range: YYYY-MM-DD to YYYY-MM-DD
    range_match = re.search(
        r"\b(\d{4}-\d{2}-\d{2})\s*(?:to|\-|–|—)\s*(\d{4}-\d{2}-\d{2})\b",
        text_query,
        re.IGNORECASE,
    )
    # date_range = {}
    # if range_match:
    #     try:
    #         start_day = datetime.strptime(range_match.group(1), "%Y-%m-%d")
    #         end_day = datetime.strptime(range_match.group(2), "%Y-%m-%d")
    #         start_ms = int(start_day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    #         end_ms = int(
    #             end_day.replace(hour=23, minute=59, second=59, microsecond=999000).timestamp() * 1000
    #         )
    #         date_range["$gte"] = start_ms
    #         date_range["$lte"] = end_ms
    #         print(
    #             f"[DEBUG] Applied explicit range: {range_match.group(1)} to {range_match.group(2)} -> {start_ms}..{end_ms}"
    #         )
    #     except ValueError:
    #         pass
    #     # Remove the full range expression from text
    #     text_query = re.sub(
    #         r"\b\d{4}-\d{2}-\d{2}\s*(?:to|\-|–|—)\s*\d{4}-\d{2}-\d{2}\b",
    #         " ",
    #         text_query,
    #         flags=re.IGNORECASE,
    #     )
    # # after:YYYY-MM-DD and before:YYYY-MM-DD
    # after_match = re.search(r"\bafter:(\d{4}-\d{2}-\d{2})\b", text_query, re.IGNORECASE)
    # before_match = re.search(r"\bbefore:(\d{4}-\d{2}-\d{2})\b", text_query, re.IGNORECASE)
    # if after_match and "$gte" not in date_range:
    #     try:
    #         dt = datetime.strptime(after_match.group(1), "%Y-%m-%d")
    #         date_range["$gte"] = int(dt.timestamp() * 1000)
    #     except ValueError:
    #         pass
    #     text_query = re.sub(r"\bafter:\d{4}-\d{2}-\d{2}\b", " ", text_query, flags=re.IGNORECASE)
    # if before_match and "$lte" not in date_range:
    #     try:
    #         dt = datetime.strptime(before_match.group(1), "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    #         date_range["$lte"] = int(dt.timestamp() * 1000)
    #     except ValueError:
    #         pass
    #     text_query = re.sub(r"\bbefore:\d{4}-\d{2}-\d{2}\b", " ", text_query, flags=re.IGNORECASE)
    # # Standalone ISO date YYYY-MM-DD → day range (only if range not already set)
    # if "$gte" not in date_range or "$lte" not in date_range:
    #     iso_date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text_query)
    #     if iso_date_match:
    #         try:
    #             day = datetime.strptime(iso_date_match.group(1), "%Y-%m-%d")
    #             start_ms = int(
    #                 day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    #             )
    #             end_ms = int(
    #                 (
    #                     day.replace(hour=0, minute=0, second=0, microsecond=0)
    #                     + timedelta(days=1)
    #                     - timedelta(milliseconds=1)
    #                 ).timestamp()
    #                 * 1000
    #             )
    #             # Merge with existing range
    #             date_range["$gte"] = max(date_range.get("$gte", start_ms), start_ms)
    #             date_range["$lte"] = (
    #                 min(date_range.get("$lte", end_ms), end_ms) if "$lte" in date_range else end_ms
    #             )
    #         except ValueError:
    #             pass
    #         # Remove the standalone date token from text
    #         text_query = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text_query)

    print(f"[DEBUG] Combined mongo_filter before text cleaning: {mongo_filter}")
    # 2) Clean text so no date artifacts leak into FTS/vector
    # Remove common connector/stop words that may be left from ranges
    text_query = re.sub(
        r"\b(to|from|between|and|on|at|in|the|of)\b",
        " ",
        text_query,
        flags=re.IGNORECASE,
    )
    # Remove any remaining punctuation-only tokens
    text_query = re.sub(r"\s+", " ", text_query)
    # Eliminate non-word symbols except basic email/url chars
    text_query = re.sub(r"[^A-Za-z0-9@._\s]+", " ", text_query)
    text_query = re.sub(r"\s+", " ", text_query).strip()
    print(f"[DEBUG] Cleaned text query: '{text_query}'")
    print(f"[DEBUG] Mongo filter: {mongo_filter}")
    # 3) Execute according to presence of filters and text
    results = []
    collection = get_collection(token)
    if mongo_filter:
        # Date/label filtered base set
        base_cursor = collection.find(mongo_filter).sort("internalDateNum", -1)
        base_docs = list(base_cursor)
        print(f"[DEBUG] Base (date/label) docs: {len(base_docs)}")
        if text_query:
            # Run $text within the filtered set by combining filters
            query_with_text = {**mongo_filter, "$text": {"$search": text_query}}
            fts_cursor = (
                collection.find(query_with_text, {"score": {"$meta": "textScore"}})
                .sort([("score", {"$meta": "textScore"})])
                .limit(effective_limit * 3)
            )
            fts_docs = list(fts_cursor)
            print(f"[DEBUG] FTS within filter returned: {len(fts_docs)}")
            # Filename-style queries (e.g. download.jpg) rarely hit $text on body/subject; match Mongo attachment names.
            if (
                not fts_docs
                and text_query
                and _query_looks_like_attachment_filename(text_query)
            ):
                att_hits = [
                    d for d in base_docs if _doc_matches_attachment_name(d, text_query)
                ]
                if att_hits:
                    print(
                        f"[DEBUG] FTS empty; attachment filename fallback matched: {len(att_hits)}"
                    )
                    fts_docs = att_hits[: effective_limit * 3]
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
            # No text to search; return date/label-filtered docs only
            results = base_docs[:effective_limit]
            print(
                f"[DEBUG] No text after stripping; returning date-filtered docs only: {len(results)}"
            )
    else:
        # No filters → fallback to combined search on text (or general placeholder if empty)
        if text_query:
            print(f"[DEBUG] No filters; using combined_search on '{text_query}'")
            results, _ = combined_search(text_query, top_n=effective_limit, token=token)

        elif not conditions:  # <-- only fallback if no filters at all
            print(
                f"[DEBUG] No filters and no text → returning latest {effective_limit} emails"
            )
            results = list(
                collection.find({}).sort("internalDateNum", -1).limit(effective_limit)
            )
        else:
            print(f"[DEBUG] No filters and no text → empty result")
            results = []
    # 4) Format the response
    response: Dict[str, Any] = {
        "query": query,
        "total_matches": len(results),
        "messages": [],
    }

    # Track thread_ids and message_ids for optional thread expansion
    thread_ids = set()
    search_message_ids = set()

    for doc in results:
        message_id = str(doc.get("id", ""))
        search_message_ids.add(message_id)

        # Extract time information from various fields
        time_info: Dict[str, Any] = {}

        # Get timestamp (Unix timestamp in milliseconds)
        if "internalDateNum" in doc:
            timestamp_ms = doc["internalDateNum"]
            if isinstance(timestamp_ms, (int, float)):
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                time_info["timestamp"] = timestamp_dt.isoformat()
                time_info["timestamp_ms"] = timestamp_ms

        # Get date string
        if "date" in doc:
            time_info["date_string"] = doc["date"]

        # Get received time if available
        if "receivedTime" in doc:
            time_info["received_time"] = doc["receivedTime"]

        # Get sent time if available
        if "sentTime" in doc:
            time_info["sent_time"] = doc["sentTime"]

        thread_id = doc.get("thread") or ""
        if thread_id:
            thread_ids.add(thread_id)

        response["messages"].append(
            {
                "message_id": message_id,
                "from": doc.get("from", "Unknown"),
                "subject": doc.get("subject", "No Subject"),
                "date": doc.get("date", "Unknown Date"),
                "body": doc.get("body", ""),
                "time_info": time_info,
                "thread_id": thread_id,
                "attachments": normalize_email_attachments(
                    doc.get("attachments"), message_id
                ),
            }
        )

    # Optionally expand each result to include its full thread context
    if get_thread and thread_ids:
        try:
            collection = get_collection(token)
            thread_docs = list(
                collection.find({"thread": {"$in": list(thread_ids)}}).sort(
                    "internalDateNum", 1
                )
            )

            threads: Dict[str, List[Dict[str, Any]]] = {}

            for doc in thread_docs:
                t_id = doc.get("thread") or str(doc.get("id", ""))
                if not t_id:
                    continue

                msg_id = str(doc.get("id", ""))

                # Extract time information from various fields
                time_info: Dict[str, Any] = {}
                if "internalDateNum" in doc:
                    timestamp_ms = doc["internalDateNum"]
                    if isinstance(timestamp_ms, (int, float)):
                        timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                        time_info["timestamp"] = timestamp_dt.isoformat()
                        time_info["timestamp_ms"] = timestamp_ms
                if "date" in doc:
                    time_info["date_string"] = doc["date"]
                if "receivedTime" in doc:
                    time_info["received_time"] = doc["receivedTime"]
                if "sentTime" in doc:
                    time_info["sent_time"] = doc["sentTime"]

                thread_message = {
                    "message_id": msg_id,
                    "from": doc.get("from", "Unknown"),
                    "subject": doc.get("subject", "No Subject"),
                    "date": doc.get("date", "Unknown Date"),
                    "body": doc.get("body", ""),
                    "time_info": time_info,
                    "thread_id": t_id,
                    "labels": doc.get("labels", []),
                    "is_search_match": msg_id in search_message_ids,
                    "attachments": normalize_email_attachments(
                        doc.get("attachments"), msg_id
                    ),
                }

                if t_id not in threads:
                    threads[t_id] = []
                threads[t_id].append(thread_message)

            response["threads"] = threads
        except Exception as e:
            # If thread expansion fails for any reason, log and still return base results
            print(f"[DEBUG] Failed to expand thread context: {e}")

    return response


def mongo_get_emails(
    message_ids: List[str], token: Optional[str] = None
) -> Dict[str, Any]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    """
    Get emails from MongoDB by their IDs
    """
    # Query MongoDB for the emails using string IDs directly (tenant-specific)
    # The 'id' field in MongoDB stores the Gmail message ID as a string
    collection = get_collection(token)
    results = list(collection.find({"id": {"$in": message_ids}}))
    # Format the response
    response = {
        "status": "success" if results else "error",
        "retrieved_emails_count": len(results),
        "emails": [],
        "errors": [],
    }
    # Format each email for the response
    for doc in results:
        message_id = str(doc.get("id", ""))

        # Extract time information from various fields
        time_info = {}

        # Get timestamp (Unix timestamp in milliseconds)
        if "internalDateNum" in doc:
            timestamp_ms = doc["internalDateNum"]
            if isinstance(timestamp_ms, (int, float)):
                timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000)
                time_info["timestamp"] = timestamp_dt.isoformat()
                time_info["timestamp_ms"] = timestamp_ms

        # Get date string
        if "date" in doc:
            time_info["date_string"] = doc["date"]

        # Get received time if available
        if "receivedTime" in doc:
            time_info["received_time"] = doc["receivedTime"]

        # Get sent time if available
        if "sentTime" in doc:
            time_info["sent_time"] = doc["sentTime"]

        response["emails"].append(
            {
                "message_id": message_id,
                "from": doc.get("from", "Unknown"),
                "to": doc.get("to", []),
                "subject": doc.get("subject", "No Subject"),
                "date": doc.get("date", "Unknown Date"),
                "body": doc.get("body", ""),
                "labels": doc.get("labels", []),
                "attachments": normalize_email_attachments(
                    doc.get("attachments"), message_id
                ),
                "time_info": time_info,
            }
        )
    # Add errors for any IDs that weren't found
    found_ids = [str(doc.get("id", "")) for doc in results if doc.get("id")]
    for msg_id in message_ids:
        if msg_id not in found_ids:
            response["errors"].append(
                {"message_id": msg_id, "error": "Email not found"}
            )
    if not results:
        response["message"] = (
            "❌ None of the requested emails were found in your synced mail. "
            "They may not be indexed yet—open Email in the app to refresh sync."
        )
        response["ui_hint"] = "open_emails_panel"
    return response


# Find all the unread emails for the current user from MongoDB
def unread_email_search(token: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Perform unread-email search for the current user.
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    print(f" Performing unread search (limit={limit})")
    try:
        collection = get_collection(token)
        if collection is None:
            print("   Error: get_collection(token) returned None")
            return []
        print(f"Debug : Successfully obtained collection {collection}")
        # Query for unread emails, sorted newest first
        featched = (
            collection.find({"is_read": False}).sort("internalDateNum", -1).limit(limit)
        )

        results: List[Dict[str, Any]] = []
        for doc in featched:

            # # Handle 'from' field which can be a dict or a string
            # from_field = doc.get("from", {})
            # if isinstance(from_field, dict):
            #     from_value = from_field.get("gmail_id", "")
            # else:
            #     from_value = str(from_field or "")

            # # Handle 'to' field which can be a list or a single dict
            # to_field = doc.get("to", [])
            # if isinstance(to_field, list):
            #     to_value = ", ".join(
            #         item.get("gmail_id", "") if isinstance(item, dict) else str(item)
            #         for item in to_field
            #     )
            # elif isinstance(to_field, dict):
            #     to_value = to_field.get("gmail_id", "")
            # else:
            #     to_value = str(to_field or "")

            mid = str(doc.get("id", ""))
            email_data = {
                "id": mid,
                "thread_id": doc.get("thread", ""),
                "from": doc.get("from", {}).get("gmail_id", ""),
                "to": (
                    ", ".join(
                        (
                            item.get("gmail_id", "")
                            if isinstance(item, dict)
                            else str(item)
                        )
                        for item in doc.get("to", [])
                    )
                    if isinstance(doc.get("to"), list)
                    else str(doc.get("to") or "")
                ),
                "subject": doc.get("subject", ""),
                "date": doc.get("internalDateNum", ""),
                "body": (doc.get("body", "") or "")[:500],
                "snippet": doc.get("snippet", ""),
                "labels": doc.get("labels", []),
                "is_unread": True,
                "attachments": normalize_email_attachments(
                    doc.get("attachments"), mid
                ),
            }
            results.append(email_data)
        print(f"Debug: Retrieved {len(results)} unread emails")

        print(f"   Found {len(results)} results in unread search with MongoDB")
        return results

    except Exception as e:
        print(f"Error in unread search: {e}")
        return []


def starred_email_search(token: str, limit: int = 10) -> List[Dict[str, Any]]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    """
    Fetch starred emails for the current user from MongoDB.
    Search with filters on flagged=True.
    """
    print(f"⭐ Performing starred search (limit={limit})")
    collection = get_collection(token)
    if collection is None:
        raise RuntimeError("get_collection(token) returned None")

    featched = (
        collection.find({"flagged": True}).sort("internalDateNum", -1).limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for doc in featched:
        mid = str(doc.get("id", ""))
        email_data = {
            "id": mid,
            "thread_id": doc.get("thread", ""),
            "from": doc.get("from", {}).get("gmail_id", ""),
            "to": (
                ", ".join(
                    item.get("gmail_id", "") if isinstance(item, dict) else str(item)
                    for item in doc.get("to", [])
                )
                if isinstance(doc.get("to"), list)
                else str(doc.get("to") or "")
            ),
            "subject": doc.get("subject", ""),
            "date": doc.get("internalDateNum", ""),
            "body": (doc.get("body", "") or "")[:500],
            "snippet": doc.get("snippet", ""),
            "labels": doc.get("labels", []),
            "is_starred": True,
            "attachments": normalize_email_attachments(
                doc.get("attachments"), mid
            ),
        }
        results.append(email_data)

    print(f"   Found {len(results)} results in starred search")
    return results


def from_email_search(token: str, sender: str, limit: int = 10) -> List[Dict[str, Any]]:
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    """
    Fetch emails from a specific sender (like Gmail 'from:' operator).
    """
    print(f"📨 Performing from-search for sender={sender} (limit={limit})")
    collection = get_collection(token)
    if collection is None:
        raise RuntimeError("get_collection(token) returned None")

    fetched = (
        collection.find(
            {
                "$or": [
                    {"from.email": {"$regex": f"^{sender}", "$options": "i"}},
                    {"from.name": {"$regex": f"^{sender}", "$options": "i"}},
                ]
            }
        )
        .sort("internalDateNum", -1)
        .limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for doc in fetched:
        mid = str(doc.get("id", ""))
        email_data = {
            "id": mid,
            "thread_id": doc.get("thread", ""),
            "from": doc.get("from", {}).get("gmail_id", ""),
            "to": (
                ", ".join(
                    item.get("gmail_id", "") if isinstance(item, dict) else str(item)
                    for item in doc.get("to", [])
                )
                if isinstance(doc.get("to"), list)
                else str(doc.get("to") or "")
            ),
            "subject": doc.get("subject", ""),
            "date": doc.get("internalDateNum", ""),
            "body": (doc.get("body", "") or "")[:500],
            "snippet": doc.get("snippet", ""),
            "labels": doc.get("labels", []),
            "is_from_match": True,
            "attachments": normalize_email_attachments(
                doc.get("attachments"), mid
            ),
        }
        results.append(email_data)

    print(f"   Found {len(results)} results in from-search")
    return results


def to_email_search(
    token: str, recipient: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Fetch emails sent to a specific recipient (like Gmail 'to:' operator).
    Matches on both 'to.email' and 'to.name' fields in the array of recipients.
    """
    # Check credentials first before any MongoDB access - actually try to get the token
    result, status = get_user_tool_access_token(token, "Gsuite")
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Gmail credentials") if isinstance(result, dict) else "Failed to retrieve Gmail credentials"
        raise PermissionError(f"Gmail access denied: {error_msg}")
    
    print(f"📨 Performing to-email-search for recipient={recipient} (limit={limit})")
    collection = get_collection(token)
    if collection is None:
        raise RuntimeError("get_collection(token) returned None")

    fetched = (
        collection.find(
            {
                "$or": [
                    {"to.email": {"$regex": f"^{recipient}", "$options": "i"}},
                    {"to.name": {"$regex": f"^{recipient}", "$options": "i"}},
                ]
            }
        )
        .sort("internalDateNum", -1)
        .limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for doc in fetched:
        mid = str(doc.get("id", ""))
        email_data = {
            "id": mid,
            "thread_id": doc.get("thread", ""),
            "from": doc.get("from", {}).get("email", ""),
            "to": (
                ", ".join(
                    item.get("email", "") if isinstance(item, dict) else str(item)
                    for item in doc.get("to", [])
                )
                if isinstance(doc.get("to"), list)
                else str(doc.get("to") or "")
            ),
            "subject": doc.get("subject", ""),
            "date": doc.get("internalDateNum", ""),
            "body": (doc.get("body", "") or "")[:500],
            "snippet": doc.get("snippet", ""),
            "labels": doc.get("labels", []),
            "is_to_match": True,
            "attachments": normalize_email_attachments(
                doc.get("attachments"), mid
            ),
        }
        results.append(email_data)

    print(f"   Found {len(results)} results in to-search")
    return results
