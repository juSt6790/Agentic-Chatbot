"""
Application Control Switches
============================
Centralized configuration switches for enabling/disabling features.

All feature toggles and control flags are defined here for easy management.
"""

# ============================================
# AI PROVIDER CONTROL
# ============================================
# Bedrock Fallback Control
# Controls which AI provider to use and fallback behavior:
#   0 = OpenAI only (no fallback, errors will be raised)
#   1 = Fallback mode (try OpenAI first, automatically fallback to Bedrock on 429/quota errors)
#   2 = Bedrock only (force Bedrock, never use OpenAI)
#
# When set to 1 (fallback mode), the system will automatically switch to Bedrock
# if OpenAI quota is exceeded (429 error) and stay in fallback mode until manually reset.
#
# To manually reset (switch back to OpenAI):
#   Set USE_BEDROCK_FALLBACK = 0
#
# To enable automatic fallback:
#   Set USE_BEDROCK_FALLBACK = 1
#
# To force Bedrock only:
#   Set USE_BEDROCK_FALLBACK = 2
USE_BEDROCK_FALLBACK = 0  # 0 = OpenAI only, 1 = Fallback mode, 2 = Bedrock only

# Bedrock model (Claude on Amazon Bedrock). Override with env BEDROCK_MODEL_ID in cosi_app.
# anthropic.claude-3-5-sonnet-20240620-v1:0 is EOL; use Sonnet 4.5 or newer.
BEDROCK_MODEL_ID_SONNET_45 = "anthropic.claude-sonnet-4-5-20250929-v1:0"
BEDROCK_MODEL_ID = BEDROCK_MODEL_ID_SONNET_45


# ============================================
# LOGGING CONTROLS
# ============================================
# Chat flow logging: request, tool calls, AI response, chat_id (like old terminal logs)
ENABLE_CHAT_LOGS = 1  # 0 = off, 1 = on

# Token usage logging: input/output tokens, model, response time
ENABLE_TOKEN_USAGE_LOGGING = 0  # 0 = off, 1 = on

# Autopilot Logging Control
# Set to 1 or True to enable autopilot logs, 0 or False to disable
ENABLE_AUTOPILOT_LOGS = 0  # Change to 1 to enable logging


# ============================================
# FEATURE TOGGLES
# ============================================
# Image Analysis Toggle
# Enable/disable image analysis functionality
ENABLE_IMAGE_ANALYSIS = True

# PDF Analysis Toggle
# Enable/disable PDF analysis functionality
ENABLE_PDF_ANALYSIS = True

# Tool Filtering Control
# Set to 1 or True to enable tool filtering, 0 or False to disable (use all tools)
USE_TOOL_FILTER = 0  # Change to 0 to disable tool filtering and use all tools

# ============================================
# TIMEZONE CONTROLS
# ============================================
# When enabled, assistant/system prompts will compute "current date/time" using
# the user's timezone from MongoDB profile (`users.timezone` / profile doc).
# When disabled, it falls back to server local time.
USE_USER_TIMEZONE_IN_PROMPT = True

# When enabled, tools that interpret "today" (date filters) will use the
# user's timezone from MongoDB (users.timezone) when converting YYYY-MM-DD
# into epoch milliseconds for Mongo queries.
USE_USER_TIMEZONE_FOR_EMAIL_DATE_FILTER = True

# Remove server-generated timestamps from tool result footers sent to the LLM.
# This prevents the model from accidentally using environment/server time.
OMIT_TOOL_GENERATED_ON_FOOTER = True