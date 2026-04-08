import hmac
import hashlib
import time
from flask import request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("AUTOPILOT_SECRET_KEY").encode()
ALLOWED_IPS = [
    ip.strip() for ip in os.getenv("ALLOWED_IPS", "").split(",") if ip.strip()
]
MCP_CHAT_API_AUTH_HEADER = os.getenv("MCP_CHAT_API_AUTH_HEADER") or "Authorization"


def check_ip():
    if ALLOWED_IPS:
        if request.remote_addr not in ALLOWED_IPS:
            return jsonify({"error": "IP not allowed"}), 403
    return None, None


def verify_hmac_and_get_user():
    # 🌐 IP Check (optional)
    # ip_error, ip_status = check_ip()
    # if ip_error:
    #     return None, ip_error, ip_status

    # 🔐 HMAC headers
    signature = request.headers.get("X-Signature")
    timestamp = request.headers.get("X-Timestamp")

    if not signature or not timestamp:
        return None, jsonify({"error": "Missing HMAC headers"}), 403

    # ⏱ Replay protection (5 min window)
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return None, jsonify({"error": "Request expired"}), 403
    except Exception:
        return None, jsonify({"error": "Invalid timestamp"}), 400

    # 🔑 Signature check (ONLY timestamp)
    message = timestamp.encode()

    expected_signature = hmac.new(
        SECRET,
        message,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        return None, jsonify({"error": "Invalid signature"}), 403

    # 👤 User token
    user_token = request.headers.get(MCP_CHAT_API_AUTH_HEADER)

    if not user_token:
        return None, jsonify({"error": "Missing user token"}), 401

    # Normalize (Bearer xxx → xxx)
    raw = user_token.strip()
    parts = raw.split()
    if len(parts) >= 2 and parts[0].lower() in ("bearer", "token", "basic"):
        raw = " ".join(parts[1:]).strip()

    if not raw:
        return None, jsonify({"error": "Invalid user token"}), 400

    return raw, None, None
