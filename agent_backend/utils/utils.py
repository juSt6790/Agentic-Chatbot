import requests
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_URL = "http://3.6.95.164:5000/users"

def get_tool_token(unified_token: str, tool_name: str) -> str:
    """
    Fetch access token for a specific tool (Google Docs or Notion) using unified token.
    Returns the raw access token string.
    """
    url = f"{BASE_URL}/get_tool_token"
    payload = {"unified_token": unified_token, "tool_name": tool_name}
    try:
        logger.debug(f"Fetching token for tool: {tool_name}, unified_token: {unified_token}")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        token_data = response.json()
        logger.debug(f"Token endpoint response: {token_data}")
        
        # Handle different token structures for Notion and Google Docs
        access_token = token_data.get("access_token")
        if isinstance(access_token, dict):
            access_token = access_token.get("token")
        if not access_token:
            logger.error("Access token not found in response")
            raise ValueError("Access token not found in response")
        
        return access_token
    except requests.exceptions.RequestException as e:
        logger.error(f"Token fetch failed: {str(e)}")
        raise ValueError(f"Token fetch failed: {str(e)}")