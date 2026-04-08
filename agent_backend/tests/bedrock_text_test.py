import os
import json
import time
import logging

import boto3
import requests
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth
from dotenv import load_dotenv


"""
Minimal Bedrock text test helper.

This is intentionally standalone so you can quickly verify Bedrock
connectivity and text responses without going through Flask.
"""


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# === AWS Bedrock Setup (mirrors app/cosi_app.py) ===
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID") or "anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.getenv("AWS_REGION", "us-east-1")

session = boto3.session.Session()
credentials = session.get_credentials().get_frozen_credentials()


def invoke_bedrock_raw(body, max_retries: int = 3, initial_backoff: float = 1.0) -> dict:
    """
    Low-level Bedrock invocation with simple exponential backoff.

    Args:
        body: Full request body to send to Bedrock.
        max_retries: Maximum retry attempts for 429s.
        initial_backoff: Initial backoff delay in seconds.
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

    last_error = None
    backoff = initial_backoff

    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                logger.warning(
                    "Retrying Bedrock (attempt %s/%s) after %.1fs",
                    attempt,
                    max_retries,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

            resp = requests.post(
                request.url,
                headers=dict(request.headers.items()),
                data=request.data,
            )

            if resp.status_code == 429 and attempt < max_retries:
                last_error = f"429 Too Many Requests: {resp.text}"
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.HTTPError as e:
            last_error = str(e)
            if resp.status_code != 429 or attempt >= max_retries:
                raise
        except Exception as e:
            last_error = str(e)
            raise

    raise RuntimeError(f"Bedrock invocation failed after retries: {last_error}")


def bedrock_text_completion(prompt: str, max_tokens: int = 512, temperature: float = 0.3) -> str:
    """
    Send a simple text prompt to Bedrock (Claude) and return the text response.
    """
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            }
        ],
    }

    logger.info(
        "Calling Bedrock text completion (model=%s, region=%s)",
        BEDROCK_MODEL_ID,
        REGION,
    )
    result = invoke_bedrock_raw(body)

    # Claude via Bedrock returns a list of content blocks; extract text parts.
    chunks = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            chunks.append(block.get("text", ""))
    return "".join(chunks).strip()


if __name__ == "__main__":
    # Simple CLI usage for quick testing:
    import argparse

    parser = argparse.ArgumentParser(description="Test Bedrock text completion.")
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Prompt to send to Bedrock. If omitted, a default test prompt is used.",
    )
    args = parser.parse_args()

    if args.prompt:
        prompt_text = " ".join(args.prompt)
    else:
        prompt_text = "Say hello and tell me one fun fact about space in 2 sentences."

    try:
        response_text = bedrock_text_completion(prompt_text)
        print("\n=== Bedrock Response ===\n")
        print(response_text)
        print("\n========================\n")
    except Exception as e:
        logger.error("Bedrock test failed: %s", e)
        raise


