

"""
service.py  —  Unified Workspace service layer
• Mongo connection + all original helpers (unchanged)
• NEW secure registration / login / profile / delete flows
• require_unified_token decorator for protected routes
"""

# ─────────────────────── Mongo connection ───────────────────────
from pymongo import MongoClient, ReturnDocument, ASCENDING
from datetime import datetime, timedelta, timezone
from flask import jsonify, request, g
from functools import wraps
import uuid, os, re, bcrypt
from typing import Tuple, Dict, Any, Optional, List
from db.mongo_client import get_mongo_client

# Get MongoDB client from centralized configuration
client = get_mongo_client()



db = client["unified_workspace"]

# Collections
users_collection        = db["users"]
tools_collection        = db["tools"]
user_tools_collection   = db["user_tools"]
auth_token_collection   = db["user_authenticate_token"]
counters_collection     = db["counters"]
workflow_collection     = db["workflow"]


def resolve_user_id_from_unified_token(unified_token: str) -> Optional[str]:
    """Return user_id for a registered unified Bearer token, or None if not in auth collection."""
    if not unified_token or not isinstance(unified_token, str):
        return None
    token = unified_token.strip()
    if not token:
        return None
    auth_entry = auth_token_collection.find_one({"tool_token": token, "tool_name": "unified"})
    if not auth_entry:
        return None
    return auth_entry["user_id"]


def resolve_user_id_for_workspace_access(raw_token: str) -> Optional[Any]:
    """
    Resolve workspace user_id for DB lookups (user_tools, per-user Mongo DBs).

    Accepts either:
      - a registered unified Bearer token (user_authenticate_token), or
      - a direct user_id string/int that exists on users (live=1).

    Returns the user_id value as stored on the user document (preserves int vs str
    so user_tools and gmail DB names match).
    """
    if not raw_token or not isinstance(raw_token, str):
        return None
    raw = raw_token.strip()
    if not raw:
        return None

    mapped = resolve_user_id_from_unified_token(raw)
    if mapped is not None:
        user = users_collection.find_one({"user_id": mapped, "live": 1})
        if user:
            return user.get("user_id")
        return mapped

    user = users_collection.find_one({"user_id": raw, "live": 1})
    if user:
        return user.get("user_id")

    try:
        n = int(raw)
    except ValueError:
        n = None
    if n is not None:
        user = users_collection.find_one({"user_id": n, "live": 1})
        if user:
            return user.get("user_id")

    return None


def user_id_mongo_variants(user_id: Any) -> List[Any]:
    """
    user_tools.user_id is sometimes stored as int and sometimes as str in Mongo.
    Build a small list of equivalent values to try in queries.
    """
    variants: List[Any] = []
    seen: set = set()

    def _add(v: Any) -> None:
        if v is None:
            return
        key = (type(v).__name__, repr(v))
        if key in seen:
            return
        seen.add(key)
        variants.append(v)

    _add(user_id)
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        _add(str(user_id))
    elif isinstance(user_id, str):
        s = user_id.strip()
        if s.isdigit():
            try:
                _add(int(s))
            except ValueError:
                pass
    return variants


def find_user_tool_entry(user_id: Any, tool_id: str) -> Optional[Dict[str, Any]]:
    """Find user_tools row matching tool_id, tolerating int/str user_id mismatch."""
    for uid in user_id_mongo_variants(user_id):
        row = user_tools_collection.find_one({"user_id": uid, "tool_id": tool_id})
        if row is not None:
            return row
    return None


def unified_token_auth_check(raw_token: str):
    """
    Verify token exists in user_authenticate_token and maps to a live user.
    Returns (None, None) if valid, else (jsonify(...), status_code) for Flask handlers.
    """
    user_id = resolve_user_id_from_unified_token(raw_token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired token"}), 401
    user = users_collection.find_one({"user_id": user_id, "live": 1})
    if not user:
        return jsonify({"error": "User not found"}), 404
    return None, None


# ─────────────────────── Legacy helpers ──────────────────────────
def generate_token():
    return str(uuid.uuid4())

def find_user(email, password):
    return users_collection.find_one(
        {"email": email, "password": password, "live": 1}
    )

def create_user_token(user_id, tool_name="unified"):
    """Replace any existing token for (user, tool_name)."""
    token   = generate_token()
    now     = datetime.utcnow()
    expires = now + timedelta(days=30)

    auth_token_collection.update_one(
        {"user_id": user_id, "tool_name": tool_name},
        {"$set": {
            "tool_token" : token,
            "created_at" : now,
            "expires_at" : expires
        }},
        upsert=True,
    )
    return token

def get_user_tools(user_id):
    tool_entries = user_tools_collection.find({"user_id": user_id})
    tools = []
    for te in tool_entries:
        tool = tools_collection.find_one({"tool_id": te.get("tool_id")})
        if not tool:
            continue
        tools.append({
            "name"                 : tool.get("name", "").lower(),
            "credential_is_available": bool(te.get("cred")),
            "tool_id"              : tool.get("tool_id"),
            "metadata"             : tool.get("metadata", {}),
            "url"                  : tool.get("url"),
        })
    return tools

# ────── ALL original tool / workflow functions (unchanged) ──────
# (Everything you pasted earlier is preserved verbatim.)
# ----------------------------------------------------------------
def add_or_update_user_tool(unified_token, tool_name, cred=None, access_token=None, error=None):
    """
    Upserts a user_tools entry for the given unified_token + tool_name.
    """
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return {"error": "Invalid or expired token"}, 401

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return {"error": f"Tool '{tool_name}' not found"}, 404
    tool_id = tool_entry["tool_id"]

    update_data = {
        "live"        : 1,
        "live_dt"     : datetime.utcnow(),
        "cred"        : cred or {},
        "access_token": access_token or {},
        "error"       : error or ""
    }
    user_tools_collection.update_one(
        {"user_id": user_id, "tool_id": tool_id},
        {"$set": update_data},
        upsert=True
    )
    return {"message": "Tool data inserted or updated successfully"}, 200


def logout_user(unified_token):
    res = auth_token_collection.delete_one({"tool_token": unified_token, "tool_name": "unified"})
    if res.deleted_count == 0:
        return {"error": "Invalid token or already logged out"}, 404
    return {"message": "User logged out successfully"}, 200


def _tool_name_is_google_workspace(tool_name: str) -> bool:
    n = (tool_name or "").strip().lower()
    return n in ("gsuite", "google workspace", "g workspace")


def _oauth_access_token_expired(access_token: Any) -> bool:
    """
    True if access_token dict has a parsed expiry in the past (UTC).
    Unknown / missing expiry → not treated as expired.
    """
    if not isinstance(access_token, dict):
        return False
    raw = access_token.get("expiry")
    if raw is None or raw == "":
        return False
    try:
        if isinstance(raw, datetime):
            exp = raw
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
        else:
            s = str(raw).replace("Z", "+00:00")
            exp = datetime.fromisoformat(s)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return datetime.now(timezone.utc) > exp


def assert_user_tool_connected_and_fresh(
    user_tool_entry: Dict[str, Any],
    *,
    tool_name: str,
) -> Tuple[bool, str]:
    """
    Enforce user_tools row signals: live, connection_status, OAuth access_token expiry.
    Used for Google Workspace (Gsuite) so Mongo-backed email/calendar/docs paths cannot
    run when the UI reports disconnected or tokens are expired in DB.
    """
    if not _tool_name_is_google_workspace(tool_name):
        return True, ""

    if "live" in user_tool_entry:
        try:
            if int(user_tool_entry.get("live")) != 1:
                return (
                    False,
                    "Google Workspace is not connected. Please connect it on the integrations / connections page.",
                )
        except (TypeError, ValueError):
            return (
                False,
                "Google Workspace is not connected. Please connect it on the integrations / connections page.",
            )

    # Only treat explicit 0 as "disconnected". Different clients use 1, 2, etc. for
    # connected / syncing; blocking everything except 1 caused false "not connected"
    # when the row still had valid OAuth data (e.g. connection_status=2).
    if "connection_status" in user_tool_entry:
        try:
            st = int(user_tool_entry.get("connection_status"))
            if st == 0:
                return (
                    False,
                    "Google Workspace is not connected. Please connect it on the integrations / connections page.",
                )
        except (TypeError, ValueError):
            return (
                False,
                "Google Workspace is not connected. Please connect it on the integrations / connections page.",
            )

    # "Connectedness" gating:
    # Per requirement: only reject explicitly disconnected rows (connection_status == 0).
    # Some clients store/refresh tokens asynchronously; enforcing expiry here caused
    # false negatives for connection_status values like `2`.
    #
    # NOTE: If connection_status is missing entirely, we keep the expiry check behavior.
    if "connection_status" not in user_tool_entry:
        at = user_tool_entry.get("access_token")
        if _oauth_access_token_expired(at):
            return (
                False,
                "Your Google Workspace connection has expired. Please reconnect on the integrations / connections page.",
            )

    return True, ""


def validate_user_tool_access(unified_token: str, tool_name: str) -> Tuple[bool, str, int]:
    """
    Validate that a user has access to a specific tool.
    Returns: (is_valid, error_message, status_code)
    """
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return False, "Invalid or expired token", 401

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return False, f"Tool '{tool_name}' not found", 404
    tool_id = tool_entry["tool_id"]

    user_tool_entry = find_user_tool_entry(user_id, tool_id)
    if not user_tool_entry:
        return False, f"User does not have access to tool '{tool_name}'", 403

    if not user_tool_entry.get("access_token") and not user_tool_entry.get("cred"):
        return False, f"No credentials found for tool '{tool_name}'", 403

    ok, conn_msg = assert_user_tool_connected_and_fresh(
        user_tool_entry, tool_name=tool_name
    )
    if not ok:
        return False, conn_msg, 403

    return True, "", 200


def get_user_tool_access_token(unified_token, tool_name):
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return {"error": "Invalid or expired token"}, 401

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return {"error": f"Tool '{tool_name}' not found"}, 404
    tool_id = tool_entry["tool_id"]

    user_tool_entry = find_user_tool_entry(user_id, tool_id)
    if not user_tool_entry or not user_tool_entry.get("access_token"):
        return {"error": f"No access token found for tool '{tool_name}'"}, 404

    ok, conn_msg = assert_user_tool_connected_and_fresh(
        user_tool_entry, tool_name=tool_name
    )
    if not ok:
        return {"error": conn_msg}, 403

    return {"access_token": user_tool_entry["access_token"]}, 200


def get_user_tool_cred(unified_token, tool_name):
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return {"error": "Invalid or expired token"}, 401

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return {"error": f"Tool '{tool_name}' not found"}, 404
    tool_id = tool_entry["tool_id"]

    user_tool_entry = find_user_tool_entry(user_id, tool_id)
    if not user_tool_entry or not user_tool_entry.get("access_token"):
        return {"error": f"No access token found for tool '{tool_name}'"}, 404

    ok, conn_msg = assert_user_tool_connected_and_fresh(
        user_tool_entry, tool_name=tool_name
    )
    if not ok:
        return {"error": conn_msg}, 403

    return {
        "cred"        : user_tool_entry["cred"],
        "access_token": user_tool_entry["access_token"]
    }, 200


def update_user_tool_access_token(unified_token, tool_name, new_token_data):
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return False

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return False
    tool_id = tool_entry["tool_id"]

    user_tool_entry = find_user_tool_entry(user_id, tool_id)
    if not user_tool_entry:
        return False
    canonical_uid = user_tool_entry.get("user_id")
    user_tools_collection.update_one(
        {"user_id": canonical_uid, "tool_id": tool_id},
        {"$set": {"access_token": new_token_data, "live_dt": datetime.utcnow()}}
    )
    return True


def get_next_tool_id():
    counter = db["counters"].find_one_and_update(
        {"_id": "tool_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True
    )
    seq = counter["seq"]
    return f"t{seq:03d}"


def create_tool(name, metadata=None, url=None):
    if not name or not isinstance(name, str):
        return {"error": "Tool name is required and must be a string."}, 400

    existing = tools_collection.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if existing:
        return {"error": f"Tool '{name}' already exists."}, 409

    tool_id = get_next_tool_id()
    doc = {
        "tool_id"   : tool_id,
        "name"      : name,
        "created_at": datetime.utcnow(),
        "metadata"  : metadata or {}
    }
    if url: doc["url"] = url
    tools_collection.insert_one(doc)
    return {"message": f"Tool '{name}' created.", "tool_id": tool_id}, 201


def get_next_sequence(name):
    counter = counters_collection.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
        upsert=True
    )
    return counter["seq"]




def save_or_update_workflow(unified_token, data):
    userid = resolve_user_id_from_unified_token(unified_token)
    if userid is None:
        return jsonify({"error": "Invalid or expired token"}), 401

    workflowid    = data.get("workflowid")
    workflowname  = data.get("workflowname")
    panels        = data.get("panel")
    is_default_in = bool(data.get("isDefault", False))   # NEW

    if not workflowname or panels is None:
        return jsonify({"error": "Missing workflowname or panels"}), 400

    user_doc = workflow_collection.find_one({"userid": userid}) or {"userid": userid, "workflows": []}
    workflows = user_doc.get("workflows", [])

    updated = False
    if workflowid and workflowid != "new":
        for wf in workflows:
            if wf["workflowid"] == workflowid:
                wf["workflowname"] = workflowname
                wf["panel"]        = panels
                wf["isDefault"]    = is_default_in     # update flag
                updated = True
                break

    if not updated:                                     # create new workflow
        new_id = f"wf{get_next_sequence('workflow_id'):03d}"
        workflows.append({
            "workflowid" : new_id,
            "workflowname": workflowname,
            "panel"      : panels,
            "isDefault"  : is_default_in               # set flag
        })
        workflowid = new_id

    # --- guarantee single default ---
    if is_default_in:
        for wf in workflows:
            if wf["workflowid"] != workflowid:
                wf["isDefault"] = False
    else:
        # If none are default after the update, make the first one default.
        if not any(wf.get("isDefault") for wf in workflows) and workflows:
            workflows[0]["isDefault"] = True

    workflow_collection.update_one(
        {"userid": userid},
        {"$set": {"workflows": workflows}},
        upsert=True
    )
    return jsonify({"message": "Workflow saved", "workflowid": workflowid}), 200



# def delete_workflow(unified_token, workflowid):
#     auth_entry = auth_token_collection.find_one({"tool_token": unified_token, "tool_name": "unified"})
#     if not auth_entry:
#         return jsonify({"error": "Invalid or expired unified token"}), 401
#     user_id = auth_entry["user_id"]

#     result = workflow_collection.update_one(
#         {"userid": user_id},
#         {"$pull": {"workflows": {"workflowid": workflowid}}}
#     )
#     if result.modified_count:
#         return jsonify({"message": "Workflow deleted"}), 200
#     return jsonify({"error": "Workflow not found or unauthorized"}), 404

def delete_workflow(unified_token, workflowid):
    user_id = resolve_user_id_from_unified_token(unified_token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired token"}), 401

    user_doc = workflow_collection.find_one({"userid": user_id})
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    workflows = user_doc.get("workflows", [])
    new_list  = [wf for wf in workflows if wf["workflowid"] != workflowid]

    if len(new_list) == len(workflows):
        return jsonify({"error": "Workflow not found or unauthorized"}), 404

    # If the removed one was default → pick another as default
    if not any(wf.get("isDefault") for wf in new_list) and new_list:
        new_list[0]["isDefault"] = True

    workflow_collection.update_one(
        {"userid": user_id},
        {"$set": {"workflows": new_list}}
    )
    return jsonify({"message": "Workflow deleted"}), 200



def get_workflow_by_id(unified_token, workflowid):
    user_id = resolve_user_id_from_unified_token(unified_token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired token"}), 401

    user_doc = workflow_collection.find_one({"userid": user_id})
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    for wf in user_doc.get("workflows", []):
        if wf["workflowid"] == workflowid:
            return jsonify(wf), 200
    return jsonify({"error": "Workflow not found"}), 404


def get_all_workflows(unified_token):
    user_id = resolve_user_id_from_unified_token(unified_token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired token"}), 401

    workflows = workflow_collection.find_one({"userid": user_id}, {"_id": 0})
    return jsonify(workflows), 200



def set_default_workflow(unified_token, workflowid, make_default=True):
    user_id = resolve_user_id_from_unified_token(unified_token)
    if user_id is None:
        return jsonify({"error": "Invalid or expired token"}), 401

    user_doc = workflow_collection.find_one({"userid": user_id})
    if not user_doc:
        return jsonify({"error": "User not found"}), 404

    workflows = user_doc.get("workflows", [])
    found = False
    for wf in workflows:
        if wf["workflowid"] == workflowid:
            wf["isDefault"] = make_default
            found = True
        elif make_default:
            wf["isDefault"] = False  # demote others only when making one default

    if not found:
        return jsonify({"error": "Workflow not found"}), 404

    # Safety: ensure at least one default
    if not any(wf.get("isDefault") for wf in workflows) and workflows:
        workflows[0]["isDefault"] = True

    workflow_collection.update_one(
        {"userid": user_id},
        {"$set": {"workflows": workflows}},
    )
    msg = "Workflow set as default" if make_default else "Workflow unset as default"
    return jsonify({"message": msg}), 200



def get_filtered_emails_from_db(brief_type="unread_starred", max_results=20, unified_token=""):
    user_id = resolve_user_id_from_unified_token(unified_token)
    if user_id is None:
        return []
    gmail_db = client[str(user_id)]
    gmail_collection = gmail_db["gmail"]

    now = datetime.now(timezone.utc)
    query = {}
    if brief_type == "unread_starred":
        seven_days_ago = int((now - timedelta(days=7)).timestamp() * 1000)
        query["internalDateNum"] = {"$gte": seven_days_ago}
        query["labels"] = {"$in": ["STARRED", "UNREAD"]}
    elif brief_type == "last_7_days":
        seven_days_ago = int((now - timedelta(days=7)).timestamp() * 1000)
        query["internalDateNum"] = {"$gte": seven_days_ago}
    elif brief_type == "last_2_days":
        two_days_ago = int((now - timedelta(days=2)).timestamp() * 1000)
        query["internalDateNum"] = {"$gte": two_days_ago}
    elif brief_type == "important":
        query["labels"] = {"$in": ["IMPORTANT"]}
    else:
        seven_days_ago = int((now - timedelta(days=7)).timestamp() * 1000)
        query["internalDateNum"] = {"$gte": seven_days_ago}

    emails = list(gmail_collection.find(query).sort("internalDateNum", -1).limit(max_results))
    for e in emails:
        e["_id"] = str(e["_id"])
    return emails


def delete_user_tool_from_db(unified_token, tool_name):
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return {"error": "Invalid or expired token"}, 401

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return {"error": f"Tool '{tool_name}' not found"}, 404
    tool_id = tool_entry["tool_id"]

    user_tool_entry = find_user_tool_entry(user_id, tool_id)
    if not user_tool_entry:
        return {"message": f"No active connection for '{tool_name}'"}, 404
    canonical_uid = user_tool_entry.get("user_id")
    result = user_tools_collection.delete_one({"user_id": canonical_uid, "tool_id": tool_id})
    if result.deleted_count == 0:
        return {"message": f"No active connection for '{tool_name}'"}, 404
    return {"message": f"Tool '{tool_name}' disconnected"}, 200


def get_user_tool_access_details(unified_token, tool_name):
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return {"error": "Invalid or expired token"}, 401

    tool_entry = tools_collection.find_one({"name": {"$regex": f"^{tool_name}$", "$options": "i"}})
    if not tool_entry:
        return {"error": f"Tool '{tool_name}' not found"}, 404
    tool_id = tool_entry["tool_id"]

    user_tool_entry = find_user_tool_entry(user_id, tool_id)
    if not user_tool_entry or not user_tool_entry.get("access_token"):
        return {"error": f"No access token for '{tool_name}'"}, 404

    connected_at = user_tool_entry.get("live_dt")
    return {
        "access_token": user_tool_entry["access_token"],
        "connected_at": connected_at.isoformat() if connected_at else None
    }, 200

# ───────────────────── Secure account layer ──────────────────────
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")

def _hash_pwd(raw: str) -> str:
    """Return a bcrypt hash as UTF‑8 text ready for Mongo."""
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()

def _verify_pwd(raw: str, stored: str) -> bool:
    """
    True iff `raw` matches `stored`.
    • Any malformed or non‑bcrypt `stored` value just returns False
      so the caller can respond with 401 instead of crashing.
    """
    try:
        return bcrypt.checkpw(raw.encode(), stored.encode())
    except (ValueError, TypeError):
        # ValueError → invalid salt / bad hash
        # TypeError   → stored was None / not str
        return False

def _clean_user_payload(data, *, for_update=False):
    required = {"fullName", "email", "password"} if not for_update else set()
    missing = [k for k in required if not data.get(k)]
    if missing:
        return None, f"Missing fields: {', '.join(missing)}"
    if "email" in data and not EMAIL_RE.fullmatch(data["email"]):
        return None, "Invalid email"
    if "phone" in data and data.get("phone") and not PHONE_RE.fullmatch(data["phone"]):
        return None, "Phone must be E.164 (+countrycode…)"
    doc = {
        "fullName"   : data.get("fullName"),
        "companyName": data.get("companyName", ""),
        "jobTitle"   : data.get("jobTitle", ""),
        "email"      : data.get("email"),
        "phone"      : data.get("phone", ""),
        "live"       : 1,
        "updatedAt"  : datetime.utcnow(),
    }
    if "password" in data:
        doc["password"] = _hash_pwd(data["password"])
    return doc, None

def require_unified_token(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "Missing Authorization token"}), 401
        auth = auth_token_collection.find_one({"tool_token": token, "tool_name": "unified"})
        if not auth:
            return jsonify({"error": "Invalid or expired token"}), 401
        user = users_collection.find_one({"user_id": auth["user_id"], "live": 1})
        if not user:
            return jsonify({"error": "User not found"}), 404
        g.user  = user
        g.token = token
        return fn(*args, **kwargs)
    return wrapper

# def register_user(payload):
#     clean, err = _clean_user_payload(payload)
#     if err: return {"error": err}, 400
#     if users_collection.find_one({"email": clean["email"]}):
#         return {"error": "Email already registered"}, 409
#     clean.update({"user_id": str(uuid.uuid4()), "createdAt": datetime.utcnow()})
#     users_collection.insert_one(clean)
#     return {"message": "Registration successful", "user_id": clean["user_id"]}, 201

def update_slack_userid(user_id,token):
    """
    Update the Slack user_id for the user associated with the given unified token.

    Args:
        user_id (str): The Slack user_id to store.
        token (str): The unified token identifying the user.

    Returns:
        bool: True if update was successful, False otherwise.
    """
    try:
        # Find the auth record for the unified token
        auth = auth_token_collection.find_one({"tool_token": token, "tool_name": "unified"})
        if not auth:
            return False

        # Update the user document with the new slack_user_id
        result = users_collection.update_one(
            {"user_id": auth["user_id"], "live": 1},
            {"$set": {"slack_user_id": user_id, "updatedAt": datetime.utcnow()}}
        )
        return result.modified_count > 0
    except Exception as e:
        # Optionally log the exception here
        return False



def login_user_secure(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    """
    Validate creds and return (response_json, status_code).
    Never raises; invalid creds always → 401.
    """
    email = payload.get("email", "").strip().lower()
    pwd   = payload.get("password", "")

    user = users_collection.find_one({"email": email, "live": 1})

    # ‼️  _verify_pwd is now exception‑safe
    if not user or not _verify_pwd(pwd, user["password"]):
        return {"error": "Invalid credentials"}, 401

    token = create_user_token(user["user_id"])
    return {
        "unified_token": token,
        "tools": get_user_tools(user["user_id"]),
        # "tours": get_user_tour_access(user["user_id"])  # <- Add tours here
    }, 200

def logout_user_secure(token):
    return logout_user(token)

def change_password_secure(email, old_pwd, new_pwd):
    if not all([email, old_pwd, new_pwd]):
        return {"error": "Missing params"}, 400
    user = users_collection.find_one({"email": email, "live": 1})
    if not user or not _verify_pwd(old_pwd, user["password"]):
        return {"error": "Invalid email or old password"}, 401
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": _hash_pwd(new_pwd), "updatedAt": datetime.utcnow()}}
    )
    return {"message": "Password updated"}, 200

def get_profile_secure(user_oid):
    user = users_collection.find_one({"_id": user_oid}, {"_id": 0, "password": 0})
    return (user, 200) if user else ({"error": "User not found"}, 404)

def update_profile_secure(user_oid, payload):
    clean, err = _clean_user_payload(payload, for_update=True)
    if err: return {"error": err}, 400
    res = users_collection.update_one({"_id": user_oid}, {"$set": clean})
    msg = "Profile updated" if res.modified_count else "No changes applied"
    return {"message": msg}, 200

def deactivate_account_secure(user_oid):
    users_collection.update_one({"_id": user_oid}, {"$set": {"live": 0}})
    auth_token_collection.delete_many({"user_id": users_collection.find_one({"_id": user_oid})["user_id"]})
    return {"message": "Account deactivated"}, 200

def user_info(unified_token):
    """
    Given a unified_token and tool_name, upserts user_tools entry.
    """
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return None
    return users_collection.find_one({"user_id": user_id, "live": 1})


def get_user_id_from_token(unified_token) -> Tuple[Optional[str], int]:
    """
    Given a unified_token, return (user_id, 200) if registered.
    Returns (None, 401) if the token is missing from user_authenticate_token.
    """
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return None, 401
    return user_id, 200

# ───────────────── Gmail helpers ────────────────────────────────
def get_distinct_gmail_senders(unified_token: str, *, with_counts: bool = False):
    """
    Return every unique sender in the user's Gmail collection.

    Parameters
    ----------
    unified_token : str
        The caller's "Authorization: Bearer …" token.
    with_counts   : bool, default False
        • False → list[{"name": str, "email": str}]
        • True  → list[{"name": str, "email": str, "count": int}]
          (ordered by descending count, then email)

    Returns
    -------
    (json-ish, status_code)
        On success: (list[dict], 200)
        On failure: ({"error": str}, 4xx / 5xx)
    """
    # --- 1. validate token and locate the user -------------------
    user_id = resolve_user_id_for_workspace_access(unified_token)
    if user_id is None:
        return {"error": "Invalid or expired token"}, 401

    # --- 2. point at that user's Gmail sub‑database --------------
    gmail_db   = client[str(user_id)]
    gmail_coll = gmail_db["gmail"]

    # --- 3. aggregation pipeline --------------------------------
    if with_counts:
        pipeline = [
            {"$group": {
                "_id"  : {"name": "$from.name", "email": "$from.email"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1, "_id.email": 1, "_id.name": 1}},
            {"$project": {
                "_id"  : 0,
                "name" : "$_id.name",
                "email": "$_id.email",
                "count": 1
            }},
        ]
    else:
        pipeline = [
            {"$group": {"_id": {"name": "$from.name", "email": "$from.email"}}},
            {"$project": {
                "_id"  : 0,
                "name" : "$_id.name",
                "email": "$_id.email"
            }},
            {"$sort": {"email": 1, "name": 1}},
        ]

    try:
        senders = list(gmail_coll.aggregate(pipeline))
    except Exception as e:
        return {"error": f"Mongo aggregation failed: {e}"}, 500

    return senders, 200



# ─────────────────────── Tours ───────────────────────



def get_next_tour_id():
    """
    Generate the next auto-incremented tour_id like 'tour001', 'tour002', etc.
    """
    counter = db["counters"].find_one_and_update(
        {"_id": "tour_id"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    seq = counter["seq"]
    return f"tour{seq:03d}"


def get_all_tours_with_user_access(user_id: str) -> list:
    """
    Returns a list of all tours, each marked with whether the user has access (seen it).
    """
    tours = list(db.tours.find({}, {"_id": 0}))
    
    for tour in tours:
        tour["seen"] = user_id in tour.get("users", [])

    return tours

def add_new_tour(title: str, description: str = "") -> Tuple[Dict[str, Any], int]:
    """
    Create a new tour document with auto-generated tour_id.
    """
    if not title:
        return {"success": False, "message": "Title is required"}, 400

    tour_id = get_next_tour_id()

    existing = db["tours"].find_one({"title": title})
    if existing:
        return {"success": False, "message": "Tour with this title already exists"}, 409

    new_tour = {
        "tour_id": tour_id,
        "title": title,
        "description": description,
        "users": []
    }

    db["tours"].insert_one(new_tour)
    return {"success": True, "message": "Tour created", "tour_id": tour_id}, 201


def mark_tour_seen_by_user(tour_id: str, user_id: str) -> Tuple[dict, int]:
    result = db.tours.update_one(
        {"tour_id": tour_id},
        {"$addToSet": {"users": user_id}}
    )

    if result.modified_count:
        return {"success": True, "message": "User marked as seen"}, 200
    else:
        return {"success": False, "message": "Already marked or tour not found"}, 404


def get_user_tour_access(user_id: str) -> list:
    """
    Returns a list of all tours with `access` marked True/False based on user membership.
    """
    all_tours = db.tours.find({}, {"_id": 0, "tour_id": 1, "title": 1, "description": 1, "users": 1})

    return [
        {
            "tour_id": tour["tour_id"],
            "title": tour["title"],
            "description": tour["description"],
            "access": user_id in tour.get("users", [])
        }
        for tour in all_tours
    ]




# ───────────── Ensure unique indexes (run once) ────────────────
users_collection.create_index([("email", ASCENDING)], unique=True)
auth_token_collection.create_index([("tool_token", ASCENDING)], unique=True, sparse=True)
