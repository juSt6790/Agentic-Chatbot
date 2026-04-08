#!/usr/bin/env python3
"""
Test script to verify if an OpenAI API key is working with gpt-4-turbo.

Usage:
    python3 -m tests.test_openai_key

Make sure to set the OPENAI_API_KEY environment variable before running:
    export OPENAI_API_KEY='your-api-key-here'
"""

import os
import openai
from openai import OpenAI
from typing import Tuple, Optional

def test_openai_key(api_key: Optional[str] = None) -> Tuple[bool, str]:
    """
    Test if the provided OpenAI API key is valid by making a simple chat completion request.
    
    Args:
        api_key: OpenAI API key. If None, will try to get from OPENAI_API_KEY environment variable.
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return False, "API key not provided and OPENAI_API_KEY environment variable not set"

    # Initialize the OpenAI client
    client = OpenAI(api_key=api_key)
    
    try:
        # Make a simple chat completion request
        response = client.chat.completions.create(
            model="gpt-4-turbo",  # or "gpt-4-1106-preview" if the above doesn't work
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'API key is working' if you can read this."}
            ],
            max_tokens=10
        )
        
        # Check if we got a valid response
        if response.choices and len(response.choices) > 0:
            return True, f"API key is working! Response: {response.choices[0].message.content}"
        else:
            return False, "Received empty response from OpenAI API"
            
    except openai.AuthenticationError as e:
        return False, f"Authentication failed. Invalid API key: {str(e)}"
    except openai.RateLimitError as e:
        return False, f"Rate limit exceeded: {str(e)}"
    except openai.APIConnectionError as e:
        return False, f"Failed to connect to OpenAI API: {str(e)}"
    except openai.APIError as e:
        return False, f"OpenAI API error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

if __name__ == "__main__":
    print("Testing OpenAI API key...")
    success, message = test_openai_key()
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
        print("\nTroubleshooting tips:")
        print("1. Make sure your API key is correct and has sufficient credits")
        print("2. Check if your account has access to the gpt-4-turbo model")
        print("3. Verify your internet connection")
        print("4. Check the OpenAI status page for any ongoing issues: https://status.openai.com/")
        exit(1)
