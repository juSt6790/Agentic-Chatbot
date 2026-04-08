#!/usr/bin/env python3
"""
Extract Recall transcript words/utterances from Mongo.

This supports documents shaped like:
- transcript_json: already decoded JSON (optional)
- transcript_json_zlib: {$binary: {base64: "..."} } (optional)
- transcript_meta.data.download_url: signed S3 URL (optional)

Usage examples:
  1) By transcript_id:
     python scripts/recall_transcript_extract_words.py \
       --mongo-db unified_workspace \
       --mongo-collection recall_transcripts \
       --transcript-id c0789983-a82c-41a0-96bd-3a176f7b7d9e

  2) By meeting_url:
     python scripts/recall_transcript_extract_words.py \
       --mongo-db unified_workspace \
       --mongo-collection recall_transcripts \
       --meeting-url "https://meet.google.com/gzw-cevm-cnh"

Outputs:
  - Writes a JSON file with:
    { "transcript_json": <raw or null>, "words_by_participant": [...], "utterances": [...] }

Notes:
  - Google Drive is NOT needed for extraction; we use the stored zlib payload or the S3 download_url.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import zlib
import gzip
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from db.mongo_client import get_mongo_client  # noqa: E402


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _decode_mongo_binary_zlib(mongo_binary: Any) -> Any:
    """
    Decode Mongo's {$binary:{base64:"..."} } where the base64 payload is zlib-compressed JSON.
    Returns decoded JSON (dict/list) if possible; else returns decoded string.
    """
    if not mongo_binary:
        raise ValueError("Empty transcript_json_zlib payload")

    base64_str: Optional[str] = None
    if isinstance(mongo_binary, dict):
        # Typical shape: {"$binary": {"base64": "..."}}
        if "$binary" in mongo_binary:
            b = mongo_binary.get("$binary") or {}
            base64_str = b.get("base64")
        else:
            base64_str = mongo_binary.get("base64")
    elif isinstance(mongo_binary, str):
        base64_str = mongo_binary

    if not base64_str:
        raise ValueError("Could not find base64 in transcript_json_zlib payload")

    compressed = base64.b64decode(base64_str)
    try:
        decompressed = zlib.decompress(compressed)
    except Exception:
        # Some payloads may be gzip-compressed instead of zlib.
        decompressed = gzip.decompress(compressed)

    text = decompressed.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        return text


def _normalize_meeting_url(url: str) -> str:
    url = (url or "").strip()
    return url.split("?")[0].rstrip("/")


def _word_token_ends_sentence(word_text: str) -> bool:
    t = (word_text or "").strip()
    if not t:
        return False
    if t in [".", "!", "?"]:
        return True
    return bool(re.search(r"[.!?]+$", t))


def _join_words(tokens: List[str]) -> str:
    if not tokens:
        return ""
    text = " ".join(tokens).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"\s+\"", '"', text)
    text = re.sub(r'"\s+', '"', text)
    return text


def _build_utterances(transcript_json: Any) -> List[Dict[str, Any]]:
    """
    Convert Recall word-level transcript JSON to sentence-like utterances.
    """
    if not isinstance(transcript_json, list):
        return []

    utterances: List[Dict[str, Any]] = []

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

        cur_tokens: List[str] = []
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

        # flush remainder
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

    def _sort_key(u: Dict[str, Any]) -> str:
        return str(u.get("start_at") or "")

    utterances.sort(key=_sort_key)
    return utterances


def _extract_words_by_participant(transcript_json: Any) -> List[Dict[str, Any]]:
    """
    Keep word tokens grouped by participant segment order as provided by Recall.
    """
    if not isinstance(transcript_json, list):
        return []

    out: List[Dict[str, Any]] = []
    for seg in transcript_json:
        if not isinstance(seg, dict):
            continue
        participant = seg.get("participant") or {}
        words = seg.get("words") or []
        out.append(
            {
                "participant": participant if isinstance(participant, dict) else {},
                "words": words if isinstance(words, list) else [],
            }
        )
    return out


def _fetch_json_from_download_url(download_url: str) -> Any:
    r = requests.get(download_url, timeout=120)
    r.raise_for_status()
    return r.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--unified-token",
        default=None,
        help="Unified auth token. Used to resolve user_id by reading unified_workspace.user_authenticate_token.",
    )
    parser.add_argument("--user-id", default=None, help="Direct user_id (db name). Optional if --unified-token is used.")
    parser.add_argument("--mongo-collection", default="meet_summaries", help="Collection name inside the user db (default: meet_summaries).")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--transcript-id", help="Recall transcript id (UUID)")
    group.add_argument("--meeting-url", help="Google Meet URL")
    group.add_argument("--doc-id", help="Mongo _id (ObjectId or string)")

    parser.add_argument("--out", default=None, help="Output json path (default: stdout only)")
    parser.add_argument(
        "--include-transcript-json",
        action="store_true",
        help="If set, include transcript_json in output (can be large).",
    )
    parser.add_argument(
        "--build-utterances",
        action="store_true",
        help="If set, also compute sentence-like utterances.",
    )

    args = parser.parse_args()

    client = get_mongo_client()

    resolved_user_id: Optional[str] = None
    if args.user_id:
        resolved_user_id = str(args.user_id)
    elif args.unified_token:
        unified_db = client["unified_workspace"]
        auth_token_collection = unified_db["user_authenticate_token"]
        auth_entry = auth_token_collection.find_one(
            {"tool_token": args.unified_token, "tool_name": "unified"}
        )
        # Same convention as the rest of the repo:
        # if token entry not present, treat token itself as user_id.
        resolved_user_id = str(auth_entry["user_id"]) if auth_entry else str(args.unified_token)
    else:
        raise SystemExit("Provide either --unified-token or --user-id.")

    coll = client[resolved_user_id][args.mongo_collection]

    query: Dict[str, Any] = {}
    if args.transcript_id:
        query = {"transcript_id": args.transcript_id}
    elif args.meeting_url:
        query = {"meeting_url": _normalize_meeting_url(args.meeting_url)}
    elif args.doc_id:
        query = {"_id": args.doc_id}

    doc = coll.find_one(query)
    if not doc:
        raise SystemExit(f"[{_utc_now_iso()}] No document found for query: {query}")

    # Support multiple possible shapes depending on where the transcript came from.
    transcript_json = doc.get("transcript_json")
    transcript_json_zlib = doc.get("transcript_json_zlib")
    transcript_raw = doc.get("transcript_raw")  # our meet-summary service may store this directly
    transcript_utterances = doc.get("transcript_utterances")

    if transcript_json is None and transcript_raw is not None:
        # If it's the truncated wrapper, use its segments.
        if isinstance(transcript_raw, dict) and transcript_raw.get("segments") is not None:
            transcript_json = transcript_raw.get("segments")
        else:
            transcript_json = transcript_raw

    if transcript_json is None and transcript_json_zlib is not None:
        print(f"[{_utc_now_iso()}] Decoding transcript_json_zlib from Mongo ...", file=sys.stderr)
        transcript_json = _decode_mongo_binary_zlib(transcript_json_zlib)

    if transcript_json is None:
        download_url = (
            ((doc.get("transcript_meta") or {}).get("data") or {}).get("download_url")
            or ((doc.get("transcript_meta") or {}).get("data") or {}).get("downloadUrl")
        )
        if not download_url:
            raise SystemExit("Could not find transcript_json nor transcript_meta.data.download_url")
        print(f"[{_utc_now_iso()}] Fetching transcript JSON from download_url ...", file=sys.stderr)
        transcript_json = _fetch_json_from_download_url(download_url)

    words_by_participant = _extract_words_by_participant(transcript_json)
    utterances: List[Dict[str, Any]] = []
    if transcript_utterances and isinstance(transcript_utterances, list):
        # Prefer precomputed utterances if they exist.
        utterances = transcript_utterances
    elif args.build_utterances:
        utterances = _build_utterances(transcript_json)

    output: Dict[str, Any] = {
        "source": {
            "transcript_id": doc.get("transcript_id"),
            "meeting_url": doc.get("meeting_url"),
            "bot_id": doc.get("bot_id"),
            "recording_id": doc.get("recording_id"),
        },
        "words_by_participant": words_by_participant,
        "utterances": utterances,
    }

    if args.include_transcript_json:
        output["transcript_json"] = transcript_json
    else:
        output["transcript_json"] = None

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"[{_utc_now_iso()}] Wrote: {args.out}", file=sys.stderr)
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

