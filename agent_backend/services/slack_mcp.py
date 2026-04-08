import uuid
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import time
import requests
from clients.db_method import get_user_tool_access_token
from db.mongo_client import get_mongo_client

def generate_slack_message_id() -> str:
    """
    Generate a UUID-based message ID in the format: slack-msg-{uuid}
    This matches the format used in MongoDB for consistency.
    """
    return {"id": str(uuid.uuid4())}

# Get MongoDB client from centralized configuration
mongo_client = get_mongo_client()

def get_slack_client(token):
    # print("Unified_token------------",token)
    print("I am here in get_slack_client")
    tool_name = "Slack"
    # result = get_tool_token(token)
    result, status = get_user_tool_access_token(token, tool_name)
    
    # Check if credentials exist before accessing
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Slack credentials") if isinstance(result, dict) else "Failed to retrieve Slack credentials"
        raise Exception(f"Failed to retrieve Slack credentials. Please connect Slack. {error_msg}")
    
    access_token = result.get("access_token", "")
    # print("access_token", access_token)
    if access_token is None:
        raise Exception("Slack access token is None.")
    # Handle both {"secret": "..."} and direct string
    if isinstance(access_token, dict) and access_token.get("secret"):
        slack_token = access_token["secret"]
        # print("slack_token from dict", slack_token)
    elif isinstance(access_token, str):
        slack_token = access_token
        # print("slack_token from str", slack_token)
    else:
        raise Exception("Slack access token format invalid.")
    # if isinstance(access_token, dict) and "secret" in access_token:
    #     slack_token = access_token["secret"]
    #     print("slack_token from dict", slack_token)
    # elif isinstance(access_token, str):
    #     slack_token = access_token
    #     print("slack_token from str", slack_token)
    # else:
    #     raise Exception("Slack access token format invalid.")
    client = WebClient(token=slack_token)
    response = client.auth_test()
    # print("response------------",response)
    return (client, response)

# Caching setup
user_cache = {"data": {}, "last_updated": 0}
channel_cache = {"data": {}, "last_updated": 0}
CACHE_TTL = 300  # 5 minutes

def refresh_channel_cache(token):
    print("I am here refresh_channel_cache")
    data_b= mongo_client["unified_workspace"]
    users_collection = data_b["users"]
    client, response = get_slack_client(token)
    # print (response)
    slack_user_id=response["user_id"]
    user_name=response["user"]
    # print(" Authenticated as user:", response)
    doc1 = users_collection.find_one({"slack_user_id": str(slack_user_id)})
    if doc1 and "slack_user_id" in doc1:
        user_id_db = doc1["user_id"]
    # print("user_id_db",user_id_db)
    db = mongo_client[user_id_db]
    # Use slack_channels collection (new schema)
    slack_channels_col = db["slack_channels"]
    # Reset cache before rebuilding
    channel_cache["data"] = {}
    
    for doc in slack_channels_col.find({}):

        channel_id = doc.get("channel_id")
        channel_name = doc.get("name") or ""
        
        if channel_id and channel_name:
            channel_cache["data"][channel_id] = channel_name

    # print("Final channel cache:", channel_cache)
    return channel_cache       
     
def list_channels(token: str = None):
    print("I am here in list channels")
    # print("Token---------",token)
    refresh_channel_cache(token)
    # print("channel_list",channel_cache)
    return {
        "channels": [
            {"id": channel_id, "name": channel_name} 
            for channel_id, channel_name in channel_cache["data"].items()
        ]
    }

def refresh_user_cache(token):
    """
    Refresh the user cache by fetching all users from Slack.
    Args:
        token: Authentication token (required)
    """
    if not token:
        print("  ⚠️ Cannot refresh user cache: token is None")
        return
    
    try:
        client, response = get_slack_client(token)
        response = client.users_list()
        # print("Users fetched:", response)
        user_cache["data"] = {
            user["id"]: {
                "id": user["id"],
                "name": user["name"],
                "real_name": user.get("real_name", user["name"]),
                "email": user.get("profile", {}).get("email", "")
            }
            for user in response["members"]
        }
        
        user_cache["last_updated"] = time.time()
        # print(f"  ✅ User cache refreshed with {len(user_cache['data'])} users")
    except SlackApiError as e:
        print(f"  ❌ Failed to refresh user cache: {str(e)}")
    except Exception as e:
        print(f"  ❌ Error refreshing user cache: {str(e)}")

def list_users(token: str = None):
    refresh_user_cache(token)
    
    return {
        "users": [
            {"name": udata["real_name"]} for udata in user_cache["data"].values()
        ]
    }

# def refresh_channel_cache1(token):
#     print("I am here")
#     client,response = get_slack_client(token)
    
#     try:

#         response = client.conversations_list()
#         channel_cache["data"] = {c["name"]: c["id"] for c in response["channels"]}
#         channel_cache["last_updated"] = time.time()
#     except SlackApiError as e:
#         print("Failed to refresh channel cache:", str(e))

def get_all_channel_ids(token: str = None, channel: str = None, user_name: str = None, slack_user_id: str = None):
    """
    Extract all channel IDs from the slack_channel_info collection for the authenticated user.
    """
    # client, response = get_slack_client(token)
    # print("Fetching all channel IDs...", channel, user_name, slack_user_id)
    channel_name=channel

    data_b = mongo_client["unified_workspace"]
    users_collection = data_b["users"]
    doc = users_collection.find_one({"slack_user_id": str(slack_user_id)})
    if not doc or "user_id" not in doc:
        return []

    user_id_db = doc["user_id"]
    db = mongo_client[user_id_db]
    slack_channel_info = db["slack_channel_info"]

    channels = []
    for info_doc in slack_channel_info.find():
        for channel_info in info_doc.get("channel_info_details", []):
            channel_id = channel_info.get("id")
            channel_members = channel_info.get("member_names", [])
            if channel_id:
                channels.append({
                    "channel_id": channel_id,
                    "members": channel_members
                })

    non_c_channels = [ch for ch in channels if not ch["channel_id"].lower().startswith("c")]
    # for channel in non_c_channels:
    #     if channel_name in channel["members"]:
    #         return True
    channel_id= [ch["channel_id"] for ch in non_c_channels if channel_name in ch["members"]]

    # return False
    # print(non_c_channels)
    return channel_id

def send_slack_messages(channel: str, message: str, token: str = None):
    client,response = get_slack_client(token)
    user_name=response["user"]
    slack_user_id = response["user_id"]
    # channel = "get_channel_id(channel,token)"
    channel_test= get_all_channel_ids(token,channel,user_name,slack_user_id)
    # print("channel_test", channel_test)
    # channel="D095T47DHJB"
    try:
        uu_id=str(uuid.uuid4())
        # print("Slack Message ID----------", uu_id)
        message_id = uu_id
        response = client.chat_postMessage(channel=channel, text=message, client_msg_id=message_id)
        return {
            "status": "success", 
            "message_ts": response["ts"],
            "id": message_id,  # UUID-based message ID
            "channel": channel
        }
    except SlackApiError as e:
        last_error = str(e)
        # Try fallback channels if the first attempt fails
        for ch in channel_test:
            try:
                message_id = generate_slack_message_id()
                resp = client.chat_postMessage(channel=ch, text=message, client_msg_id=message_id)
                return {
                    "status": "success", 
                    "message_ts": resp["ts"], 
                    "id": message_id,  # UUID-based message ID
                    "channel": ch
                }
            except SlackApiError as e2:
                last_error = str(e2)
                continue
        # If all attempts fail
        return {"status": "error", "message": last_error}
    # except SlackApiError as e:
        # return {"status": "error", "message": str(e)}
    
def get_user_id_from_name(user_name: str, token: str = None) -> str:
    """
    Find a Slack user ID from a user's name (real_name, name, or ID).
    Supports exact and partial name matching.
    Returns the user ID if found, None otherwise.
    """
    if not token:
        print(f"  ⚠️ Cannot find user '{user_name}': token is None")
        return None
    
    # Refresh user cache if needed
    if time.time() - user_cache["last_updated"] > CACHE_TTL or not user_cache["data"]:
        refresh_user_cache(token)
    
    user_name_lower = user_name.lower().strip()
    
    # First, try exact matches (case-insensitive)
    user_id = None
    for uid, udata in user_cache["data"].items():
        real_name = udata.get("real_name", "").lower()
        name = udata.get("name", "").lower()
        uid_lower = uid.lower()
        
        # Exact match
        if (real_name == user_name_lower or 
            name == user_name_lower or 
            uid_lower == user_name_lower):
            user_id = uid
            print(f"  ✅ Found exact match: '{user_name}' -> ID: {user_id}")
            break
    
    # If no exact match, try partial matches (name contains the search term)
    if not user_id:
        for uid, udata in user_cache["data"].items():
            real_name = udata.get("real_name", "").lower()
            name = udata.get("name", "").lower()
            
            # Check if search term is contained in real_name or name
            if (user_name_lower in real_name or 
                user_name_lower in name):
                user_id = uid
                print(f"  ✅ Found partial match: '{user_name}' -> '{udata.get('real_name', udata.get('name'))}' (ID: {user_id})")
                break
    
    if not user_id:
        print(f"  ⚠️ User '{user_name}' not found in cache")
        print(f"  💡 Available users: {', '.join([udata.get('real_name', udata.get('name', 'Unknown')) for udata in list(user_cache['data'].values())[:10]])}")
    
    return user_id

def get_current_user_dm_channel(token: str = None) -> dict:
    """
    Get the current authenticated user's direct message channel ID.
    This opens a DM with the user themselves.
    Args:
        token: Authentication token
    Returns:
        dict with channel_id or error status
    """
    if not token:
        return {"status": "error", "message": "Authentication token is required"}
    
    client, auth_response = get_slack_client(token)
    current_user_id = auth_response.get("user_id")
    
    if not current_user_id:
        return {"status": "error", "message": "Could not determine current user ID"}
    
    try:
        # Open DM with the current user (themselves)
        response = client.conversations_open(users=current_user_id)
        channel_id = response["channel"]["id"]
        print(f"  ✅ Current user DM channel: {channel_id}")
        return {"channel_id": channel_id}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}

def open_dm_with_user(user: str, token: str = None):
    """
    Open a direct message channel with a user.
    Args:
        user: User's name (real_name, name), user ID, or special value "me" to open DM with current user
        token: Authentication token
    """
    # Special case: "me" means send to current user's DM
    if user.lower() in ["me", "myself", "my chat", "my dm", "to me"]:
        return get_current_user_dm_channel(token)
    
    client, response = get_slack_client(token)
    
    # Find user ID from name
    user_id = get_user_id_from_name(user, token)
    if not user_id:
        return {"status": "error", "message": f"User '{user}' not found. Please use the user's display name as shown in Slack."}
    
    try:
        response = client.conversations_open(users=user_id)
        return {"channel_id": response["channel"]["id"]}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}
    

# def get_channel_id(channel_name: str, token: str = None) -> str:
#     if time.time() - channel_cache["last_updated"] > CACHE_TTL:
#         refresh_channel_cache1(token)
#     return channel_cache["data"].get(channel_name, channel_name)

def get_channel_id_from_list(channel_name, channel_list):
    # print ("--------------------------------------",channel_name, channel_list)
    for channel in channel_list["channels"]:
        if channel["name"] == channel_name or channel["id"] == channel_name:
            return channel["id"]
    return None  # Not found

def send_dm(user: str, message: str, token: str = None):
    """
    Send a direct message to a user.
    Args:
        user: User's name (real_name, name) or user ID
        message: Message text to send
        token: Authentication token
    """
    if not token:
        return {"status": "error", "message": "Authentication token is required"}
    
    client, response = get_slack_client(token)
    print(f"  📤 Sending DM to '{user}'")
    
    # Open DM channel with user
    dm = open_dm_with_user(user, token)
    
    # Check if DM was opened successfully
    if "status" in dm and dm["status"] == "error":
        return dm  # Return the error from open_dm_with_user
    if "channel_id" not in dm:
        return {"status": "error", "message": "Unable to open DM channel"}
    
    try:
        uu_id=str(uuid.uuid4())
        # print("Slack Message ID----------", uu_id)
        # message_id = generate_slack_message_id()
        message_id = uu_id
        response1 = client.chat_postMessage(channel=dm["channel_id"], text=message, client_msg_id=uu_id)
        print(f"  ✅ DM sent successfully to channel {dm['channel_id']}")
        # print("Slack Message ID----------", response1)
        return {
            "status": "success", 
            "message_ts": response1["ts"], 
            "id": f"slack-msg-{uu_id}",  # UUID-based message ID
            "channel_id": dm["channel_id"]
        }
    except SlackApiError as e:
        print(f"  ❌ Error sending DM: {str(e)}")
        return {"status": "error", "message": str(e)}

def get_dm_messages(user: str, limit: int = 10, token: str = None):
    """
    Retrieve the latest messages from a direct message (DM) conversation with a user.
    Args:
        user: User's name (real_name, name), user ID, or special value "me" to get current user's DM
        limit: Maximum number of messages to retrieve (default: 10)
        token: Authentication token
    Returns:
        dict with messages list or error status
    """
    if not token:
        return {"status": "error", "message": "Authentication token is required"}
    
    # print(f"  📥 Fetching DM messages with '{user}'")
    
    # Open DM channel with user
    dm = open_dm_with_user(user, token)
    
    # Check if DM was opened successfully
    if "status" in dm and dm["status"] == "error":
        return dm  # Return the error from open_dm_with_user
    if "channel_id" not in dm:
        return {"status": "error", "message": "Unable to open DM channel"}
    
    # Get the DM channel ID
    dm_channel_id = dm.get("channel_id")
    # print(f"  ✅ DM channel ID: {dm_channel_id}")
    
    # Use slack_get_channel_messages with the DM channel ID
    # Note: slack_get_channel_messages should handle DM channel IDs
    # Directly fetch messages using your fixed function
    return slack_get_channel_messages(
        dm_channel_id,
        limit=limit,
        token=token
    )

def get_user_name_from_id(user_id: str, user_cache_data: dict = None) -> str:
    """
    Resolve a Slack user ID to the user's real name.
    Returns the user ID if name cannot be resolved.
    
    Args:
        user_id: The Slack user ID to resolve
        user_cache_data: Pre-fetched user cache data (optional, for efficiency)
    """
    if not user_id:
        return user_id
    
    # Use provided cache or global cache
    cache = user_cache_data if user_cache_data is not None else user_cache["data"]
    
    # Debug logging
    # print(f"  🔍 Resolving user ID: {user_id}")
    print(f"  📊 Cache size: {len(cache)} users")
    
    # Try to get real_name from cache
    user_data = cache.get(user_id)
    if user_data:
        name = user_data.get("real_name", user_data.get("name", user_id))
        print(f"  ✅ Resolved {user_id} -> {name}")
        return name
    
    # Fallback: return the user_id if not found
    print(f"  ⚠️ User ID {user_id} not found in cache, returning ID")
    return user_id

def slack_get_channel_messages(channel: str, limit: int = 10, token: str = None, order: str = "desc"):
    # print("Token_______________",token)
    # print("owner_id--------", owner_id)
    print("I am here in slack_get_channel_messages")
    try:
        data_b= mongo_client["unified_workspace"]
        users_collection = data_b["users"]
        # print(f"Received arguments: channel={channel}, limit={limit}, token={token}, order={order}")
        # channel_id = get_channel_id(channel, token)
        channel_id = channel
        
        # Check if channel is already a channel ID (starts with C, D, or G)
        # C = public channel, D = DM, G = private channel/group
        is_channel_id = channel.startswith(("C", "D", "G"))
        
        if is_channel_id:
            # Already a channel ID, use it directly (especially for DM channels)
            print(f"  ✅ Channel is already an ID: {channel_id}")
        else:
            # Try to resolve channel ID from channel name
            # print(f"Looking for channel: {channel}")
            channel_list = list_channels(token)
            # print(f"Channel list retrieved, found {len(channel_list.get('channels', []))} channels")
            
            # Resolve channel ID from channel name or ID
            channel_id = get_channel_id_from_list(channel, channel_list)
            # print(f"Resolved channel ID: {channel_id}")
            if not channel_id:
                return {"status": "error", "message": "Channel not found."}
        
        # print(f"Resolved channel ID: {channel_id}")
        client,response = get_slack_client(token)
        print("Slack client authenticated successfully")
        # print("client", client)
        # print("response", response)
        # response = client.auth_test()
        # print(" Authenticated as user:", response)
        
        slack_user_id=response["user_id"]
        print(f"Slack user ID: {slack_user_id}")
        # user_name=response["user"]
        # refresh_channel_cache1(token)
        doc = users_collection.find_one({"slack_user_id": str(slack_user_id)})
        if not doc or "user_id" not in doc:
            # print("User not found in database")
            return {"status": "error", "message": "User not found in database."}
        
        user_id_db = doc["user_id"]
        # print(f"User DB: {user_id_db}")
        # print("user_id_db",user_id_db)
        db = mongo_client[user_id_db]
        slack_history = db["slack_messages"]
        
        # Find the document with channel messages
        messages_doc = None
        for doc in slack_history.find():
            messages_doc = doc
            break  # Get the first document
        
        if not messages_doc:
            # print("No channel messages document found")
            return {"status": "error", "message": "No channel messages found in database."}
        
        print(f"Found messages document with {len(messages_doc.get('channel_info_details', []))} channel info details")

        # Refresh user cache once for efficient lookups
        # print("  🔄 Refreshing user cache...")
        refresh_user_cache(token)
        user_cache_data = user_cache["data"]
        # Fetch messages directly by channel_id
        cursor = slack_history.find({"channel_id": channel_id})
        print(f"Querying messages for channel_id: {channel_id}")
        messages = list(cursor)

        print(f"Found {len(messages)} messages in channel")

        if not messages:
            return {
                "success": True,
                "type": "messages",
                "data": [],
                "ui_hint": "slack_panel",
                "message": "No messages found in this channel."
            }

        # Sort messages by timestamp
        messages_sorted = sorted(
            messages,
            key=lambda x: float(x.get("ts", 0)),
            reverse=True
        )

        latest_messages = messages_sorted[:limit]

        messages_list = []

        for msg in latest_messages:

            sender_name = msg.get("userName") or "Unknown"
            sender_id = msg.get("userId")

            messages_list.append({
                "id": msg.get("messageId"),
                "time": float(msg.get("ts", 0)),
                "sender": sender_name,
                "content": msg.get("content"),
                "channel_id": msg.get("channel_id"),
                "sender_id": sender_id,
                "channel_name": msg.get("channel_name") or msg.get("channelName")
            })
        
        # print("Final messages list:", messages_list)
        return {"messages": messages_list}
    except Exception as e:
        print(f"Error in slack_get_channel_messages: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)} 

def get_channel_members(channel_id,token: str = None):
    client,response = get_slack_client(token)
    try:
        data_b= mongo_client["unified_workspace"]
        users_collection = data_b["users"]
        # client = get_slack_client(token)
        # response = client.auth_test()
        client, response = get_slack_client(token)
        # print(" Authenticated as user:", response)
        slack_user_id=response["user_id"]
        user_name=response["user"]
        doc = users_collection.find_one({"slack_user_id": str(slack_user_id)})
        if doc and "slack_user_id" in doc:
            user_id_db = doc["user_id"]
        # print("user_id_db",user_id_db)
        db = mongo_client[user_id_db]
        slack_channel_details= db["slack_channels"]
        # Fetch the channel document directly
        channel_doc = slack_channel_details.find_one({
                "$or": [
                    {"channel_id": channel_id},
                    {"name": channel_id}
                ]
            })

        if not channel_doc:
            return {
                "status": "error",
                "message": "Channel not found"
            }

        members = channel_doc.get("members", [])

        # Extract only member names
        member_names = []

        for member in members:
            name = member.get("user_name")
            if name:
                member_names.append(name)
        return {"members": member_names}
            # user_cache[channel_id] = members_name
            # print("user_cache------------", user_cache)
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}
    
def get_user_info(token: str = None, channel: str = None):
    
    try:
        client,response = get_slack_client(token)
        return {
            "user_info": {
                "user_id": response.data["user_id"],
                "user_name": response.data["user"],
                "team": response.data.get("team")
            }
        }
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}


def create_channel(name: str, is_private: bool = False, token: str = None):

    client,response= get_slack_client(token)
    try:
        response1 = client.conversations_create(name=name, is_private=is_private)
        return {"channel": response1["channel"]}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}


def archive_channel(channel: str, token: str = None):
    # print("I am here in archive_channel-------------",channel)
    client,response = get_slack_client(token)
    try:
        client.conversations_archive(channel=channel)
        return {"status": "success"}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}
    
def invite_user_to_channel(channel: str, user: str, token: str = None):
    client,response = get_slack_client(token)
    # channel = list_channels(token)
    channel_list = list_channels(token)
    channel_id = get_channel_id_from_list(channel, channel_list)
    # print ("channel_id--------------------", channel_id)
    # print(f"Channel list : {channel_list}")
    if not channel_id:
        return {"status": "error", "message": "Channel not found."}
    # Refresh and use user_cache to get user ID by name
    refresh_user_cache(token)
    # print("user_cache", user_cache)
    
    user_input = user.strip().lower()
    input_first = user_input.split()[0]
    matches = []
    user_id = None
    is_email = "@" in user_input

    for uid, udata in user_cache["data"].items():
        real_name = udata.get("real_name", "").strip().lower()
        username = udata.get("name", "").strip().lower()
        email = udata.get("email", "").strip().lower()

        real_first = real_name.split()[0] if real_name else ""
        user_first = username.split(".")[0] if username else ""
        
        # exact match first
        if is_email:
            if email == user_input:
                user_id = uid
                break
        else:
            if (
                real_name == user_input
                or username == user_input
                or uid.lower() == user_input
            ):
                user_id = uid
                break
            # first-name fallback
            if (
                real_first == input_first
                or user_first == input_first
            ):
                matches.append({
                    "id": uid,
                    "name": udata.get("real_name") or udata.get("name")
                })
                
            # loose match
            if (
                user_input in real_name
                or user_input in username
                or real_name.startswith(user_input)
                or username.startswith(user_input)
            ):
                matches.append({
                    "id": uid,
                    "name": udata.get("real_name") or udata.get("name")
                })

    # if no exact match found
    if not user_id:
        if len(matches) == 1:
            user_id = matches[0]["id"]

        elif len(matches) > 1:
            return {
                "status": "error",
                "message": "Multiple users found. Please specify which user to add.",
                "matches": [m["name"] for m in matches]
            }

        else:
            return {
                "status": "error",
                "message": f"User '{user}' not found in workspace."
            }
    
    try:
        # print(f"userid{user_id}")
        client.conversations_invite(channel=channel_id, users=user_id)
        return {"status": "success"}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}
    

def kick_user_from_channel(channel: str, user: str, token: str = None):
    client,response = get_slack_client(token)
    refresh_user_cache(token)
    channel_list = list_channels(token)
    channel_id = get_channel_id_from_list(channel, channel_list)
    # print ("channel_id--------------------", channel_id)
    if not channel_id:
        return {"status": "error", "message": "Channel not found."}
    # print("user_cache", user_cache)
    user_id = None
    for uid, udata in user_cache["data"].items():
        if udata["real_name"] == user or udata["name"] == user or uid == user:
            user_id = uid
            # print("User ID found:------------", user_id)
            break
    if not user_id:
        return {"status": "error", "message": "User not found."}
    channel = channel_id
    user = user_id
    try:
        client.conversations_kick(channel=channel, user=user)
        return {"status": "success"}
    except SlackApiError as e:
        error_message = str(e)
        if "'error': 'restricted_action'" in error_message:
            return {
                "status": "error",
                "message": "You do not have permission to remove this user from the channel. Please ensure you are an admin or have the required privileges."
            }
        return {"status": "error", "message": error_message}
    
from datetime import datetime
def pin_message(channel: str, timestamp: str, token: str = None):
    if isinstance(timestamp, (int, float)) or (isinstance(timestamp, str) and timestamp.replace('.', '', 1).isdigit()):
        timestamp1=timestamp
    else:
        timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        timestamp1=timestamp.timestamp()
    
    # print("timestamp---------------------",timestamp1)
    # dt = pin_message(channel, timestamp)
    # print("dt",dt)
    client,response = get_slack_client(token)
    channel_list = list_channels(token)
    channel_id = get_channel_id_from_list(channel, channel_list)
    # channel = get_channel_id(channel,token)
    try:
        client.pins_add(channel=channel_id, timestamp=timestamp1)
        return {"status": "success"}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}

def unpin_message(channel: str, timestamp: str, token: str = None):
    client,response = get_slack_client(token)
    channel_list = list_channels(token)
    channel_id = get_channel_id_from_list(channel, channel_list)
    try:
        client.pins_remove(channel=channel_id, timestamp=timestamp)
        return {"status": "success"}
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}
    
def slack_reply_message(token, channel: str, timestamp: float, message: str):
    """Reply to a thread in Slack."""
    client,response = get_slack_client(token)
    channel_list = list_channels(token)
    channel_id = get_channel_id_from_list(channel, channel_list)
    
    try:
        message_id = generate_slack_message_id()
        response = client.chat_postMessage(
            channel=channel_id, 
            text=message, 
            thread_ts=timestamp, 
            client_msg_id=message_id
        )
        return {
            "status": "success", 
            "message_ts": response["ts"],
            "id": message_id  # UUID-based message ID
        }
    except SlackApiError as e:
        return {"status": "error", "message": str(e)}