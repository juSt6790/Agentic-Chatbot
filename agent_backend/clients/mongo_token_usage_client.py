"""
MongoDB client for storing AI usage per user.
Tracks token consumption for OpenAI and Bedrock API calls.
One document per user per day per purpose - values are incremented.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from db.mongo_client import get_mongo_client
from clients.db_method import get_user_id_from_token

mongo_client = get_mongo_client()


def get_ai_usage_collection(token: Optional[str]):
    """
    Return the per-user AI usage collection for the provided token.
    """
    user_id, status = get_user_id_from_token(token)
    if status != 200 or not user_id:
        raise ValueError("Invalid or expired token")
    return mongo_client[user_id]["ai_usage"]


def _determine_model_provider(model: str) -> str:
    """
    Determine the model provider (bedrock or openai) from the model name.
    
    Args:
        model: Model name (e.g., "gpt-4.1", "anthropic.claude-3-5-sonnet-20240620-v1:0", "amazon.nova-2-lite-v1:0")
    
    Returns:
        "bedrock" or "openai"
    """
    model_lower = model.lower()
    # Bedrock models typically start with "anthropic." or "amazon."
    if model_lower.startswith("anthropic.") or model_lower.startswith("amazon."):
        return "bedrock"
    # OpenAI models typically start with "gpt-", "text-", "davinci-", etc.
    return "openai"


def upsert_ai_usage(
    token: Optional[str],
    purpose: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    system_prompt_tokens: int,
    total_tokens: int,
    ip_address: Optional[str] = None,
    total_api_calls: int = 1,
) -> bool:
    """
    Upsert (update or insert) AI usage in MongoDB.
    One document per user per day per purpose - values are incremented.
    
    New structure:
    {
        "userId": "...",
        "date": "YYYY-MM-DD",
        "month": "YYYY-MM",
        "purpose": "...",
        "created_at": ISODate,
        "updated_at": ISODate,
        "models": {
            "bedrock": {
                "inputTokens": int,
                "outputTokens": int,
                "totalTokens": int,
                "model": "model_name"
            },
            "openai": {
                "inputTokens": int,
                "outputTokens": int,
                "totalTokens": int,
                "model": "model_name"
            }
        },
        "totalTokensAllModels": int
    }
    
    Args:
        token: User authentication token
        purpose: Purpose of the API call (briefing/cosilive/autopilot/embedding/context_embedding)
        model: Model name (e.g., "gpt-4.1", "anthropic.claude-3-5-sonnet-20240620-v1:0")
        input_tokens: Number of input tokens to add (user query + images/PDFs)
        output_tokens: Number of output tokens to add (AI response + tool calls)
        system_prompt_tokens: Number of tokens in system prompt to add
        total_tokens: Total tokens to add (input + output + system prompt)
        ip_address: User's IP address (optional, updated if provided)
        total_api_calls: Number of API calls made in this request (incremented)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        collection = get_ai_usage_collection(token)
        user_id, status = get_user_id_from_token(token)
        
        now = datetime.utcnow()
        date = now.strftime("%Y-%m-%d")  # Date in YYYY-MM-DD format
        month = now.strftime("%Y-%m")
        
        # Determine model provider
        provider = _determine_model_provider(model)
        
        # Check if document exists for today with same purpose
        query = {
            "userId": user_id,
            "date": date,
            "purpose": purpose,
        }
        
        existing_doc = collection.find_one(query)
        
        if existing_doc:
            # Update existing document
            # Check if document has new structure (has "models" field)
            if "models" in existing_doc:
                # New structure - increment nested fields
                # Note: system_prompt_tokens are included in input_tokens for the new structure
                # total_tokens = input_tokens + output_tokens (system_prompt included in input)
                input_tokens_with_system = input_tokens + system_prompt_tokens
                calculated_total = input_tokens_with_system + output_tokens
                
                # Check if provider exists in models
                existing_models = existing_doc.get("models", {})
                provider_exists = provider in existing_models
                
                if not provider_exists:
                    # Provider doesn't exist yet - initialize it
                    update_doc = {
                        "$set": {
                            f"models.{provider}": {
                                "inputTokens": input_tokens_with_system,
                                "outputTokens": output_tokens,
                                "totalTokens": calculated_total,
                                "model": model
                            },
                            "updated_at": now,
                        },
                        "$inc": {
                            "totalTokensAllModels": calculated_total,
                        }
                    }
                else:
                    # Provider exists - increment values
                    update_doc = {
                        "$inc": {
                            f"models.{provider}.inputTokens": input_tokens_with_system,
                            f"models.{provider}.outputTokens": output_tokens,
                            f"models.{provider}.totalTokens": calculated_total,
                            "totalTokensAllModels": calculated_total,
                        },
                        "$set": {
                            f"models.{provider}.model": model,  # Update model name (may change)
                            "updated_at": now,
                        }
                    }
            else:
                # Old structure - migrate to new structure
                # Calculate existing totals from old structure
                old_input = existing_doc.get("inputTokens", 0)
                old_output = existing_doc.get("outputTokens", 0)
                old_system = existing_doc.get("systemPromptTokens", 0)
                old_total = existing_doc.get("totalTokens", 0)
                old_model = existing_doc.get("model", model)
                old_provider = _determine_model_provider(old_model)
                
                # Include system prompt tokens in input tokens for new structure
                old_input_with_system = old_input + old_system
                # Recalculate old total as input + output (if old structure had separate system tokens)
                old_total_recalculated = old_input_with_system + old_output
                
                # Initialize models structure with existing data
                models = {
                    old_provider: {
                        "inputTokens": old_input_with_system,
                        "outputTokens": old_output,
                        "totalTokens": old_total_recalculated,
                        "model": old_model
                    }
                }
                
                # Add new tokens to the appropriate provider
                # Include system_prompt_tokens in input_tokens
                input_tokens_with_system = input_tokens + system_prompt_tokens
                calculated_total = input_tokens_with_system + output_tokens
                
                if provider in models:
                    models[provider]["inputTokens"] += input_tokens_with_system
                    models[provider]["outputTokens"] += output_tokens
                    models[provider]["totalTokens"] += calculated_total
                    models[provider]["model"] = model
                else:
                    models[provider] = {
                        "inputTokens": input_tokens_with_system,
                        "outputTokens": output_tokens,
                        "totalTokens": calculated_total,
                        "model": model
                    }
                
                # Calculate total across all models
                total_all_models = sum(m["totalTokens"] for m in models.values())
                
                update_doc = {
                    "$set": {
                        "models": models,
                        "totalTokensAllModels": total_all_models,
                        "updated_at": now,
                    },
                    "$unset": {
                        "inputTokens": "",
                        "outputTokens": "",
                        "systemPromptTokens": "",
                        "totalTokens": "",
                        "model": "",
                        "totalApiCalls": "",
                        "totalQueries": "",
                        "ip": "",
                    }
                }
            
            # Update IP if provided (use latest)
            if ip_address:
                if "$set" not in update_doc:
                    update_doc["$set"] = {}
                update_doc["$set"]["ip"] = ip_address
            
            collection.update_one(query, update_doc)
        else:
            # Create new document for this day with new structure
            # Include system_prompt_tokens in input_tokens for new structure
            input_tokens_with_system = input_tokens + system_prompt_tokens
            calculated_total = input_tokens_with_system + output_tokens
            
            models = {
                provider: {
                    "inputTokens": input_tokens_with_system,
                    "outputTokens": output_tokens,
                    "totalTokens": calculated_total,
                    "model": model
                }
            }
            
            document = {
                "userId": user_id,
                "date": date,
                "month": month,
                "purpose": purpose,
                "created_at": now,
                "updated_at": now,
                "models": models,
                "totalTokensAllModels": calculated_total,
            }
            
            # Add IP if provided
            if ip_address:
                document["ip"] = ip_address
            
            collection.insert_one(document)
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to upsert AI usage: {e}")
        return False
