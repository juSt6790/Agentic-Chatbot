"""
Trello MCP utilities

This module provides a thin wrapper around Trello's REST API using user-scoped
credentials stored in the database via `db_method.get_user_tool_access_token`.
It exposes helper functions to manage boards, lists, members and tasks (cards).

Auth requirements (per user):
- api_key
- token
- secret (not required for simple key+token requests but stored for completeness)

All public functions accept `unified_token` to fetch the user's Trello credentials.
"""
from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from clients.db_method import get_user_tool_access_token

BASE_URL = "https://api.trello.com/1/"


def _get_auth(unified_token: Optional[str]) -> Dict[str, str]:
    """Retrieve Trello API credentials for the user from the DB."""
    tool_name = "Trello"
    result, status = get_user_tool_access_token(unified_token, tool_name)
    if status != 200 or not isinstance(result, dict):
        raise Exception("Failed to retrieve Trello credentials. Please connect Trello.")

    access = result.get("access_token") or {}
    api_key = access.get("api_key")
    token = access.get("token")
    secret = access.get("secret")  # not used for requests, but may be stored

    if not api_key or not token:
        raise Exception("Trello credentials missing 'api_key' or 'token'.")

    return {"key": api_key, "token": token}


def _request(
    method: str,
    path: str,
    unified_token: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
) -> Any:
    auth = _get_auth(unified_token)
    params = params.copy() if params else {}
    params.update(auth)
    url = urljoin(BASE_URL, path.lstrip("/"))
    resp = requests.request(method.upper(), url, params=params, json=json, timeout=30)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return resp.text


# Boards

def trello_list_boards(unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """List boards for the current user."""
    boards = _request("GET", "members/me/boards", unified_token)
    return [
        {
            "idboard": board.get("id"),
            "board_name": board.get("name"),
            "url": board.get("url"),
        }
        for board in boards
    ]


def trello_list_members(board_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """List members of a board."""
    members = _request("GET", f"boards/{board_id}/members", unified_token)

    return [
        {
            "idboard": board_id,
            "idmember": m.get("id"),
            "fullName": m.get("fullName"),
            "username": m.get("username")
        }
        for m in members
    ]

# Lists

def trello_list_lists(board_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """List lists in a board."""
    lists = _request("GET", f"boards/{board_id}/lists", unified_token)

    return [
        {
            "idboard": l.get("idBoard"),
            "idlist": l.get("id"),
            "list_name": l.get("name"),
            "closed": l.get("closed"),
            "pos": l.get("pos"),
            "subscribed": l.get("subscribed"),
            "color": l.get("color")
        }
        for l in lists
    ]

def trello_create_list(
    board_id: str,
    name: str,
    unified_token: Optional[str] = None,
    pos: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a list on a board."""
    params: Dict[str, Any] = {"idBoard": board_id, "name": name}
    if pos is not None:
        params["pos"] = pos
    # Trello docs: POST /1/lists with idBoard and name
    new_list = _request("POST", "lists", unified_token, params=params)

    return {
        "idboard": new_list.get("idBoard"),
        "idlist": new_list.get("id"),
        "list_name": new_list.get("name"),
        "closed": new_list.get("closed"),
    }
    

# Cards (Tasks)

def trello_list_cards(
    unified_token: Optional[str] = None,
    list_id: Optional[str] = None,
    board_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List cards either by list or by board."""
    if list_id:
        cards = _request("GET", f"lists/{list_id}/cards", unified_token)
    elif board_id:
        cards = _request("GET", f"boards/{board_id}/cards", unified_token)
    else : 
        raise ValueError("Provide either list_id or board_id to list cards")
    
    return [
        {
            "idboard": c.get("idBoard"),
            "board_name": c.get("board", {}).get("name"),
            "idlist": c.get("idList"),
            "list_name": c.get("list", {}).get("name"),
            "idcard": c.get("id"),
            "idmember": c.get("idMembers"),
            "card_name": c.get("name"),
            "closed": c.get("closed"),
            "due_date": c.get("due"),
            "labels": [
                    {
                        "idlabel": l.get("id"),
                        "label_name": l.get("name")
                    }
                    for l in c.get("labels", [])
                ],
            "url": c.get("url"),
            "metadata": {
                "desc": c.get("desc"),
                "datelastactivity": c.get("dateLastActivity"),
                "cover": c.get("cover"),
                "badges": c.get("badges"),
                "subscribed": c.get("subscribed"),
                "pos": c.get("pos")
            }
        }
        for c in cards
    ]


def trello_create_card(
    list_id: str,
    name: str,
    unified_token: Optional[str] = None,
    desc: Optional[str] = None,
    due: Optional[str] = None,
    member_ids: Optional[List[str]] = None,
    label_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a card in a list."""
    params: Dict[str, Any] = {"idList": list_id, "name": name}
    if desc:
        params["desc"] = desc
    if due:
        params["due"] = due
    if member_ids:
        params["idMembers"] = ",".join(member_ids)
    if label_ids:
        params["idLabels"] = ",".join(label_ids)
    
    card = _request("POST", "cards", unified_token, params=params)
    return {
        "idboard": card.get("idBoard"),
        "idlist": card.get("idList"),
        "idcard": card.get("id"),
        "idmember": card.get("idMembers"),
        "card_name": card.get("name"),
        "closed": card.get("closed"),
        "due_date": card.get("due"),
        "labels": card.get("labels", []),
        "url": card.get("url"),
        "metadata": {
            "desc": card.get("desc"),
            "date_last_activity": card.get("dateLastActivity"),
            "cover": card.get("cover"),
            "badges": card.get("badges"),
            "subscribed": card.get("subscribed"),
            "pos": card.get("pos")
        }
    }


def trello_update_card(
    card_id: str,
    unified_token: Optional[str] = None,
    name: Optional[str] = None,
    desc: Optional[str] = None,
    due: Optional[str] = None,
    closed: Optional[bool] = None,
    list_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Update a card's basic fields or move to another list."""
    params: Dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if desc is not None:
        params["desc"] = desc
    if due is not None:
        params["due"] = due
    if closed is not None:
        params["closed"] = str(bool(closed)).lower()
    if list_id is not None:
        params["idList"] = list_id
    
    card = _request("PUT", f"cards/{card_id}", unified_token, params=params)
    return {
        "idboard": card.get("idBoard"),
        "idlist": card.get("idList"),
        "idcard": card.get("id"),
        "idmember": card.get("idMembers"),
        "card_name": card.get("name"),
        "closed": card.get("closed"),
        "due_date": card.get("due"),
        "labels": card.get("labels", []),
        "url": card.get("url"),
        "metadata": {
            "desc": card.get("desc"),
            "date_last_activity": card.get("dateLastActivity"),
            "cover": card.get("cover"),
            "badges": card.get("badges"),
            "subscribed": card.get("subscribed"),
            "pos": card.get("pos")
        }
    }




def trello_move_card(
    card_id: str,
    list_id: str,
    unified_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Move a card to another list."""
    return trello_update_card(card_id=card_id, list_id=list_id, unified_token=unified_token)


def trello_delete_card(card_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    """Delete (close) a card."""
    
    response = _request("DELETE", f"cards/{card_id}", unified_token)

    return {
        "idcard": card_id,
        "metadata": response if response else {}
    }


# Search

def trello_search(
    query: str,
    unified_token: Optional[str] = None,
    board_id: Optional[str] = None,
    partial: bool = True,
    limit: int = 50,
) -> Dict[str, Any]:
    """Search cards (and optionally restrict to a board)."""
    params: Dict[str, Any] = {
        "query": query,
        "modelTypes": "cards",
        "card_fields": "id,name,desc,due,url,idList,idBoard,labels,idMembers,shortUrl,dateLastActivity,closed",
        "partial": str(bool(partial)).lower(),
        "limit": limit,
    }
    if board_id:
        params["idBoards"] = board_id
    
    response = _request("GET", "search", unified_token, params=params)
    cards = response.get("cards", [])
    return [
        {
            "idboard": c.get("idBoard"),
            "board_name": c.get("board", {}).get("name"),
            "idlist": c.get("idList"),
            "list_name": c.get("list", {}).get("name"),
            "idcard": c.get("id"),
            "idmember": c.get("idMembers"),
            "card_name": c.get("name"),
            "closed": c.get("closed"),
            "due_date": c.get("due"),
            "url": c.get("url"),
            "labels": c.get("labels", []),
            "metadata": {
                "desc": c.get("desc"),
                "datelastactivity": c.get("dateLastActivity"),
                "cover": c.get("cover"),
                "badges": c.get("badges"),
                "subscribed": c.get("subscribed"),
                "pos": c.get("pos"),
            },
        }
        for c in cards
    ]

# Additional helpers to support server.py tool surface

# Card fetch
def trello_get_card(card_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    card = _request("GET", f"cards/{card_id}", unified_token)

    return {
        "idboard": card.get("idBoard"),
        "idlist": card.get("idList"),
        "idcard": card.get("id"),
        "idmember": card.get("idMembers"),
        "card_name": card.get("name"),
        "closed": card.get("closed"),
        "due_date": card.get("due"),
        "labels": [
            {
                "idlabel": l.get("id"),
                "label_name": l.get("name")
            }
            for l in card.get("labels", [])
        ],
        "url": card.get("url"),
        "metadata": {
            "desc": card.get("desc"),
            "datelastactivity": card.get("dateLastActivity"),
            "cover": card.get("cover"),
            "badges": card.get("badges"),
            "subscribed": card.get("subscribed"),
            "pos": card.get("pos"),
        },
    }


# Comments
def trello_add_comment(card_id: str, text: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    params = {"text": text}
    comment = _request("POST", f"cards/{card_id}/actions/comments", unified_token, params=params)

    return {
        "idboard": comment.get("data", {}).get("board", {}).get("id"),
        "idlist": comment.get("data", {}).get("list", {}).get("id"),
        "idcard": comment.get("data", {}).get("card", {}).get("id"),
        "idcomment": comment.get("id"),
        "idmember": comment.get("idMemberCreator"),
        "fullname": comment.get("memberCreator", {}).get("fullName"),
        "username": comment.get("memberCreator", {}).get("username"),
        "comment_text": comment.get("data", {}).get("text"),
        "card_name": comment.get("data", {}).get("card", {}).get("name"),
        "board_name": comment.get("data", {}).get("board", {}).get("name"),
        "list_name": comment.get("data", {}).get("list", {}).get("name"),
    }

def trello_list_card_comments(card_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all comments (actions of type 'commentCard') on a given Trello card.
    """
    # Fetch all comment actions for the card
    actions = _request(
        "GET",
        f"cards/{card_id}/actions",
        unified_token,
        params={"filter": "commentCard"}
    )

    # Standardized unified return structure
    return [
        {
            "idboard": a.get("data", {}).get("board", {}).get("id"),
            "idcard": a.get("data", {}).get("card", {}).get("id"),
            "idmember": a.get("idMemberCreator"),
            "card_name": a.get("data", {}).get("card", {}).get("name"),
            "list_name": a.get("data", {}).get("list", {}).get("name"),
            "idcomment": a.get("id"),
            "comment_text": a.get("data", {}).get("text"),
            "date": a.get("date"),
            "fullName": a.get("memberCreator", {}).get("fullName"),
            "username": a.get("memberCreator", {}).get("username"),
            "metadata": {
                "board_name": a.get("data", {}).get("board", {}).get("name"),
                "short_url": a.get("data", {}).get("card", {}).get("shortLink"),
                "type": a.get("type"),
                "display": a.get("display"),
            },
        }
        for a in actions
    ]

def trello_update_comment(card_id: str, action_id: str, text: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    # Trello updates comment via action id
    params = {"value": text}
    # return _request("PUT", f"actions/{action_id}/text", unified_token, params=params)
    comment = _request("PUT", f"actions/{action_id}/text", unified_token, params=params)

    return {
        "idcomment": comment.get("id"),
        "idcard": comment.get("data", {}).get("card", {}).get("id"),
        "card_name": comment.get("data", {}).get("card", {}).get("name"),
        "idboard": comment.get("data", {}).get("board", {}).get("id"),
        "board_name": comment.get("data", {}).get("board", {}).get("name"),
        "idlist": comment.get("data", {}).get("list", {}).get("id"),
        "list_name": comment.get("data", {}).get("list", {}).get("name"),
        "comment_text": comment.get("data", {}).get("text"),
    }


def trello_delete_comment(card_id: str, action_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    response = _request("DELETE", f"actions/{action_id}", unified_token)
    return {
            "idcomment": action_id,
            "idcard" : card_id
    }


# Members
def trello_add_members(card_id: str, member_ids: List[str], unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    
    added_members = []
    for mid in member_ids:
        params = {"value": mid}
        response  = _request("POST", f"cards/{card_id}/idMembers", unified_token, params=params)
        # Handle both possible return types (list or dict)
        member = response[0] if isinstance(response, list) and response else response
        added_members.append({
            "idmember": member.get("id"),
            "fullname": member.get("fullName"),
            "username": member.get("username"),
            "avatarurl": member.get("avatarUrl"),
        })
    return {
        "idcard": card_id,
        "members": added_members
    }

def trello_remove_member(card_id: str, member_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    
    _request("DELETE", f"cards/{card_id}/idMembers/{member_id}", unified_token)
    return {
        "idcard": card_id,
        "idmember": member_id,
    }


# Labels
def trello_add_label(card_id: str, label_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    params = {"value": label_id}
    response = _request("POST", f"cards/{card_id}/idLabels", unified_token, params=params)
    added_label_id = response[0] if isinstance(response, list) and response else label_id
    return {
        "idcard": card_id,
        "idlabel": added_label_id,
    }


def trello_remove_label(card_id: str, label_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    _request("DELETE", f"cards/{card_id}/idLabels/{label_id}", unified_token)
    # Return consistent schema
    return {
        "idcard": card_id,
        "idlabel": label_id,
    }


def trello_list_board_labels(board_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    labels = _request("GET", f"boards/{board_id}/labels", unified_token)
    
    return [
        {
            "idboard": label.get("idBoard"),
            "idlabel": label.get("id"),
            "label_name": label.get("name"),
            "color": label.get("color"),
            "uses": label.get("uses")
        }
        for label in labels
    ]


def trello_create_board_label(board_id: str, name: Optional[str], color: Optional[str], unified_token: Optional[str] = None) -> Dict[str, Any]:
    """Create a label on a board. Color should be a Trello-supported color or None."""
    params: Dict[str, Any] = {"idBoard": board_id}
    if name is not None:
        params["name"] = name
    if color is not None:
        params["color"] = color
    
    label = _request("POST", "labels", unified_token, params=params)
    return {
        "idboard": label.get("idBoard"),
        "idlabel": label.get("id"),
        "label_name": label.get("name"),
        "color": label.get("color"),
        "uses": label.get("uses")
    }


def trello_update_label(label_id: str, name: Optional[str] = None, color: Optional[str] = None, unified_token: Optional[str] = None) -> Dict[str, Any]:
    """Update a label's name and/or color."""
    params: Dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if color is not None:
        params["color"] = color
    label = _request("PUT", f"labels/{label_id}", unified_token, params=params)

    return {
        "idboard": label.get("idBoard"),
        "idlabel": label.get("id"),
        "labels": label.get("name"),
        "color": label.get("color"),
        "uses": label.get("uses")
    }


# Checklists
def trello_create_checklist(card_id: str, name: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    params = {"name": name}
    
    checklist = _request("POST", f"cards/{card_id}/checklists", unified_token, params=params)

    return {
        "idboard": checklist.get("idBoard"),
        "idcard": checklist.get("idCard"),
        "idchecklist": checklist.get("id"),
        "checklist_name": checklist.get("name"),
        "metadata": {
            "pos": checklist.get("pos"),
            "checkitems": checklist.get("checkItems")
        }
    }

def trello_list_checklists(card_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
    checklists = _request("GET", f"cards/{card_id}/checklists", unified_token)

    return [
        {
            "idboard": c.get("idBoard"),
            "idcard": c.get("idCard"),
            "idchecklist": c.get("id"),
            "checklist_name": c.get("name"),
            "metadata": {
                "pos": c.get("pos"),
                "checkitems": c.get("checkItems"),
            }
        }
        for c in checklists
    ]


def trello_add_checkitem(checklist_id: str, name: str, pos: Optional[str] = None, checked: Optional[bool] = None, unified_token: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"name": name}
    if pos is not None:
        params["pos"] = pos
    if checked is not None:
        params["checked"] = str(bool(checked)).lower()
    item = _request("POST", f"checklists/{checklist_id}/checkItems", unified_token, params=params)

    return {
        "idchecklist": item.get("idChecklist"),
        "idcheckitem": item.get("id"),
        "checkitem_name": item.get("name"),
        "state": item.get("state"),
        "metadata": {
            "pos": item.get("pos")
        }
    }

def trello_update_checkitem(card_id: str, checkitem_id: str, name: Optional[str] = None, state: Optional[str] = None, pos: Optional[str] = None, unified_token: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if name is not None:
        params["name"] = name
    if state is not None:
        params["state"] = state  # complete | incomplete
    if pos is not None:
        params["pos"] = pos
    
    item = _request("PUT", f"cards/{card_id}/checkItem/{checkitem_id}", unified_token, params=params)

    return {
        "idchecklist": item.get("idChecklist"),
        "idcheckitem": item.get("id"),
        "checkitem_name": item.get("name"),
        "state": item.get("state"),
        "metadata": {
            "pos": item.get("pos")
        }
    }

def trello_delete_checkitem(checklist_id: str, checkitem_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
    _request("DELETE", f"checklists/{checklist_id}/checkItems/{checkitem_id}", unified_token)
    return {
        "idchecklist": checklist_id,
        "idcheckitem": checkitem_id,
    }

# Attachments
def trello_add_attachment_url(card_id: str, url: str, name: Optional[str] = None, unified_token: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"url": url}
    if name:
        params["name"] = name
    attachment = _request("POST", f"cards/{card_id}/attachments", unified_token, params=params)

    return {
        "idcard": attachment.get("idCard"),
        "idattachment": attachment.get("id"),
        "attachment_name": attachment.get("name"),
        "url": attachment.get("url"),
        "isupload": attachment.get("isUpload"),
        "mimetype": attachment.get("mimeType"),
        "metadata": {
            "bytes": attachment.get("bytes"),
            "pos": attachment.get("pos"),
            "idmember": attachment.get("idMember"),
            "date": attachment.get("date"),
            "previews": attachment.get("previews"),
        }
    }


# Custom fields
def trello_set_custom_field(card_id: str, custom_field_id: str, value: Dict[str, Any], unified_token: Optional[str] = None) -> Dict[str, Any]:
    # Per Trello custom fields API, value is a JSON object like {"text": "..."} or {"number": "..."}
    response = _request("PUT", f"cards/{card_id}/customField/{custom_field_id}/item", unified_token, json={"value": value})

    return {
        "idcard": response.get("idModel"),
        "idcustomfield": response.get("idCustomField"),
        "idcustomvalue": response.get("id"),
        "value": response.get("value"),
        "metadata": {
            "modeltype": response.get("modelType"),
            "idplugin": response.get("idPlugin")
        }
    }

# -------------------------
# Name-based resolvers
# -------------------------

def trello_find_board_by_name(name: str, unified_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    boards = trello_list_boards(unified_token)
    lname = name.strip().lower()
    exact = [b for b in boards if b.get("name", "").strip().lower() == lname]
    if exact:
        return exact[0]
    # fallback: startswith/contains
    starts = [b for b in boards if b.get("name", "").strip().lower().startswith(lname)]
    if starts:
        return starts[0]
    contains = [b for b in boards if lname in b.get("name", "").strip().lower()]
    if not contains:
        return None

    board = contains[0]
    return {
        "idboard": board.get("id"),
        "board_name": board.get("name"),
        "url": board.get("url"),
        "closed": board.get("closed", False),
        "pinned": board.get("pinned", False),
        "starred": board.get("starred", False),
        "metadata": {
            "datelastactivity": board.get("dateLastActivity"),
            "short_url": board.get("shortUrl"),
            "prefs": board.get("prefs", {}),
        },
    }


def trello_create_card_by_names(
    board_name: str,
    list_name: str,
    name: str,
    unified_token: Optional[str] = None,
    desc: Optional[str] = None,
    due: Optional[str] = None,
    member_ids: Optional[List[str]] = None,
    label_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Resolve board and list by names, then create a card in that list."""
    board = trello_find_board_by_name(board_name, unified_token)
    if not board:
        return {"status": "error", "message": f"Board not found: {board_name}"}
    lst = trello_find_list_by_name(board.get("idboard"), list_name, unified_token)
    if not lst:
        return {"status": "error", "message": f"List not found on board '{board_name}': {list_name}"}
    return trello_create_card(
        list_id=lst.get("idlist"),
        name=name,
        unified_token=unified_token,
        desc=desc,
        due=due,
        member_ids=member_ids,
        label_ids=label_ids,
    )


def trello_find_list_by_name(board_id: str, list_name: str, unified_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    lists = trello_list_lists(board_id, unified_token)
    lname = list_name.strip().lower()
    exact = [l for l in lists if l.get("name", "").strip().lower() == lname]
    if exact:
        return exact[0]
    starts = [l for l in lists if l.get("name", "").strip().lower().startswith(lname)]
    if starts:
        return starts[0]
    contains = [l for l in lists if lname in l.get("name", "").strip().lower()]
    if not contains:
        return None

    lst = contains[0]
    return {
        "idlist": lst.get("id"),
        "list_name": lst.get("name"),
        "idboard": lst.get("idBoard"),
        "closed": lst.get("closed", False),
        "pos": lst.get("pos"),
        "metadata": {
            "color": lst.get("color"),
            "subscribed": lst.get("subscribed"),
            "softlimit": lst.get("softLimit"),
            "type": lst.get("type"),
        },
    }


# -------------------------
# Extended Card Operations
# -------------------------

# def trello_get_card(card_id: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
#     """Get a card by ID."""
#     card = _request("GET", f"cards/{card_id}", unified_token)

#     return {
#         "idboard": card.get("idBoard"),
#         "idlist": card.get("idList"),
#         "idcard": card.get("id"),
#         "idmember": card.get("idMembers"),
#         "card_name": card.get("name"),
#         "closed": card.get("closed"),
#         "due_date": card.get("due"),
#         "url": card.get("url"),
#         "labels": card.get("labels"),
#         "metadata": {
#             "desc": card.get("desc"),
#             "datelastactivity": card.get("dateLastActivity"),
#             "cover": card.get("cover"),
#             "badges": card.get("badges"),
#             "subscribed": card.get("subscribed"),
#             "pos": card.get("pos")
#         }
#     }


# Comments (Actions)
# def trello_add_comment(card_id: str, text: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
#     """Add a new comment to a card."""
#     params = {"text": text}
#     comment = _request("POST", f"cards/{card_id}/actions/comments", unified_token, params=params)

#     return {
#         "idboard": comment.get("data", {}).get("board", {}).get("id"),
#         "idcard": comment.get("data", {}).get("card", {}).get("id"),
#         "idmember": comment.get("idMemberCreator"),
#         "card_name": comment.get("data", {}).get("card", {}).get("name"),
#         "list_name": comment.get("data", {}).get("list", {}).get("name"),
#         "idcomment": comment.get("id"),
#         "comment_text": comment.get("data", {}).get("text"),
#         "date": comment.get("date"),
#         "fullName": comment.get("memberCreator", {}).get("fullName"),
#         "username": comment.get("memberCreator", {}).get("username"),
#         "board_name": comment.get("data", {}).get("board", {}).get("name"),
#     }

# def trello_update_comment(
#     card_id: str,
#     action_id: str,
#     text: str,
#     unified_token: Optional[str] = None,
# ) -> Dict[str, Any]:
#     """Update an existing comment action on a card."""
#     params = {"text": text}
#     return _request("PUT", f"cards/{card_id}/actions/{action_id}/comments", unified_token, params=params)


# def trello_delete_comment(
#     card_id: str,
#     action_id: str,
#     unified_token: Optional[str] = None,
# ) -> Any:
#     """Delete a comment action from a card."""
#     return _request("DELETE", f"cards/{card_id}/actions/{action_id}/comments", unified_token)


# Members
# def trello_add_members(card_id: str, member_ids: List[str], unified_token: Optional[str] = None) -> List[Any]:
#     """Add one or more members to a card (loops over Trello's single-member endpoint)."""
#     results = []
#     for member_id in member_ids:
#         params = {"value": member_id}
#         results.append(_request("POST", f"cards/{card_id}/idMembers", unified_token, params=params))
#     return results


# def trello_remove_member(card_id: str, member_id: str, unified_token: Optional[str] = None) -> Any:
#     """Remove a member from a card."""
#     return _request("DELETE", f"cards/{card_id}/idMembers/{member_id}", unified_token)


# # Labels
# def trello_add_label(card_id: str, label_id: str, unified_token: Optional[str] = None) -> Any:
#     """Add an existing label to a card."""
#     params = {"value": label_id}
#     return _request("POST", f"cards/{card_id}/idLabels", unified_token, params=params)


# def trello_remove_label(card_id: str, label_id: str, unified_token: Optional[str] = None) -> Any:
#     """Remove a label from a card."""
#     return _request("DELETE", f"cards/{card_id}/idLabels/{label_id}", unified_token)


# def trello_list_board_labels(board_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
#     """List all labels on a board."""
#     return _request("GET", f"boards/{board_id}/labels", unified_token)


# Checklists and items
# def trello_create_checklist(card_id: str, name: str, unified_token: Optional[str] = None) -> Dict[str, Any]:
#     """Create a new checklist on a card."""
#     params = {"name": name}
#     return _request("POST", f"cards/{card_id}/checklists", unified_token, params=params)


# def trello_list_checklists(card_id: str, unified_token: Optional[str] = None) -> List[Dict[str, Any]]:
#     """Get all checklists on a card."""
#     return _request("GET", f"cards/{card_id}/checklists", unified_token)


# def trello_add_checkitem(
#     checklist_id: str,
#     name: str,
#     pos: str | None = None,
#     checked: bool | None = None,
#     unified_token: Optional[str] = None,
# ) -> Dict[str, Any]:
#     """Add a check item to a checklist."""
#     params: Dict[str, Any] = {"name": name}
#     if pos:
#         params["pos"] = pos
#     if checked is not None:
#         params["checked"] = str(bool(checked)).lower()
#     return _request("POST", f"checklists/{checklist_id}/checkItems", unified_token, params=params)


# def trello_update_checkitem(
#     card_id: str,
#     checkitem_id: str,
#     name: Optional[str] = None,
#     state: Optional[str] = None,  # "complete" or "incomplete"
#     pos: Optional[str] = None,
#     unified_token: Optional[str] = None,
# ) -> Dict[str, Any]:
#     """Update a check item on a card."""
#     params: Dict[str, Any] = {}
#     if name is not None:
#         params["name"] = name
#     if state is not None:
#         params["state"] = state
#     if pos is not None:
#         params["pos"] = pos
#     return _request("PUT", f"cards/{card_id}/checkItem/{checkitem_id}", unified_token, params=params)


# def trello_delete_checkitem(checklist_id: str, checkitem_id: str, unified_token: Optional[str] = None) -> Any:
#     """Delete a check item from a checklist."""
#     return _request("DELETE", f"checklists/{checklist_id}/checkItems/{checkitem_id}", unified_token)


# Attachments
# def trello_add_attachment_url(card_id: str, url: str, name: Optional[str] = None, unified_token: Optional[str] = None) -> Dict[str, Any]:
#     """Attach a URL to the card (file upload not handled here)."""
#     params: Dict[str, Any] = {"url": url}
#     if name:
#         params["name"] = name
#     return _request("POST", f"cards/{card_id}/attachments", unified_token, params=params)


# # Custom Fields
# def trello_set_custom_field(
#     card_id: str,
#     custom_field_id: str,
#     value: Dict[str, Any],
#     unified_token: Optional[str] = None,
# ) -> Any:
#     """Set a custom field value on a card. `value` must follow Trello's expected structure for the field type."""
#     return _request(
#         "PUT",
#         f"cards/{card_id}/customField/{custom_field_id}/item",
#         unified_token,
#         json={"value": value},
#     )
