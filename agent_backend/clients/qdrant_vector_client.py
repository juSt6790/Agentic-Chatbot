"""
Qdrant Vector Search Client
Performs semantic vector search across different tool context collections using Qdrant.
Allows AI to search for related content based on keywords from user queries.
"""

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import SearchParams
from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_id_from_token
import numpy as np

load_dotenv()

# ---------------------------------------------------------------------------
# Initial setup
# ---------------------------------------------------------------------------
mongo_client = get_mongo_client()
QDRANT_URL = os.getenv("QDRANT_URL")
qdrant = QdrantClient(url=QDRANT_URL) if QDRANT_URL else None
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

# Similarity threshold (default 0.30, can be overridden via env)
SIMILARITY_THRESHOLD = float(os.getenv("VECTOR_THRESHOLD", "0.30"))

# Tool to collection suffix mapping
TOOL_COLLECTION_MAP = {
    "gmail": "gmail",
    "slack": "slack",
    "calendar": "calendar",
    "docs": "gdocs",  # Google Docs
    "gdocs": "gdocs",  # Alias for Google Docs
    "sheets": "gsheets",  # Google Sheets
    "gsheets": "gsheets",  # Alias
    "slides": "gslides",  # Google Slides
    "gslides": "gslides",  # Alias
    "trello": "trello",
    "notion": "notiondocs",  # Notion
    "notiondocs": "notiondocs",  # Alias
}

# Tool name mapping for validation
TOOL_VALIDATION_MAP = {
    "gmail": "Gsuite",
    "slack": "Slack",
    "calendar": "Gsuite",
    "docs": "Gsuite",
    "gdocs": "Gsuite",
    "sheets": "Gsuite",
    "gsheets": "Gsuite",
    "slides": "Gsuite",
    "gslides": "Gsuite",
    "trello": "Trello",
    "notion": "Notion",
    "notiondocs": "Notion",
}


def normalize(v: List[float]) -> List[float]:
    """
    Normalize a vector to unit length.
    """
    v = np.array(v, dtype=float)
    n = np.linalg.norm(v)
    return (v / n).tolist() if n != 0 else v.tolist()


def generate_openai_embedding(text: str) -> List[float]:
    """
    Generate embedding vector using OpenAI text-embedding-3-small model.
    
    Args:
        text: Text to generate embedding for
        
    Returns:
        Normalized embedding vector (1536 dimensions)
    """
    if not openai_client:
        print("[ERROR] OpenAI client not initialized. Check OPENAI_API_KEY environment variable.")
        return []
    
    try:
        resp = openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        embedding = resp.data[0].embedding
        return normalize(embedding)
    except Exception as e:
        print(f"[ERROR] Failed to generate embedding: {e}")
        return []


def vector_context_search(
    keywords: str,
    tool: Optional[str] = None,
    token: Optional[str] = None,
    limit: int = 10,
    min_similarity: Optional[float] = None
) -> Dict[str, Any]:
    """
    Perform semantic vector search across ALL tool context collections.
    
    This function takes keywords from the user's query and searches for semantically
    similar content across ALL available tool context collections using vector embeddings.
    This allows finding related content across the entire workspace (Gmail, Slack, Calendar,
    Docs, Sheets, Slides, Trello, Notion) in a single search.
    
    Args:
        keywords: Search query/keywords from user prompt
        tool: Optional tool name to prioritize or filter (if provided, still searches all but may prioritize this tool)
        token: User's unified token
        limit: Maximum number of results to return per tool (default: 10). Total results may be higher.
        min_similarity: Minimum similarity score threshold (default: uses SIMILARITY_THRESHOLD)
        
    Returns:
        Dictionary containing:
        - matches: List of matched contexts with similarity scores, grouped by tool
        - matches_by_tool: Dictionary of matches grouped by tool name
        - total_matches: Total number of matches found across all tools
        - tools_searched: List of tools that were searched
        - query: The keywords that were searched
        - message: Success/error message
    """
    print(f"🔍 [VECTOR_SEARCH] Starting cross-platform vector search, keywords: {keywords[:60]}...")
    if tool:
        print(f"   [INFO] Tool hint provided: {tool} (will search all tools)")
    
    # Validate inputs
    if not keywords or not keywords.strip():
        return {
            "matches": [],
            "matches_by_tool": {},
            "total_matches": 0,
            "tools_searched": [],
            "query": keywords,
            "error": "No keywords provided"
        }
    
    if not qdrant:
        return {
            "matches": [],
            "matches_by_tool": {},
            "total_matches": 0,
            "tools_searched": [],
            "query": keywords,
            "error": "Qdrant client not initialized. Check QDRANT_URL environment variable."
        }
    
    # Get user ID from token
    try:
        user_id, status = get_user_id_from_token(token)
        if status != 200 or not user_id:
            return {
                "matches": [],
                "matches_by_tool": {},
                "total_matches": 0,
                "tools_searched": [],
                "query": keywords,
                "error": "Invalid or expired token",
            }
        print(f"   [DEBUG] Resolved user_id: {user_id}")
    except Exception as e:
        return {
            "matches": [],
            "matches_by_tool": {},
            "total_matches": 0,
            "tools_searched": [],
            "query": keywords,
            "error": f"Failed to resolve user_id: {str(e)}"
        }
    
    # Generate embedding for keywords (once, reuse for all tools)
    query_vector = generate_openai_embedding(keywords)
    if not query_vector:
        return {
            "matches": [],
            "matches_by_tool": {},
            "total_matches": 0,
            "tools_searched": [],
            "query": keywords,
            "error": "Failed to generate embedding for keywords"
        }
    
    # Use provided min_similarity or default threshold
    score_threshold = min_similarity if min_similarity is not None else SIMILARITY_THRESHOLD
    
    # Get all available tools (unique collection suffixes)
    all_tools = list(set(TOOL_COLLECTION_MAP.values()))
    
    # If tool hint provided, validate access and prioritize it
    tool_hint = None
    if tool:
        tool_lower = tool.lower().strip()
        tool_hint = TOOL_COLLECTION_MAP.get(tool_lower)
        if tool_hint:
            tool_name = TOOL_VALIDATION_MAP.get(tool_lower, "Gsuite")
            is_valid, error_msg, status_code = validate_user_tool_access(token, tool_name)
            if not is_valid:
                print(f"[WARNING] {tool_name} access denied, will skip this tool: {error_msg}")
                # Remove from search list if access denied
                if tool_hint in all_tools:
                    all_tools.remove(tool_hint)
    
    # Search across all tools
    all_matches = []
    matches_by_tool = {}
    tools_searched = []
    tools_with_results = []
    
    # Reorder tools to prioritize the hint tool if provided
    if tool_hint and tool_hint in all_tools:
        all_tools.remove(tool_hint)
        all_tools.insert(0, tool_hint)
    
    print(f"   [DEBUG] Searching across {len(all_tools)} tool collections...")
    
    for collection_suffix in all_tools:
        # Find the tool name for this collection suffix
        tool_name = None
        for t, suffix in TOOL_COLLECTION_MAP.items():
            if suffix == collection_suffix:
                tool_name = t
                break
        
        if not tool_name:
            continue
        
        # Validate user has access to this tool
        tool_validation_name = TOOL_VALIDATION_MAP.get(tool_name, "Gsuite")
        is_valid, error_msg, status_code = validate_user_tool_access(token, tool_validation_name)
        if not is_valid:
            print(f"   [SKIP] {tool_validation_name} access denied, skipping {tool_name}")
            continue
        
        collection_name = f"{user_id}_context_{collection_suffix}"
        tools_searched.append(tool_name)
        
        print(f"   [DEBUG] 🔍 Searching {tool_name} in collection: {collection_name}")
        
        try:
            hits = qdrant.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                search_params=SearchParams(
                    hnsw_ef=256,
                    exact=False,
                ),
                with_payload=True,
                with_vectors=False,
            )
            
            print(f"   [DEBUG] 📊 {tool_name}: Qdrant returned {len(hits.points)} raw hits")
            
            tool_matches = []
            for idx, point in enumerate(hits.points, 1):
                payload = point.payload or {}
                
                match = {
                    "id": str(point.id),
                    "similarity": float(point.score),
                    "source": tool_name,
                    "embedding_text": payload.get("embedding_text", ""),
                    "title": payload.get("title") or payload.get("channel_name") or payload.get("summary") or "",
                    "summary": payload.get("summary") or payload.get("brief_description") or "",
                }
                
                # Add tool-specific fields
                if tool_name == "slack":
                    match["channel_id"] = payload.get("channel_id", "")
                    match["channel_name"] = payload.get("channel_name", "")
                    match["message_count"] = payload.get("message_count", 0)
                elif tool_name in ["docs", "gdocs", "slides", "gslides"]:
                    match["document_id"] = payload.get("document_id") or payload.get("presentation_id", "")
                    match["link"] = payload.get("link", "")
                    match["last_edited_time"] = payload.get("last_edited_time", "")
                elif tool_name == "calendar":
                    match["event_id"] = payload.get("id", "")
                    match["start_time"] = payload.get("start_time", "")
                    match["attendees"] = payload.get("attendees", [])
                elif tool_name == "trello":
                    match["card_id"] = payload.get("page_id", "")
                    match["board_id"] = payload.get("board_id", "")
                    match["list_id"] = payload.get("list_id", "")
                elif tool_name in ["notion", "notiondocs"]:
                    match["page_id"] = payload.get("page_id", "")
                    match["url"] = payload.get("url", "")
                elif tool_name == "gmail":
                    match["email_ids"] = payload.get("email_ids", [])
                
                tool_matches.append(match)
                all_matches.append(match)
                
                # Print detailed info for each match
                print(f"      [{tool_name}] Match #{idx}:")
                print(f"         - ID: {match['id']}")
                print(f"         - Similarity: {match['similarity']:.4f}")
                print(f"         - Title: {match['title'][:80] if match['title'] else 'N/A'}")
                if match['summary']:
                    print(f"         - Summary: {match['summary'][:100]}...")
                if match['embedding_text']:
                    emb_text_preview = match['embedding_text'][:150].replace('\n', ' ')
                    print(f"         - Context preview: {emb_text_preview}...")
            
            if tool_matches:
                matches_by_tool[tool_name] = tool_matches
                tools_with_results.append(tool_name)
                print(f"   [DEBUG] ✅ {tool_name}: Found {len(tool_matches)} matches (similarity range: {min(m['similarity'] for m in tool_matches):.4f} - {max(m['similarity'] for m in tool_matches):.4f})")
            else:
                print(f"   [DEBUG] ⚠️  {tool_name}: No matches found (all hits below threshold {score_threshold})")
        
        except Exception as e:
            print(f"   [WARNING] Error searching {tool_name} ({collection_name}): {e}")
            continue
    
    # Sort all matches by similarity (highest first)
    all_matches.sort(key=lambda x: x["similarity"], reverse=True)
    
    # Sort matches within each tool by similarity
    for tool_name in matches_by_tool:
        matches_by_tool[tool_name].sort(key=lambda x: x["similarity"], reverse=True)
    
    # Print summary by tool
    print(f"\n📋 [VECTOR_SEARCH] === SEARCH SUMMARY ===")
    print(f"   Query: '{keywords}'")
    print(f"   Tools searched: {len(tools_searched)} ({', '.join(tools_searched)})")
    print(f"   Tools with results: {len(tools_with_results)} ({', '.join(tools_with_results) if tools_with_results else 'none'})")
    print(f"   Total matches: {len(all_matches)}")
    print(f"   Similarity threshold used: {score_threshold}")
    
    if all_matches:
        print(f"\n   Top matches by tool:")
        for tool_name in tools_with_results:
            tool_results = matches_by_tool[tool_name]
            print(f"      • {tool_name}: {len(tool_results)} matches")
            if tool_results:
                top_match = tool_results[0]
                print(f"        Top match (similarity: {top_match['similarity']:.4f}): {top_match['title'][:60] if top_match['title'] else 'N/A'}")
    
    if all_matches:
        print(f"\n   Top 5 overall matches:")
        for idx, match in enumerate(all_matches[:5], 1):
            print(f"      {idx}. [{match['source']}] Similarity: {match['similarity']:.4f} | {match['title'][:60] if match['title'] else 'N/A'}")
    
    print(f"✅ [VECTOR_SEARCH] Search complete\n")
    
    return {
        "matches": all_matches,
        "matches_by_tool": matches_by_tool,
        "total_matches": len(all_matches),
        "tools_searched": tools_searched,
        "tools_with_results": tools_with_results,
        "query": keywords,
        "min_similarity_used": score_threshold,
        "message": f"Found {len(all_matches)} semantically similar context(s) across {len(tools_with_results)} platform(s): {', '.join(tools_with_results)}"
    }

