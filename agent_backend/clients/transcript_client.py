"""
Meeting transcript storage access (Mongo meet_summaries) and optional workspace API.

- Reads zlib-compressed transcript payloads the same way as the Recall webhook pipeline.
- POST /meet/schedule-bot and GET /meet/transcript when MEET_API_BASE_URL is set.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import re
import zlib
from typing import Any, Optional

import requests

from clients.db_method import get_user_id_from_token
from db.mongo_client import get_mongo_client

MEET_SUMMARIES = "meet_summaries"
MEET_API_BASE_URL = os.getenv("MEET_API_BASE_URL", "").rstrip("/")


def normalize_meeting_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    return url.split("?")[0].rstrip("/")


def _auth_header(token: str) -> dict[str, str]:
    t = (token or "").strip()
    return {"Authorization": f"Bearer {t}", "Accept": "application/json"}


def decompress_stored_transcript(blob: Any) -> Any:
    if blob is None:
        return None
    if isinstance(blob, list):
        return blob
    raw_bytes: Optional[bytes] = None
    if isinstance(blob, (bytes, bytearray)):
        raw_bytes = bytes(blob)
    elif hasattr(blob, "binary_subtype"):  # bson.Binary
        raw_bytes = bytes(blob)
    elif isinstance(blob, dict):
        bwrap = blob.get("$binary") or {}
        b64 = bwrap.get("base64") or blob.get("base64")
        if b64:
            raw_bytes = base64.b64decode(b64)
    elif isinstance(blob, str):
        try:
            raw_bytes = base64.b64decode(blob)
        except Exception:
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                return None
    if raw_bytes is None:
        return None
    try:
        data = zlib.decompress(raw_bytes)
    except Exception:
        try:
            data = gzip.decompress(raw_bytes)
        except Exception:
            return None
    text = data.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _word_token_ends_sentence(word_text: str) -> bool:
    t = (word_text or "").strip()
    if not t:
        return False
    if t in [".", "!", "?"]:
        return True
    return bool(re.search(r"[.!?]+$", t))


def _join_words(tokens: list[str]) -> str:
    if not tokens:
        return ""
    text = " ".join(tokens).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"\s+\"", '"', text)
    text = re.sub(r'"\s+', '"', text)
    return text


def build_utterances_from_transcript_json(transcript_json: Any) -> list[dict[str, Any]]:
    if not isinstance(transcript_json, list):
        return []

    utterances: list[dict[str, Any]] = []

    for seg in transcript_json:
        if not isinstance(seg, dict):
            continue
        participant = seg.get("participant") or {}
        if not isinstance(participant, dict):
            participant = {}

        participant_id = participant.get("id")
        participant_name = participant.get("name")
        participant_is_host = participant.get("is_host")

        words = seg.get("words") or []
        if not isinstance(words, list) or not words:
            continue

        cur_tokens: list[str] = []
        cur_start: Optional[str] = None
        cur_end: Optional[str] = None

        for w in words:
            if not isinstance(w, dict):
                continue
            word_text = w.get("text")
            if not word_text:
                continue

            start_ts = (w.get("start_timestamp") or {}).get("absolute")
            end_ts = (w.get("end_timestamp") or {}).get("absolute")
            if cur_start is None and start_ts:
                cur_start = start_ts
            if end_ts:
                cur_end = end_ts

            cur_tokens.append(str(word_text))

            if _word_token_ends_sentence(str(word_text)):
                sentence_text = _join_words(cur_tokens)
                if sentence_text:
                    utterances.append(
                        {
                            "participant_id": participant_id,
                            "participant_name": participant_name,
                            "is_host": participant_is_host,
                            "text": sentence_text,
                            "start_at": cur_start,
                            "end_at": cur_end,
                        }
                    )
                cur_tokens = []
                cur_start = None
                cur_end = None

        if cur_tokens:
            sentence_text = _join_words(cur_tokens)
            if sentence_text:
                utterances.append(
                    {
                        "participant_id": participant_id,
                        "participant_name": participant_name,
                        "is_host": participant_is_host,
                        "text": sentence_text,
                        "start_at": cur_start,
                        "end_at": cur_end,
                    }
                )

    utterances.sort(key=lambda u: str(u.get("start_at") or ""))
    return utterances


def spoken_text_from_utterances(utterances: list[dict[str, Any]], max_chars: Optional[int]) -> str:
    lines: list[str] = []
    for u in utterances:
        name = u.get("participant_name") or u.get("participant_id") or "Speaker"
        t = u.get("text") or ""
        if not t:
            continue
        lines.append(f"{name}: {t}")
    out = "\n".join(lines)
    if max_chars is not None and len(out) > max_chars:
        out = out[: max_chars - 80] + "\n... [truncated for length]"
    return out


def mongo_fetch_meeting_transcript(
    *,
    token: str,
    calendar_id: Optional[str] = None,
    meeting_url: Optional[str] = None,
    max_transcript_chars: int = 120_000,
) -> dict[str, Any]:
    """
    Load the latest meet_summaries row for this user and return a spoken transcript string.
    Prefer calendar_id (Google event id) — same id returned by search_calendar_events / get_events.
    """
    user_id, status = get_user_id_from_token(token)
    if status != 200 or not user_id:
        return {"status": "error", "message": "Invalid or unknown user token"}

    cid = (calendar_id or "").strip()
    murl = normalize_meeting_url(meeting_url or "")
    if not cid and not murl:
        return {
            "status": "error",
            "message": "Provide calendar_id (Google Calendar event id) and/or meeting_url",
        }

    coll = get_mongo_client()[str(user_id)][MEET_SUMMARIES]
    doc = None
    if cid:
        cur = coll.find({"calendar_id": cid}).sort("updated_at", -1).limit(1)
        docs = list(cur)
        doc = docs[0] if docs else None
    if doc is None and murl:
        cur = coll.find({"meeting_url": murl}).sort("updated_at", -1).limit(1)
        docs = list(cur)
        doc = docs[0] if docs else None

    if doc is None:
        return {
            "status": "error",
            "message": "No meeting transcript record found for this calendar event or Meet link",
            "calendar_id": cid or None,
            "meeting_url": murl or None,
        }

    tj = doc.get("transcript_json_zlib")
    raw = decompress_stored_transcript(tj) if tj is not None else doc.get("transcript_json")
    event_code = doc.get("transcript_event")
    fetch_err = doc.get("transcript_fetch_error")

    meet_summary_id = str(doc.get("_id")) if doc.get("_id") is not None else None
    transcript_summary = doc.get("transcript_summary")

    if raw is None:
        return {
            "status": "pending",
            "message": "Transcript is not stored yet (meeting may not have finished or processing is in progress).",
            "meet_summary_id": meet_summary_id,
            "calendar_id": doc.get("calendar_id"),
            "meeting_url": doc.get("meeting_url"),
            "bot_id": doc.get("bot_id"),
            "recording_id": doc.get("recording_id"),
            "transcript_id": doc.get("transcript_id"),
            "transcript_event": event_code,
            "transcript_code": doc.get("transcript_code"),
            "transcript_fetch_error": fetch_err,
            "transcript_summary": transcript_summary,
        }

    utterances = build_utterances_from_transcript_json(raw)
    spoken = spoken_text_from_utterances(utterances, max_transcript_chars)

    return {
        "status": "success",
        "meet_summary_id": meet_summary_id,
        "calendar_id": doc.get("calendar_id"),
        "meeting_url": doc.get("meeting_url"),
        "bot_id": doc.get("bot_id"),
        "recording_id": doc.get("recording_id"),
        "transcript_id": doc.get("transcript_id"),
        "transcript_event": event_code,
        "transcript_code": doc.get("transcript_code"),
        "transcript_fetch_error": fetch_err,
        "transcript_summary": transcript_summary,
        "utterance_count": len(utterances),
        "spoken_transcript": spoken,
    }


def post_schedule_meeting_bot(
    *,
    calendar_id: str,
    meeting_url: str,
    token: str,
    join_at: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    transcript_mode: str = "prioritize_accuracy",
    bot_name: Optional[str] = None,
) -> dict[str, Any]:
    if not MEET_API_BASE_URL:
        return {
            "status": "error",
            "message": "Meeting transcript API is not configured (set MEET_API_BASE_URL).",
        }
    url = f"{MEET_API_BASE_URL}/meet/schedule-bot"
    body: dict[str, Any] = {
        "calendar_id": str(calendar_id).strip(),
        "meeting_url": str(meeting_url).strip(),
        "transcript_mode": transcript_mode,
    }
    if join_at:
        body["join_at"] = join_at
    if attendees:
        body["attendees"] = attendees
    if bot_name:
        body["bot_name"] = bot_name
    try:
        r = requests.post(
            url,
            headers={**_auth_header(token), "Content-Type": "application/json"},
            json=body,
            timeout=90,
        )
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:2000]
            return {
                "status": "error",
                "message": "schedule-bot request failed",
                "http_status": r.status_code,
                "detail": detail,
            }
        return {"status": "success", **(r.json() if r.content else {})}
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}


def get_transcript_from_api(*, calendar_id: str, token: str) -> dict[str, Any]:
    if not MEET_API_BASE_URL:
        return {"status": "error", "message": "MEET_API_BASE_URL not configured"}
    url = f"{MEET_API_BASE_URL}/meet/transcript"
    try:
        r = requests.get(
            url,
            params={"calendar_id": calendar_id},
            headers=_auth_header(token),
            timeout=120,
        )
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:2000]
            return {
                "status": "error",
                "message": "transcript request failed",
                "http_status": r.status_code,
                "detail": detail,
            }
        data = r.json()
        transcript = data.get("transcript")
        utterances = build_utterances_from_transcript_json(transcript)
        spoken = spoken_text_from_utterances(utterances, 120_000)
        return {
            "status": "success",
            "source": "api",
            "meet_summary_id": None,
            "calendar_id": data.get("calendar_id"),
            "meeting_url": None,
            "bot_id": data.get("bot_id"),
            "recording_id": None,
            "transcript_id": None,
            "transcript_event": data.get("transcript_event"),
            "transcript_code": data.get("transcript_code"),
            "transcript_fetch_error": data.get("transcript_fetch_error"),
            "transcript_summary": None,
            "utterance_count": len(utterances),
            "spoken_transcript": spoken,
        }
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}
