"""
Meeting transcript: schedule notetaker bot (workspace API) and read stored transcripts (Mongo / API).
"""

from __future__ import annotations

from typing import Any, Optional

from clients.transcript_client import (
    get_transcript_from_api,
    mongo_fetch_meeting_transcript,
    post_schedule_meeting_bot,
)


def schedule_meeting_transcript(
    calendar_id: str,
    meeting_url: str,
    token: str,
    join_at: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    transcript_mode: str = "prioritize_accuracy",
    bot_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Ask the workspace backend to join the Meet and store a transcript linked to calendar_id.
    """
    return post_schedule_meeting_bot(
        calendar_id=calendar_id,
        meeting_url=meeting_url,
        token=token,
        join_at=join_at,
        attendees=attendees,
        transcript_mode=transcript_mode,
        bot_name=bot_name,
    )


def get_meeting_transcript(
    token: str,
    calendar_id: Optional[str] = None,
    meeting_url: Optional[str] = None,
    max_transcript_chars: int = 120_000,
    prefer_api: bool = False,
) -> dict[str, Any]:
    """
    Return spoken_transcript for summarization. Resolves by Google event id or Meet URL.
    Default: read from the user's Mongo meet_summaries. If prefer_api=True, tries HTTP first.
    """
    if not (calendar_id or "").strip() and not (meeting_url or "").strip():
        return {
            "status": "error",
            "message": "Provide calendar_id (event id from calendar search) and/or meeting_url.",
        }

    if prefer_api and calendar_id:
        api_res = get_transcript_from_api(calendar_id=str(calendar_id), token=token)
        if api_res.get("status") == "success":
            spoken = (api_res.get("spoken_transcript") or "").strip()
            if spoken:
                return api_res

    return mongo_fetch_meeting_transcript(
        token=token,
        calendar_id=calendar_id,
        meeting_url=meeting_url,
        max_transcript_chars=max_transcript_chars,
    )


def schedule_transcript_after_event_created(
    *,
    calendar_id: str,
    hangout_link: Optional[str],
    join_at_iso: str,
    attendees: list[str],
    token: str,
    transcript_mode: str = "prioritize_accuracy",
) -> dict[str, Any]:
    """Called from calendar create_event when the user opted in to transcription."""
    if not hangout_link:
        return {
            "status": "skipped",
            "message": "No Google Meet link on the event; cannot schedule a meeting notetaker.",
        }
    return schedule_meeting_transcript(
        calendar_id=calendar_id,
        meeting_url=hangout_link,
        token=token,
        join_at=join_at_iso,
        attendees=attendees or None,
        transcript_mode=transcript_mode,
    )
