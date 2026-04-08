"""
Script to extract email writing personality for ALL users in the system.

This script:
1. Fetches all users from unified_workspace.users collection
2. For each user, queries their sent emails from their user database
3. Cleans and processes the email bodies
4. Uses AWS Bedrock (Claude) to analyze writing style
5. Stores the personality profile in the user's database (user_id.personality)
"""

import os
import re
import json
import sys
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv
import boto3
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
import requests

# Add parent directory to path to import mcp_gmail modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.mongo_client import get_mongo_client

load_dotenv()

# Configuration
NUM_EMAILS = 20  # Number of emails to analyze per user
NUM_SLACK_MESSAGES = 100  # Number of Slack messages to analyze per user

# AWS Bedrock setup
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID") or "anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.getenv("AWS_REGION", "us-east-1")

session = boto3.session.Session()
credentials = session.get_credentials().get_frozen_credentials()


def invoke_bedrock(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Invoke AWS Bedrock Claude model.
    
    Args:
        body: Request body for Bedrock
    
    Returns:
        Response from Bedrock
    """
    url = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{BEDROCK_MODEL_ID}/invoke"
    headers = {"Content-Type": "application/json"}
    
    request = AWSRequest(
        method="POST",
        url=url,
        data=json.dumps(body),
        headers=headers,
    )
    SigV4Auth(credentials, "bedrock", REGION).add_auth(request)
    
    try:
        response = requests.post(
            request.url, headers=dict(request.headers.items()), data=request.data
        )
        response.raise_for_status()
        result = response.json()
        return result
    except requests.exceptions.HTTPError as e:
        print(f"  ❌ Bedrock HTTP error: {e}")
        print(f"  Response text: {response.text}")
        raise
    except Exception as e:
        print(f"  ❌ Bedrock invocation failed: {e}")
        raise


def clean_email_body(text: str) -> str:
    """
    Clean email body by removing common noise:
    - Email thread markers
    - URLs
    - Email addresses
    - Excessive whitespace
    """
    if not text:
        return ""
    
    # Remove email thread markers
    text = re.sub(r'On .* wrote:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'From:.*?Subject:', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    
    # Remove email addresses
    text = re.sub(r'\S+@\S+', '', text)
    
    # Remove excessive whitespace and newlines
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def get_sent_emails(user_id: str, user_email: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Query MongoDB for sent emails from a specific user's database.
    
    Args:
        user_id: The user's database ID
        user_email: The user's email address
        limit: Maximum number of emails to retrieve
    
    Returns:
        List of email documents
    """
    print(f"  🔍 Fetching sent emails for: {user_email} (user_id: {user_id})")
    
    mongo_client = get_mongo_client()
    
    try:
        db = mongo_client[user_id]
        collection = db["gmail"]
        
        # Query for emails where 'from' field contains user's email (sent BY user)
        queries = [
            {"from.email": {"$regex": user_email, "$options": "i"}},
            {"from": {"$regex": user_email, "$options": "i"}},
        ]
        
        emails = []
        for query in queries:
            try:
                results = list(
                    collection.find(query)
                    .sort("internalDateNum", -1)
                    .limit(limit)
                )
                if results:
                    print(f"    ✅ Found {len(results)} emails")
                    emails.extend(results)
                    if len(emails) >= limit:
                        return emails[:limit]
            except Exception as e:
                print(f"    ⚠️ Query failed: {e}")
                continue
        
        if not emails:
            print(f"    ⚠️ No emails found with 'from' field matching {user_email}")
        
        return emails[:limit]
        
    except Exception as e:
        print(f"    ❌ Error accessing database {user_id}.gmail: {e}")
        return []


def get_slack_messages(user_id: str, limit: int = 100) -> List[str]:
    """
    Query MongoDB for Slack messages sent by a specific user.
    Uses owner_names from the document to match against message sender field.
    
    Args:
        user_id: The user's database ID
        limit: Maximum number of messages to retrieve
    
    Returns:
        List of message content strings
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
        
        # Extract owner_ids to match against message metadata.userId (per schema)
        owner_ids = slack_doc.get("owner_ids", [])
        if not owner_ids:
            print(f"    ⚠️ No owner_ids found in Slack document")
            return []
        
        print(f"    📝 Owner IDs: {owner_ids}")
        
        messages: List[str] = []
        channel_info_details = slack_doc.get("channel_info_details", [])
        if not isinstance(channel_info_details, list):
            print("    ⚠️ channel_info_details is not a list; schema mismatch")
            return []
        
        total_seen = 0
        total_matched = 0
        
        # Iterate through all channels
        for channel_info in channel_info_details:
            channel = channel_info.get("channel", {})
            # Per schema, channel.messages is an array of message objects
            channel_messages = channel.get("messages", [])
            if not isinstance(channel_messages, list):
                # Some older documents may have nested shape; try to recover
                channel_messages = channel.get("messages", {}).get("messages", [])
            
            if not isinstance(channel_messages, list):
                continue
            
            for msg in channel_messages:
                try:
                    total_seen += 1
                    metadata = msg.get("metadata", {}) if isinstance(msg, dict) else {}
                    user_id_in_msg = metadata.get("userId")
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    
                    if not content:
                        continue
                    
                    # Keep only messages authored by the owner (by userId)
                    if user_id_in_msg and user_id_in_msg in owner_ids:
                        messages.append(content)
                        total_matched += 1
                        if len(messages) >= limit:
                            print(
                                f"    ✅ Collected {len(messages)} Slack messages (matched {total_matched}/{total_seen} scanned)"
                            )
                            return messages
                except Exception as inner_e:
                    # Don't let one bad message abort the whole process
                    continue
        
        print(
            f"    ✅ Collected {len(messages)} Slack messages (matched {total_matched}/{total_seen} scanned)"
        )
        return messages
        
    except Exception as e:
        print(f"    ❌ Error accessing Slack messages: {e}")
        return []


def extract_personality_with_bedrock(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Use AWS Bedrock (Claude) to analyze email writing style and extract personality traits.
    
    Args:
        emails: List of email documents
    
    Returns:
        Dictionary containing personality profile with email_personality nested structure
    """
    print(f"\n🧠 Analyzing writing style from {len(emails)} emails...")
    
    if not emails:
        print("  ❌ No emails to analyze")
        return {}
    
    # Extract and clean email bodies
    email_bodies = []
    for email in emails:
        body = email.get("body", "")
        if body:
            cleaned = clean_email_body(body)
            if cleaned and len(cleaned) > 20:  # Only include substantial content
                email_bodies.append(cleaned)
    
    if not email_bodies:
        print("  ❌ No valid email bodies found after cleaning")
        return {}
    
    print(f"  📧 Analyzing {len(email_bodies)} email bodies...")
    
    # Create prompt for Claude
    prompt = f"""You are an expert linguistic analyzer specializing in email communication styles.

Below are {len(email_bodies)} emails written by a single user. 
Your task is to analyze their writing style and create a comprehensive personality profile.

Output format (JSON only, no explanations):
{{
  "tone": "description of overall tone (e.g., professional, casual, friendly, formal)",
  "formality": "high/medium/low with brief explanation",
  "greeting_style": "how they typically start emails",
  "closing_style": "how they typically end emails",
  "sentence_structure": "description of sentence patterns",
  "vocabulary_level": "assessment of vocabulary sophistication",
  "common_phrases": ["list", "of", "frequently", "used", "phrases"],
  "emotional_tone": "description of emotional expression",
  "signature_style": "how they sign off",
  "communication_style": "direct/indirect, concise/verbose, etc.",
  "personality_traits": ["list", "of", "inferred", "personality", "traits"],
  "other_notes": "any other notable patterns or characteristics"
}}

Emails:
"""
    
    # Add email samples (limit to avoid token limits)
    for i, body in enumerate(email_bodies[:15], 1):  # Limit to 15 emails for token efficiency
        # Truncate very long emails
        truncated_body = body[:500] if len(body) > 500 else body
        prompt += f"\n\nEmail {i}:\n{truncated_body}\n"
    
    try:
        # Prepare Bedrock request
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        response = invoke_bedrock(body)
        content = response.get("content", [])
        
        if not content or not isinstance(content, list) or len(content) == 0:
            print("  ❌ No content in Bedrock response")
            return {}
        
        personality_json_str = content[0].get("text", "")
        
        # Try to parse JSON
        try:
            # Remove markdown code blocks if present
            personality_json_str = re.sub(r'```json\s*', '', personality_json_str)
            personality_json_str = re.sub(r'```\s*$', '', personality_json_str)
            personality_json_str = personality_json_str.strip()
            
            email_personality = json.loads(personality_json_str)
            
            # Wrap email-specific fields in email_personality
            personality_profile = {
                "email_personality": email_personality
            }
            
            print("  ✅ Successfully extracted personality profile")
            return personality_profile
        except json.JSONDecodeError as e:
            print(f"  ⚠️ Failed to parse JSON response: {e}")
            print(f"  Raw response: {personality_json_str[:200]}...")
            # Return raw string as fallback with nested structure
            return {"email_personality": {"raw_analysis": personality_json_str}}
    
    except Exception as e:
        print(f"  ❌ Bedrock API error: {e}")
        return {}


def extract_slack_personality_with_bedrock(messages: List[str]) -> Dict[str, Any]:
    """
    Use AWS Bedrock (Claude) to analyze Slack writing style and extract personality traits.
    
    Args:
        messages: List of Slack message content strings
    
    Returns:
        Dictionary containing Slack personality profile
    """
    print(f"\n💬 Analyzing Slack writing style from {len(messages)} messages...")
    
    if not messages:
        print("  ❌ No Slack messages to analyze")
        return {}
    
    # Filter out very short messages
    substantial_messages = [msg for msg in messages if len(msg) > 10]
    
    if not substantial_messages:
        print("  ❌ No substantial Slack messages found")
        return {}
    
    print(f"  💬 Analyzing {len(substantial_messages)} Slack messages...")
    
    # Create prompt for Claude
    prompt = f"""You are an expert linguistic analyzer specializing in Slack communication styles.

Below are {len(substantial_messages)} Slack messages written by a single user. 
Your task is to analyze their writing style and create a comprehensive personality profile.

Output format (JSON only, no explanations):
{{
  "tone": "description of overall tone (e.g., casual, friendly, professional, humorous)",
  "formality": "high/medium/low with brief explanation",
  "greeting_style": "how they typically start conversations or greet people",
  "response_style": "how they respond to messages (quick/detailed, emoji usage, etc.)",
  "sentence_structure": "description of sentence patterns (short/long, fragmented, etc.)",
  "vocabulary_level": "assessment of vocabulary (casual slang, professional, technical, etc.)",
  "common_phrases": ["list", "of", "frequently", "used", "phrases"],
  "emoji_usage": "description of emoji and reaction usage patterns",
  "communication_style": "direct/indirect, concise/verbose, collaborative/independent, etc.",
  "personality_traits": ["list", "of", "inferred", "personality", "traits"],
  "other_notes": "any other notable patterns or characteristics"
}}

Slack Messages:
"""
    
    # Add message samples (limit to avoid token limits)
    for i, msg in enumerate(substantial_messages[:50], 1):  # Limit to 50 messages for token efficiency
        # Truncate very long messages
        truncated_msg = msg[:300] if len(msg) > 300 else msg
        prompt += f"\n\nMessage {i}:\n{truncated_msg}\n"
    
    try:
        # Prepare Bedrock request
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        response = invoke_bedrock(body)
        content = response.get("content", [])
        
        if not content or not isinstance(content, list) or len(content) == 0:
            print("  ❌ No content in Bedrock response")
            return {}
        
        personality_json_str = content[0].get("text", "")
        
        # Try to parse JSON
        try:
            # Remove markdown code blocks if present
            personality_json_str = re.sub(r'```json\s*', '', personality_json_str)
            personality_json_str = re.sub(r'```\s*$', '', personality_json_str)
            personality_json_str = personality_json_str.strip()
            
            slack_personality = json.loads(personality_json_str)
            
            print("  ✅ Successfully extracted Slack personality profile")
            return slack_personality
        except json.JSONDecodeError as e:
            print(f"  ⚠️ Failed to parse JSON response: {e}")
            print(f"  Raw response: {personality_json_str[:200]}...")
            # Return raw string as fallback
            return {"raw_analysis": personality_json_str}
    
    except Exception as e:
        print(f"  ❌ Bedrock API error: {e}")
        return {}


def store_personality_in_mongo(
    user_id: str, 
    user_email: str, 
    personality_profile: Dict[str, Any], 
    num_emails: int,
    num_slack_messages: int = 0
) -> bool:
    """
    Store the personality profile in user's database personality collection.
    
    Args:
        user_id: User's database ID
        user_email: User's email address
        personality_profile: The extracted personality profile (with email_personality and/or slack_personality)
        num_emails: Number of emails analyzed
        num_slack_messages: Number of Slack messages analyzed
    
    Returns:
        True if successful, False otherwise
    """
    print(f"  💾 Storing personality profile...")
    
    try:
        mongo_client = get_mongo_client()
        
        # Store in user's own database
        db = mongo_client[user_id]
        collection = db["personality"]
        
        # Create document to store
        document = {
            "user_email": user_email,
            "personality_profile": personality_profile,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "version": "1.0",
            "source": "sent_emails_and_slack",
            "num_emails_analyzed": num_emails,
            "num_slack_messages_analyzed": num_slack_messages
        }
        
        # Upsert: update if exists, insert if not
        result = collection.update_one(
            {},
            {"$set": document},
            upsert=True
        )
        
        if result.upserted_id:
            print(f"    ✅ Inserted new personality profile")
        else:
            print(f"    ✅ Updated existing personality profile")
        
        return True
    
    except Exception as e:
        print(f"    ❌ Error storing in MongoDB: {e}")
        return False


def get_all_users() -> List[Dict[str, Any]]:
    """
    Get all active users from unified_workspace.users collection.
    
    Returns:
        List of user documents
    """
    mongo_client = get_mongo_client()
    db = mongo_client["unified_workspace"]
    users_collection = db["users"]
    
    # Get all active users (live=1)
    users = list(users_collection.find({"live": 1}))
    return users


def process_user(user: Dict[str, Any]) -> bool:
    """
    Process a single user: fetch emails and Slack messages, extract personality, store in DB.
    
    Args:
        user: User document from unified_workspace.users
    
    Returns:
        True if successful, False otherwise
    """
    user_id = user.get("user_id")
    user_email = user.get("email")
    user_name = user.get("name", "Unknown")
    
    if not user_id or not user_email:
        print(f"  ⚠️ Skipping user - missing user_id or email")
        return False
    
    print(f"\n{'='*60}")
    print(f"👤 Processing: {user_name} ({user_email})")
    print(f"   User ID: {user_id}")
    print(f"{'='*60}")
    
    # Initialize combined personality profile
    combined_personality_profile = {}
    num_emails = 0
    num_slack_msgs = 0
    
    # Step 1: Fetch and analyze sent emails
    emails = get_sent_emails(user_id, user_email, NUM_EMAILS)
    
    if emails:
        print(f"  ✅ Retrieved {len(emails)} emails")
        num_emails = len(emails)
        
        # Extract email personality using Bedrock (Claude)
        print(f"  🧠 Analyzing email writing style from {len(emails)} emails...")
        email_personality_profile = extract_personality_with_bedrock(emails)
        
        if email_personality_profile:
            combined_personality_profile.update(email_personality_profile)
            print(f"  ✅ Successfully extracted email personality profile")
        else:
            print(f"  ⚠️ Failed to extract email personality profile")
    else:
        print(f"  ⚠️ No emails found for {user_email}")
    
    # Step 2: Fetch and analyze Slack messages
    slack_messages = get_slack_messages(user_id, NUM_SLACK_MESSAGES)
    
    if slack_messages:
        print(f"  ✅ Retrieved {len(slack_messages)} Slack messages")
        num_slack_msgs = len(slack_messages)
        
        # Extract Slack personality using Bedrock (Claude)
        print(f"  💬 Analyzing Slack writing style from {len(slack_messages)} messages...")
        slack_personality = extract_slack_personality_with_bedrock(slack_messages)
        
        if slack_personality:
            # Add slack_personality to the combined profile
            combined_personality_profile["slack_personality"] = slack_personality
            print(f"  ✅ Successfully extracted Slack personality profile")
        else:
            print(f"  ⚠️ Failed to extract Slack personality profile")
    else:
        print(f"  ⚠️ No Slack messages found for user {user_id}")
    
    # Check if we have at least one personality profile
    if not combined_personality_profile:
        print(f"  ❌ No personality data extracted (no emails or Slack messages)")
        return False
    
    # Step 3: Store in MongoDB
    success = store_personality_in_mongo(
        user_id, 
        user_email, 
        combined_personality_profile, 
        num_emails,
        num_slack_msgs
    )
    
    if success:
        print(f"  ✅ Personality profile stored in {user_id}.personality")
    else:
        print(f"  ❌ Failed to store personality profile")
    
    return success


def main():
    """Main execution function - processes all users"""
    print("\n" + "=" * 60)
    print("📧💬 BULK EMAIL & SLACK PERSONALITY EXTRACTION")
    print("=" * 60)
    print(f"Analyzing up to {NUM_EMAILS} emails per user")
    print(f"Analyzing up to {NUM_SLACK_MESSAGES} Slack messages per user")
    print("=" * 60)
    
    # Get all users
    print("\n🔍 Fetching all users from unified_workspace.users...")
    users = get_all_users()
    
    if not users:
        print("❌ No users found in the database")
        return
    
    print(f"✅ Found {len(users)} active users\n")
    
    # Process each user
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for i, user in enumerate(users, 1):
        print(f"\n[{i}/{len(users)}] ", end="")
        
        try:
            result = process_user(user)
            if result:
                success_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"  ❌ Error processing user: {e}")
            failed_count += 1
            continue
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)
    print(f"Total users: {len(users)}")
    print(f"✅ Successfully processed: {success_count}")
    print(f"⚠️  Skipped (no emails): {skipped_count}")
    print(f"❌ Failed (errors): {failed_count}")
    print("=" * 60)
    print("✨ Script completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
