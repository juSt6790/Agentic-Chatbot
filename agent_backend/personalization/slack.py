"""
Slack Message Extraction Script

This script extracts Slack messages sent by a specific user from MongoDB.
It properly matches owner_names with message sender fields to identify user's messages.
"""

import os
import sys
from typing import List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path to import mcp_gmail modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mongo_client import get_mongo_client

load_dotenv()

# Configuration
NUM_SLACK_MESSAGES = 100  # Number of Slack messages to extract


def get_user_id_from_token(unified_token: str) -> str:
    """
    Get user_id from unified token.
    
    Args:
        unified_token: The unified token
    
    Returns:
        user_id string or None
    """
    mongo_client = get_mongo_client()
    db = mongo_client["unified_workspace"]
    auth_token_collection = db["user_authenticate_token"]
    
    auth_entry = auth_token_collection.find_one(
        {"tool_token": unified_token, "tool_name": "unified"}
    )
    
    if not auth_entry:
        return None
    
    return auth_entry["user_id"]


def get_slack_messages(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Query MongoDB for Slack messages sent by a specific user.
    Uses owner_names from the document to match against message sender field.
    
    Args:
        user_id: The user's database ID
        limit: Maximum number of messages to retrieve
    
    Returns:
        List of message dictionaries with full details, sorted by time descending
    """
    print(f"  🔍 Fetching Slack messages for user_id: {user_id}")
    
    mongo_client = get_mongo_client()
    
    try:
        db = mongo_client[user_id]
        collection = db["slack_channel_messages"]
        
        # Get the document containing all channel info
        slack_doc = collection.find_one({})
        
        if not slack_doc:
            print(f"    ⚠️ No Slack data found for user {user_id}")
            return []
        
        # Extract owner_names from the document for accurate sender matching
        owner_names = slack_doc.get("owner_names", [])
        if not owner_names:
            print(f"    ⚠️ No owner_names found in Slack document")
            return []
        
        print(f"    📝 Owner names: {owner_names}")
        
        messages = []
        channel_info_details = slack_doc.get("channel_info_details", [])
        
        # Iterate through all channels
        for channel_info in channel_info_details:
            channel = channel_info.get("channel", {})
            channel_name = channel.get("name", "unknown")
            channel_id = channel.get("id", "")
            
            channel_messages = channel.get("messages", {}).get("messages", [])
            
            # Filter messages sent by the user (match sender with owner_names)
            for msg in channel_messages:
                sender = msg.get("sender", "")
                content = msg.get("content", "")
                time = msg.get("time", 0)
                
                # Match sender name with any of the owner_names (case-insensitive)
                if any(sender.lower() == owner.lower() for owner in owner_names) and content:
                    message_data = {
                        "content": content,
                        "sender": sender,
                        "time": time,
                        "channel_name": channel_name,
                        "channel_id": channel_id,
                        "message_id": msg.get("id"),
                        "conversation_id": msg.get("conversationId"),
                        "reactions": msg.get("reactions", []),
                        "thread": msg.get("thread", "False"),
                        "thread_messages": msg.get("thread_message", [])
                    }
                    messages.append(message_data)
                    
                    if len(messages) >= limit:
                        break
            
            if len(messages) >= limit:
                break
        
        # Sort messages by time (descending - newest first)
        messages.sort(key=lambda x: x.get("time", 0), reverse=True)
        
        print(f"    ✅ Found {len(messages)} Slack messages from {owner_names}")
        return messages[:limit]
        
    except Exception as e:
        print(f"    ❌ Error accessing Slack messages: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_message_contents(messages: List[Dict[str, Any]]) -> List[str]:
    """
    Extract just the content strings from message dictionaries.
    
    Args:
        messages: List of message dictionaries
    
    Returns:
        List of message content strings
    """
    return [msg.get("content", "") for msg in messages if msg.get("content")]


def main():
    """Main execution function - extracts Slack messages for a user"""
    print("\n" + "=" * 60)
    print("💬 SLACK MESSAGE EXTRACTION")
    print("=" * 60)
    
    # TODO: Replace with actual unified token
    UNIFIED_TOKEN = "448b3cd8-fe81-4f97-bd5a-0ef6d0e5d7ef"  # <-- PASTE YOUR UNIFIED TOKEN HERE
    
    if not UNIFIED_TOKEN or UNIFIED_TOKEN == "":
        print("❌ Please set UNIFIED_TOKEN in the script")
        print("   Edit line 157 and paste your unified token")
        return
    
    # Get user_id from token
    print(f"\n🔍 Getting user_id from token...")
    user_id = get_user_id_from_token(UNIFIED_TOKEN)
    
    if not user_id:
        print("❌ Could not find user_id for the provided token")
        return
    
    print(f"✅ User ID: {user_id}")
    
    # Extract Slack messages
    print(f"\n💬 Extracting up to {NUM_SLACK_MESSAGES} Slack messages...")
    messages = get_slack_messages(user_id, NUM_SLACK_MESSAGES)
    
    if not messages:
        print("❌ No Slack messages found")
        return
    
    print(f"\n✅ Successfully extracted {len(messages)} messages")
    
    # Display sample messages
    print("\n" + "=" * 60)
    print("📝 SAMPLE MESSAGES (First 5)")
    print("=" * 60)
    
    for i, msg in enumerate(messages[:5], 1):
        print(f"\n--- Message {i} ---")
        print(f"Channel: {msg.get('channel_name')}")
        print(f"Sender: {msg.get('sender')}")
        print(f"Time: {datetime.fromtimestamp(msg.get('time', 0))}")
        print(f"Content: {msg.get('content')[:100]}...")  # First 100 chars
        print(f"Reactions: {len(msg.get('reactions', []))} reactions")
    
    # Extract just content for analysis
    message_contents = extract_message_contents(messages)
    
    print("\n" + "=" * 60)
    print("📊 STATISTICS")
    print("=" * 60)
    print(f"Total messages: {len(messages)}")
    print(f"Messages with content: {len(message_contents)}")
    if message_contents:
        avg_length = sum(len(c) for c in message_contents) / len(message_contents)
        print(f"Average message length: {avg_length:.1f} characters")
    
    # Count messages per channel
    channels = {}
    for msg in messages:
        channel = msg.get('channel_name', 'unknown')
        channels[channel] = channels.get(channel, 0) + 1
    
    print(f"\nMessages per channel:")
    for channel, count in sorted(channels.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {channel}: {count} messages")
    
    # Show some example message contents
    print("\n" + "=" * 60)
    print("💬 EXAMPLE MESSAGE CONTENTS (First 3)")
    print("=" * 60)
    for i, content in enumerate(message_contents[:3], 1):
        print(f"\n{i}. {content}")
    
    print("\n" + "=" * 60)
    print("✨ Extraction completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
