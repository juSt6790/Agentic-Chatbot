import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow  # Import InstalledAppFlow
from datetime import datetime, timedelta
import calendar
import uuid
import requests
import pytz
from clients.db_method import get_user_tool_access_token

# Default settings
DEFAULT_CALENDAR_ID = "primary"  # Google Calendar API uses "primary" for user's primary calendar
DEFAULT_MEETING_TIMEZONE = "Asia/Kolkata"



# BASE_URL = "http://3.6.95.164:5000/users"

# # Example: Call get_tool_token endpoint
# def get_tool_token(unified_token):
#     url = f"{BASE_URL}/get_tool_token"
#     payload = {
#         "unified_token": unified_token,
#         "tool_name": "Gsuite"
#     }

#     response = requests.post(url, json=payload)
#     print(response.json())
#     if response.status_code == 200:
#         # print("Access Token:", response.json())
         
#         return response.json()
#     else:
#         print("Error:", response.status_code, response.text)



def get_calendar_service(unified_token):
    tool_name="Gsuite"
    # Step 1: Get access token details
    # print("token2:", unified_token)
    # result = get_tool_token(unified_token)
    result, status = get_user_tool_access_token(unified_token, tool_name)
    
    # Check if credentials exist before accessing
    if status != 200 or not isinstance(result, dict) or "access_token" not in result:
        error_msg = result.get("error", "Failed to retrieve Calendar credentials") if isinstance(result, dict) else "Failed to retrieve Calendar credentials"
        raise Exception(f"Failed to retrieve Calendar credentials. Please connect Google Calendar. {error_msg}")

    access_data = result["access_token"]

    # Note: Don't specify scopes - use whatever was originally granted
    # to avoid "invalid_scope" errors during token refresh
    creds = Credentials(
        token=access_data.get("token"),
        refresh_token=access_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=access_data.get("client_id"),
        client_secret=access_data.get("client_secret"),
    )

    # Step 2: Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        # Step 3: Update MongoDB with new token
        # update_user_tool_access_token(unified_token, tool_name, {
        #     "token": creds.token,
        #     "refresh_token": creds.refresh_token,
        #     "client_id": creds.client_id,
        #     "client_secret": creds.client_secret,
        #     "expiry": creds.expiry.isoformat() if creds.expiry else None
        # })

    # Step 4: Build and return service
    return build("calendar", "v3", credentials=creds)





# def create_event( summary, start_time, end_time, description=None, attendees=None, token: str = None):
#     service=get_calendar_service(token)
#     """
#     Creates a new Google Calendar event with a Google Meet link.
#     """
#     event = {
#         "summary": summary,
#         "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
#         "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
#         "description": description if description else "",
#         "attendees": [{"email": email} for email in attendees] if attendees else [],
#         "conferenceData": {
#             "createRequest": {
#                 "requestId": "meet-" + str(uuid.uuid4()),  # unique ID for the request
#                 "conferenceSolutionKey": {"type": "hangoutsMeet"}
#             }
#         }
#     }

#     event_rstlt= service.events().insert(
#         calendarId=settings_config_calender.user_id,
#         body=event,
#         conferenceDataVersion=1
#     ).execute()
#     return {
#         "status": "success",
#         "message": "Event created successfully.",
#         "event": {
#             "id": event_rstlt.get("event_id"),
#             "summary": event_rstlt.get("summary"),
#             "start": event_rstlt.get("start"),
#             "end": event_rstlt.get("end"),
#             "attendees": event_rstlt.get("attendees"),
#             "htmlLink": event_rstlt.get("htmlLink")
#         }
#     }





def create_event(
    summary,
    start_time,
    end_time,
    description=None,
    attendees=None,
    token: str = None,
    enable_transcript: bool = False,
    transcript_mode: str = "prioritize_accuracy",
):
    service = get_calendar_service(token)

    def _normalize_for_meeting_and_bot(dt_raw: str, tz_name: str = DEFAULT_MEETING_TIMEZONE) -> tuple[str, str]:
        """
        Returns:
        - calendar_date_time: ISO string without timezone offset (used with explicit timeZone field)
        - bot_join_at_iso: timezone-aware ISO string with offset for backend /meet/schedule-bot
        """
        s = str(dt_raw or "").strip()
        if not s:
            return "", ""
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            # Keep legacy behavior when parsing fails
            return s, s
        tz = pytz.timezone(tz_name)
        if dt.tzinfo is None:
            dt_local = tz.localize(dt)
        else:
            dt_local = dt.astimezone(tz)
        calendar_date_time = dt_local.replace(tzinfo=None).isoformat()
        bot_join_at_iso = dt_local.isoformat()
        return calendar_date_time, bot_join_at_iso

    start_calendar_dt, start_join_at_iso = _normalize_for_meeting_and_bot(start_time)
    end_calendar_dt, _ = _normalize_for_meeting_and_bot(end_time)

    # Normalize attendees: handle both comma-separated string and list
    attendees_list = []
    if attendees:
        if isinstance(attendees, str):
            # Split comma-separated string and clean up whitespace
            attendees_list = [email.strip() for email in attendees.split(",") if email.strip()]
        elif isinstance(attendees, list):
            # Already a list, but ensure all items are strings and clean them
            attendees_list = [str(email).strip() for email in attendees if str(email).strip()]
    
    # Validate email format (basic check)
    import re
    email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    valid_attendees = []
    for email in attendees_list:
        if email_pattern.match(email):
            valid_attendees.append(email)
        else:
            print(f"Warning: Invalid email format skipped: {email}")

    event = {
        "summary": summary,
        "start": {
            "dateTime": start_calendar_dt or start_time,
            "timeZone": DEFAULT_MEETING_TIMEZONE
        },
        "end": {
            "dateTime": end_calendar_dt or end_time,
            "timeZone": DEFAULT_MEETING_TIMEZONE
        },
        "description": description if description else "",
        "attendees": [{"email": email} for email in valid_attendees],
        "conferenceData": {
            "createRequest": {
                "requestId": "meet-" + str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }
        }
    }

    try:
        event_result = service.events().insert(
            calendarId=DEFAULT_CALENDAR_ID,
            body=event,
            conferenceDataVersion=1
        ).execute()

        out = {
            "status": "success",
            "message": "Event created successfully.",
            "event": {
                "id": event_result.get("id"),
                "summary": event_result.get("summary"),
                "start": event_result.get("start"),
                "end": event_result.get("end"),
                "attendees": event_result.get("attendees"),
                "hangoutLink": event_result.get("hangoutLink"),
                "htmlLink": event_result.get("htmlLink")
            }
        }

        if enable_transcript:
            from services.transcript_mcp import schedule_transcript_after_event_created

            out["transcript_bot"] = schedule_transcript_after_event_created(
                calendar_id=str(event_result.get("id") or ""),
                hangout_link=event_result.get("hangoutLink"),
                join_at_iso=start_join_at_iso or start_time,
                attendees=valid_attendees,
                token=token,
                transcript_mode=transcript_mode,
            )

        return out
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to create event: {str(e)}"
        }


def update_event(event_id: str,
                 summary: str = None,
                 start_time: str = None,
                 end_time: str = None,
                 description: str = None,
                 attendees: list[str] | None = None,
                 location: str | None = None,
                 token: str = None) -> dict:
    """
    Update an existing Google Calendar event. Any provided field will be updated;
    omitted fields will remain unchanged. Times should be RFC3339 strings. If
    you're supplying naive ISO strings, ensure the server-side wrapper converts
    them appropriately.

    Args:
        event_id: ID of the event to update
        summary: New title
        start_time: RFC3339 dateTime string
        end_time: RFC3339 dateTime string
        description: Event description
        attendees: List of attendee emails
        location: Location string
        token: Unified auth token

    Returns:
        dict with status and the updated event fields
    """
    import re
    service = get_calendar_service(token)

    body: dict = {}
    if summary is not None:
        body["summary"] = summary
    if description is not None:
        body["description"] = description
    if location is not None:
        body["location"] = location
    if start_time is not None:
        body.setdefault("start", {})
        # Normalize datetime: if timezone offset is present, remove it and use timeZone field
        # If no timezone offset, use the datetime as-is with timeZone field
        # Check if datetime has timezone offset (e.g., +05:30, -05:00, Z)
        if re.search(r'[+-]\d{2}:\d{2}$|Z$', start_time):
            # Remove timezone offset from datetime string
            start_time_clean = re.sub(r'[+-]\d{2}:\d{2}$|Z$', '', start_time)
            body["start"]["dateTime"] = start_time_clean
            body["start"]["timeZone"] = "Asia/Kolkata"
        else:
            # No timezone offset, use as-is with timeZone
            body["start"]["dateTime"] = start_time
            body["start"]["timeZone"] = "Asia/Kolkata"
    if end_time is not None:
        body.setdefault("end", {})
        # Normalize datetime: if timezone offset is present, remove it and use timeZone field
        # Check if datetime has timezone offset (e.g., +05:30, -05:00, Z)
        if re.search(r'[+-]\d{2}:\d{2}$|Z$', end_time):
            # Remove timezone offset from datetime string
            end_time_clean = re.sub(r'[+-]\d{2}:\d{2}$|Z$', '', end_time)
            body["end"]["dateTime"] = end_time_clean
            body["end"]["timeZone"] = "Asia/Kolkata"
        else:
            # No timezone offset, use as-is with timeZone
            body["end"]["dateTime"] = end_time
            body["end"]["timeZone"] = "Asia/Kolkata"
    if attendees is not None:
        # Normalize attendees: handle both comma-separated string and list
        attendees_list = []
        if isinstance(attendees, str):
            # Split comma-separated string and clean up whitespace
            attendees_list = [email.strip() for email in attendees.split(",") if email.strip()]
        elif isinstance(attendees, list):
            # Already a list, but ensure all items are strings and clean them
            attendees_list = [str(email).strip() for email in attendees if str(email).strip()]
        
        # Validate email format (basic check)
        import re
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        valid_attendees = []
        for email in attendees_list:
            if email_pattern.match(email):
                valid_attendees.append(email)
            else:
                print(f"Warning: Invalid email format skipped: {email}")
        
        body["attendees"] = [{"email": email} for email in valid_attendees]

    if not body:
        return {"status": "error", "message": "No fields provided to update."}

    try:
        updated = service.events().patch(
            calendarId=DEFAULT_CALENDAR_ID,
            eventId=event_id,
            body=body,
            conferenceDataVersion=1,
        ).execute()

        return {
            "status": "success",
            "message": "Event updated successfully.",
            "event": {
                "id": updated.get("id"),
                "summary": updated.get("summary"),
                "start": updated.get("start"),
                "end": updated.get("end"),
                "attendees": updated.get("attendees"),
                "hangoutLink": updated.get("hangoutLink"),
                "htmlLink": updated.get("htmlLink"),
                "location": updated.get("location"),
                "description": updated.get("description"),
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to update event: {str(e)}",
        }

# def list_events( max_results=100, token: str = None):
#     service=get_calendar_service(token)
#     print("token2:", token)
#     """
#     Lists upcoming events from the user's Google Calendar.
#     """
#     return service.events().list(calendarId=settings_config_calender.user_id, maxResults=max_results, singleEvents=True,
#                                  orderBy="startTime").execute().get("items", [])


def list_events(max_results=100, token: str = None):
    try:
       
        service = get_calendar_service(token)
       

        events_result = service.events().list(
            calendarId=DEFAULT_CALENDAR_ID,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        # return events_result.get("items", [])
        return {
        "status": "success",
        "message": "Event fetched successfully.",
        "events": events_result.get("items", [])
    }
    

    except Exception as e:
        print(f"Error fetching calendar events: {e}")
        return {
        "status": "success",
        "message": "Event fetched successfully.",
        "events": []
    }




def delete_event( event_id, token: str = None):
    service=get_calendar_service(token)
    """
    Deletes a specific event from the user's Google Calendar using the event ID.
    """
    service.events().delete(calendarId=DEFAULT_CALENDAR_ID, eventId=event_id).execute()

# def get_event(service, event_id, token: str = None):
#     service=get_calendar_service(token)
#     """
#     Retrieves the details of a specific event from the user's Google Calendar.
#     """
#     return service.events().get(calendarId=settings_config_calender.user_id, eventId=event_id).execute()

def get_event(event_id: str,token: str) -> str:
    # print("token",token)
    # event =get_event(service, event_id)
    # return f"{event['summary']} from {event['start']['dateTime']} to {event['end']['dateTime']}"
    service_calender=get_calendar_service(token)
    try:
        event =service_calender.events().get(calendarId=DEFAULT_CALENDAR_ID, eventId=event_id).execute()
        # event = service.events().get(calendarId=settings.user_id, eventId=event_id).execute()
        return {
            "status": "success",
            "message": f"Event Created successfully.",
            "event": {
                "id": event.get("id"),
                "summary": event.get("summary"),
                "description": event.get("description"),
                "start": event.get("start", {}).get("dateTime", event.get("start", {}).get("date")),
                "end": event.get("end", {}).get("dateTime", event.get("end", {}).get("date")),
                "location": event.get("location"),
                "attendees": [att.get("email") for att in event.get("attendees", [])] if event.get("attendees") else [],
                "htmlLink": event.get("htmlLink")
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to retrieve event: {str(e)}"
        }


# def search_events(service, email=None, date=None, max_results=100):
#     """
#     Searches events by attendee email or date.
#     """
#     all_events = list_events(service, max_results=max_results)

#     filtered_events = []
#     for event in all_events:
#         # Check email match
#         if email:
#             attendees = event.get("attendees", [])
#             if not any(attendee.get("email") == email for attendee in attendees):
#                 continue

#         # Check date match
#         if date:
#             event_start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
#             if event_start:
#                 try:
#                     event_date = datetime.fromisoformat(event_start[:10])  # just date part
#                     target_date = datetime.fromisoformat(date)
#                     if event_date.date() != target_date.date():
#                         continue
#                 except Exception:
#                     continue

#         filtered_events.append(event)

#     return filtered_events


# from datetime import datetime

# def fetch_all_events( token: str = None):
#     service=get_calendar_service(token)
#     """
#     Fetches all events from the user's Google Calendar using pagination.
#     """
#     events = []
#     page_token = None

#     while True:
#         response = service.events().list(
#             calendarId=DEFAULT_CALENDAR_ID,
#             singleEvents=True,
#             orderBy="startTime",
#             pageToken=page_token
#         ).execute()

#         events.extend(response.get("items", []))
#         page_token = response.get("nextPageToken")

#         if not page_token:
#             break

#     return events
    # return {
    #         "status": "success",
    #         "message": "Event fetched successfully.",
    #         "events": events
    #     }


def fetch_all_events(token: str = None):
    service = get_calendar_service(token)
    events = []
    page_token = None
    print("testing token:", token)
    while True:
        response = service.events().list(
            calendarId=DEFAULT_CALENDAR_ID,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token
        ).execute()

        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return events



# def search_events( email=None, date=None, token: str = None):
#     service=get_calendar_service(token)
#     """
#     Searches all calendar events by attendee email and/or event start date (YYYY-MM-DD).
#     """
#     all_events = fetch_all_events(service)
#     filtered_events = []
#     # seen_ids = set()
#     start_range = None
#     end_range = None

#     # for event in all_events:
#     #     # Check email
#     #     if email:
#     #         attendees = event.get("attendees", [])
#     #         if not any(attendee.get("email") == email for attendee in attendees):
#     #             continue

#     # Check date
#     if date:
#         try:
#             if len(date) == 7:  # 'YYYY-MM' -> month filtering
#                 year, month = map(int, date.split('-'))
#                 start_range = datetime(year, month, 1)
#                 last_day = calendar.monthrange(year, month)[1]
#                 end_range = datetime(year, month, last_day)
#             elif len(date) == 10:  # 'YYYY-MM-DD' -> exact date
#                 single_date = datetime.strptime(date, "%Y-%m-%d")
#                 start_range = end_range = single_date
#         except Exception as e:
#             print("Invalid date format:", e)
#             return []
            
#         for event in all_events:
#         # Filter by email
#             if email:
#                 attendees = event.get("attendees", [])
#                 if not any(attendee.get("email") == email for attendee in attendees):
#                     continue
#             # Filter by date or month
#             if start_range and end_range:
#                 event_start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
#                 if event_start:
#                     try:
#                         event_date = datetime.fromisoformat(event_start[:10])
#                         if not (start_range.date() <= event_date.date() <= end_range.date()):
#                             continue
#                     except:
#                         continue

#         filtered_events.append(event)

#     # return filtered_events
#     return {
#             "status": "success",
#             "message": "Event fetched successfully.",
#             "events": filtered_events
#         }


def search_events(email=None, date=None, after_date=None, before_date=None, q=None, token: str = None):
    """
    Search for calendar events with support for:
    - after_date: ISO date string (YYYY-MM-DD) for timeMin
    - before_date: ISO date string (YYYY-MM-DD) for timeMax
    - q: keyword search
    - email: attendee email filter (done in Python)
    - date: legacy single date or month (YYYY-MM-DD or YYYY-MM)
    """
    service = get_calendar_service(token)
    events = []
    page_token = None
    params = {
        "calendarId": DEFAULT_CALENDAR_ID,
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": 2500  # fetch as many as possible for filtering
    }
    # Handle new date range params
    if after_date:
        try:
            params["timeMin"] = datetime.strptime(after_date, "%Y-%m-%d").isoformat() + "Z"
        except Exception:
            pass
    if before_date:
        try:
            params["timeMax"] = datetime.strptime(before_date, "%Y-%m-%d").isoformat() + "Z"
        except Exception:
            pass
    if q:
        params["q"] = q
    # Legacy date param (single date or month)
    if date and not (after_date or before_date):
        try:
            if len(date) == 7:  # YYYY-MM
                year, month = map(int, date.split('-'))
                params["timeMin"] = datetime(year, month, 1).isoformat() + "Z"
                last_day = calendar.monthrange(year, month)[1]
                params["timeMax"] = datetime(year, month, last_day, 23, 59, 59).isoformat() + "Z"
            elif len(date) == 10:  # YYYY-MM-DD
                day = datetime.strptime(date, "%Y-%m-%d")
                params["timeMin"] = day.isoformat() + "Z"
                params["timeMax"] = (day + timedelta(days=1)).isoformat() + "Z"
        except Exception:
            pass
    # Fetch events with pagination
    while True:
        if page_token:
            params["pageToken"] = page_token
        response = service.events().list(**params).execute()
        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    # Filter by attendee email if provided
    filtered_events = []
    for event in events:
        if email:
            attendees = event.get("attendees", [])
            if not any(attendee.get("email") == email for attendee in attendees):
                continue
        filtered_events.append({
            "id": event.get("id"),
            "summary": event.get("summary"),
            "start": event.get("start"),
            "end": event.get("end"),
            "attendees": event.get("attendees", []),
            "hangoutLink": event.get("hangoutLink"),
            "organizer": event.get("organizer", {}),
            "location": event.get("location"),
            "description": event.get("description"),
        })
    return {
        "status": "success",
        "message": "Events fetched successfully.",
        "events": filtered_events
    }



# def delete_events_by_filter( email=None, date=None, token: str = None):
#     """
#     Deletes events from the calendar that match the given attendee email or start date.
    
#     """
#     service=get_calendar_service(token)
#     events_to_delete = search_events(service, email=email, date=date)
#     deleted_ids = []

#     for event in events_to_delete:
#         try:
#             service.events().delete(calendarId=settings_config_calender.user_id, eventId=event["id"]).execute()
#             deleted_ids.append(event["id"])
#         except Exception as e:
#             print(f"Failed to delete event {event['id']}: {e}")

#     return {
#         "deleted_count": len(deleted_ids),
#         "deleted_event_ids": deleted_ids
#     }

def delete_events_by_filter(email=None, date=None, token: str = None):
    """
    Deletes events from the calendar that match the given attendee email or start date.
    """
    # from .calendar_tools import search_events  # adjust import path as needed
    service = get_calendar_service(token)

    # Only get the filtered event list (safe fields)
    search_result = search_events(email=email, date=date, token=token)
    events_to_delete = search_result.get("events", [])

    deleted_ids = []

    for event in events_to_delete:
        try:
            service.events().delete(
                calendarId=DEFAULT_CALENDAR_ID,
                eventId=event["id"]
            ).execute()
            deleted_ids.append(event["id"])
        except Exception as e:
            print(f"Failed to delete event {event['id']}: {e}")

    return {
        "status": "success",
        "message": f"{len(deleted_ids)} event(s) deleted.",
        "deleted_count": len(deleted_ids),
        "deleted_event_ids": deleted_ids
    }
