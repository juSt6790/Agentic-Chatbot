"""
Token counting utilities for OpenAI and Bedrock/Claude models.
"""
import tiktoken
from typing import List, Dict, Any, Optional


# Initialize encodings
try:
    # OpenAI models (GPT-4, GPT-3.5) use cl100k_base
    openai_encoding = tiktoken.get_encoding("cl100k_base")
    # Claude models also use cl100k_base
    claude_encoding = tiktoken.get_encoding("cl100k_base")
except Exception as e:
    print(f"[WARNING] Failed to load tiktoken encodings: {e}")
    openai_encoding = None
    claude_encoding = None


def count_tokens_openai(text: str) -> int:
    """Count tokens for OpenAI models using tiktoken."""
    if not openai_encoding:
        # Fallback: rough estimate (1 token ≈ 4 characters)
        return len(text) // 4
    try:
        return len(openai_encoding.encode(text))
    except Exception:
        return len(text) // 4


def count_tokens_claude(text: str) -> int:
    """Count tokens for Claude models using tiktoken."""
    if not claude_encoding:
        # Fallback: rough estimate (1 token ≈ 4 characters)
        return len(text) // 4
    try:
        return len(claude_encoding.encode(text))
    except Exception:
        return len(text) // 4


def count_tokens_in_messages(messages: List[Dict[str, Any]], model_type: str = "openai") -> int:
    """
    Count tokens in a list of messages.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        model_type: "openai" or "claude"
    
    Returns:
        Total token count
    """
    total = 0
    counter = count_tokens_openai if model_type == "openai" else count_tokens_claude
    
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        
        # Count role token (typically 1-2 tokens)
        total += counter(role) if role else 0
        
        # Count content tokens
        if isinstance(content, str):
            total += counter(content)
        elif isinstance(content, list):
            # Handle multimodal content (text + images)
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "")
                    if item_type == "text":
                        total += counter(item.get("text", ""))
                    elif item_type == "image" or item_type == "image_url":
                        # Images are encoded as base64, estimate tokens
                        # For Claude: base64 images are ~170 tokens per image
                        # For OpenAI: depends on image size, roughly 85-170 tokens
                        total += 170  # Conservative estimate
                    elif item_type == "tool_use":
                        # Count tool use tokens
                        name = item.get("name", "")
                        input_data = item.get("input", {})
                        total += counter(name)
                        total += counter(str(input_data))
                    elif item_type == "tool_result":
                        # Count tool result tokens
                        content_data = item.get("content", "")
                        total += counter(str(content_data))
    
    return total


def count_tokens_in_system_prompt(system_prompt: str, model_type: str = "openai") -> int:
    """Count tokens in system prompt."""
    counter = count_tokens_openai if model_type == "openai" else count_tokens_claude
    return counter(system_prompt) if system_prompt else 0


def estimate_image_tokens(image_base64: str, model_type: str = "openai") -> int:
    """
    Estimate tokens for base64-encoded images.
    
    For OpenAI: ~85 tokens for low-res, ~170 for high-res
    For Claude: ~170 tokens per image
    """
    if model_type == "openai":
        # Rough estimate based on image size
        size_kb = len(image_base64) / 1024
        if size_kb < 100:
            return 85
        else:
            return 170
    else:  # Claude
        return 170



