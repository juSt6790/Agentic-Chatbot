"""
MongoDB Personalization Client

This module provides functions to interact with the personalization collection
in MongoDB, which stores user communication personality profiles derived from
emails and Slack messages.
"""

import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from pymongo import MongoClient

from db.mongo_client import get_mongo_client
from clients.db_method import validate_user_tool_access, get_user_id_from_token

# Get MongoDB client
mongo_client = get_mongo_client()


def get_personality_collection(unified_token: str) -> Any:
    """
    Return the per-tenant personality collection for the provided token.
    Note: Personality is derived from Gmail/Slack, so we validate Gsuite access.
    """
    # Validate user has access to Gsuite (needed for personality extraction from emails)
    is_valid, error_msg, status_code = validate_user_tool_access(unified_token, "Gsuite")
    if not is_valid:
        raise PermissionError(f"Personality access denied: {error_msg}")
    
    user_id, status = get_user_id_from_token(unified_token)

    if status != 200 or not user_id:
        return None

    return mongo_client[user_id]["personality"]

def get_user_profile_collection(unified_token: str) -> Optional[Dict[str, Any]]:
    """
    Return the user profile document for the provided token.
    Note: Profile data is stored in unified_workspace and doesn't require specific tool validation.
    """
    try:
        user_id, status = get_user_id_from_token(unified_token)

        if status != 200 or not user_id:
            return None

        # Get user document from users collection
        user_doc = mongo_client["unified_workspace"]["users"].find_one({"user_id": user_id})
        
        if not user_doc:
            return None
        
        # Get profile_id from user document
        profile_id = user_doc.get("profile_id")
        
        if not profile_id:
            return None
        
        # print(f"Profile ID: {profile_id}")
        
        # Get the profile document - adjust the field name based on your schema
        # If profile_id is a dict with nested 'profile' field, use: profile_id.get("profile")
        # If profile_id is already the ID string, use: profile_id
        profile_doc = mongo_client["unified_workspace"]["profiles"].find_one({"profile": profile_id})
        
        if profile_doc:
            # Remove MongoDB _id field for cleaner output
            profile_doc.pop("_id", None)
            # Timezone is stored on `users`, not always on `profiles`; merge so callers see it.
            user_tz = user_doc.get("timezone")
            if user_tz:
                profile_doc["timezone"] = user_tz
            # print("doc: ", profile_doc)
            return profile_doc
        
        return None
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        return None


def get_user_personality(unified_token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve personality profile for a user.
    
    Args:
        unified_token: The unified token
    
    Returns:
        Personality profile dictionary or None if not found
    """
    try:
        collection = get_personality_collection(unified_token)
        
        if collection is None:
            return None
        
        # Get the latest personality document (sorted by updated_at descending)
        result = collection.find_one({}, sort=[("updated_at", -1)])
        
        if result:
            # Remove MongoDB _id field for cleaner output
            result.pop("_id", None)
            return result
        
        return None
    except Exception as e:
        return None


def save_user_personality(
    unified_token: str,
    personality_profile: Dict[str, Any],
    source: str = "manual",
    num_emails_analyzed: int = 0,
    user_email: str = None,
    num_slack_messages_analyzed: int = 0,
) -> bool:
    """
    Save or update a user's personality profile.
    
    Args:
        unified_token: The unified token
        personality_profile: The personality profile dictionary
        source: Source of the profile (e.g., 'sent_emails', 'sent_emails_and_slack', 'manual')
        num_emails_analyzed: Number of emails used for analysis
        num_slack_messages_analyzed: Number of Slack messages used for analysis
        user_email: Optional user email for reference
    
    Returns:
        True if successful, False otherwise
    """
    try:
        collection = get_personality_collection(unified_token)
        
        if collection is None:
            return False
        
        document = {
            "personality_profile": personality_profile,
            "updated_at": datetime.now(),
            "source": source,
            "num_emails_analyzed": num_emails_analyzed,
            "num_slack_messages_analyzed": num_slack_messages_analyzed,
        }
        
        if user_email:
            document["user_email"] = user_email
        
        # Update existing or insert new (should only be one document per user)
        result = collection.update_one(
            {},
            {
                "$set": document,
                "$setOnInsert": {"created_at": datetime.now(), "version": "1.0"}
            },
            upsert=True
        )
        
        return True
    except Exception as e:
        return False
